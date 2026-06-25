from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from creativity_layer.search import (
    DeterministicSearchProvider,
    SearchPurpose,
    SearchQuery,
    SearchResult,
)


def test_search_query_normalizes_text_and_rejects_blank() -> None:
    query = SearchQuery(
        text="  Reversible team decisions  ",
        purpose=SearchPurpose.INSPIRATION,
        limit=3,
        freshness_bucket="2026-06",
    )

    assert query.normalized_text == "reversible team decisions"

    with pytest.raises(ValidationError):
        SearchQuery(
            text=" ",
            purpose=SearchPurpose.INSPIRATION,
            limit=3,
            freshness_bucket="2026-06",
        )


def test_search_result_records_stable_content_hash_without_secrets() -> None:
    result = SearchResult(
        source_id="src-1",
        title="Decision gardens",
        url="https://example.com/decision-gardens",
        provider="deterministic-search",
        rank=1,
        snippet="Teams use reversible claims.",
        bounded_excerpt="Teams use reversible claims.",
        retrieved_at=datetime(2026, 6, 25, tzinfo=UTC),
    )

    assert result.content_hash
    assert result.content_hash != "Teams use reversible claims."


def test_deterministic_search_provider_quotes_and_returns_metered_results() -> None:
    provider = DeterministicSearchProvider(
        fixtures={
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
    )
    query = SearchQuery(
        text="Reversible team decisions",
        purpose=SearchPurpose.INSPIRATION,
        limit=2,
        freshness_bucket="2026-06",
    )

    quote = provider.quote_search(query)
    response = provider.search(query)

    assert quote.max_cost_usd == 0.0
    assert response.provider == "deterministic-search"
    assert response.cost_usd == 0.0
    assert response.value == provider.fixtures["reversible team decisions"]
