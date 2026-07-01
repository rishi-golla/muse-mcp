from __future__ import annotations

import asyncio
import tomllib
from pathlib import Path

from creativity_layer.mcp_server import build_mcp_server, creative_plan


def test_creative_plan_tool_delegates_to_middleware_runner() -> None:
    result = creative_plan(
        goal="Design a backend middleware planning hook for arbitrary repos",
        repo_signals={"detected_languages": ("Python",)},
        provider_mode="deterministic",
    )

    assert result["provider_mode"] == "deterministic"
    assert result["config"]["effort"] == "quick"
    assert result["config"]["budget_usd"] == 0.20
    assert result["config"]["seed_count"] == 2
    assert result["finalist_count"] == 1
    assert result["finalists"][0]["inputs_required"]
    assert result["context_tags"] == ["python"]
    assert result["agent_guidance"]["intended_use"] == "planning_middleware"


def test_creative_plan_tool_accepts_deep_effort_preset() -> None:
    result = creative_plan(
        goal="Design a backend middleware planning hook for arbitrary repos",
        effort="deep",
        repo_signals={"detected_languages": ("Python",)},
        provider_mode="deterministic",
    )

    assert result["config"]["effort"] == "deep"
    assert result["config"]["budget_usd"] == 0.75
    assert result["config"]["seed_count"] == 6
    assert result["config"]["finalist_count"] == 3
    assert result["config"]["max_generations"] == 2


def test_creative_plan_tool_preserves_old_positional_numeric_arguments() -> None:
    result = creative_plan(
        "Design a backend middleware planning hook for arbitrary repos",
        {"detected_languages": ("Python",)},
        "deterministic",
        "research",
        0.35,
        4,
        2,
        1,
    )

    assert result["stopped_reason"] == "generation_limit"
    assert result["config"]["effort"] == "quick"
    assert result["config"]["budget_usd"] == 0.35
    assert result["config"]["seed_count"] == 4
    assert result["config"]["finalist_count"] == 2
    assert result["config"]["max_generations"] == 1


def test_build_mcp_server_returns_named_server() -> None:
    server = build_mcp_server()

    assert server is not None


def test_fastmcp_server_exposes_and_invokes_creative_plan_tool() -> None:
    async def run_probe() -> None:
        server = build_mcp_server()

        tools = await server.list_tools()
        tool_names = {tool.name for tool in tools}
        result = await server.call_tool(
            "creative_plan",
            {
                "goal": "Design a retry strategy for AI coding agents",
                "repo_signals": {"detected_languages": ("Python",)},
                "provider_mode": "deterministic",
            },
        )
        _content_blocks, structured_result = result

        assert "creative_plan" in tool_names
        assert isinstance(structured_result, dict)
        assert structured_result["provider_mode"] == "deterministic"
        assert structured_result["config"]["effort"] == "quick"
        assert structured_result["finalist_count"] == 1
        assert structured_result["context_tags"] == ["python"]

    asyncio.run(run_probe())


def test_creative_plan_live_mode_returns_structured_configuration_error(
    monkeypatch,
) -> None:
    for name in (
        "OPENAI_API_KEY",
        "OPENAI_ECONOMY_MODEL",
        "OPENAI_STRONG_MODEL",
        "OPENAI_PRICING_FILE",
    ):
        monkeypatch.delenv(name, raising=False)

    result = creative_plan(
        goal="Design a retry strategy for AI coding agents",
        provider_mode="live_openai",
        privacy="private",
    )

    assert result["provider_mode"] == "live_openai"
    assert result["stopped_reason"] == "configuration_error"
    assert result["finalist_count"] == 0
    assert result["errors"][0]["stage"] == "configuration"


def test_creative_plan_invalid_provider_mode_returns_structured_error() -> None:
    result = creative_plan(
        goal="Design a retry strategy for AI coding agents",
        provider_mode="bogus",
    )

    assert result["provider_mode"] == "bogus"
    assert result["stopped_reason"] == "configuration_error"
    assert result["finalist_count"] == 0
    assert result["errors"][0]["category"] == "configuration_error"


def test_fastmcp_invalid_provider_mode_returns_structured_error() -> None:
    async def run_probe() -> None:
        server = build_mcp_server()

        result = await server.call_tool(
            "creative_plan",
            {
                "goal": "Design a retry strategy for AI coding agents",
                "provider_mode": "bogus",
            },
        )
        _content_blocks, structured_result = result

        assert isinstance(structured_result, dict)
        assert structured_result["provider_mode"] == "bogus"
        assert structured_result["stopped_reason"] == "configuration_error"
        assert structured_result["finalist_count"] == 0

    asyncio.run(run_probe())


def test_package_exposes_mcp_console_script() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    assert pyproject["project"]["scripts"]["creativity-layer-mcp"] == (
        "creativity_layer.mcp_server:main"
    )
