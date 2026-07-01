from __future__ import annotations

import json
import tomllib
from pathlib import Path

from creativity_layer.mcp_smoke import run_smoke


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
    assert payload["config"]["effort"] == "quick"
    assert payload["finalist_count"] == 1
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
        "CREATIVITY_LAYER_PROVIDER_MODE",
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
    monkeypatch.setenv("CREATIVITY_LAYER_PROVIDER_MODE", "deterministic")

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
    monkeypatch.setenv("CREATIVITY_LAYER_PROVIDER_MODE", "deterministic")
    monkeypatch.setenv("CREATIVITY_LAYER_EFFORT", "standard")
    monkeypatch.setenv("CREATIVITY_LAYER_BUDGET_USD", "0.23")

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
    assert payload["config"]["effort"] == "standard"
    assert payload["config"]["budget_usd"] == 0.23


def test_mcp_smoke_reports_invalid_runtime_default_environment(
    capsys,
    monkeypatch,
) -> None:
    monkeypatch.delenv("CREATIVITY_LAYER_PROVIDER_MODE", raising=False)
    monkeypatch.setenv("CREATIVITY_LAYER_BUDGET_USD", "not-money")

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
    assert "CREATIVITY_LAYER_BUDGET_USD" in payload["errors"][0]["message"]


def test_mcp_smoke_explicit_budget_overrides_invalid_runtime_default(
    capsys,
    monkeypatch,
) -> None:
    monkeypatch.setenv("CREATIVITY_LAYER_PROVIDER_MODE", "live_openai")
    monkeypatch.setenv("CREATIVITY_LAYER_BUDGET_USD", "not-money")

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
    assert payload["config"]["budget_usd"] == 0.20
    assert payload["finalist_count"] == 1


def test_package_exposes_mcp_smoke_console_script() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    assert pyproject["project"]["scripts"]["creativity-layer-mcp-smoke"] == (
        "creativity_layer.mcp_smoke:main"
    )
