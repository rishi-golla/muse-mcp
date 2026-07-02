from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from importlib import resources
from pathlib import Path

from pydantic import Field

from muse.live_config import LiveModelConfig, OpenAICredentials
from muse.models import FrozenModel
from muse.pricing import PricingTable

DEFAULT_PRICING_RESOURCE = "openai-pricing.example.json"


class LivePreflightStatus(StrEnum):
    OK = "ok"
    WARNING = "warning"
    ERROR = "error"


class LivePreflightCheck(FrozenModel):
    name: str
    status: LivePreflightStatus
    message: str


class LivePreflightReport(FrozenModel):
    status: LivePreflightStatus
    pricing_source: str | None = None
    checks: tuple[LivePreflightCheck, ...]
    action_items: tuple[str, ...] = ()
    redacted_environment: dict[str, str] = Field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status is LivePreflightStatus.OK

    def checks_by_name(self) -> dict[str, LivePreflightCheck]:
        return {check.name: check for check in self.checks}


def resolve_openai_pricing_table(
    environ: Mapping[str, str] | None = None,
) -> tuple[PricingTable, str]:
    values = _environment(environ)
    raw_path = values.get("OPENAI_PRICING_FILE")
    if raw_path and raw_path.strip():
        path = Path(raw_path.strip())
        return _load_pricing_file(path), str(path)
    payload = resources.files("muse").joinpath(DEFAULT_PRICING_RESOURCE).read_text(
        encoding="utf-8"
    )
    return (
        PricingTable.model_validate_json(payload),
        f"packaged:{DEFAULT_PRICING_RESOURCE}",
    )


def check_live_openai_environment(
    environ: Mapping[str, str] | None = None,
) -> LivePreflightReport:
    values = _environment(environ)
    checks: list[LivePreflightCheck] = []
    action_items: list[str] = []
    pricing_source: str | None = None

    try:
        OpenAICredentials.from_environment_mapping(values)
        checks.append(
            LivePreflightCheck(
                name="openai_api_key",
                status=LivePreflightStatus.OK,
                message="OPENAI_API_KEY is set",
            )
        )
    except ValueError as error:
        checks.append(
            LivePreflightCheck(
                name="openai_api_key",
                status=LivePreflightStatus.ERROR,
                message=str(error),
            )
        )
        action_items.append("Set OPENAI_API_KEY in the agent host environment.")

    config: LiveModelConfig | None = None
    try:
        config = LiveModelConfig.from_environment_mapping(values)
        checks.append(
            LivePreflightCheck(
                name="openai_models",
                status=LivePreflightStatus.OK,
                message="OpenAI model environment variables are valid",
            )
        )
    except ValueError as error:
        checks.append(
            LivePreflightCheck(
                name="openai_models",
                status=LivePreflightStatus.ERROR,
                message=str(error),
            )
        )
        action_items.append(
            "Set OPENAI_ECONOMY_MODEL and OPENAI_STRONG_MODEL to explicit model ids."
        )

    try:
        pricing, pricing_source = resolve_openai_pricing_table(values)
        checks.append(
            LivePreflightCheck(
                name="openai_pricing",
                status=LivePreflightStatus.OK,
                message=f"Pricing table loaded from {pricing_source}",
            )
        )
        if config is not None:
            _validate_pricing_coverage(config, pricing)
            checks.append(
                LivePreflightCheck(
                    name="pricing_coverage",
                    status=LivePreflightStatus.OK,
                    message="Pricing table covers selected models",
                )
            )
    except ValueError as error:
        checks.append(
            LivePreflightCheck(
                name="openai_pricing",
                status=LivePreflightStatus.ERROR,
                message=str(error),
            )
        )
        action_items.append(
            "Set OPENAI_PRICING_FILE to a valid pricing JSON file or use supported default models."
        )

    status = (
        LivePreflightStatus.ERROR
        if any(check.status is LivePreflightStatus.ERROR for check in checks)
        else LivePreflightStatus.OK
    )
    return LivePreflightReport(
        status=status,
        pricing_source=pricing_source,
        checks=tuple(checks),
        action_items=tuple(action_items),
        redacted_environment=_redacted_environment(values),
    )


def _load_pricing_file(path: Path) -> PricingTable:
    try:
        payload = path.read_text(encoding="utf-8")
    except OSError as error:
        raise ValueError(f"could not read pricing config {path}: {error}") from error
    try:
        return PricingTable.model_validate_json(payload)
    except ValueError as error:
        raise ValueError(f"invalid pricing config {path}: {error}") from error


def _validate_pricing_coverage(config: LiveModelConfig, pricing: PricingTable) -> None:
    try:
        pricing.text_price(config.economy_model)
        pricing.text_price(config.strong_model)
        pricing.embedding_price(config.embedding_model)
    except KeyError as error:
        raise ValueError(str(error).strip("'")) from error


def _environment(environ: Mapping[str, str] | None) -> Mapping[str, str]:
    if environ is not None:
        return environ
    import os

    return os.environ


def _redacted_environment(values: Mapping[str, str]) -> dict[str, str]:
    names = (
        "OPENAI_API_KEY",
        "OPENAI_ECONOMY_MODEL",
        "OPENAI_STRONG_MODEL",
        "OPENAI_EMBEDDING_MODEL",
        "OPENAI_PRICING_FILE",
        "MUSE_LIVE_SEARCH_APPROVED",
        "EXA_API_KEY",
        "BRAVE_SEARCH_API_KEY",
    )
    redacted: dict[str, str] = {}
    for name in names:
        value = values.get(name)
        redacted[name] = "set" if value and value.strip() else "missing"
    return redacted
