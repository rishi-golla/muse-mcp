from __future__ import annotations

from creativity_layer.context_provider import RepoSignals
from creativity_layer.models import TaskContext
from creativity_layer.search import DeterministicSearchProvider
from creativity_layer.search_context import SearchContextMode, SearchContextResolver


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
