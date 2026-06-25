from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from creativity_layer.deterministic import DeterministicCreativeProvider
from creativity_layer.engine import CreativeEngine
from creativity_layer.models import InspirationKind, RunConfig, RunResult, TaskContext
from creativity_layer.providers import OperationQuote
from creativity_layer.search import (
    MeteredSearchUsage,
    SearchProviderResponse,
    SearchPurpose,
    SearchQuery,
    SearchResult,
)
from creativity_layer.search_pipeline import SearchAwareEngine


class RecordingSearchProvider:
    name = "recording-search"
    version = "test-v1"

    def __init__(self, results: tuple[SearchResult, ...]) -> None:
        self.results = results
        self.queries: list[SearchQuery] = []

    def search(self, query: SearchQuery) -> SearchProviderResponse:
        self.queries.append(query)
        return SearchProviderResponse(
            query=query,
            provider_name=self.name,
            results=self.results[: query.limit],
            usage=MeteredSearchUsage(
                result_count=min(len(self.results), query.limit),
                cost_usd=0.0,
            ),
        )


class FailingSeedQuoteCreativeProvider(DeterministicCreativeProvider):
    name = "failing-seed-quote"
    version = "test-v1"

    def quote_seed(self, framed_task, config) -> OperationQuote:
        raise RuntimeError("seed quote failed")


class RaisingSearchProvider:
    name = "raising-search"
    version = "test-v1"

    def __init__(self) -> None:
        self.called = False

    def search(self, query: SearchQuery) -> SearchProviderResponse:
        self.called = True
        raise AssertionError("search provider should not be called")


def source(
    *,
    source_id: str = "src-1",
    url: str = "https://example.com/source-1",
    rank: int = 1,
) -> SearchResult:
    return SearchResult(
        source_id=source_id,
        title="Decision garden",
        url=url,
        provider="recording-search",
        rank=rank,
        snippet="Teams use reversible claims.",
        bounded_excerpt="Teams use reversible claims.",
        retrieved_at=datetime(2026, 6, 25, tzinfo=UTC),
    )


def run_with_sources(
    sources: tuple[SearchResult, ...],
    *,
    goal: str = "Reversible team decisions",
) -> tuple[RunResult, RecordingSearchProvider]:
    provider = DeterministicCreativeProvider()
    search_provider = RecordingSearchProvider(sources)
    result = SearchAwareEngine(
        creative_provider=provider,
        search_provider=search_provider,
    ).run(
        TaskContext(goal=goal),
        RunConfig(seed_count=4, finalist_count=4, max_generations=0),
    )
    return result, search_provider


def seed_candidates(result: RunResult):
    return tuple(candidate for candidate in result.all_candidates if candidate.generation == 0)


def test_search_aware_engine_marks_at_least_half_of_seed_branches_independent():
    result, search_provider = run_with_sources((source(),))

    independent_seeds = tuple(
        candidate
        for candidate in seed_candidates(result)
        if candidate.inspiration_kind is InspirationKind.INDEPENDENT
    )

    assert len(independent_seeds) >= 2
    assert search_provider.queries == [
        SearchQuery(
            text="Reversible team decisions",
            purpose=SearchPurpose.NOVELTY,
            limit=2,
            freshness_bucket="static",
        )
    ]


def test_independent_candidates_do_not_inherit_search_source_provenance():
    result, _search_provider = run_with_sources((source(),))

    independent_candidates = tuple(
        candidate
        for candidate in result.all_candidates
        if candidate.inspiration_kind is InspirationKind.INDEPENDENT
    )

    assert independent_candidates
    assert all(candidate.source_urls == () for candidate in independent_candidates)
    assert all(
        candidate.inspiration_principles == () for candidate in independent_candidates
    )


def test_inspired_candidates_receive_source_provenance_when_abstractions_exist():
    result, _search_provider = run_with_sources(
        (
            source(source_id="src-1", url="https://example.com/source-1", rank=1),
            source(source_id="src-2", url="https://example.com/source-2", rank=2),
        )
    )

    inspired_candidates = tuple(
        candidate
        for candidate in seed_candidates(result)
        if candidate.inspiration_kind is InspirationKind.INSPIRED
    )

    assert inspired_candidates
    assert {candidate.source_urls for candidate in inspired_candidates} <= {
        ("https://example.com/source-1",),
        ("https://example.com/source-2",),
    }
    assert all(
        candidate.inspiration_principles[0].startswith("Transfer the mechanism of")
        for candidate in inspired_candidates
    )


def test_finalists_reference_updated_candidates_not_stale_pre_search_candidates():
    result, _search_provider = run_with_sources((source(),))
    candidates_by_id = {candidate.id: candidate for candidate in result.all_candidates}

    assert result.finalists
    assert all(finalist == candidates_by_id[finalist.id] for finalist in result.finalists)
    assert any(
        finalist.inspiration_kind is InspirationKind.INSPIRED
        and finalist.source_urls == ("https://example.com/source-1",)
        for finalist in result.finalists
    )


def test_result_fingerprint_is_recomputed_after_candidate_provenance_changes():
    creative_provider = DeterministicCreativeProvider()
    task = TaskContext(goal="Reversible team decisions")
    config = RunConfig(seed_count=4, finalist_count=4, max_generations=0)
    base_result = CreativeEngine(
        framer=creative_provider,
        seeder=creative_provider,
        transformer=creative_provider,
        evaluator=creative_provider,
    ).run(task, config)

    result, _search_provider = run_with_sources((source(),))

    assert result.reproducibility_fingerprint != base_result.reproducibility_fingerprint
    assert RunResult.model_validate(result.model_dump(mode="json")) == result

    stale_payload = result.model_dump(mode="json")
    stale_payload["reproducibility_fingerprint"] = base_result.reproducibility_fingerprint
    with pytest.raises(ValidationError, match="reproducibility_fingerprint"):
        RunResult.model_validate(stale_payload)


def test_search_is_skipped_when_creative_run_returns_no_candidates():
    creative_provider = FailingSeedQuoteCreativeProvider()
    search_provider = RaisingSearchProvider()

    result = SearchAwareEngine(
        creative_provider=creative_provider,
        search_provider=search_provider,
    ).run(
        TaskContext(goal="Reversible team decisions"),
        RunConfig(seed_count=4, finalist_count=4, max_generations=0),
    )

    assert result.stopped_reason == "provider_error"
    assert result.all_candidates == ()
    assert search_provider.called is False


def test_empty_search_results_leave_independent_candidates_without_source_provenance():
    result, search_provider = run_with_sources(())

    assert search_provider.queries == [
        SearchQuery(
            text="Reversible team decisions",
            purpose=SearchPurpose.NOVELTY,
            limit=2,
            freshness_bucket="static",
        )
    ]
    assert result.stopped_reason == "generation_limit"
    assert result.all_candidates
    assert all(
        candidate.inspiration_kind is InspirationKind.INDEPENDENT
        for candidate in result.all_candidates
    )
    assert all(candidate.source_urls == () for candidate in result.all_candidates)
    assert all(
        candidate.inspiration_principles == ()
        for candidate in result.all_candidates
    )
