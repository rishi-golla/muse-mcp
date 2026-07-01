from __future__ import annotations

import tomllib
from pathlib import Path

from creativity_layer.mcp_server import build_mcp_server, creative_plan


def test_creative_plan_tool_delegates_to_middleware_runner() -> None:
    result = creative_plan(
        goal="Design a backend middleware planning hook for arbitrary repos",
        repo_signals={"detected_languages": ("Python",)},
        seed_count=2,
        finalist_count=1,
        max_generations=0,
        budget_usd=0.20,
    )

    assert result["finalist_count"] == 1
    assert result["finalists"][0]["inputs_required"]
    assert result["context_tags"] == ["python"]


def test_build_mcp_server_returns_named_server() -> None:
    server = build_mcp_server()

    assert server is not None


def test_package_exposes_mcp_console_script() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    assert pyproject["project"]["scripts"]["creativity-layer-mcp"] == (
        "creativity_layer.mcp_server:main"
    )
