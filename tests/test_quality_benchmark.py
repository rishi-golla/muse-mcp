import pytest
from pydantic import ValidationError

from muse.quality_benchmark import (
    DEFAULT_BENCHMARK_CORPUS,
    BenchmarkArtifact,
    BenchmarkCorpus,
    BenchmarkTask,
    JudgeArtifact,
    PairwiseJudgment,
    Preference,
    run_quality_benchmark,
)


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
        JudgeArtifact(content="A concrete proposal.", system_identity="muse")


def test_pairwise_judgment_rejects_unknown_preferences() -> None:
    with pytest.raises(ValidationError):
        PairwiseJudgment(
            preference="candidate-c",
            confidence=0.8,
            rationale="The artifact is better grounded in the request.",
            originality=Preference.A,
            usefulness=Preference.A,
            operational_specificity=Preference.B,
            task_fit=Preference.A,
        )


def test_benchmark_corpus_rejects_duplicate_task_names() -> None:
    task = BenchmarkTask(
        name="release-notes-triage",
        domain="operations",
        prompt="Propose a lightweight process for triaging release notes from several teams.",
    )

    with pytest.raises(ValidationError, match="unique"):
        BenchmarkCorpus(tasks=(task, task))


def test_default_benchmark_corpus_is_domain_varied_and_blind() -> None:
    corpus = DEFAULT_BENCHMARK_CORPUS
    domains = {task.domain for task in corpus.tasks}

    assert len(corpus.tasks) >= 30
    assert {"coding", "product", "design", "operations", "research"} <= domains
    assert len({task.name for task in corpus.tasks}) == len(corpus.tasks)

    forbidden_keywords = ("expected", "correct", "ideal", "answer")
    for task in corpus.tasks:
        prompt = task.prompt.lower()
        assert not any(keyword in prompt for keyword in forbidden_keywords)


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


def test_runner_blinds_judge_inputs_and_reproducibly_randomizes_repetitions() -> None:
    corpus = BenchmarkCorpus(
        tasks=(
            BenchmarkTask(name="one", domain="coding", prompt="Improve a deployment workflow."),
            BenchmarkTask(name="two", domain="product", prompt="Improve team onboarding."),
        )
    )
    observed_candidates: list[tuple[JudgeArtifact, JudgeArtifact]] = []

    def muse_generator(task: BenchmarkTask) -> BenchmarkArtifact:
        return BenchmarkArtifact(
            content=f"Muse solution for {task.name}.", cost_usd=0.2, latency_ms=20.0
        )

    def baseline_generator(task: BenchmarkTask) -> BenchmarkArtifact:
        return BenchmarkArtifact(
            content=f"Baseline solution for {task.name}.", cost_usd=0.1, latency_ms=10.0
        )

    def judge(
        _task: BenchmarkTask, candidate_a: JudgeArtifact, candidate_b: JudgeArtifact
    ) -> PairwiseJudgment:
        observed_candidates.append((candidate_a, candidate_b))
        return _judgment(Preference.TIE)

    first = run_quality_benchmark(
        corpus, muse_generator, baseline_generator, judge, repetitions=3, random_seed=17
    )
    second = run_quality_benchmark(
        corpus, muse_generator, baseline_generator, judge, repetitions=3, random_seed=17
    )

    assert len(first.records) == 6
    first_order = [
        (record.task.name, record.repetition, record.muse_label) for record in first.records
    ]
    second_order = [
        (record.task.name, record.repetition, record.muse_label) for record in second.records
    ]
    assert first_order == second_order
    assert first.judged_comparisons == 6
    assert first.ties == 6
    assert first.wins == first.losses == 0
    assert len(observed_candidates) == 12
    for candidate_a, candidate_b in observed_candidates:
        assert isinstance(candidate_a, JudgeArtifact)
        assert isinstance(candidate_b, JudgeArtifact)
        assert candidate_a.model_dump() == {"content": candidate_a.content}
        assert candidate_b.model_dump() == {"content": candidate_b.content}
        assert not hasattr(candidate_a, "cost_usd")
        assert not hasattr(candidate_a, "latency_ms")
        assert not hasattr(candidate_a, "system")


def test_runner_records_generation_failures_without_scoring_them() -> None:
    corpus = BenchmarkCorpus(
        tasks=(
            BenchmarkTask(name="available", domain="operations", prompt="Improve a handoff."),
            BenchmarkTask(name="unavailable", domain="operations", prompt="Improve a handoff."),
        )
    )
    judge_calls = 0

    def muse_generator(task: BenchmarkTask) -> BenchmarkArtifact:
        if task.name == "unavailable":
            raise RuntimeError("Muse provider is unavailable")
        return BenchmarkArtifact(content="Muse plan.", cost_usd=0.2, latency_ms=20.0)

    def baseline_generator(_task: BenchmarkTask) -> BenchmarkArtifact:
        return BenchmarkArtifact(content="Baseline plan.", cost_usd=0.1, latency_ms=10.0)

    def judge(
        _task: BenchmarkTask, _candidate_a: JudgeArtifact, _candidate_b: JudgeArtifact
    ) -> PairwiseJudgment:
        nonlocal judge_calls
        judge_calls += 1
        return _judgment(Preference.TIE)

    report = run_quality_benchmark(corpus, muse_generator, baseline_generator, judge, random_seed=5)

    failed_record = next(record for record in report.records if record.task.name == "unavailable")
    assert len(report.records) == 2
    assert judge_calls == 1
    assert report.generation_failures == 1
    assert report.judged_comparisons == 1
    assert report.ties == 1
    assert report.total_cost_usd == pytest.approx(0.4)
    assert report.total_latency_ms == pytest.approx(40.0)
    assert failed_record.judgment is None
    assert failed_record.muse.failure is not None
    assert failed_record.muse.failure.system == "muse"
    assert failed_record.baseline.artifact is not None


def test_runner_reports_ties_accounting_and_wilson_bounds_for_decisive_judgments() -> None:
    corpus = BenchmarkCorpus(
        tasks=tuple(
            BenchmarkTask(name=name, domain="research", prompt=f"Investigate {name}.")
            for name in ("win", "loss", "tie")
        )
    )

    def muse_generator(task: BenchmarkTask) -> BenchmarkArtifact:
        return BenchmarkArtifact(content=f"Muse {task.name}.", cost_usd=1.25, latency_ms=100.0)

    def baseline_generator(task: BenchmarkTask) -> BenchmarkArtifact:
        return BenchmarkArtifact(content=f"Baseline {task.name}.", cost_usd=2.5, latency_ms=50.0)

    def judge(
        task: BenchmarkTask, candidate_a: JudgeArtifact, _candidate_b: JudgeArtifact
    ) -> PairwiseJudgment:
        if task.name == "tie":
            return _judgment(Preference.TIE)
        muse_is_a = candidate_a.content.startswith("Muse ")
        muse_wins = task.name == "win"
        return _judgment(Preference.A if muse_is_a == muse_wins else Preference.B)

    report = run_quality_benchmark(
        corpus, muse_generator, baseline_generator, judge, random_seed=29
    )

    assert report.generation_attempts == 6
    assert report.generation_failures == 0
    assert report.judged_comparisons == 3
    assert report.wins == report.losses == report.ties == 1
    assert report.decisive_comparisons == 2
    assert report.preference_rate == pytest.approx(0.5)
    assert report.wilson_lower == pytest.approx(0.0945312057)
    assert report.wilson_upper == pytest.approx(0.9054687943)
    assert report.total_cost_usd == pytest.approx(11.25)
    assert report.total_latency_ms == pytest.approx(450.0)


def test_runner_rejects_nonpositive_repetitions() -> None:
    def generator(_task: BenchmarkTask) -> BenchmarkArtifact:
        return BenchmarkArtifact(content="A proposal.", cost_usd=0.0, latency_ms=0.0)

    def judge(
        _task: BenchmarkTask, _candidate_a: JudgeArtifact, _candidate_b: JudgeArtifact
    ) -> PairwiseJudgment:
        return _judgment(Preference.TIE)

    with pytest.raises(ValueError, match="repetitions"):
        run_quality_benchmark(
            BenchmarkCorpus(
                tasks=(BenchmarkTask(name="one", domain="coding", prompt="Improve a workflow."),)
            ),
            generator,
            generator,
            judge,
            repetitions=0,
        )
