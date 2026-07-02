import json
from math import inf, nan

import pytest
from pydantic import ValidationError

from muse.models import TokenUsage
from muse.pricing import (
    EmbeddingModelPricing,
    EmbeddingPrice,
    ModelPrice,
    PricingTable,
    TextModelPricing,
)


def test_pricing_table_calculates_cached_and_uncached_tokens_exactly() -> None:
    table = PricingTable(
        version="test-2026-06-23",
        models=(
            TextModelPricing(
                model="economy-test-model",
                price=ModelPrice(
                    input_per_million=1.00,
                    cached_input_per_million=0.10,
                    output_per_million=4.00,
                ),
            ),
        ),
    )
    usage = TokenUsage(
        input_tokens=1_000,
        cached_input_tokens=400,
        output_tokens=500,
        reasoning_tokens=100,
    )

    estimate = table.estimate("economy-test-model", usage)

    assert estimate.pricing_version == "test-2026-06-23"
    assert estimate.estimated_cost_usd == 0.00264
    assert estimate.is_estimated is True


def test_pricing_table_accepts_exact_plan_mapping_constructor() -> None:
    table = PricingTable(
        version="test-2026-06-23",
        models={
            "economy-test-model": ModelPrice(
                input_per_million=1.00,
                cached_input_per_million=0.10,
                output_per_million=4.00,
            )
        },
        embeddings={
            "embedding-test-model": EmbeddingPrice(input_per_million=0.02)
        },
    )

    assert isinstance(table.models, tuple)
    assert table.text_price("economy-test-model").output_per_million == 4.0
    assert table.embedding_price("embedding-test-model").input_per_million == 0.02


def test_pricing_table_config_dump_uses_stable_mapping_shape() -> None:
    table = PricingTable(
        version="test",
        models={
            "model": ModelPrice(
                input_per_million=1.0,
                cached_input_per_million=0.1,
                output_per_million=4.0,
            )
        },
        embeddings={
            "embedding": EmbeddingPrice(input_per_million=0.02),
        },
    )

    config = table.model_dump(mode="json")

    assert config == {
        "version": "test",
        "models": {
            "model": {
                "input_per_million": 1.0,
                "cached_input_per_million": 0.1,
                "output_per_million": 4.0,
            }
        },
        "embeddings": {
            "embedding": {
                "input_per_million": 0.02,
            }
        },
    }
    assert json.loads(table.model_dump_json()) == config
    assert PricingTable.model_validate(config) == table
    assert PricingTable.model_validate_json(table.model_dump_json()) == table


def test_reasoning_tokens_are_metadata_not_additional_billable_output() -> None:
    table = PricingTable(
        version="test",
        models=(
            TextModelPricing(
                model="model",
                price=ModelPrice(
                    input_per_million=0.0,
                    cached_input_per_million=0.0,
                    output_per_million=10.0,
                ),
            ),
        ),
    )

    estimate = table.estimate(
        "model",
        TokenUsage(output_tokens=1_000, reasoning_tokens=900),
    )

    assert estimate.estimated_cost_usd == 0.01


def test_embedding_pricing_is_exact() -> None:
    table = PricingTable(
        version="test",
        models=(),
        embeddings=(
            EmbeddingModelPricing(
                model="embedding-test-model",
                price=EmbeddingPrice(input_per_million=0.02),
            ),
        ),
    )

    estimate = table.estimate_embeddings("embedding-test-model", 12_345)

    assert estimate.estimated_cost_usd == 0.0002469
    assert estimate.pricing_version == "test"


def test_public_pricing_and_estimate_json_values_are_numbers() -> None:
    table = PricingTable(
        version="test",
        models=(
            TextModelPricing(
                model="economy-test-model",
                price=ModelPrice(
                    input_per_million=1.0,
                    cached_input_per_million=0.1,
                    output_per_million=4.0,
                ),
            ),
        ),
    )
    estimate = table.estimate(
        "economy-test-model",
        TokenUsage(input_tokens=1),
    )
    table_json = json.loads(table.model_dump_json())
    estimate_json = json.loads(estimate.model_dump_json())

    assert isinstance(
        table_json["models"]["economy-test-model"]["input_per_million"],
        float,
    )
    assert isinstance(estimate_json["estimated_cost_usd"], float)


def test_unknown_text_model_cannot_be_quoted() -> None:
    table = PricingTable(version="test", models=())

    with pytest.raises(
        KeyError,
        match="no pricing configured for model: missing",
    ):
        table.estimate("missing", TokenUsage())


def test_unknown_embedding_model_cannot_be_quoted() -> None:
    table = PricingTable(version="test", models=())

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
        models=(),
        embeddings=(
            EmbeddingModelPricing(
                model="embedding-test-model",
                price=EmbeddingPrice(input_per_million=0.02),
            ),
        ),
    )

    with pytest.raises(ValueError, match="non-negative integer"):
        table.estimate_embeddings(  # type: ignore[arg-type]
            "embedding-test-model",
            input_tokens,
        )


@pytest.mark.parametrize(
    "price",
    [-0.01, nan, inf],
)
def test_prices_must_be_finite_and_non_negative(price: float) -> None:
    with pytest.raises(ValidationError):
        ModelPrice(
            input_per_million=price,
            cached_input_per_million=0.0,
            output_per_million=0.0,
        )


def test_pricing_table_entries_are_deeply_immutable() -> None:
    table = PricingTable(
        version="test",
        models=(
            TextModelPricing(
                model="model",
                price=ModelPrice(
                    input_per_million=1.0,
                    cached_input_per_million=0.1,
                    output_per_million=4.0,
                ),
            ),
        ),
    )

    assert isinstance(table.models, tuple)
    with pytest.raises(ValidationError):
        table.models[0].price.input_per_million = 2.0


def test_duplicate_pricing_entries_are_rejected() -> None:
    entry = TextModelPricing(
        model="model",
        price=ModelPrice(
            input_per_million=1.0,
            cached_input_per_million=0.1,
            output_per_million=4.0,
        ),
    )

    with pytest.raises(ValidationError, match="duplicate text model pricing"):
        PricingTable(version="test", models=(entry, entry))
