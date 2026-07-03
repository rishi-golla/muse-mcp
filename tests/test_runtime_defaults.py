from __future__ import annotations

import pytest

from muse.runtime_defaults import RuntimeDefaults


def test_runtime_defaults_are_live_first_when_environment_is_absent() -> None:
    defaults = RuntimeDefaults.from_environment({})

    assert defaults.provider_mode == "live_openai"
    assert defaults.mode == "normal"
    assert defaults.effort == "quick"
    assert defaults.privacy == "research"
    assert defaults.budget_usd is None


def test_runtime_defaults_read_environment_overrides() -> None:
    defaults = RuntimeDefaults.from_environment(
        {
            "MUSE_PROVIDER_MODE": "live_openai",
            "MUSE_MODE": "extensive",
            "MUSE_EFFORT": "standard",
            "MUSE_PRIVACY": "private",
            "MUSE_BUDGET_USD": "0.25",
            "MUSE_SEARCH_MODE": "light",
            "MUSE_SEARCH_PROVIDER": "brave",
            "MUSE_SEARCH_STRICT": "true",
        }
    )

    assert defaults.provider_mode == "live_openai"
    assert defaults.mode == "extensive"
    assert defaults.effort == "standard"
    assert defaults.privacy == "private"
    assert defaults.budget_usd is None
    assert defaults.search_mode == "light"
    assert defaults.search_provider == "brave"
    assert defaults.search_strict is True


def test_runtime_defaults_ignore_blank_environment_values() -> None:
    defaults = RuntimeDefaults.from_environment(
        {
            "MUSE_PROVIDER_MODE": " ",
            "MUSE_EFFORT": "",
            "MUSE_PRIVACY": "\t",
            "MUSE_BUDGET_USD": "",
        }
    )

    assert defaults.provider_mode == "live_openai"
    assert defaults.effort == "quick"
    assert defaults.privacy == "research"
    assert defaults.budget_usd is None


def test_runtime_defaults_ignore_public_budget_environment() -> None:
    defaults = RuntimeDefaults.from_environment({"MUSE_BUDGET_USD": "not-money"})

    assert defaults.budget_usd is None


def test_runtime_defaults_explicit_budget_overrides_invalid_environment() -> None:
    defaults = RuntimeDefaults.resolve(
        provider_mode="live_openai",
        budget_usd=0.2,
        environ={"MUSE_BUDGET_USD": "not-money"},
    )

    assert defaults.provider_mode == "live_openai"
    assert defaults.budget_usd == 0.2


def test_runtime_defaults_explicit_search_mode_overrides_environment() -> None:
    defaults = RuntimeDefaults.resolve(
        search_mode="deep",
        environ={"MUSE_SEARCH_MODE": "light"},
    )

    assert defaults.search_mode == "deep"


def test_runtime_defaults_explicit_search_policy_overrides_environment() -> None:
    defaults = RuntimeDefaults.resolve(
        search_provider="exa",
        search_strict=False,
        environ={
            "MUSE_SEARCH_PROVIDER": "brave",
            "MUSE_SEARCH_STRICT": "true",
        },
    )

    assert defaults.search_provider == "exa"
    assert defaults.search_strict is False


def test_runtime_defaults_reject_invalid_search_strict() -> None:
    with pytest.raises(ValueError, match="MUSE_SEARCH_STRICT"):
        RuntimeDefaults.from_environment({"MUSE_SEARCH_STRICT": "maybe"})


def test_runtime_defaults_reject_public_deterministic_provider() -> None:
    with pytest.raises(ValueError, match="MUSE_ENABLE_TEST_PROVIDER"):
        RuntimeDefaults.resolve(
            provider_mode="deterministic",
            environ={},
        )


def test_runtime_defaults_reject_environment_deterministic_provider() -> None:
    with pytest.raises(ValueError, match="MUSE_ENABLE_TEST_PROVIDER"):
        RuntimeDefaults.from_environment(
            {
                "MUSE_PROVIDER_MODE": "deterministic",
            }
        )


def test_runtime_defaults_allow_internal_test_provider_when_enabled() -> None:
    defaults = RuntimeDefaults.resolve(
        provider_mode="deterministic",
        environ={"MUSE_ENABLE_TEST_PROVIDER": "1"},
    )

    assert defaults.provider_mode == "deterministic"
