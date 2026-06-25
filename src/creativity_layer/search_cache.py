from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterable
from datetime import UTC, datetime

from pydantic import AwareDatetime, Field

from creativity_layer.models import FrozenModel, RequiredText
from creativity_layer.search import SearchQuery, SearchResult


class SearchCacheKey(FrozenModel):
    provider: RequiredText
    digest: str = Field(min_length=64, max_length=64)

    @classmethod
    def from_query(cls, provider: str, query: SearchQuery) -> SearchCacheKey:
        payload = {
            "provider": provider,
            "purpose": query.purpose.value,
            "normalized_text": query.normalized_text,
            "limit": query.limit,
            "freshness_bucket": query.freshness_bucket,
            "domain_hints": sorted(query.domain_hints),
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        return cls(provider=provider, digest=digest)


class SearchCacheHit(FrozenModel):
    results: tuple[SearchResult, ...]
    cached_at: AwareDatetime
    reused_at: AwareDatetime


class SearchCacheEntry(FrozenModel):
    results: tuple[SearchResult, ...]
    cached_at: AwareDatetime


class SearchCache:
    def __init__(self, now: Callable[[], datetime] | None = None) -> None:
        self._now = now or _utc_now
        self._entries: dict[SearchCacheKey, SearchCacheEntry] = {}

    def get(self, key: SearchCacheKey) -> SearchCacheHit | None:
        entry = self._entries.get(key)
        if entry is None:
            return None
        return SearchCacheHit(
            results=entry.results,
            cached_at=entry.cached_at,
            reused_at=self._now(),
        )

    def store(
        self,
        key: SearchCacheKey,
        results: Iterable[SearchResult],
    ) -> None:
        self._entries[key] = SearchCacheEntry(
            results=tuple(results),
            cached_at=self._now(),
        )


def _utc_now() -> datetime:
    return datetime.now(UTC)
