from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

INTERNAL_TEST_PROVIDER_ENV = "MUSE_ENABLE_TEST_PROVIDER"
LIVE_PROVIDER_MODE = "live_openai"
TEST_PROVIDER_MODE = "deterministic"
DEFAULT_AGENT_MODE = "normal"


@dataclass(frozen=True)
class RuntimeDefaults:
    provider_mode: str = LIVE_PROVIDER_MODE
    mode: str = DEFAULT_AGENT_MODE
    effort: str = "quick"
    privacy: str = "research"
    budget_usd: float | None = None
    search_mode: str = "off"
    search_provider: str = "auto"
    search_strict: bool = False

    @classmethod
    def from_environment(
        cls,
        environ: Mapping[str, str] | None = None,
    ) -> RuntimeDefaults:
        values = os.environ if environ is None else environ
        return cls(
            provider_mode=_resolve_provider_mode(None, values),
            mode=_env_text(values, "MUSE_MODE", DEFAULT_AGENT_MODE),
            effort=_env_text(values, "MUSE_EFFORT", "quick"),
            privacy=_env_text(values, "MUSE_PRIVACY", "research"),
            budget_usd=None,
            search_mode=_env_text(values, "MUSE_SEARCH_MODE", "off"),
            search_provider=_env_text(
                values,
                "MUSE_SEARCH_PROVIDER",
                "auto",
            ),
            search_strict=_env_bool(
                values,
                "MUSE_SEARCH_STRICT",
                False,
            ),
        )

    @classmethod
    def resolve(
        cls,
        *,
        provider_mode: str | None = None,
        mode: str | None = None,
        effort: str | None = None,
        privacy: str | None = None,
        budget_usd: float | None = None,
        search_mode: str | None = None,
        search_provider: str | None = None,
        search_strict: bool | None = None,
        environ: Mapping[str, str] | None = None,
    ) -> RuntimeDefaults:
        values = os.environ if environ is None else environ
        return cls(
            provider_mode=_resolve_provider_mode(provider_mode, values),
            mode=mode or _env_text(values, "MUSE_MODE", DEFAULT_AGENT_MODE),
            effort=effort or _env_text(values, "MUSE_EFFORT", "quick"),
            privacy=privacy or _env_text(values, "MUSE_PRIVACY", "research"),
            budget_usd=budget_usd,
            search_mode=search_mode
            or _env_text(values, "MUSE_SEARCH_MODE", "off"),
            search_provider=search_provider
            or _env_text(values, "MUSE_SEARCH_PROVIDER", "auto"),
            search_strict=search_strict
            if search_strict is not None
            else _env_bool(values, "MUSE_SEARCH_STRICT", False),
        )


def _env_text(values: Mapping[str, str], name: str, default: str) -> str:
    value = values.get(name)
    if value is None or not value.strip():
        return default
    return value.strip()


def _resolve_provider_mode(
    requested: str | None,
    values: Mapping[str, str],
) -> str:
    provider_mode = requested or _env_text(
        values,
        "MUSE_PROVIDER_MODE",
        LIVE_PROVIDER_MODE,
    )
    if provider_mode == TEST_PROVIDER_MODE and not _env_bool(
        values,
        INTERNAL_TEST_PROVIDER_ENV,
        False,
    ):
        raise ValueError(
            "deterministic provider is internal-only for tests; "
            f"set {INTERNAL_TEST_PROVIDER_ENV}=1 to use it"
        )
    return provider_mode


def _env_float(values: Mapping[str, str], name: str) -> float | None:
    value = values.get(name)
    if value is None or not value.strip():
        return None
    try:
        return float(value)
    except ValueError as error:
        raise ValueError(f"{name} must be a valid number") from error


def _env_bool(values: Mapping[str, str], name: str, default: bool) -> bool:
    value = values.get(name)
    if value is None or not value.strip():
        return default
    normalized = value.strip().casefold()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean")
