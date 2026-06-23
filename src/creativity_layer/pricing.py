from __future__ import annotations

from decimal import Decimal

from pydantic import Field, model_validator

from creativity_layer.models import CostEstimate, FrozenModel, RequiredText, TokenUsage

MILLION = Decimal(1_000_000)


class ModelPrice(FrozenModel):
    input_per_million: Decimal = Field(ge=0)
    cached_input_per_million: Decimal = Field(ge=0)
    output_per_million: Decimal = Field(ge=0)


class EmbeddingPrice(FrozenModel):
    input_per_million: Decimal = Field(ge=0)


class PricingTable(FrozenModel):
    version: RequiredText
    models: dict[str, ModelPrice]
    embeddings: dict[str, EmbeddingPrice] = Field(default_factory=dict)

    @model_validator(mode="after")
    def reject_blank_model_names(self) -> PricingTable:
        if any(not model.strip() for model in (*self.models, *self.embeddings)):
            raise ValueError("pricing model names must not be blank")
        return self

    def estimate(self, model: str, usage: TokenUsage) -> CostEstimate:
        if model not in self.models:
            raise KeyError(f"no pricing configured for model: {model}")
        price = self.models[model]
        cached = Decimal(usage.cached_input_tokens)
        uncached = Decimal(usage.input_tokens - usage.cached_input_tokens)
        output = Decimal(usage.output_tokens + usage.reasoning_tokens)
        cost = (
            uncached * price.input_per_million
            + cached * price.cached_input_per_million
            + output * price.output_per_million
        ) / MILLION
        return CostEstimate(
            estimated_cost_usd=cost,
            pricing_version=self.version,
        )

    def estimate_embeddings(
        self,
        model: str,
        input_tokens: int,
    ) -> CostEstimate:
        if (
            isinstance(input_tokens, bool)
            or not isinstance(input_tokens, int)
            or input_tokens < 0
        ):
            raise ValueError("input_tokens must be a non-negative integer")
        if model not in self.embeddings:
            raise KeyError(f"no embedding pricing configured for model: {model}")
        price = self.embeddings[model]
        cost = Decimal(input_tokens) * price.input_per_million / MILLION
        return CostEstimate(
            estimated_cost_usd=cost,
            pricing_version=self.version,
        )
