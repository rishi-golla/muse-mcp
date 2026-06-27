from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime

from pydantic import ValidationError

from creativity_layer.live_search_config import (
    ExaSearchCredentials,
    LiveSearchRuntime,
    SearchProviderError,
)
from creativity_layer.models import OperationTrace
from creativity_layer.providers import OperationQuote
from creativity_layer.search import (
    MeteredSearchUsage,
    SearchProviderResponse,
    SearchQuery,
    SearchResult,
)


class ExaSearchProvider:
    name = "exa"
    version = "exa-search-v1"

    def __init__(
        self,
        *,
        credentials: ExaSearchCredentials,
        client: object | None = None,
        runtime: LiveSearchRuntime | None = None,
    ) -> None:
        self.credentials = credentials
        self._client = client
        self.runtime = runtime or LiveSearchRuntime()

    def quote_search(self, query: SearchQuery) -> OperationQuote:
        return OperationQuote(max_cost_usd=0.0)

    def search(self, query: SearchQuery) -> SearchProviderResponse:
        effective_limit = min(query.limit, self.runtime.max_results)
        try:
            payload = self.client.search(
                query.text,
                num_results=effective_limit,
                contents={"highlights": True, "text": True},
            )
        except SearchProviderError:
            raise
        except Exception as error:
            raise SearchProviderError(
                provider=self.name,
                category="search_error",
                message=str(error),
                secret_values=(self.credentials.api_key.get_secret_value(),),
            ) from error

        results, skipped_count = self._build_results(payload)
        source_ids = tuple(result.source_id for result in results)
        trace = OperationTrace.from_payload(
            request={
                "operation": "search",
                "provider": self.name,
                "provider_version": self.version,
                "search": {
                    "normalized_text": query.normalized_text,
                    "purpose": query.purpose.value,
                    "limit": query.limit,
                    "effective_limit": effective_limit,
                    "freshness_bucket": query.freshness_bucket,
                    "domain_hints": query.domain_hints,
                    "contents": {"highlights": True, "text": True},
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
        return SearchProviderResponse(
            query=query,
            provider_name=self.name,
            results=results,
            usage=MeteredSearchUsage(result_count=len(results), cost_usd=0.0),
            trace=trace,
        )

    @property
    def client(self) -> object:
        if self._client is None:
            self._client = self._build_default_client()
        return self._client

    def _build_default_client(self) -> object:
        api_key = self.credentials.api_key.get_secret_value()
        try:
            from exa_py import Exa  # type: ignore[import-not-found]
        except ImportError:
            try:
                from exa import Exa  # type: ignore[import-not-found]
            except ImportError as error:
                raise SearchProviderError(
                    provider=self.name,
                    category="configuration_error",
                    message=(
                        "Exa SDK is not installed; install exa_py or exa to use "
                        "live Exa search."
                    ),
                    secret_values=(api_key,),
                ) from error
        return Exa(api_key)

    def _build_results(self, payload: object) -> tuple[tuple[SearchResult, ...], int]:
        raw_results = _as_iterable(_read_field(payload, "results"))
        results: list[SearchResult] = []
        skipped_count = 0
        for item in raw_results:
            result = self._build_result(item=item, rank=len(results) + 1)
            if result is None:
                skipped_count += 1
                continue
            results.append(result)
        return tuple(results), skipped_count

    def _build_result(self, *, item: object, rank: int) -> SearchResult | None:
        title = _read_text(item, "title")
        url = _read_text(item, "url")
        if title is None or url is None:
            return None

        highlights = tuple(_iter_text_items(_read_field(item, "highlights")))
        summary = _read_text(item, "summary")
        text = _read_text(item, "text")
        snippet_source = _first_nonblank((*highlights, summary, text))
        excerpt_source = _first_nonblank((text, summary, snippet_source))
        if snippet_source is None or excerpt_source is None:
            return None

        try:
            return SearchResult(
                source_id=_source_id(url, title),
                title=title,
                url=url,
                provider=self.name,
                rank=rank,
                snippet=_bound(snippet_source, self.runtime.snippet_chars),
                bounded_excerpt=_bound(excerpt_source, self.runtime.snippet_chars),
                retrieved_at=datetime.now(UTC),
                provider_metadata={"source": self.name},
            )
        except (TypeError, ValueError, ValidationError):
            return None


def _read_field(value: object, field: str) -> object:
    if isinstance(value, Mapping):
        return value.get(field)
    return getattr(value, field, None)


def _read_text(value: object, field: str) -> str | None:
    raw = _read_field(value, field)
    if not isinstance(raw, str):
        return None
    stripped = raw.strip()
    return stripped or None


def _as_iterable(value: object) -> Iterable[object]:
    if isinstance(value, Iterable) and not isinstance(value, (str, bytes, Mapping)):
        return value
    return ()


def _iter_text_items(value: object) -> Iterable[str]:
    if isinstance(value, str):
        stripped = value.strip()
        if stripped:
            yield stripped
        return
    for item in _as_iterable(value):
        if isinstance(item, str):
            stripped = item.strip()
            if stripped:
                yield stripped


def _first_nonblank(values: Iterable[str | None]) -> str | None:
    for value in values:
        if value is None:
            continue
        stripped = value.strip()
        if stripped:
            return stripped
    return None


def _bound(value: str, limit: int) -> str:
    return value[:limit]


def _source_id(url: str, title: str) -> str:
    identity = url or title
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
    return f"exa-{digest}"
