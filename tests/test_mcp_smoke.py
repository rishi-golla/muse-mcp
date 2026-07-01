from __future__ import annotations

import json
import tomllib
from pathlib import Path

from creativity_layer.mcp_smoke import run_smoke


def test_mcp_smoke_invokes_fastmcp_tool_and_prints_json(capsys) -> None:
    exit_code = run_smoke(
        [
            "Design a retry strategy for AI coding agents",
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


def test_mcp_smoke_forwards_effort_preset(capsys) -> None:
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


def test_package_exposes_mcp_smoke_console_script() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    assert pyproject["project"]["scripts"]["creativity-layer-mcp-smoke"] == (
        "creativity_layer.mcp_smoke:main"
    )
