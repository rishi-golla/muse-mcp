from __future__ import annotations

import os
import unicodedata
from enum import StrEnum
from typing import Annotated

from pydantic import AfterValidator, Field, SecretStr

from muse.models import FrozenModel


def reject_invalid_model_identifier(value: str) -> str:
    if any(character.isspace() for character in value):
        raise ValueError("model identifier must not contain whitespace")
    if any(unicodedata.category(character).startswith("C") for character in value):
        raise ValueError("model identifier must not contain unsafe Unicode characters")
    return value


ModelIdentifier = Annotated[
    str,
    Field(min_length=1),
    AfterValidator(reject_invalid_model_identifier),
]


class PrivacyMode(StrEnum):
    RESEARCH = "research"
    PRIVATE = "private"


class OpenAICredentials(FrozenModel):
    api_key: SecretStr

    @classmethod
    def from_environment(cls) -> OpenAICredentials:
        value = os.getenv("OPENAI_API_KEY")
        if not value or not value.strip():
            raise ValueError("OPENAI_API_KEY is required for live OpenAI runs")
        return cls(api_key=SecretStr(value.strip()))


class LiveModelConfig(FrozenModel):
    economy_model: ModelIdentifier
    strong_model: ModelIdentifier
    embedding_model: ModelIdentifier = "text-embedding-3-small"
    default_budget_usd: float = Field(default=0.10, strict=True, gt=0)
    timeout_seconds: float = Field(default=30.0, strict=True, gt=0)
    max_retries: int = Field(default=2, strict=True, ge=0, le=5)
    repair_attempts: int = Field(default=1, strict=True, ge=0, le=2)
    circuit_failure_threshold: int = Field(default=3, strict=True, ge=1)
    privacy_mode: PrivacyMode = PrivacyMode.RESEARCH
    frame_max_input_tokens: int = Field(default=2_000, strict=True, ge=1)
    frame_max_output_tokens: int = Field(default=800, strict=True, ge=1)
    seed_max_input_tokens: int = Field(default=3_000, strict=True, ge=1)
    seed_max_output_tokens: int = Field(default=2_500, strict=True, ge=1)
    transform_max_input_tokens: int = Field(default=3_000, strict=True, ge=1)
    transform_max_output_tokens: int = Field(default=1_500, strict=True, ge=1)
    evaluation_max_input_tokens: int = Field(default=3_000, strict=True, ge=1)
    evaluation_max_output_tokens: int = Field(default=800, strict=True, ge=1)
    embedding_max_input_tokens: int = Field(default=8_000, strict=True, ge=1)

    @classmethod
    def from_environment(cls) -> LiveModelConfig:
        economy = os.getenv("OPENAI_ECONOMY_MODEL")
        strong = os.getenv("OPENAI_STRONG_MODEL")
        if not economy or not economy.strip() or not strong or not strong.strip():
            raise ValueError(
                "OPENAI_ECONOMY_MODEL and OPENAI_STRONG_MODEL are required"
            )
        return cls(
            economy_model=economy,
            strong_model=strong,
            embedding_model=os.getenv(
                "OPENAI_EMBEDDING_MODEL",
                "text-embedding-3-small",
            ),
        )
