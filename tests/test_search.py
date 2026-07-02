from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

import muse.search as search_module
from muse.search import (
    DeterministicSearchProvider,
    SearchPurpose,
    SearchQuery,
    SearchResult,
)


def _search_result(
    *,
    source_id: str = "src-1",
    title: str = "Decision gardens",
    provider: str = "deterministic-search",
    rank: int = 1,
    snippet: str = "Teams use reversible claims.",
    bounded_excerpt: str = "Teams use reversible claims.",
) -> SearchResult:
    return SearchResult(
        source_id=source_id,
        title=title,
        url=f"https://example.com/{source_id}",
        provider=provider,
        rank=rank,
        snippet=snippet,
        bounded_excerpt=bounded_excerpt,
        retrieved_at=datetime(2026, 6, 25, tzinfo=UTC),
    )


def test_search_purpose_exposes_2b_contract_values() -> None:
    assert {purpose.value for purpose in SearchPurpose} == {
        "novelty",
        "analogy",
        "prior_art",
        "evidence",
    }


def test_search_query_normalizes_text_and_rejects_blank() -> None:
    query = SearchQuery(
        text="  Reversible   team    decisions  ",
        purpose=SearchPurpose.NOVELTY,
        limit=3,
        freshness_bucket="2026-06",
    )

    assert query.normalized_text == "reversible team decisions"

    with pytest.raises(ValidationError):
        SearchQuery(
            text=" ",
            purpose=SearchPurpose.NOVELTY,
            limit=3,
            freshness_bucket="2026-06",
        )


@pytest.mark.parametrize("limit", [0, 11, "2"])
def test_search_query_rejects_non_strict_or_out_of_bounds_limits(limit: object) -> None:
    with pytest.raises(ValidationError):
        SearchQuery(
            text="reversible team decisions",
            purpose=SearchPurpose.NOVELTY,
            limit=limit,
            freshness_bucket="2026-06",
        )


def test_search_result_records_stable_content_hash_without_secrets() -> None:
    result = _search_result()

    assert result.content_hash
    assert result.content_hash != "Teams use reversible claims."


def test_search_result_rejects_naive_retrieved_at() -> None:
    with pytest.raises(ValidationError):
        SearchResult(
            source_id="src-1",
            title="Decision gardens",
            url="https://example.com/decision-gardens",
            provider="deterministic-search",
            rank=1,
            snippet="Teams use reversible claims.",
            bounded_excerpt="Teams use reversible claims.",
            retrieved_at=datetime(2026, 6, 25),
        )


@pytest.mark.parametrize(
    "provider_metadata",
    [
        {"api_key": "redacted"},
        {"access_token": "redacted"},
        {"headers": {"authorization": "redacted"}},
        {"note": "Bearer abc123"},
        {"note": "sk-1234567890"},
        {"raw": object()},
    ],
)
def test_search_result_rejects_unsafe_provider_metadata(
    provider_metadata: object,
) -> None:
    with pytest.raises(ValidationError):
        SearchResult(
            source_id="src-1",
            title="Decision gardens",
            url="https://example.com/decision-gardens",
            provider="deterministic-search",
            rank=1,
            snippet="Teams use reversible claims.",
            bounded_excerpt="Teams use reversible claims.",
            retrieved_at=datetime(2026, 6, 25, tzinfo=UTC),
            provider_metadata=provider_metadata,
        )


def test_deterministic_search_provider_quotes_and_returns_search_response() -> None:
    provider = DeterministicSearchProvider(
        fixtures={
            "reversible team decisions": (
                _search_result(),
            )
        }
    )
    query = SearchQuery(
        text="Reversible team decisions",
        purpose=SearchPurpose.NOVELTY,
        limit=2,
        freshness_bucket="2026-06",
    )

    quote = provider.quote_search(query)
    response = provider.search(query)

    assert quote.max_cost_usd == 0.0
    assert hasattr(search_module, "SearchProviderResponse")
    assert isinstance(response, search_module.SearchProviderResponse)
    assert response.query == query
    assert response.provider_name == "deterministic-search"
    assert response.results == provider.fixtures["reversible team decisions"]
    assert hasattr(search_module, "MeteredSearchUsage")
    assert response.usage == search_module.MeteredSearchUsage(
        result_count=1,
        cost_usd=0.0,
    )
    assert response.trace is not None


def test_deterministic_search_provider_instances_do_not_share_fixture_mapping() -> None:
    first = DeterministicSearchProvider()
    second = DeterministicSearchProvider()

    assert first.fixtures is not second.fixtures


def test_deterministic_search_provider_prevents_fixture_provider_spoofing() -> None:
    provider = DeterministicSearchProvider(
        fixtures={
            "reversible team decisions": (
                _search_result(provider="spoofed-provider"),
            )
        }
    )
    query = SearchQuery(
        text="Reversible team decisions",
        purpose=SearchPurpose.NOVELTY,
        limit=2,
        freshness_bucket="2026-06",
    )

    response = provider.search(query)

    assert response.results[0].provider == provider.name


def test_deterministic_search_provider_supports_quoted_substring_matching() -> None:
    provider = DeterministicSearchProvider(
        fixtures={
            "unrelated key": (
                _search_result(snippet="Teams use Reversible Claims when stakes shift."),
            )
        }
    )
    query = SearchQuery(
        text='"reversible claims"',
        purpose=SearchPurpose.EVIDENCE,
        limit=2,
        freshness_bucket="2026-06",
    )

    response = provider.search(query)

    assert tuple(result.source_id for result in response.results) == ("src-1",)
