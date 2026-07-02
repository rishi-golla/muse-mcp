from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from typing import Protocol

from pydantic import ValidationError

from muse.live_search_config import (
    LiveSearchRuntime,
    OpenAIWebSearchConfig,
    SearchProviderError,
)
from muse.models import OperationTrace
from muse.providers import OperationQuote
from muse.search import (
    MeteredSearchUsage,
    SearchProviderResponse,
    SearchQuery,
    SearchResult,
)

WEB_SEARCH_TOOL = {"type": "web_search_preview"}
SECRET_LIKE_VALUE = re.compile(r"(?:\bBearer\s+\S+|\bsk-[A-Za-z0-9_-]{10,})")


class OpenAIResponsesResource(Protocol):
    def create(self, **kwargs: object) -> object: ...


class OpenAIWebSearchClient(Protocol):
    responses: OpenAIResponsesResource


class OpenAIWebSearchProvider:
    name = "openai-web-search"
    version = "openai-web-search-v1"

    def __init__(
        self,
        *,
        client: OpenAIWebSearchClient,
        config: OpenAIWebSearchConfig,
        runtime: LiveSearchRuntime | None = None,
    ) -> None:
        self.client = client
        self.config = config
        self.runtime = runtime or LiveSearchRuntime()

    def quote_search(self, query: SearchQuery) -> OperationQuote:
        return OperationQuote(max_cost_usd=0.0)

    def search(self, query: SearchQuery) -> SearchProviderResponse:
        effective_limit = min(query.limit, self.runtime.max_results)
        try:
            payload = self.client.responses.create(
                model=self.config.model,
                input=query.text,
                tools=[WEB_SEARCH_TOOL],
            )
            results, skipped_count = self._build_results(payload, effective_limit)
            trace = self._build_trace(query, effective_limit, results, skipped_count)
            return SearchProviderResponse(
                query=query,
                provider_name=self.name,
                results=results,
                usage=MeteredSearchUsage(result_count=len(results), cost_usd=0.0),
                trace=trace,
            )
        except SearchProviderError:
            raise
        except Exception as error:
            provider_error = SearchProviderError(
                provider=self.name,
                category="search_error",
                message=_sanitize_error_message(str(error)),
                secret_values=(),
            )

        raise provider_error

    def _build_results(
        self,
        payload: object,
        effective_limit: int,
    ) -> tuple[tuple[SearchResult, ...], int]:
        results: list[SearchResult] = []
        skipped_count = 0
        for content in _iter_response_content(payload):
            text = _read_text_value(content, "text")
            snippet_source = text or "OpenAI web search citation."
            annotations = _as_iterable(_read_field(content, "annotations"))
            for annotation in annotations:
                if _read_text_value(annotation, "type") != "url_citation":
                    continue
                result = self._build_result(
                    annotation=annotation,
                    snippet_source=snippet_source,
                    rank=len(results) + 1,
                )
                if result is None:
                    skipped_count += 1
                    continue
                results.append(result)
                if len(results) >= effective_limit:
                    return tuple(results), skipped_count
        return tuple(results), skipped_count

    def _build_result(
        self,
        *,
        annotation: object,
        snippet_source: str,
        rank: int,
    ) -> SearchResult | None:
        url = _read_text_value(annotation, "url")
        if url is None:
            return None
        title = _read_text_value(annotation, "title") or url
        try:
            return SearchResult(
                source_id=_source_id(url, title),
                title=title,
                url=url,
                provider=self.name,
                rank=rank,
                snippet=_bound(snippet_source, self.runtime.snippet_chars),
                bounded_excerpt=_bound(snippet_source, self.runtime.snippet_chars),
                retrieved_at=datetime.now(UTC),
                provider_metadata={"source": self.name},
            )
        except (TypeError, ValueError, ValidationError):
            return None

    def _build_trace(
        self,
        query: SearchQuery,
        effective_limit: int,
        results: tuple[SearchResult, ...],
        skipped_count: int,
    ) -> OperationTrace:
        source_ids = tuple(result.source_id for result in results)
        return OperationTrace.from_payload(
            request={
                "operation": "search",
                "provider": self.name,
                "provider_version": self.version,
                "model": self.config.model,
                "search": {
                    "normalized_text": query.normalized_text,
                    "purpose": query.purpose.value,
                    "limit": query.limit,
                    "effective_limit": effective_limit,
                    "freshness_bucket": query.freshness_bucket,
                    "domain_hints": query.domain_hints,
                    "tool": WEB_SEARCH_TOOL,
                },
            },
            response={
                "operation": "search",
                "provider": self.name,
                "source_ids": source_ids,
                "result_count": len(results),
                "skipped_count": skipped_count,
            },
        )


def _iter_response_content(payload: object) -> Iterable[object]:
    for output_item in _as_iterable(_read_field(payload, "output")):
        yield from _as_iterable(_read_field(output_item, "content"))


def _read_field(value: object, field: str) -> object:
    if isinstance(value, Mapping):
        return value.get(field)
    return getattr(value, field, None)


def _read_text_value(value: object, field: str) -> str | None:
    raw = _read_field(value, field)
    if not isinstance(raw, str):
        return None
    stripped = raw.strip()
    return stripped or None


def _as_iterable(value: object) -> Iterable[object]:
    if isinstance(value, Iterable) and not isinstance(value, (str, bytes, Mapping)):
        return value
    return ()


def _bound(value: str, limit: int) -> str:
    return value[:limit]


def _source_id(url: str, title: str) -> str:
    identity = url or title
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
    return f"openai-web-{digest}"


def _sanitize_error_message(message: str) -> str:
    return SECRET_LIKE_VALUE.sub("[REDACTED]", message)
