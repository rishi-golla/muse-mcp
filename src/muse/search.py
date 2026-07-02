from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol

from pydantic import AwareDatetime, Field, HttpUrl, computed_field, field_validator

from muse.models import FrozenModel, OperationTrace, RequiredText
from muse.providers import OperationQuote


class SearchPurpose(StrEnum):
    NOVELTY = "novelty"
    ANALOGY = "analogy"
    PRIOR_ART = "prior_art"
    EVIDENCE = "evidence"


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

    @field_validator("provider_metadata")
    @classmethod
    def require_safe_provider_metadata(
        cls,
        value: Mapping[str, object],
    ) -> Mapping[str, object]:
        _reject_unsafe_provider_metadata(value)
        return value

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


class MeteredSearchUsage(FrozenModel):
    result_count: int = Field(strict=True, ge=0)
    cost_usd: float = Field(default=0.0, strict=True, ge=0.0)


class SearchProviderResponse(FrozenModel):
    query: SearchQuery
    provider_name: RequiredText
    results: tuple[SearchResult, ...]
    usage: MeteredSearchUsage
    trace: OperationTrace | None = None


class SearchProvider(Protocol):
    name: str
    version: str

    def quote_search(self, query: SearchQuery) -> OperationQuote: ...

    def search(self, query: SearchQuery) -> SearchProviderResponse: ...


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
        default_factory=lambda: dict(DEFAULT_SEARCH_FIXTURES)
    )

    def quote_search(self, query: SearchQuery) -> OperationQuote:
        return OperationQuote(max_cost_usd=0.0)

    def search(self, query: SearchQuery) -> SearchProviderResponse:
        results = self._matching_results(query)[: query.limit]
        results = tuple(
            result if result.provider == self.name else result.model_copy(
                update={"provider": self.name}
            )
            for result in results
        )
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
        return SearchProviderResponse(
            query=query,
            provider_name=self.name,
            results=results,
            usage=MeteredSearchUsage(result_count=len(results), cost_usd=0.0),
            trace=trace,
        )

    def _matching_results(self, query: SearchQuery) -> tuple[SearchResult, ...]:
        exact_results = self.fixtures.get(query.normalized_text)
        if exact_results is not None:
            return exact_results

        quoted_phrase = _quoted_phrase(query.normalized_text)
        if quoted_phrase is None:
            return ()

        return tuple(
            result
            for fixture_results in self.fixtures.values()
            for result in fixture_results
            if _result_contains_phrase(result, quoted_phrase)
        )


def _normalize_search_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip()).casefold()


def _quoted_phrase(normalized_text: str) -> str | None:
    if len(normalized_text) < 3:
        return None
    if not (normalized_text.startswith('"') and normalized_text.endswith('"')):
        return None
    phrase = normalized_text[1:-1].strip()
    return phrase or None


def _result_contains_phrase(result: SearchResult, phrase: str) -> bool:
    haystack = " ".join(
        (
            result.title,
            result.snippet,
            result.bounded_excerpt,
        )
    )
    return phrase in _normalize_search_text(haystack)


SECRET_METADATA_KEYS = frozenset(
    {
        "auth",
        "authorization",
        "api_key",
        "apikey",
        "token",
        "secret",
        "password",
    }
)
SECRET_METADATA_VALUE = re.compile(r"(?:\bBearer\b|sk-)", re.IGNORECASE)


def _reject_unsafe_provider_metadata(value: object) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if _is_secret_metadata_key(str(key)):
                raise ValueError("provider metadata contains a secret-bearing key")
            _reject_unsafe_provider_metadata(item)
        _require_json_safe(value)
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            _reject_unsafe_provider_metadata(item)
        _require_json_safe(value)
        return
    if isinstance(value, str) and SECRET_METADATA_VALUE.search(value):
        raise ValueError("provider metadata contains an apparent secret value")
    _require_json_safe(value)


def _is_secret_metadata_key(key: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", "_", key.casefold()).strip("_")
    parts = normalized.split("_")
    compact = normalized.replace("_", "")
    return (
        normalized in SECRET_METADATA_KEYS
        or compact in SECRET_METADATA_KEYS
        or any(part in SECRET_METADATA_KEYS for part in parts)
    )


def _require_json_safe(value: object) -> None:
    try:
        json.dumps(value, allow_nan=False)
    except (TypeError, ValueError) as error:
        raise ValueError("provider metadata must be JSON-safe") from error
