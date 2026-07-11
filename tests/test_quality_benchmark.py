import pytest
from pydantic import ValidationError

from muse.quality_benchmark import (
    DEFAULT_BENCHMARK_CORPUS,
    BenchmarkArtifact,
    BenchmarkCorpus,
    BenchmarkTask,
    PairwiseJudgment,
    Preference,
)


def test_benchmark_artifact_rejects_blank_content_and_negative_telemetry() -> None:
    with pytest.raises(ValidationError):
        BenchmarkArtifact(content="   ", cost_usd=0.0, latency_ms=0.0)

    with pytest.raises(ValidationError):
        BenchmarkArtifact(content="A concrete proposal.", cost_usd=-0.01, latency_ms=20.0)

    with pytest.raises(ValidationError):
        BenchmarkArtifact(content="A concrete proposal.", cost_usd=0.01, latency_ms=-1.0)


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
