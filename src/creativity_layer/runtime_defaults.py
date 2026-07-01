from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class RuntimeDefaults:
    provider_mode: str = "live_openai"
    effort: str = "quick"
    privacy: str = "research"
    budget_usd: float | None = None

    @classmethod
    def from_environment(
        cls,
        environ: Mapping[str, str] | None = None,
    ) -> RuntimeDefaults:
        values = os.environ if environ is None else environ
        return cls(
            provider_mode=_env_text(
                values,
                "CREATIVITY_LAYER_PROVIDER_MODE",
                "live_openai",
            ),
            effort=_env_text(values, "CREATIVITY_LAYER_EFFORT", "quick"),
            privacy=_env_text(values, "CREATIVITY_LAYER_PRIVACY", "research"),
            budget_usd=_env_float(values, "CREATIVITY_LAYER_BUDGET_USD"),
        )

    @classmethod
    def resolve(
        cls,
        *,
        provider_mode: str | None = None,
        effort: str | None = None,
        privacy: str | None = None,
        budget_usd: float | None = None,
        environ: Mapping[str, str] | None = None,
    ) -> RuntimeDefaults:
        values = os.environ if environ is None else environ
        return cls(
            provider_mode=provider_mode
            or _env_text(
                values,
                "CREATIVITY_LAYER_PROVIDER_MODE",
                "live_openai",
            ),
            effort=effort or _env_text(values, "CREATIVITY_LAYER_EFFORT", "quick"),
            privacy=privacy or _env_text(values, "CREATIVITY_LAYER_PRIVACY", "research"),
            budget_usd=budget_usd
            if budget_usd is not None
            else _env_float(values, "CREATIVITY_LAYER_BUDGET_USD"),
        )


def _env_text(values: Mapping[str, str], name: str, default: str) -> str:
    value = values.get(name)
    if value is None or not value.strip():
        return default
    return value.strip()


def _env_float(values: Mapping[str, str], name: str) -> float | None:
    value = values.get(name)
    if value is None or not value.strip():
        return None
    try:
        return float(value)
    except ValueError as error:
        raise ValueError(f"{name} must be a valid number") from error
