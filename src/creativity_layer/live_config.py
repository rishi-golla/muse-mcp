from __future__ import annotations

import os
from enum import StrEnum

from pydantic import Field, SecretStr

from creativity_layer.models import FrozenModel, RequiredText


class PrivacyMode(StrEnum):
    RESEARCH = "research"
    PRIVATE = "private"


class OpenAICredentials(FrozenModel):
    api_key: SecretStr

    @classmethod
    def from_environment(cls) -> OpenAICredentials:
        value = os.getenv("OPENAI_API_KEY")
        if not value:
            raise ValueError("OPENAI_API_KEY is required for live OpenAI runs")
        return cls(api_key=SecretStr(value))


class LiveModelConfig(FrozenModel):
    economy_model: RequiredText
    strong_model: RequiredText
    embedding_model: RequiredText = "text-embedding-3-small"
    default_budget_usd: float = Field(default=0.10, strict=True, gt=0)
    timeout_seconds: float = Field(default=30.0, strict=True, gt=0)
    max_retries: int = Field(default=2, strict=True, ge=0, le=5)
    repair_attempts: int = Field(default=1, strict=True, ge=0, le=2)
    circuit_failure_threshold: int = Field(default=3, strict=True, ge=1)
    privacy_mode: PrivacyMode = PrivacyMode.RESEARCH

    @classmethod
    def from_environment(cls) -> LiveModelConfig:
        economy = os.getenv("OPENAI_ECONOMY_MODEL")
        strong = os.getenv("OPENAI_STRONG_MODEL")
        if not economy or not strong:
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
