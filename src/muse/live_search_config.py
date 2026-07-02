from __future__ import annotations

import os

from pydantic import Field, SecretStr

from muse.models import FrozenModel, RequiredText
from muse.privacy import REDACTED


class ExaSearchCredentials(FrozenModel):
    api_key: SecretStr

    @classmethod
    def from_environment(cls) -> ExaSearchCredentials:
        return cls(api_key=_secret_from_env("EXA_API_KEY"))


class BraveSearchCredentials(FrozenModel):
    api_key: SecretStr

    @classmethod
    def from_environment(cls) -> BraveSearchCredentials:
        return cls(api_key=_secret_from_env("BRAVE_SEARCH_API_KEY"))


class OpenAIWebSearchConfig(FrozenModel):
    model: RequiredText

    @classmethod
    def from_environment(cls) -> OpenAIWebSearchConfig:
        value = os.getenv("OPENAI_WEB_SEARCH_MODEL")
        if value is None or not value.strip():
            raise ValueError("OPENAI_WEB_SEARCH_MODEL is required")
        return cls(model=value.strip())


class LiveSearchRuntime(FrozenModel):
    timeout_seconds: float = Field(default=10.0, strict=True, gt=0, le=30.0)
    max_results: int = Field(default=10, strict=True, ge=1, le=10)
    snippet_chars: int = Field(default=500, strict=True, ge=80, le=2000)


class SearchProviderError(RuntimeError):
    def __init__(
        self,
        *,
        provider: str,
        category: str,
        message: str,
        secret_values: tuple[str, ...] = (),
    ) -> None:
        sanitized = message
        for secret in sorted(
            (item for item in secret_values if item),
            key=len,
            reverse=True,
        ):
            sanitized = sanitized.replace(secret, REDACTED)

        self.provider = provider
        self.category = category
        self.message = sanitized
        self.redacted_secret_count = sum(1 for item in secret_values if item)
        super().__init__(f"{provider} {category}: {sanitized}")


def _secret_from_env(name: str) -> SecretStr:
    value = os.getenv(name)
    if value is None or not value.strip():
        raise ValueError(f"{name} is required")
    return SecretStr(value.strip())
