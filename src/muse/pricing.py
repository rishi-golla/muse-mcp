from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal

from pydantic import Field, model_serializer, model_validator

from muse.models import CostEstimate, FrozenModel, RequiredText, TokenUsage

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

    @model_validator(mode="before")
    @classmethod
    def canonicalize_mapping_config(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        payload = dict(value)
        models = payload.get("models")
        if isinstance(models, Mapping):
            payload["models"] = tuple(
                {"model": model, "price": price}
                for model, price in models.items()
            )
        embeddings = payload.get("embeddings")
        if isinstance(embeddings, Mapping):
            payload["embeddings"] = tuple(
                {"model": model, "price": price}
                for model, price in embeddings.items()
            )
        return payload

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

    def to_config_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "models": {
                entry.model: entry.price.model_dump(mode="json")
                for entry in self.models
            },
            "embeddings": {
                entry.model: entry.price.model_dump(mode="json")
                for entry in self.embeddings
            },
        }

    @model_serializer(mode="plain")
    def serialize_config_shape(self) -> dict[str, object]:
        return self.to_config_dict()

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
