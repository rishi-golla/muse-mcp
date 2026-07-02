from __future__ import annotations

from datetime import UTC, datetime, timedelta

from muse.search import SearchPurpose, SearchQuery, SearchResult
from muse.search_cache import SearchCache, SearchCacheKey


def _query(
    *,
    text: str = "  Reversible   Team Decisions  ",
    purpose: SearchPurpose = SearchPurpose.NOVELTY,
    limit: int = 3,
    freshness_bucket: str = "2026-06",
    domain_hints: tuple[str, ...] = ("papers.example", "docs.example"),
) -> SearchQuery:
    return SearchQuery(
        text=text,
        purpose=purpose,
        limit=limit,
        freshness_bucket=freshness_bucket,
        domain_hints=domain_hints,
    )


def _result(source_id: str = "src-1") -> SearchResult:
    return SearchResult(
        source_id=source_id,
        title="Decision gardens",
        url=f"https://example.com/{source_id}",
        provider="deterministic-search",
        rank=1,
        snippet="Teams use reversible claims.",
        bounded_excerpt="Teams use reversible claims.",
        retrieved_at=datetime(2026, 6, 25, tzinfo=UTC),
    )


def test_cache_key_is_stable_for_query_text_spacing_case_and_domain_hint_order() -> None:
    first = SearchCacheKey.from_query("deterministic-search", _query())
    second = SearchCacheKey.from_query(
        "deterministic-search",
        _query(
            text="reversible team decisions",
            domain_hints=("docs.example", "papers.example"),
        ),
    )

    assert first == second
    assert len(first.digest) == 64


def test_cache_key_differs_for_cache_identity_fields() -> None:
    base = SearchCacheKey.from_query("deterministic-search", _query())

    variants = (
        SearchCacheKey.from_query("other-search", _query()),
        SearchCacheKey.from_query(
            "deterministic-search",
            _query(purpose=SearchPurpose.PRIOR_ART),
        ),
        SearchCacheKey.from_query("deterministic-search", _query(limit=4)),
        SearchCacheKey.from_query(
            "deterministic-search",
            _query(freshness_bucket="2026-07"),
        ),
        SearchCacheKey.from_query(
            "deterministic-search",
            _query(domain_hints=("docs.example", "patents.example")),
        ),
    )

    assert {variant.digest for variant in variants}.isdisjoint({base.digest})


def test_cache_stores_tuple_copy_and_returns_hit_with_cached_and_reused_times() -> None:
    times = iter(
        (
            datetime(2026, 6, 25, 10, 0, tzinfo=UTC),
            datetime(2026, 6, 25, 10, 5, tzinfo=UTC),
        )
    )
    cache = SearchCache(now=lambda: next(times))
    key = SearchCacheKey.from_query("deterministic-search", _query())
    results = [_result("src-1")]

    cache.store(key, results)
    results.append(_result("src-2"))
    hit = cache.get(key)

    assert hit is not None
    assert hit.results == (_result("src-1"),)
    assert hit.cached_at == datetime(2026, 6, 25, 10, 0, tzinfo=UTC)
    assert hit.reused_at == datetime(2026, 6, 25, 10, 5, tzinfo=UTC)


def test_cache_returns_none_for_missing_key() -> None:
    cache = SearchCache(now=lambda: datetime.now(UTC) + timedelta(seconds=1))
    key = SearchCacheKey.from_query("deterministic-search", _query())

    assert cache.get(key) is None
