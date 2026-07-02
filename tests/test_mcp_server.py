from __future__ import annotations

import asyncio
import tomllib
from pathlib import Path

import pytest

from muse.mcp_server import build_mcp_server, muse_plan


@pytest.fixture(autouse=True)
def enable_internal_test_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MUSE_ENABLE_TEST_PROVIDER", "1")


def test_muse_plan_tool_delegates_to_middleware_runner() -> None:
    result = muse_plan(
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


def test_muse_plan_tool_defaults_to_live_openai_when_provider_is_omitted(
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

    result = muse_plan(
        goal="Design a backend middleware planning hook for arbitrary repos",
        repo_signals={"detected_languages": ("Python",)},
    )

    assert result["provider_mode"] == "live_openai"
    assert result["stopped_reason"] == "configuration_error"
    assert result["finalist_count"] == 0
    assert "OPENAI_API_KEY" in result["errors"][0]["message"]


def test_muse_plan_tool_uses_runtime_default_environment(monkeypatch) -> None:
    monkeypatch.setenv("MUSE_PROVIDER_MODE", "deterministic")
    monkeypatch.setenv("MUSE_EFFORT", "standard")
    monkeypatch.setenv("MUSE_BUDGET_USD", "0.22")
    monkeypatch.setenv("MUSE_SEARCH_MODE", "light")

    result = muse_plan(
        goal="Design a backend middleware planning hook for arbitrary repos",
        repo_signals={"detected_languages": ("Python",)},
    )

    assert result["provider_mode"] == "deterministic"
    assert result["config"]["effort"] == "standard"
    assert result["config"]["budget_usd"] == 0.22
    assert result["config"]["search_mode"] == "light"
    assert result["search_context"]["skipped_reason"] == "approval_required"
    assert result["finalist_count"] == 2


def test_muse_plan_tool_reports_invalid_runtime_default_environment(
    monkeypatch,
) -> None:
    monkeypatch.delenv("MUSE_PROVIDER_MODE", raising=False)
    monkeypatch.delenv("MUSE_ENABLE_TEST_PROVIDER", raising=False)
    monkeypatch.setenv("MUSE_BUDGET_USD", "not-money")

    result = muse_plan(
        goal="Design a backend middleware planning hook for arbitrary repos",
        repo_signals={"detected_languages": ("Python",)},
    )

    assert result["provider_mode"] == "live_openai"
    assert result["stopped_reason"] == "configuration_error"
    assert result["finalist_count"] == 0
    assert "MUSE_BUDGET_USD" in result["errors"][0]["message"]


def test_muse_plan_tool_explicit_budget_overrides_invalid_runtime_default(
    monkeypatch,
) -> None:
    monkeypatch.setenv("MUSE_PROVIDER_MODE", "live_openai")
    monkeypatch.setenv("MUSE_BUDGET_USD", "not-money")

    result = muse_plan(
        goal="Design a backend middleware planning hook for arbitrary repos",
        provider_mode="deterministic",
        budget_usd=0.20,
        repo_signals={"detected_languages": ("Python",)},
    )

    assert result["provider_mode"] == "deterministic"
    assert result["stopped_reason"] == "generation_limit"
    assert result["config"]["budget_usd"] == 0.20
    assert result["finalist_count"] == 1


def test_muse_plan_tool_accepts_deep_effort_preset() -> None:
    result = muse_plan(
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


def test_muse_plan_tool_forwards_explicit_search_mode(monkeypatch) -> None:
    monkeypatch.setenv("MUSE_SEARCH_MODE", "deep")

    result = muse_plan(
        goal="Design a backend middleware planning hook for arbitrary repos",
        search_mode="off",
        repo_signals={"detected_languages": ("Python",)},
        provider_mode="deterministic",
    )

    assert result["config"]["search_mode"] == "off"
    assert result["search_context"]["mode"] == "off"


def test_muse_plan_tool_forwards_explicit_search_policy(monkeypatch) -> None:
    monkeypatch.setenv("MUSE_LIVE_SEARCH_APPROVED", "1")

    result = muse_plan(
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


def test_muse_plan_tool_uses_approved_search_context(monkeypatch) -> None:
    monkeypatch.setenv("MUSE_LIVE_SEARCH_APPROVED", "1")

    result = muse_plan(
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


def test_muse_plan_configuration_error_includes_search_context(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("MUSE_ENABLE_TEST_PROVIDER", raising=False)

    result = muse_plan(
        goal="Design a backend middleware planning hook for arbitrary repos",
        provider_mode="live_openai",
        search_mode="light",
    )

    assert result["stopped_reason"] == "configuration_error"
    assert result["config"]["search_mode"] == "light"
    assert result["search_context"]["mode"] == "light"
    assert result["search_context"]["used"] is False


def test_muse_plan_tool_preserves_old_positional_numeric_arguments() -> None:
    result = muse_plan(
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


def test_fastmcp_server_exposes_and_invokes_muse_plan_tool() -> None:
    async def run_probe() -> None:
        server = build_mcp_server()

        tools = await server.list_tools()
        tool_names = {tool.name for tool in tools}
        result = await server.call_tool(
            "muse_plan",
            {
                "goal": "Design a retry strategy for AI coding agents",
                "repo_signals": {"detected_languages": ("Python",)},
                "provider_mode": "deterministic",
            },
        )
        _content_blocks, structured_result = result

        assert "muse_plan" in tool_names
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
            "muse_plan",
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


def test_fastmcp_server_exposes_quality_action_policy() -> None:
    async def run_probe() -> None:
        server = build_mcp_server()

        result = await server.call_tool(
            "muse_plan",
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
        assert structured_result["quality_action_policy"]["status"] == "needs_retry"
        assert (
            structured_result["quality_action_policy"]
            == structured_result["agent_guidance"]["quality_action_policy"]
        )

    asyncio.run(run_probe())


def test_fastmcp_server_exposes_suggested_next_call() -> None:
    async def run_probe() -> None:
        server = build_mcp_server()

        result = await server.call_tool(
            "muse_plan",
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
        assert structured_result["suggested_next_call"]["tool"] == "muse_plan"
        assert (
            structured_result["suggested_next_call"]
            == structured_result["agent_guidance"]["suggested_next_call"]
        )

    asyncio.run(run_probe())


def test_fastmcp_server_exposes_agent_handoff() -> None:
    async def run_probe() -> None:
        server = build_mcp_server()

        result = await server.call_tool(
            "muse_plan",
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
        assert structured_result["agent_handoff"]["status"] == "retry_recommended"
        assert (
            structured_result["agent_handoff"]
            == structured_result["agent_guidance"]["agent_handoff"]
        )

    asyncio.run(run_probe())


def test_muse_plan_live_mode_returns_structured_configuration_error(
    monkeypatch,
) -> None:
    for name in (
        "OPENAI_API_KEY",
        "OPENAI_ECONOMY_MODEL",
        "OPENAI_STRONG_MODEL",
        "OPENAI_PRICING_FILE",
        "MUSE_ENABLE_TEST_PROVIDER",
    ):
        monkeypatch.delenv(name, raising=False)

    result = muse_plan(
        goal="Design a retry strategy for AI coding agents",
        provider_mode="live_openai",
        privacy="private",
    )

    assert result["provider_mode"] == "live_openai"
    assert result["stopped_reason"] == "configuration_error"
    assert result["finalist_count"] == 0
    assert result["errors"][0]["stage"] == "configuration"


def test_muse_plan_invalid_provider_mode_returns_structured_error() -> None:
    result = muse_plan(
        goal="Design a retry strategy for AI coding agents",
        provider_mode="bogus",
    )

    assert result["provider_mode"] == "bogus"
    assert result["stopped_reason"] == "configuration_error"
    assert result["finalist_count"] == 0
    assert result["errors"][0]["category"] == "configuration_error"


def test_muse_plan_rejects_public_deterministic_provider(monkeypatch) -> None:
    monkeypatch.delenv("MUSE_ENABLE_TEST_PROVIDER", raising=False)

    result = muse_plan(
        goal="Design a retry strategy for AI coding agents",
        provider_mode="deterministic",
    )

    assert result["provider_mode"] == "deterministic"
    assert result["stopped_reason"] == "configuration_error"
    assert result["finalist_count"] == 0
    assert "MUSE_ENABLE_TEST_PROVIDER" in result["errors"][0]["message"]


def test_fastmcp_invalid_provider_mode_returns_structured_error() -> None:
    async def run_probe() -> None:
        server = build_mcp_server()

        result = await server.call_tool(
            "muse_plan",
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

    assert pyproject["project"]["scripts"]["muse-mcp"] == (
        "muse.mcp_server:main"
    )
