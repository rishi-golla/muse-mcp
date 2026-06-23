from __future__ import annotations

from decimal import Decimal

from pydantic import Field, model_validator

from creativity_layer.models import CostEstimate, FrozenModel, RequiredText, TokenUsage

MILLION = Decimal(1_000_000)


class ModelPrice(FrozenModel):
    input_per_million: float = Field(strict=True, ge=0)
    cached_input_per_million: float = Field(strict=True, ge=0)
    output_per_million: float = Field(strict=True, ge=0)


class EmbeddingPrice(FrozenModel):
    input_per_million: float = Field(strict=True, ge=0)


class TextModelPricing(FrozenModel):
    model: RequiredText
    price: ModelPrice


class EmbeddingModelPricing(FrozenModel):
    model: RequiredText
    price: EmbeddingPrice


class PricingTable(FrozenModel):
    version: RequiredText
    models: tuple[TextModelPricing, ...]
    embeddings: tuple[EmbeddingModelPricing, ...] = ()

    @model_validator(mode="after")
    def reject_duplicate_models(self) -> PricingTable:
        text_models = tuple(entry.model for entry in self.models)
        if len(text_models) != len(set(text_models)):
            raise ValueError("duplicate text model pricing")
        embedding_models = tuple(entry.model for entry in self.embeddings)
        if len(embedding_models) != len(set(embedding_models)):
            raise ValueError("duplicate embedding model pricing")
        return self

    def text_price(self, model: str) -> ModelPrice:
        for entry in self.models:
            if entry.model == model:
                return entry.price
        raise KeyError(f"no pricing configured for model: {model}")

    def embedding_price(self, model: str) -> EmbeddingPrice:
        for entry in self.embeddings:
            if entry.model == model:
                return entry.price
        raise KeyError(f"no embedding pricing configured for model: {model}")

    def estimate(self, model: str, usage: TokenUsage) -> CostEstimate:
        price = self.text_price(model)
        cached = Decimal(usage.cached_input_tokens)
        uncached = Decimal(usage.input_tokens - usage.cached_input_tokens)
        output = Decimal(usage.output_tokens)
        cost = (
            uncached * Decimal(str(price.input_per_million))
            + cached * Decimal(str(price.cached_input_per_million))
            + output * Decimal(str(price.output_per_million))
        ) / MILLION
        return CostEstimate(
            estimated_cost_usd=float(cost),
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
        price = self.embedding_price(model)
        cost = (
            Decimal(input_tokens)
            * Decimal(str(price.input_per_million))
            / MILLION
        )
        return CostEstimate(
            estimated_cost_usd=float(cost),
            pricing_version=self.version,
        )
