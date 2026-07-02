from __future__ import annotations

import os
from collections.abc import Mapping
from enum import StrEnum

from pydantic import Field

from creativity_layer.context_provider import RepoSignals
from creativity_layer.models import (
    ContextBundle,
    ContextSensitivity,
    ContextSnippet,
    FrozenModel,
    TaskContext,
)
from creativity_layer.search import SearchProvider, SearchPurpose, SearchQuery, SearchResult


class SearchContextMode(StrEnum):
    OFF = "off"
    LIGHT = "light"
    DEEP = "deep"


class SearchContextMetadata(FrozenModel):
    mode: str
    used: bool = False
    skipped_reason: str | None = None
    provider: str | None = None
    source_count: int = Field(default=0, strict=True, ge=0)
    query_count: int = Field(default=0, strict=True, ge=0)
    errors: tuple[str, ...] = ()


class SearchContextResult(FrozenModel):
    bundle: ContextBundle = Field(default_factory=ContextBundle)
    metadata: SearchContextMetadata


class SearchContextResolver:
    def __init__(
        self,
        *,
        provider: SearchProvider | None = None,
        approval_required: bool = True,
        environ: Mapping[str, str] | None = None,
    ) -> None:
        self._provider = provider
        self._approval_required = approval_required
        self._environ = os.environ if environ is None else environ

    def resolve(
        self,
        *,
        mode: SearchContextMode,
        task: TaskContext,
        repo_signals: RepoSignals,
        max_snippets: int,
    ) -> SearchContextResult:
        if mode is SearchContextMode.OFF:
            return _skipped(mode=mode, reason="disabled")
        if self._approval_required and not _live_search_approved(self._environ):
            return _skipped(mode=mode, reason="approval_required")
        if self._provider is None:
            return _skipped(
                mode=mode,
                reason="configuration_error",
                errors=("search provider is not configured",),
            )

        try:
            results = self._search(mode, task, repo_signals, max_snippets)
        except Exception as error:  # noqa: BLE001 - provider details are sanitized here.
            return _skipped(
                mode=mode,
                reason="provider_error",
                provider=self._provider.name,
                errors=(f"search provider failed: {type(error).__name__}",),
            )

        snippets = tuple(
            _snippet_from_search_result(result)
            for result in results[:max_snippets]
        )
        if not snippets:
            return SearchContextResult(
                metadata=SearchContextMetadata(
                    mode=mode.value,
                    used=False,
                    skipped_reason="empty_results",
                    provider=self._provider.name,
                    query_count=_query_count(mode),
                )
            )
        bundle = ContextBundle(
            snippets=snippets,
            tags=(f"search:{mode.value}", f"search:{self._provider.name}"),
        )
        return SearchContextResult(
            bundle=bundle,
            metadata=SearchContextMetadata(
                mode=mode.value,
                used=True,
                provider=self._provider.name,
                source_count=len(snippets),
                query_count=_query_count(mode),
            ),
        )

    def _search(
        self,
        mode: SearchContextMode,
        task: TaskContext,
        repo_signals: RepoSignals,
        max_snippets: int,
    ) -> tuple[SearchResult, ...]:
        assert self._provider is not None
        queries = _queries_for_mode(mode, task, repo_signals, max_snippets)
        collected: list[SearchResult] = []
        for query in queries:
            response = self._provider.search(query)
            collected.extend(response.results)
        return tuple(collected)


def _queries_for_mode(
    mode: SearchContextMode,
    task: TaskContext,
    repo_signals: RepoSignals,
    max_snippets: int,
) -> tuple[SearchQuery, ...]:
    hints = tuple(
        dict.fromkeys(
            tag.strip()
            for tag in (
                *repo_signals.detected_languages,
                *repo_signals.detected_frameworks,
            )
            if tag.strip()
        )
    )
    light_limit = max(1, min(3, max_snippets))
    if mode is SearchContextMode.LIGHT:
        return (
            SearchQuery(
                text=task.goal,
                purpose=SearchPurpose.EVIDENCE,
                limit=light_limit,
                domain_hints=hints,
            ),
        )
    deep_limit = max(1, min(5, max_snippets))
    return (
        SearchQuery(
            text=task.goal,
            purpose=SearchPurpose.EVIDENCE,
            limit=deep_limit,
            domain_hints=hints,
        ),
        SearchQuery(
            text=task.goal,
            purpose=SearchPurpose.ANALOGY,
            limit=deep_limit,
            domain_hints=hints,
        ),
    )


def _query_count(mode: SearchContextMode) -> int:
    if mode is SearchContextMode.OFF:
        return 0
    if mode is SearchContextMode.LIGHT:
        return 1
    return 2


def _snippet_from_search_result(result: SearchResult) -> ContextSnippet:
    return ContextSnippet(
        source=f"search/{result.provider}/{result.source_id}",
        title=result.title,
        content=result.snippet,
        metadata={
            "url": str(result.url),
            "provider": result.provider,
            "rank": result.rank,
            "content_hash": result.content_hash,
        },
        sensitivity=ContextSensitivity.PRIVATE,
    )


def _skipped(
    *,
    mode: SearchContextMode,
    reason: str,
    provider: str | None = None,
    errors: tuple[str, ...] = (),
) -> SearchContextResult:
    return SearchContextResult(
        metadata=SearchContextMetadata(
            mode=mode.value,
            used=False,
            skipped_reason=reason,
            provider=provider,
            errors=errors,
        )
    )


def _live_search_approved(environ: Mapping[str, str]) -> bool:
    return environ.get("CREATIVITY_LAYER_LIVE_SEARCH_APPROVED", "").strip() == "1"
