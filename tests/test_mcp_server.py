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


def test_creative_plan_tool_defaults_to_live_openai_when_provider_is_omitted(
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

    result = creative_plan(
        goal="Design a backend middleware planning hook for arbitrary repos",
        repo_signals={"detected_languages": ("Python",)},
    )

    assert result["provider_mode"] == "live_openai"
    assert result["stopped_reason"] == "configuration_error"
    assert result["finalist_count"] == 0
    assert "OPENAI_API_KEY" in result["errors"][0]["message"]


def test_creative_plan_tool_uses_runtime_default_environment(monkeypatch) -> None:
    monkeypatch.setenv("CREATIVITY_LAYER_PROVIDER_MODE", "deterministic")
    monkeypatch.setenv("CREATIVITY_LAYER_EFFORT", "standard")
    monkeypatch.setenv("CREATIVITY_LAYER_BUDGET_USD", "0.22")
    monkeypatch.setenv("CREATIVITY_LAYER_SEARCH_MODE", "light")

    result = creative_plan(
        goal="Design a backend middleware planning hook for arbitrary repos",
        repo_signals={"detected_languages": ("Python",)},
    )

    assert result["provider_mode"] == "deterministic"
    assert result["config"]["effort"] == "standard"
    assert result["config"]["budget_usd"] == 0.22
    assert result["config"]["search_mode"] == "light"
    assert result["search_context"]["skipped_reason"] == "approval_required"
    assert result["finalist_count"] == 2


def test_creative_plan_tool_reports_invalid_runtime_default_environment(
    monkeypatch,
) -> None:
    monkeypatch.delenv("CREATIVITY_LAYER_PROVIDER_MODE", raising=False)
    monkeypatch.setenv("CREATIVITY_LAYER_BUDGET_USD", "not-money")

    result = creative_plan(
        goal="Design a backend middleware planning hook for arbitrary repos",
        repo_signals={"detected_languages": ("Python",)},
    )

    assert result["provider_mode"] == "live_openai"
    assert result["stopped_reason"] == "configuration_error"
    assert result["finalist_count"] == 0
    assert "CREATIVITY_LAYER_BUDGET_USD" in result["errors"][0]["message"]


def test_creative_plan_tool_explicit_budget_overrides_invalid_runtime_default(
    monkeypatch,
) -> None:
    monkeypatch.setenv("CREATIVITY_LAYER_PROVIDER_MODE", "live_openai")
    monkeypatch.setenv("CREATIVITY_LAYER_BUDGET_USD", "not-money")

    result = creative_plan(
        goal="Design a backend middleware planning hook for arbitrary repos",
        provider_mode="deterministic",
        budget_usd=0.20,
        repo_signals={"detected_languages": ("Python",)},
    )

    assert result["provider_mode"] == "deterministic"
    assert result["stopped_reason"] == "generation_limit"
    assert result["config"]["budget_usd"] == 0.20
    assert result["finalist_count"] == 1


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


def test_creative_plan_tool_forwards_explicit_search_mode(monkeypatch) -> None:
    monkeypatch.setenv("CREATIVITY_LAYER_SEARCH_MODE", "deep")

    result = creative_plan(
        goal="Design a backend middleware planning hook for arbitrary repos",
        search_mode="off",
        repo_signals={"detected_languages": ("Python",)},
        provider_mode="deterministic",
    )

    assert result["config"]["search_mode"] == "off"
    assert result["search_context"]["mode"] == "off"


def test_creative_plan_tool_forwards_explicit_search_policy(monkeypatch) -> None:
    monkeypatch.setenv("CREATIVITY_LAYER_LIVE_SEARCH_APPROVED", "1")

    result = creative_plan(
        goal="reversible team decisions",
        search_mode="light",
        search_provider="deterministic",
        search_strict=True,
        repo_signals={"detected_languages": ("Python",)},
        provider_mode="deterministic",
    )

    assert result["config"]["search_mode"] == "light"
    assert result["config"]["search_provider"] == "deterministic"
    assert result["config"]["search_strict"] is True
    assert result["search_context"]["provider_policy"] == "deterministic"
    assert result["search_context"]["strict"] is True
    assert result["search_context"]["used"] is True


def test_creative_plan_tool_uses_approved_search_context(monkeypatch) -> None:
    monkeypatch.setenv("CREATIVITY_LAYER_LIVE_SEARCH_APPROVED", "1")

    result = creative_plan(
        goal="reversible team decisions",
        search_mode="light",
        provider_mode="deterministic",
        seed_count=2,
        finalist_count=1,
        max_generations=0,
        budget_usd=0.20,
    )

    assert result["search_context"]["used"] is True
    assert result["search_context"]["provider"] == "deterministic-search"
    assert "search/deterministic-search/src-1" in result["context_sources"]


def test_creative_plan_configuration_error_includes_search_context(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    result = creative_plan(
        goal="Design a backend middleware planning hook for arbitrary repos",
        provider_mode="live_openai",
        search_mode="light",
    )

    assert result["stopped_reason"] == "configuration_error"
    assert result["config"]["search_mode"] == "light"
    assert result["search_context"]["mode"] == "light"
    assert result["search_context"]["used"] is False


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


def test_fastmcp_server_exposes_quality_warnings() -> None:
    async def run_probe() -> None:
        server = build_mcp_server()

        result = await server.call_tool(
            "creative_plan",
            {
                "goal": "Design a retry strategy for AI coding agents",
                "repo_signals": {
                    "ci_logs": ("pytest failed after retry loop change",),
                    "detected_languages": ("Python",),
                    "detected_frameworks": ("pytest",),
                },
                "provider_mode": "deterministic",
            },
        )
        _content_blocks, structured_result = result

        assert isinstance(structured_result, dict)
        assert "quality_warnings" in structured_result
        assert "quality_summary" in structured_result
        assert "quality_warnings" in structured_result["finalists"][0]
        assert "generic_title" in structured_result["quality_warnings"]

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
