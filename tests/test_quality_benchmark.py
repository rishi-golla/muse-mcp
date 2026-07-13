from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from muse.quality_benchmark import (
    DEFAULT_BENCHMARK_CORPUS,
    ArtifactGenerator,
    BenchmarkArtifact,
    BenchmarkCorpus,
    BenchmarkReport,
    BenchmarkTask,
    JudgeArtifact,
    JudgeAttempt,
    PairwiseJudgment,
    Preference,
    run_quality_benchmark,
)

RUN_TIMESTAMP = datetime(2026, 7, 12, 12, 0, tzinfo=UTC)


def test_benchmark_artifact_rejects_blank_content_and_negative_telemetry() -> None:
    with pytest.raises(ValidationError):
        BenchmarkArtifact(content="   ", cost_usd=0.0, latency_ms=0.0)

    with pytest.raises(ValidationError):
        BenchmarkArtifact(content="A concrete proposal.", cost_usd=-0.01, latency_ms=20.0)

    with pytest.raises(ValidationError):
        BenchmarkArtifact(content="A concrete proposal.", cost_usd=0.01, latency_ms=-1.0)


def test_judge_artifact_redacts_telemetry_and_system_identity() -> None:
    artifact = BenchmarkArtifact(
        content="A concrete proposal.",
        cost_usd=0.01,
        latency_ms=20.0,
    )

    judge_artifact = artifact.for_judge()

    assert isinstance(judge_artifact, JudgeArtifact)
    assert judge_artifact.model_dump() == {"content": "A concrete proposal."}
    assert not hasattr(judge_artifact, "cost_usd")
    assert not hasattr(judge_artifact, "latency_ms")
    assert not hasattr(judge_artifact, "system_identity")

    with pytest.raises(ValidationError):
        JudgeArtifact(content="A concrete proposal.", cost_usd=0.01)

    with pytest.raises(ValidationError):
        JudgeArtifact(content="A concrete proposal.", system_identity="system-x")


def _judgment(preference: Preference) -> PairwiseJudgment:
    return PairwiseJudgment(
        preference=preference,
        confidence=0.8,
        rationale="The selected candidate is more concrete for the task.",
        originality=preference,
        usefulness=preference,
        operational_specificity=preference,
        task_fit=preference,
    )


def _judge_attempt(
    preference: Preference, *, cost_usd: float = 0.0, latency_ms: float = 0.0
) -> JudgeAttempt:
    return JudgeAttempt(
        judgment=_judgment(preference),
        cost_usd=cost_usd,
        latency_ms=latency_ms,
    )


def _neutral_generators() -> tuple[ArtifactGenerator, ArtifactGenerator]:
    def first_generator(_task: BenchmarkTask) -> BenchmarkArtifact:
        return BenchmarkArtifact(content="alpha option", cost_usd=0.2, latency_ms=20.0)

    def second_generator(_task: BenchmarkTask) -> BenchmarkArtifact:
        return BenchmarkArtifact(content="beta option", cost_usd=0.1, latency_ms=10.0)

    return first_generator, second_generator


def _run_benchmark(
    corpus: object,
    first_generator: ArtifactGenerator,
    second_generator: ArtifactGenerator,
    judge: object,
    **kwargs: object,
) -> BenchmarkReport:
    return run_quality_benchmark(
        corpus,
        first_generator,
        second_generator,
        judge,
        run_timestamp=RUN_TIMESTAMP,
        prompt_version="prompt-v1",
        config_version="config-v1",
        **kwargs,
    )


def test_pairwise_judgment_rejects_unknown_preferences() -> None:
    with pytest.raises(ValidationError):
        PairwiseJudgment(
            preference="candidate-c",
            confidence=0.8,
            rationale="The selected candidate is more concrete for the task.",
            originality=Preference.A,
            usefulness=Preference.A,
            operational_specificity=Preference.B,
            task_fit=Preference.A,
        )


def test_pairwise_judge_attempt_requires_judgment_or_sanitized_failure() -> None:
    successful = _judge_attempt(Preference.A, cost_usd=0.04, latency_ms=4.0)
    assert successful.judgment is not None
    assert successful.failure is None

    with pytest.raises(ValidationError):
        JudgeAttempt(cost_usd=0.0, latency_ms=0.0)

    with pytest.raises(ValidationError):
        JudgeAttempt(
            judgment=_judgment(Preference.A),
            failure={"error_type": "RuntimeError", "message": "failure"},
            cost_usd=0.0,
            latency_ms=0.0,
        )


def test_benchmark_corpus_rejects_duplicate_task_names() -> None:
    task = BenchmarkTask(name="same", domain="coding", prompt="Improve a workflow.")
    with pytest.raises(ValidationError):
        BenchmarkCorpus(tasks=(task, task))


def test_default_benchmark_corpus_is_domain_varied_and_blind() -> None:
    corpus = DEFAULT_BENCHMARK_CORPUS

    assert len(corpus.tasks) >= 30
    assert {task.domain for task in corpus.tasks} >= {
        "coding",
        "product",
        "design",
        "operations",
        "research",
    }
    assert corpus.version

    forbidden_keywords = ("expected", "correct", "ideal", "answer")
    for task in corpus.tasks:
        prompt = task.prompt.lower()
        assert not any(keyword in prompt for keyword in forbidden_keywords)


def test_default_label_checks_allow_ordinary_baseline_and_judge_prose() -> None:
    corpus = BenchmarkCorpus(
        tasks=(BenchmarkTask(name="one", domain="research", prompt="Investigate a signal."),)
    )

    def first_generator(_task: BenchmarkTask) -> BenchmarkArtifact:
        return BenchmarkArtifact(
            content="The judge should compare a baseline proposal.", cost_usd=0.2, latency_ms=20.0
        )

    def second_generator(_task: BenchmarkTask) -> BenchmarkArtifact:
        return BenchmarkArtifact(content="A neutral proposal.", cost_usd=0.1, latency_ms=10.0)

    def judge(
        _task: BenchmarkTask, _candidate_a: JudgeArtifact, _candidate_b: JudgeArtifact
    ) -> JudgeAttempt:
        return _judge_attempt(Preference.TIE)

    report = _run_benchmark(corpus, first_generator, second_generator, judge)

    assert report.judged_comparisons == 1
    assert report.records[0].muse.failure is None


def test_label_checks_use_boundaries_and_only_explicit_labels() -> None:
    corpus = BenchmarkCorpus(
        tasks=(BenchmarkTask(name="one", domain="research", prompt="Investigate a signal."),)
    )
    judge_calls = 0

    def first_generator(_task: BenchmarkTask) -> BenchmarkArtifact:
        return BenchmarkArtifact(content="baseline prose", cost_usd=0.2, latency_ms=20.0)

    def second_generator(_task: BenchmarkTask) -> BenchmarkArtifact:
        return BenchmarkArtifact(content="system-alpha result", cost_usd=0.1, latency_ms=10.0)

    def judge(
        _task: BenchmarkTask, _candidate_a: JudgeArtifact, _candidate_b: JudgeArtifact
    ) -> JudgeAttempt:
        nonlocal judge_calls
        judge_calls += 1
        return _judge_attempt(Preference.TIE)

    ordinary = _run_benchmark(
        corpus,
        first_generator,
        second_generator,
        judge,
        blind_labels=("base",),
    )
    explicit = _run_benchmark(
        corpus,
        first_generator,
        second_generator,
        judge,
        blind_labels=("baseline",),
        system_identifiers=("system-alpha",),
    )

    assert ordinary.judged_comparisons == 1
    assert explicit.judged_comparisons == 0
    assert explicit.records[0].baseline.failure is not None
    assert explicit.records[0].baseline.failure.leaked_labels == ("system-alpha",)
    assert judge_calls == 1


def test_runner_assignment_is_independent_of_earlier_failed_cells() -> None:
    later = BenchmarkTask(name="later", domain="coding", prompt="Improve a workflow.")
    earlier = BenchmarkTask(name="earlier", domain="coding", prompt="Improve a workflow.")
    first_generator, second_generator = _neutral_generators()

    def failing_first_generator(task: BenchmarkTask) -> BenchmarkArtifact:
        if task.name == "earlier":
            raise RuntimeError("first cell unavailable")
        return first_generator(task)

    def judge(
        _task: BenchmarkTask, _candidate_a: JudgeArtifact, _candidate_b: JudgeArtifact
    ) -> JudgeAttempt:
        return _judge_attempt(Preference.TIE)

    full = _run_benchmark(
        BenchmarkCorpus(tasks=(earlier, later)),
        failing_first_generator,
        second_generator,
        judge,
        repetitions=2,
        random_seed=17,
    )
    isolated = _run_benchmark(
        BenchmarkCorpus(tasks=(later,)),
        first_generator,
        second_generator,
        judge,
        repetitions=2,
        random_seed=17,
    )

    full_later = [record for record in full.records if record.task.name == "later"]
    assert [record.muse_label for record in full_later] == [
        record.muse_label for record in isolated.records
    ]


def test_runner_aggregates_repetitions_per_task_before_wilson() -> None:
    corpus = BenchmarkCorpus(
        tasks=(BenchmarkTask(name="one", domain="research", prompt="Investigate a signal."),)
    )
    first_generator, second_generator = _neutral_generators()
    preferred_contents = iter(("alpha option", "alpha option", "beta option"))

    def judge(
        _task: BenchmarkTask, candidate_a: JudgeArtifact, _candidate_b: JudgeArtifact
    ) -> JudgeAttempt:
        preferred = next(preferred_contents)
        preference = Preference.A if candidate_a.content == preferred else Preference.B
        return _judge_attempt(preference, cost_usd=0.05, latency_ms=5.0)

    report = _run_benchmark(
        corpus,
        first_generator,
        second_generator,
        judge,
        repetitions=3,
        random_seed=29,
    )

    assert report.judged_comparisons == 3
    assert report.repetition_wins == 2
    assert report.repetition_losses == 1
    assert report.wins == 1
    assert report.losses == report.ties == 0
    assert report.decisive_comparisons == 1
    assert report.preference_rate == pytest.approx(1.0)
    assert report.wilson_lower == pytest.approx(0.20654931437723745)
    assert report.wilson_upper == pytest.approx(1.0)


def test_runner_records_configured_label_leaks_without_calling_judge() -> None:
    corpus = BenchmarkCorpus(
        tasks=(BenchmarkTask(name="one", domain="operations", prompt="Improve a handoff."),)
    )
    judge_calls = 0

    def leaking_generator(_task: BenchmarkTask) -> BenchmarkArtifact:
        return BenchmarkArtifact(
            content="A provider-x result.", cost_usd=0.2, latency_ms=20.0
        )

    def clean_generator(_task: BenchmarkTask) -> BenchmarkArtifact:
        return BenchmarkArtifact(content="A neutral result.", cost_usd=0.1, latency_ms=10.0)

    def judge(
        _task: BenchmarkTask, _candidate_a: JudgeArtifact, _candidate_b: JudgeArtifact
    ) -> JudgeAttempt:
        nonlocal judge_calls
        judge_calls += 1
        return _judge_attempt(Preference.TIE)

    report = _run_benchmark(
        corpus,
        leaking_generator,
        clean_generator,
        judge,
        provider_labels=("provider-x", "model-y"),
    )

    failure = report.records[0].muse.failure
    assert judge_calls == 0
    assert failure is not None
    assert failure.error_type == "ArtifactLabelLeak"
    assert failure.leaked_labels == ("provider-x",)
    assert report.judged_comparisons == 0
    assert report.generation_failures == 1
    assert report.total_cost_usd == pytest.approx(0.3)
    assert report.total_latency_ms == pytest.approx(30.0)


def test_runner_preserves_partial_record_when_judge_raises_and_counts_judge_telemetry() -> None:
    corpus = BenchmarkCorpus(
        tasks=(
            BenchmarkTask(name="one", domain="operations", prompt="Improve a handoff."),
            BenchmarkTask(name="two", domain="operations", prompt="Improve a handoff."),
        )
    )
    first_generator, second_generator = _neutral_generators()
    calls = 0

    def judge(
        _task: BenchmarkTask, _candidate_a: JudgeArtifact, _candidate_b: JudgeArtifact
    ) -> JudgeAttempt:
        nonlocal calls
        calls += 1
        if calls == 1:
            return _judge_attempt(Preference.TIE, cost_usd=0.4, latency_ms=40.0)
        raise RuntimeError("provider token\nshould not escape")

    report = _run_benchmark(corpus, first_generator, second_generator, judge)

    assert len(report.records) == 2
    assert report.records[1].judge_attempt is not None
    failure = report.records[1].judge_attempt.failure
    assert failure is not None
    assert failure.error_type == "RuntimeError"
    assert failure.message == "provider token should not escape"
    assert report.judge_attempts == 2
    assert report.judge_failures == 1
    assert report.judged_comparisons == 1
    assert report.judge_cost_usd == pytest.approx(0.4)
    assert report.judge_latency_ms == pytest.approx(40.0)
    assert report.total_cost_usd == pytest.approx(1.0)
    assert report.total_latency_ms == pytest.approx(100.0)


def test_report_metadata_is_self_describing_and_deterministic() -> None:
    corpus = BenchmarkCorpus(
        version="corpus-v2",
        tasks=(BenchmarkTask(name="one", domain="coding", prompt="Improve a workflow."),),
    )
    first_generator, second_generator = _neutral_generators()

    def judge(
        _task: BenchmarkTask, _candidate_a: JudgeArtifact, _candidate_b: JudgeArtifact
    ) -> JudgeAttempt:
        return _judge_attempt(Preference.TIE)

    arguments = {
        "repetitions": 2,
        "random_seed": 31,
        "muse_adapter": "adapter-a",
        "baseline_adapter": "adapter-b",
        "judge_adapter": "judge-c",
        "provider_labels": ("provider-x",),
        "run_timestamp": RUN_TIMESTAMP,
        "prompt_version": "prompt-v3",
        "config_version": "config-v4",
    }
    first = run_quality_benchmark(corpus, first_generator, second_generator, judge, **arguments)
    second = run_quality_benchmark(corpus, first_generator, second_generator, judge, **arguments)

    assert first.metadata.model_dump() == {
        "random_seed": 31,
        "repetitions": 2,
        "corpus_version": "corpus-v2",
        "muse_adapter": "adapter-a",
        "baseline_adapter": "adapter-b",
        "judge_adapter": "judge-c",
        "provider_labels": ("provider-x",),
        "run_timestamp": RUN_TIMESTAMP,
        "prompt_version": "prompt-v3",
        "config_version": "config-v4",
        "blind_labels": (),
        "system_identifiers": (),
    }
    assert first.metadata == second.metadata


def test_run_metadata_rejects_naive_run_timestamp() -> None:
    first_generator, second_generator = _neutral_generators()

    def judge(
        _task: BenchmarkTask, _candidate_a: JudgeArtifact, _candidate_b: JudgeArtifact
    ) -> JudgeAttempt:
        return _judge_attempt(Preference.TIE)

    with pytest.raises(ValidationError):
        run_quality_benchmark(
            BenchmarkCorpus(
                tasks=(BenchmarkTask(name="one", domain="coding", prompt="Improve a workflow."),)
            ),
            first_generator,
            second_generator,
            judge,
            run_timestamp=datetime(2026, 7, 12, 12, 0),
            prompt_version="prompt-v1",
            config_version="config-v1",
        )


def test_failure_messages_redact_secret_patterns_and_caller_secrets_from_report() -> None:
    bearer = "Bearer abcdefghijklmnopqrstuvwxyz"
    sdk_key = "sk-abcdefghijklmnopqrstuvwxyz123456"
    caller_secret = "caller-secret-value"
    corpus = BenchmarkCorpus(
        tasks=(
            BenchmarkTask(name="generation", domain="operations", prompt="Improve a handoff."),
            BenchmarkTask(name="judge", domain="operations", prompt="Improve a handoff."),
        )
    )

    def first_generator(task: BenchmarkTask) -> BenchmarkArtifact:
        if task.name == "generation":
            raise RuntimeError(f"generation failed: {bearer} {sdk_key} {caller_secret}")
        return BenchmarkArtifact(content="alpha plan", cost_usd=0.2, latency_ms=20.0)

    def second_generator(_task: BenchmarkTask) -> BenchmarkArtifact:
        return BenchmarkArtifact(content="beta plan", cost_usd=0.1, latency_ms=10.0)

    def judge(
        _task: BenchmarkTask, _candidate_a: JudgeArtifact, _candidate_b: JudgeArtifact
    ) -> JudgeAttempt:
        raise RuntimeError(f"judge failed: {bearer} {sdk_key} {caller_secret}")

    report = _run_benchmark(
        corpus,
        first_generator,
        second_generator,
        judge,
        secret_values=(caller_secret,),
    )
    serialized = report.model_dump_json()

    for secret in (bearer, sdk_key, caller_secret):
        assert secret not in serialized
    assert "[REDACTED]" in serialized
    assert report.records[0].muse.failure is not None
    assert report.records[0].muse.failure.message != caller_secret
    assert report.records[1].judge_attempt is not None
    assert report.records[1].judge_attempt.failure is not None
    assert report.records[1].judge_attempt.failure.message != sdk_key


def test_runner_records_generation_failures_without_scoring_them() -> None:
    corpus = BenchmarkCorpus(
        tasks=(
            BenchmarkTask(name="available", domain="operations", prompt="Improve a handoff."),
            BenchmarkTask(name="unavailable", domain="operations", prompt="Improve a handoff."),
        )
    )
    judge_calls = 0

    def first_generator(task: BenchmarkTask) -> BenchmarkArtifact:
        if task.name == "unavailable":
            raise RuntimeError("provider is unavailable")
        return BenchmarkArtifact(content="alpha plan", cost_usd=0.2, latency_ms=20.0)

    def second_generator(_task: BenchmarkTask) -> BenchmarkArtifact:
        return BenchmarkArtifact(content="beta plan", cost_usd=0.1, latency_ms=10.0)

    def judge(
        _task: BenchmarkTask, _candidate_a: JudgeArtifact, _candidate_b: JudgeArtifact
    ) -> JudgeAttempt:
        nonlocal judge_calls
        judge_calls += 1
        return _judge_attempt(Preference.TIE)

    report = _run_benchmark(corpus, first_generator, second_generator, judge, random_seed=5)

    failed_record = next(record for record in report.records if record.task.name == "unavailable")
    assert len(report.records) == 2
    assert judge_calls == 1
    assert report.generation_failures == 1
    assert report.judged_comparisons == 1
    assert report.ties == 1
    assert report.total_cost_usd == pytest.approx(0.4)
    assert report.total_latency_ms == pytest.approx(40.0)
    assert failed_record.judge_attempt is None
    assert failed_record.muse.failure is not None
    assert failed_record.muse.failure.system == "muse"
    assert failed_record.baseline.artifact is not None


def test_runner_rejects_nonpositive_repetitions() -> None:
    first_generator, second_generator = _neutral_generators()

    def judge(
        _task: BenchmarkTask, _candidate_a: JudgeArtifact, _candidate_b: JudgeArtifact
    ) -> JudgeAttempt:
        return _judge_attempt(Preference.TIE)

    with pytest.raises(ValueError, match="repetitions"):
        _run_benchmark(
            BenchmarkCorpus(
                tasks=(BenchmarkTask(name="one", domain="coding", prompt="Improve a workflow."),)
            ),
            first_generator,
            second_generator,
            judge,
            repetitions=0,
        )
