from __future__ import annotations

import json
import tomllib
from pathlib import Path

import pytest

from muse.mcp_smoke import run_smoke


@pytest.fixture(autouse=True)
def enable_internal_test_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MUSE_ENABLE_TEST_PROVIDER", "1")


def test_mcp_smoke_invokes_fastmcp_tool_and_prints_json(capsys) -> None:
    exit_code = run_smoke(
        [
            "Design a retry strategy for AI coding agents",
            "--provider-mode",
            "deterministic",
            "--repo-language",
            "Python",
            "--seed-count",
            "2",
            "--finalist-count",
            "1",
            "--generations",
            "0",
            "--budget-usd",
            "0.20",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["provider_mode"] == "deterministic"
    assert payload["config"]["mode"] == "normal"
    assert payload["config"]["effort"] == "standard"
    assert payload["finalist_count"] == 2
    assert payload["context_tags"] == ["python"]


def test_mcp_smoke_defaults_to_live_openai_when_provider_is_omitted(
    capsys,
    monkeypatch,
) -> None:
    for name in (
        "OPENAI_API_KEY",
        "OPENAI_ECONOMY_MODEL",
        "OPENAI_STRONG_MODEL",
        "OPENAI_PRICING_FILE",
        "MUSE_PROVIDER_MODE",
        "MUSE_ENABLE_TEST_PROVIDER",
    ):
        monkeypatch.delenv(name, raising=False)

    exit_code = run_smoke(
        [
            "Design a retry strategy for AI coding agents",
            "--repo-language",
            "Python",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert payload["provider_mode"] == "live_openai"
    assert payload["stopped_reason"] == "configuration_error"
    assert "OPENAI_API_KEY" in payload["errors"][0]["message"]


def test_mcp_smoke_forwards_effort_preset(capsys, monkeypatch) -> None:
    monkeypatch.setenv("MUSE_PROVIDER_MODE", "deterministic")

    exit_code = run_smoke(
        [
            "Design a retry strategy for AI coding agents",
            "--effort",
            "standard",
            "--repo-language",
            "Python",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["config"]["effort"] == "standard"
    assert payload["config"]["budget_usd"] == 0.35
    assert payload["config"]["seed_count"] == 4
    assert payload["config"]["finalist_count"] == 2


def test_mcp_smoke_uses_runtime_default_environment(capsys, monkeypatch) -> None:
    monkeypatch.setenv("MUSE_PROVIDER_MODE", "deterministic")
    monkeypatch.setenv("MUSE_MODE", "extensive")
    monkeypatch.setenv("MUSE_BUDGET_USD", "0.23")
    monkeypatch.setenv("MUSE_SEARCH_MODE", "light")

    exit_code = run_smoke(
        [
            "Design a retry strategy for AI coding agents",
            "--repo-language",
            "Python",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["provider_mode"] == "deterministic"
    assert payload["config"]["mode"] == "extensive"
    assert payload["config"]["effort"] == "deep"
    assert payload["config"]["budget_usd"] == 0.75
    assert payload["config"]["search_mode"] == "light"
    assert payload["search_context"]["skipped_reason"] == "approval_required"


def test_mcp_smoke_reports_invalid_runtime_default_environment(
    capsys,
    monkeypatch,
) -> None:
    monkeypatch.delenv("MUSE_PROVIDER_MODE", raising=False)
    monkeypatch.delenv("MUSE_ENABLE_TEST_PROVIDER", raising=False)
    monkeypatch.setenv("MUSE_BUDGET_USD", "not-money")

    exit_code = run_smoke(
        [
            "Design a retry strategy for AI coding agents",
            "--repo-language",
            "Python",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert payload["provider_mode"] == "live_openai"
    assert payload["stopped_reason"] == "configuration_error"
    assert "OPENAI_API_KEY" in payload["errors"][0]["message"]


def test_mcp_smoke_explicit_budget_overrides_invalid_runtime_default(
    capsys,
    monkeypatch,
) -> None:
    monkeypatch.setenv("MUSE_PROVIDER_MODE", "live_openai")
    monkeypatch.setenv("MUSE_BUDGET_USD", "not-money")

    exit_code = run_smoke(
        [
            "Design a retry strategy for AI coding agents",
            "--provider-mode",
            "deterministic",
            "--budget-usd",
            "0.20",
            "--repo-language",
            "Python",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["provider_mode"] == "deterministic"
    assert payload["config"]["budget_usd"] == 0.35
    assert payload["finalist_count"] == 2


def test_mcp_smoke_rejects_public_deterministic_provider(
    capsys,
    monkeypatch,
) -> None:
    monkeypatch.delenv("MUSE_ENABLE_TEST_PROVIDER", raising=False)

    exit_code = run_smoke(
        [
            "Design a retry strategy for AI coding agents",
            "--provider-mode",
            "deterministic",
            "--repo-language",
            "Python",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert payload["provider_mode"] == "deterministic"
    assert payload["stopped_reason"] == "configuration_error"
    assert "MUSE_ENABLE_TEST_PROVIDER" in payload["errors"][0]["message"]


def test_mcp_smoke_forwards_explicit_search_mode(capsys, monkeypatch) -> None:
    monkeypatch.setenv("MUSE_PROVIDER_MODE", "deterministic")
    monkeypatch.setenv("MUSE_SEARCH_MODE", "deep")

    exit_code = run_smoke(
        [
            "Design a retry strategy for AI coding agents",
            "--search-mode",
            "off",
            "--repo-language",
            "Python",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["config"]["search_mode"] == "off"
    assert payload["search_context"]["mode"] == "off"


def test_mcp_smoke_forwards_explicit_search_policy(capsys, monkeypatch) -> None:
    monkeypatch.setenv("MUSE_LIVE_SEARCH_APPROVED", "1")

    exit_code = run_smoke(
        [
            "reversible team decisions",
            "--provider-mode",
            "deterministic",
            "--search-mode",
            "light",
            "--search-provider",
            "deterministic",
            "--search-strict",
            "--repo-language",
            "Python",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["config"]["search_provider"] == "deterministic"
    assert payload["config"]["search_strict"] is True
    assert payload["search_context"]["strict"] is True
    assert payload["search_context"]["used"] is True


def test_package_exposes_mcp_smoke_console_script() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    assert pyproject["project"]["scripts"]["muse-mcp-smoke"] == (
        "muse.mcp_smoke:main"
    )
