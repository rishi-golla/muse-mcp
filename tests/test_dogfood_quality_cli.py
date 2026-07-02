from __future__ import annotations

import json
import tomllib
from pathlib import Path

from muse.dogfood_quality_cli import main


def test_dogfood_quality_cli_prints_json_report(capsys, monkeypatch) -> None:
    monkeypatch.setenv("MUSE_PROVIDER_MODE", "deterministic")

    exit_code = main(
        [
            "--provider-mode",
            "deterministic",
            "--case",
            "agent-retry-python",
            "--variant",
            "search-off",
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["summary"]["run_count"] == 1
    assert payload["runs"][0]["case"] == "agent-retry-python"
    assert payload["runs"][0]["variant"] == "search-off"


def test_dogfood_quality_cli_fail_on_gates_returns_nonzero(
    capsys,
    monkeypatch,
) -> None:
    monkeypatch.setenv("MUSE_PROVIDER_MODE", "deterministic")

    exit_code = main(
        [
            "--provider-mode",
            "deterministic",
            "--case",
            "agent-retry-python",
            "--variant",
            "search-off",
            "--fail-on-gates",
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert payload["summary"]["failing_run_count"] == 1
    assert payload["runs"][0]["quality_gates"]


def test_dogfood_quality_cli_forwards_search_policy(capsys, monkeypatch) -> None:
    monkeypatch.setenv("MUSE_PROVIDER_MODE", "deterministic")

    exit_code = main(
        [
            "--provider-mode",
            "deterministic",
            "--case",
            "agent-retry-python",
            "--variant",
            "search-light",
            "--search-provider",
            "deterministic",
            "--search-strict",
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["variants"][0]["search_provider"] == "deterministic"
    assert payload["variants"][0]["search_strict"] is True
    assert payload["runs"][0]["search_context"]["strict"] is True


def test_package_exposes_dogfood_quality_console_script() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    assert pyproject["project"]["scripts"]["muse-dogfood-quality"] == (
        "muse.dogfood_quality_cli:main"
    )
