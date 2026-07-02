from __future__ import annotations

import hashlib
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Protocol

from pydantic import ValidationError

from muse.live_search_config import (
    BraveSearchCredentials,
    LiveSearchRuntime,
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

BRAVE_WEB_SEARCH_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"


class BraveHttpResponse(Protocol):
    def raise_for_status(self) -> None: ...

    def json(self) -> object: ...


class BraveHttpClient(Protocol):
    def get(
        self,
        url: str,
        *,
        params: Mapping[str, object],
        headers: Mapping[str, str],
        timeout: float,
    ) -> BraveHttpResponse: ...


class BraveSearchProvider:
    name = "brave"
    version = "brave-search-v1"

    def __init__(
        self,
        *,
        credentials: BraveSearchCredentials,
        http_client: BraveHttpClient | None = None,
        runtime: LiveSearchRuntime | None = None,
    ) -> None:
        self.credentials = credentials
        self._http_client = http_client
        self.runtime = runtime or LiveSearchRuntime()

    def quote_search(self, query: SearchQuery) -> OperationQuote:
        return OperationQuote(max_cost_usd=0.0)

    def search(self, query: SearchQuery) -> SearchProviderResponse:
        effective_limit = min(query.limit, self.runtime.max_results)
        api_key = self.credentials.api_key.get_secret_value()
        try:
            response = self.http_client.get(
                BRAVE_WEB_SEARCH_ENDPOINT,
                params={
                    "q": query.text,
                    "count": effective_limit,
                    "search_lang": "en",
                },
                headers={"X-Subscription-Token": api_key},
                timeout=self.runtime.timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        except SearchProviderError:
            raise
        except Exception as error:
            provider_error = SearchProviderError(
                provider=self.name,
                category="search_error",
                message=str(error),
                secret_values=(api_key,),
            )
        else:
            provider_error = None

        if provider_error is not None:
            raise provider_error

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
    def http_client(self) -> BraveHttpClient:
        if self._http_client is None:
            self._http_client = self._build_default_client()
        return self._http_client

    def _build_default_client(self) -> BraveHttpClient:
        api_key = self.credentials.api_key.get_secret_value()
        try:
            import httpx
        except ImportError:
            provider_error = SearchProviderError(
                provider=self.name,
                category="configuration_error",
                message="httpx is not installed; install httpx to use live Brave search.",
                secret_values=(api_key,),
            )
        else:
            provider_error = None

        if provider_error is not None:
            raise provider_error
        return httpx.Client()

    def _build_results(self, payload: object) -> tuple[tuple[SearchResult, ...], int]:
        raw_results = _read_web_results(payload)
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
        if not isinstance(item, Mapping):
            return None
        title = _read_text(item, "title")
        url = _read_text(item, "url")
        snippet = _read_text(item, "description")
        if title is None or url is None or snippet is None:
            return None

        try:
            return SearchResult(
                source_id=_source_id(url, title),
                title=title,
                url=url,
                provider=self.name,
                rank=rank,
                snippet=_bound(snippet, self.runtime.snippet_chars),
                bounded_excerpt=_bound(snippet, self.runtime.snippet_chars),
                retrieved_at=datetime.now(UTC),
                provider_metadata={"source": self.name},
            )
        except (TypeError, ValueError, ValidationError):
            return None


def _read_web_results(payload: object) -> tuple[object, ...]:
    if not isinstance(payload, Mapping):
        return ()
    web = payload.get("web")
    if not isinstance(web, Mapping):
        return ()
    results = web.get("results")
    if not isinstance(results, list):
        return ()
    return tuple(results)


def _read_text(value: Mapping[object, object], field: str) -> str | None:
    raw = value.get(field)
    if not isinstance(raw, str):
        return None
    stripped = raw.strip()
    return stripped or None


def _bound(value: str, limit: int) -> str:
    return value[:limit]


def _source_id(url: str, title: str) -> str:
    identity = url or title
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
    return f"brave-{digest}"
