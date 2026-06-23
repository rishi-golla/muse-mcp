from decimal import Decimal

import pytest
from pydantic import ValidationError

from creativity_layer.models import TokenUsage
from creativity_layer.pricing import EmbeddingPrice, ModelPrice, PricingTable


def test_pricing_table_calculates_cached_and_uncached_tokens_exactly() -> None:
    table = PricingTable(
        version="test-2026-06-23",
        models={
            "economy-test-model": ModelPrice(
                input_per_million=Decimal("1.00"),
                cached_input_per_million=Decimal("0.10"),
                output_per_million=Decimal("4.00"),
            )
        },
    )
    usage = TokenUsage(
        input_tokens=1_000,
        cached_input_tokens=400,
        output_tokens=500,
        reasoning_tokens=100,
    )

    estimate = table.estimate("economy-test-model", usage)

    assert estimate.pricing_version == "test-2026-06-23"
    assert estimate.estimated_cost_usd == Decimal("0.00304")
    assert estimate.is_estimated is True


def test_embedding_pricing_is_exact() -> None:
    table = PricingTable(
        version="test",
        models={},
        embeddings={
            "embedding-test-model": EmbeddingPrice(
                input_per_million=Decimal("0.02")
            )
        },
    )

    estimate = table.estimate_embeddings("embedding-test-model", 12_345)

    assert estimate.estimated_cost_usd == Decimal("0.0002469")
    assert estimate.pricing_version == "test"


def test_pricing_models_accept_json_numeric_values() -> None:
    table = PricingTable.model_validate(
        {
            "version": "test",
            "models": {
                "economy-test-model": {
                    "input_per_million": 1.0,
                    "cached_input_per_million": 0.1,
                    "output_per_million": 4.0,
                }
            },
            "embeddings": {
                "embedding-test-model": {
                    "input_per_million": 0.02,
                }
            },
        }
    )

    assert table.models["economy-test-model"].input_per_million == Decimal("1.0")
    assert table.embeddings["embedding-test-model"].input_per_million == Decimal(
        "0.02"
    )


def test_unknown_text_model_cannot_be_quoted() -> None:
    table = PricingTable(version="test", models={})

    with pytest.raises(
        KeyError,
        match="no pricing configured for model: missing",
    ):
        table.estimate("missing", TokenUsage())


def test_unknown_embedding_model_cannot_be_quoted() -> None:
    table = PricingTable(version="test", models={})

    with pytest.raises(
        KeyError,
        match="no embedding pricing configured for model: missing",
    ):
        table.estimate_embeddings("missing", 1)


def test_cached_tokens_cannot_exceed_total_input_tokens() -> None:
    with pytest.raises(ValidationError):
        TokenUsage(input_tokens=10, cached_input_tokens=11)


@pytest.mark.parametrize("input_tokens", [-1, True, 1.5])
def test_embedding_token_count_must_be_a_non_negative_integer(
    input_tokens: object,
) -> None:
    table = PricingTable(
        version="test",
        models={},
        embeddings={
            "embedding-test-model": EmbeddingPrice(
                input_per_million=Decimal("0.02")
            )
        },
    )

    with pytest.raises(ValueError, match="non-negative integer"):
        table.estimate_embeddings(  # type: ignore[arg-type]
            "embedding-test-model",
            input_tokens,
        )


@pytest.mark.parametrize(
    "price",
    [Decimal("-0.01"), Decimal("NaN"), Decimal("Infinity")],
)
def test_prices_must_be_finite_and_non_negative(price: Decimal) -> None:
    with pytest.raises(ValidationError):
        ModelPrice(
            input_per_million=price,
            cached_input_per_million=Decimal("0"),
            output_per_million=Decimal("0"),
        )
