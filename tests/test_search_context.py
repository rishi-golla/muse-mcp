from __future__ import annotations

from pydantic import PrivateAttr

from creativity_layer.context_provider import RepoSignals
from creativity_layer.models import TaskContext
from creativity_layer.search import (
    DeterministicSearchProvider,
    SearchProviderResponse,
    SearchQuery,
)
from creativity_layer.search_context import (
    SearchContextMode,
    SearchContextResolver,
    SearchProviderPolicy,
)


class RecordingSearchProvider(DeterministicSearchProvider):
    _queries: list[SearchQuery] = PrivateAttr(default_factory=list)

    @property
    def queries(self) -> tuple[SearchQuery, ...]:
        return tuple(self._queries)

    def __init__(self) -> None:
        super().__init__()

    def search(self, query: SearchQuery) -> SearchProviderResponse:
        self._queries.append(query)
        return super().search(query)


def test_search_context_off_returns_empty_metadata() -> None:
    result = SearchContextResolver().resolve(
        mode=SearchContextMode.OFF,
        task=TaskContext(goal="reversible team decisions"),
        repo_signals=RepoSignals(),
        max_snippets=4,
    )

    assert result.bundle.snippets == ()
    assert result.metadata.mode == "off"
    assert result.metadata.used is False
    assert result.metadata.skipped_reason == "disabled"


def test_search_context_requires_approval_before_provider_use() -> None:
    result = SearchContextResolver(
        provider=DeterministicSearchProvider(),
        approval_required=True,
        environ={},
    ).resolve(
        mode=SearchContextMode.LIGHT,
        task=TaskContext(goal="reversible team decisions"),
        repo_signals=RepoSignals(detected_frameworks=("pytest",)),
        max_snippets=4,
    )

    assert result.bundle.snippets == ()
    assert result.metadata.used is False
    assert result.metadata.skipped_reason == "approval_required"


def test_search_context_reports_missing_provider_after_approval() -> None:
    result = SearchContextResolver(
        provider=None,
        approval_required=True,
        environ={"CREATIVITY_LAYER_LIVE_SEARCH_APPROVED": "1"},
    ).resolve(
        mode=SearchContextMode.LIGHT,
        task=TaskContext(goal="reversible team decisions"),
        repo_signals=RepoSignals(),
        max_snippets=4,
    )

    assert result.bundle.snippets == ()
    assert result.metadata.skipped_reason == "configuration_error"
    assert "search provider" in result.metadata.errors[0]


def test_search_context_converts_results_to_context_snippets() -> None:
    result = SearchContextResolver(
        provider=DeterministicSearchProvider(),
        approval_required=False,
    ).resolve(
        mode=SearchContextMode.LIGHT,
        task=TaskContext(goal="reversible team decisions"),
        repo_signals=RepoSignals(detected_languages=("Python",)),
        max_snippets=4,
    )

    assert result.metadata.used is True
    assert result.metadata.mode == "light"
    assert result.metadata.source_count == 1
    assert result.bundle.tags == ("search:light", "search:deterministic-search")
    assert result.bundle.snippets[0].source == "search/deterministic-search/src-1"
    assert "Teams use reversible claims" in result.bundle.snippets[0].content


def test_light_search_plans_stack_and_failure_queries_from_repo_signals() -> None:
    provider = RecordingSearchProvider()

    result = SearchContextResolver(
        provider=provider,
        provider_policy=SearchProviderPolicy.DETERMINISTIC,
        approval_required=False,
    ).resolve(
        mode=SearchContextMode.LIGHT,
        task=TaskContext(goal="reversible team decisions"),
        repo_signals=RepoSignals(
            test_commands=("pnpm test --filter apps/web -- --shard=2/4",),
            ci_logs=("Vitest shard 2 failed after Playwright smoke tests",),
            detected_languages=("TypeScript",),
            detected_frameworks=("Vitest", "Playwright"),
            dependency_hints=("apps/web depends on packages/ui",),
        ),
        max_snippets=4,
    )

    query_texts = [query.text for query in provider.queries]

    assert result.metadata.provider_policy == "deterministic"
    assert result.metadata.query_count == 3
    assert result.metadata.queries[0]["purpose"] == "evidence"
    assert "TypeScript" in query_texts[1]
    assert "Vitest" in query_texts[1]
    assert "apps/web depends on packages/ui" in query_texts[1]
    assert "Vitest shard 2 failed" in query_texts[2]
    assert result.metadata.query_source_counts == (1, 0, 0)


def test_deep_search_adds_prior_art_and_analogy_queries() -> None:
    provider = RecordingSearchProvider()

    result = SearchContextResolver(
        provider=provider,
        provider_policy=SearchProviderPolicy.DETERMINISTIC,
        approval_required=False,
    ).resolve(
        mode=SearchContextMode.DEEP,
        task=TaskContext(goal="reversible team decisions"),
        repo_signals=RepoSignals(detected_languages=("Python",)),
        max_snippets=5,
    )

    purposes = [query.purpose.value for query in provider.queries]

    assert purposes == ["evidence", "evidence", "prior_art", "analogy"]
    assert result.metadata.query_count == 4
    assert result.metadata.queries[-2]["purpose"] == "prior_art"
    assert result.metadata.queries[-1]["purpose"] == "analogy"
