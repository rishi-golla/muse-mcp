from __future__ import annotations

import pytest

from creativity_layer.runtime_defaults import RuntimeDefaults


def test_runtime_defaults_are_live_first_when_environment_is_absent() -> None:
    defaults = RuntimeDefaults.from_environment({})

    assert defaults.provider_mode == "live_openai"
    assert defaults.effort == "quick"
    assert defaults.privacy == "research"
    assert defaults.budget_usd is None


def test_runtime_defaults_read_environment_overrides() -> None:
    defaults = RuntimeDefaults.from_environment(
        {
            "CREATIVITY_LAYER_PROVIDER_MODE": "deterministic",
            "CREATIVITY_LAYER_EFFORT": "standard",
            "CREATIVITY_LAYER_PRIVACY": "private",
            "CREATIVITY_LAYER_BUDGET_USD": "0.25",
        }
    )

    assert defaults.provider_mode == "deterministic"
    assert defaults.effort == "standard"
    assert defaults.privacy == "private"
    assert defaults.budget_usd == 0.25


def test_runtime_defaults_ignore_blank_environment_values() -> None:
    defaults = RuntimeDefaults.from_environment(
        {
            "CREATIVITY_LAYER_PROVIDER_MODE": " ",
            "CREATIVITY_LAYER_EFFORT": "",
            "CREATIVITY_LAYER_PRIVACY": "\t",
            "CREATIVITY_LAYER_BUDGET_USD": "",
        }
    )

    assert defaults.provider_mode == "live_openai"
    assert defaults.effort == "quick"
    assert defaults.privacy == "research"
    assert defaults.budget_usd is None


def test_runtime_defaults_reject_invalid_budget() -> None:
    with pytest.raises(ValueError, match="CREATIVITY_LAYER_BUDGET_USD"):
        RuntimeDefaults.from_environment({"CREATIVITY_LAYER_BUDGET_USD": "not-money"})


def test_runtime_defaults_explicit_budget_overrides_invalid_environment() -> None:
    defaults = RuntimeDefaults.resolve(
        provider_mode="deterministic",
        budget_usd=0.2,
        environ={"CREATIVITY_LAYER_BUDGET_USD": "not-money"},
    )

    assert defaults.provider_mode == "deterministic"
    assert defaults.budget_usd == 0.2
