from __future__ import annotations

import os
from collections.abc import Mapping
from enum import StrEnum

from pydantic import Field

from muse.context_provider import RepoSignals
from muse.models import (
    ContextBundle,
    ContextSensitivity,
    ContextSnippet,
    FrozenModel,
    TaskContext,
)
from muse.search import SearchProvider, SearchPurpose, SearchQuery, SearchResult


class SearchContextMode(StrEnum):
    OFF = "off"
    LIGHT = "light"
    DEEP = "deep"


class SearchProviderPolicy(StrEnum):
    AUTO = "auto"
    DETERMINISTIC = "deterministic"
    EXA = "exa"
    BRAVE = "brave"


class SearchContextMetadata(FrozenModel):
    mode: str
    used: bool = False
    skipped_reason: str | None = None
    provider: str | None = None
    provider_policy: str = SearchProviderPolicy.AUTO.value
    strict: bool = False
    source_count: int = Field(default=0, strict=True, ge=0)
    query_count: int = Field(default=0, strict=True, ge=0)
    queries: tuple[Mapping[str, object], ...] = ()
    query_source_counts: tuple[int, ...] = ()
    errors: tuple[str, ...] = ()


class SearchContextResult(FrozenModel):
    bundle: ContextBundle = Field(default_factory=ContextBundle)
    metadata: SearchContextMetadata


class SearchContextResolver:
    def __init__(
        self,
        *,
        provider: SearchProvider | None = None,
        provider_policy: SearchProviderPolicy = SearchProviderPolicy.AUTO,
        approval_required: bool = True,
        environ: Mapping[str, str] | None = None,
    ) -> None:
        self._provider = provider
        self._provider_policy = provider_policy
        self._approval_required = approval_required
        self._environ = os.environ if environ is None else environ

    def resolve(
        self,
        *,
        mode: SearchContextMode,
        task: TaskContext,
        repo_signals: RepoSignals,
        max_snippets: int,
        strict: bool = False,
    ) -> SearchContextResult:
        if mode is SearchContextMode.OFF:
            return _skipped(
                mode=mode,
                reason="disabled",
                provider_policy=self._provider_policy,
                strict=strict,
            )
        if self._approval_required and not _live_search_approved(self._environ):
            return _skipped(
                mode=mode,
                reason="approval_required",
                provider_policy=self._provider_policy,
                strict=strict,
            )
        if self._provider is None:
            return _skipped(
                mode=mode,
                reason="configuration_error",
                provider_policy=self._provider_policy,
                strict=strict,
                errors=("search provider is not configured",),
            )

        try:
            search_result = self._search(mode, task, repo_signals, max_snippets)
        except Exception as error:  # noqa: BLE001 - provider details are sanitized here.
            return _skipped(
                mode=mode,
                reason="provider_error",
                provider=self._provider.name,
                provider_policy=self._provider_policy,
                strict=strict,
                errors=(f"search provider failed: {type(error).__name__}",),
            )

        snippets = tuple(
            _snippet_from_search_result(result)
            for result in search_result.results[:max_snippets]
        )
        if not snippets:
            return SearchContextResult(
                metadata=SearchContextMetadata(
                    mode=mode.value,
                    used=False,
                    skipped_reason="empty_results",
                    provider=self._provider.name,
                    provider_policy=self._provider_policy.value,
                    strict=strict,
                    query_count=len(search_result.queries),
                    queries=_query_metadata(search_result.queries),
                    query_source_counts=search_result.query_source_counts,
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
                provider_policy=self._provider_policy.value,
                strict=strict,
                source_count=len(snippets),
                query_count=len(search_result.queries),
                queries=_query_metadata(search_result.queries),
                query_source_counts=search_result.query_source_counts,
            ),
        )

    def _search(
        self,
        mode: SearchContextMode,
        task: TaskContext,
        repo_signals: RepoSignals,
        max_snippets: int,
    ) -> _SearchExecutionResult:
        assert self._provider is not None
        queries = _queries_for_mode(mode, task, repo_signals, max_snippets)
        collected: list[SearchResult] = []
        counts: list[int] = []
        for query in queries:
            response = self._provider.search(query)
            collected.extend(response.results)
            counts.append(len(response.results))
        return _SearchExecutionResult(
            queries=queries,
            results=tuple(collected),
            query_source_counts=tuple(counts),
        )


class _SearchExecutionResult(FrozenModel):
    queries: tuple[SearchQuery, ...]
    results: tuple[SearchResult, ...]
    query_source_counts: tuple[int, ...]


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
    queries = [
        SearchQuery(
            text=task.goal,
            purpose=SearchPurpose.EVIDENCE,
            limit=light_limit,
            domain_hints=hints,
        )
    ]
    stack_query = _stack_query_text(task, repo_signals)
    if stack_query is not None:
        queries.append(
            SearchQuery(
                text=stack_query,
                purpose=SearchPurpose.EVIDENCE,
                limit=light_limit,
                domain_hints=hints,
            )
        )
    failure_query = _failure_query_text(task, repo_signals)
    if failure_query is not None:
        queries.append(
            SearchQuery(
                text=failure_query,
                purpose=SearchPurpose.EVIDENCE,
                limit=light_limit,
                domain_hints=hints,
            )
        )
    if mode is SearchContextMode.LIGHT:
        return tuple(queries)
    deep_limit = max(1, min(5, max_snippets))
    return tuple(
        query.model_copy(update={"limit": deep_limit})
        for query in (
            *queries,
            SearchQuery(
                text=f"prior art for {task.goal}",
                purpose=SearchPurpose.PRIOR_ART,
                limit=deep_limit,
                domain_hints=hints,
            ),
            SearchQuery(
                text=f"analogous mechanisms for {task.goal}",
                purpose=SearchPurpose.ANALOGY,
                limit=deep_limit,
                domain_hints=hints,
            ),
        )
    )


def _stack_query_text(task: TaskContext, repo_signals: RepoSignals) -> str | None:
    parts = tuple(
        item
        for item in (
            *repo_signals.detected_languages,
            *repo_signals.detected_frameworks,
            *repo_signals.package_manifests,
            *repo_signals.dependency_hints,
        )
        if item.strip()
    )
    if not parts:
        return None
    return f"{task.goal} stack context " + " ".join(parts[:8])


def _failure_query_text(task: TaskContext, repo_signals: RepoSignals) -> str | None:
    parts = tuple(
        item
        for item in (*repo_signals.test_commands, *repo_signals.ci_logs)
        if item.strip()
    )
    if not parts:
        return None
    return f"{task.goal} failure context " + " ".join(parts[:4])


def _query_metadata(queries: tuple[SearchQuery, ...]) -> tuple[Mapping[str, object], ...]:
    return tuple(
        {
            "text": query.text,
            "purpose": query.purpose.value,
            "limit": query.limit,
            "domain_hints": query.domain_hints,
        }
        for query in queries
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
    provider_policy: SearchProviderPolicy = SearchProviderPolicy.AUTO,
    strict: bool = False,
    errors: tuple[str, ...] = (),
) -> SearchContextResult:
    return SearchContextResult(
        metadata=SearchContextMetadata(
            mode=mode.value,
            used=False,
            skipped_reason=reason,
            provider=provider,
            provider_policy=provider_policy.value,
            strict=strict,
            errors=errors,
        )
    )


def _live_search_approved(environ: Mapping[str, str]) -> bool:
    return environ.get("MUSE_LIVE_SEARCH_APPROVED", "").strip() == "1"
