from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol

from pydantic import AwareDatetime, Field, HttpUrl, computed_field

from creativity_layer.models import FrozenModel, OperationTrace, RequiredText
from creativity_layer.providers import MeteredResponse, OperationQuote


class SearchPurpose(StrEnum):
    INSPIRATION = "inspiration"
    PRIOR_ART = "prior_art"


class SearchQuery(FrozenModel):
    text: RequiredText
    purpose: SearchPurpose
    limit: int = Field(strict=True, ge=1, le=10)
    freshness_bucket: RequiredText = "static"
    domain_hints: tuple[str, ...] = ()

    @computed_field
    @property
    def normalized_text(self) -> str:
        return _normalize_search_text(self.text)


class SearchResult(FrozenModel):
    source_id: RequiredText
    title: RequiredText
    url: HttpUrl
    provider: RequiredText
    rank: int = Field(strict=True, ge=1)
    snippet: RequiredText
    bounded_excerpt: RequiredText
    retrieved_at: AwareDatetime
    provider_metadata: Mapping[str, object] = Field(default_factory=dict)

    @computed_field
    @property
    def content_hash(self) -> str:
        payload = {
            "bounded_excerpt": self.bounded_excerpt,
            "snippet": self.snippet,
            "title": self.title,
            "url": str(self.url),
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class SearchProvider(Protocol):
    name: str
    version: str

    def quote_search(self, query: SearchQuery) -> OperationQuote: ...

    def search(self, query: SearchQuery) -> MeteredResponse[tuple[SearchResult, ...]]: ...


DEFAULT_SEARCH_FIXTURES: Mapping[str, tuple[SearchResult, ...]] = {
    "reversible team decisions": (
        SearchResult(
            source_id="src-1",
            title="Decision gardens",
            url="https://example.com/decision-gardens",
            provider="deterministic-search",
            rank=1,
            snippet="Teams use reversible claims.",
            bounded_excerpt="Teams use reversible claims.",
            retrieved_at=datetime(2026, 6, 25, tzinfo=UTC),
        ),
    )
}


class DeterministicSearchProvider(FrozenModel):
    name: RequiredText = "deterministic-search"
    version: RequiredText = "fixtures-v1"
    fixtures: Mapping[str, tuple[SearchResult, ...]] = Field(
        default_factory=lambda: DEFAULT_SEARCH_FIXTURES
    )

    def quote_search(self, query: SearchQuery) -> OperationQuote:
        return OperationQuote(max_cost_usd=0.0)

    def search(self, query: SearchQuery) -> MeteredResponse[tuple[SearchResult, ...]]:
        results = self.fixtures.get(query.normalized_text, ())[: query.limit]
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
                    "freshness_bucket": query.freshness_bucket,
                    "domain_hints": query.domain_hints,
                },
            },
            response={
                "operation": "search",
                "provider": self.name,
                "source_ids": source_ids,
                "result_count": len(results),
            },
        )
        return MeteredResponse(
            value=results,
            provider=self.name,
            model=self.version,
            cost_usd=0.0,
            latency_ms=0,
            operation_trace=trace,
        )


def _normalize_search_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip()).casefold()
