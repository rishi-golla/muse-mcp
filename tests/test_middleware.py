from __future__ import annotations

import json

from muse import middleware as middleware_module
from muse.deterministic import DeterministicCreativeProvider
from muse.middleware import (
    CreativeMiddlewareRunner,
    CreativePlanRequest,
    EffortPreset,
    ProviderMode,
    run_muse_plan,
)
from muse.search import DeterministicSearchProvider
from muse.search_context import SearchContextResolver, SearchProviderPolicy


def test_runner_returns_json_safe_operational_plan_from_repo_signals() -> None:
    request = CreativePlanRequest(
        goal="Design a debugging workflow for a TypeScript monorepo with flaky CI",
        repo_signals={
            "file_paths": ("pnpm-workspace.yaml", "apps/web/package.json"),
            "changed_files": ("packages/ui/src/Button.tsx",),
            "test_commands": ("pnpm test --filter apps/web -- --shard=2/4",),
            "ci_logs": ("Vitest shard 2 failed after Playwright smoke tests",),
            "dependency_hints": ("apps/web depends on packages/ui",),
            "detected_languages": ("TypeScript",),
            "detected_frameworks": ("Vitest", "Playwright"),
        },
        seed_count=4,
        finalist_count=2,
        max_generations=1,
        budget_usd=0.35,
    )

    result = CreativeMiddlewareRunner.deterministic().run(request)

    assert result["stopped_reason"] == "generation_limit"
    assert result["generated_count"] >= 4
    assert result["finalist_count"] == 2
    assert result["context_tags"] == ["typescript", "vitest", "playwright"]
    assert "test shards" in result["finalists"][0]["agent_workflow"][1]
    assert result["finalists"][0]["verification_strategy"]
    assert json.loads(json.dumps(result)) == result


def test_runner_returns_quality_warnings_for_generic_finalists() -> None:
    result = CreativeMiddlewareRunner.deterministic().run(
        CreativePlanRequest(
            goal="Design a better retry strategy for AI coding agents after failed tests",
            repo_signals={
                "ci_logs": ("pytest failed after retry loop change",),
                "detected_languages": ("Python",),
                "detected_frameworks": ("pytest",),
            },
            seed_count=2,
            finalist_count=1,
            max_generations=0,
            budget_usd=0.20,
        )
    )

    finalist = result["finalists"][0]

    assert "quality_warnings" in result
    assert "quality_summary" in result
    assert "quality_warnings" in finalist
    assert "generic_title" in result["quality_warnings"]
    assert "generic_title" in finalist["quality_warnings"]
    assert result["quality_summary"]["finalist_warning_count"] == 1
    assert result["quality_summary"]["warnings"]["generic_title"] == 1


def test_runner_returns_quality_action_policy_for_warning_results() -> None:
    result = CreativeMiddlewareRunner.deterministic().run(
        CreativePlanRequest(
            goal="Design a better retry strategy for AI coding agents after failed tests",
            repo_signals={
                "ci_logs": ("pytest failed after retry loop change",),
                "detected_languages": ("Python",),
                "detected_frameworks": ("pytest",),
            },
            seed_count=2,
            finalist_count=1,
            max_generations=0,
            budget_usd=0.20,
        )
    )

    policy = result["quality_action_policy"]

    assert policy["status"] == "needs_retry"
    assert policy["escalate_effort_to"] == "standard"
    assert "supply more repo signals" in policy["recommended_actions"]
    assert policy == result["agent_guidance"]["quality_action_policy"]


def test_runner_returns_suggested_next_call_for_warning_results() -> None:
    result = CreativeMiddlewareRunner.deterministic().run(
        CreativePlanRequest(
            goal="Design a better retry strategy for AI coding agents after failed tests",
            repo_signals={
                "ci_logs": ("pytest failed after retry loop change",),
                "detected_languages": ("Python",),
                "detected_frameworks": ("pytest",),
            },
            seed_count=2,
            finalist_count=1,
            max_generations=0,
            budget_usd=0.20,
        )
    )

    suggestion = result["suggested_next_call"]

    assert suggestion["tool"] == "muse_plan"
    assert suggestion["automatic"] is False
    assert suggestion["request"]["goal"] == (
        "Design a better retry strategy for AI coding agents after failed tests"
    )
    assert suggestion["request"]["effort"] == "standard"
    assert "repo_signals" not in suggestion["request"]
    assert "test commands" in suggestion["repo_signal_requests"][0]
    assert suggestion == result["agent_guidance"]["suggested_next_call"]


def test_runner_returns_agent_handoff_for_warning_results() -> None:
    result = CreativeMiddlewareRunner.deterministic().run(
        CreativePlanRequest(
            goal="Design a better retry strategy for AI coding agents after failed tests",
            repo_signals={
                "ci_logs": ("pytest failed after retry loop change",),
                "detected_languages": ("Python",),
                "detected_frameworks": ("pytest",),
            },
            seed_count=2,
            finalist_count=1,
            max_generations=0,
            budget_usd=0.20,
        )
    )

    handoff = result["agent_handoff"]

    assert handoff["status"] == "retry_recommended"
    assert handoff["recommended_action"] == "retry_muse_plan"
    assert handoff["use_current_finalist"] is False
    assert handoff["selected_finalist_id"] == result["finalists"][0]["id"]
    assert handoff["suggested_next_call_available"] is True
    assert handoff["verification_required"] is True
    assert handoff == result["agent_guidance"]["agent_handoff"]


def test_runner_returns_review_agent_handoff_for_generic_review_results() -> None:
    result = CreativeMiddlewareRunner.deterministic().run(
        CreativePlanRequest(
            goal="Design a planning hook for arbitrary repos",
            seed_count=2,
            finalist_count=1,
            max_generations=0,
            budget_usd=0.20,
        )
    )

    handoff = result["agent_handoff"]

    assert result["quality_action_policy"]["status"] == "review"
    assert handoff["status"] == "review"
    assert handoff["recommended_action"] == "review_current_finalist"
    assert handoff["use_current_finalist"] is True
    assert handoff["selected_finalist_id"] == result["finalists"][0]["id"]
    assert handoff["suggested_next_call_available"] is True


def test_runner_uses_cheap_agent_defaults() -> None:
    request = CreativePlanRequest(goal="Design a planning hook for arbitrary repos")

    result = CreativeMiddlewareRunner.deterministic().run(request)

    assert request.provider_mode is ProviderMode.DETERMINISTIC
    assert request.effort is EffortPreset.QUICK
    assert result["provider_mode"] == "deterministic"
    assert result["config"]["effort"] == "quick"
    assert result["config"]["budget_usd"] == 0.20
    assert result["config"]["seed_count"] == 2
    assert result["config"]["finalist_count"] == 1
    assert result["config"]["max_generations"] == 0
    assert result["config"]["search_mode"] == "off"
    assert result["config"]["search_provider"] == "auto"
    assert result["config"]["search_strict"] is False
    assert result["search_context"]["mode"] == "off"
    assert result["search_context"]["provider_policy"] == "deterministic"
    assert result["search_context"]["used"] is False
    assert result["finalist_count"] == 1


def test_runner_resolves_standard_and_deep_effort_presets() -> None:
    standard = CreativePlanRequest(
        goal="Design a planning hook for arbitrary repos",
        effort="standard",
    )
    deep = CreativePlanRequest(
        goal="Design a planning hook for arbitrary repos",
        effort="deep",
    )

    assert standard.budget_usd == 0.35
    assert standard.seed_count == 4
    assert standard.finalist_count == 2
    assert standard.max_generations == 1
    assert deep.budget_usd == 0.75
    assert deep.seed_count == 6
    assert deep.finalist_count == 3
    assert deep.max_generations == 2


def test_runner_explicit_values_override_effort_presets() -> None:
    request = CreativePlanRequest(
        goal="Design a planning hook for arbitrary repos",
        effort="deep",
        budget_usd=0.21,
        seed_count=2,
        finalist_count=1,
        max_generations=0,
    )

    result = CreativeMiddlewareRunner.deterministic().run(request)

    assert result["config"]["effort"] == "deep"
    assert result["config"]["budget_usd"] == 0.21
    assert result["config"]["seed_count"] == 2
    assert result["config"]["finalist_count"] == 1
    assert result["config"]["max_generations"] == 0


def test_runner_returns_agent_guidance_contract() -> None:
    result = CreativeMiddlewareRunner.deterministic().run(
        CreativePlanRequest(goal="Design a planning hook for arbitrary repos")
    )

    guidance = result["agent_guidance"]

    assert guidance["intended_use"] == "planning_middleware"
    assert guidance["verification_required"] is True
    assert "observe_repo_state" in guidance["recommended_agent_loop"]
    assert "verification keeps failing" in guidance["escalation_policy"]


def test_runner_reports_search_approval_skip() -> None:
    result = CreativeMiddlewareRunner.deterministic().run(
        CreativePlanRequest(
            goal="reversible team decisions",
            search_mode="light",
            seed_count=2,
            finalist_count=1,
            max_generations=0,
            budget_usd=0.20,
        )
    )

    assert result["config"]["search_mode"] == "light"
    assert result["search_context"]["mode"] == "light"
    assert result["search_context"]["used"] is False
    assert result["search_context"]["skipped_reason"] == "approval_required"


def test_runner_merges_injected_search_context() -> None:
    runner = CreativeMiddlewareRunner.deterministic(
        search_context_resolver=SearchContextResolver(
            provider=DeterministicSearchProvider(),
            approval_required=False,
        )
    )

    result = runner.run(
        CreativePlanRequest(
            goal="reversible team decisions",
            search_mode="light",
            seed_count=2,
            finalist_count=1,
            max_generations=0,
            budget_usd=0.20,
        )
    )

    assert result["search_context"]["used"] is True
    assert result["search_context"]["source_count"] == 1
    assert "search/deterministic-search/src-1" in result["context_sources"]


def test_runner_strict_search_returns_configuration_error_when_unavailable() -> None:
    runner = CreativeMiddlewareRunner.deterministic(
        search_context_resolver=SearchContextResolver(
            provider=None,
            provider_policy=SearchProviderPolicy.DETERMINISTIC,
            approval_required=False,
        )
    )

    result = runner.run(
        CreativePlanRequest(
            goal="reversible team decisions",
            search_mode="light",
            search_provider="deterministic",
            search_strict=True,
            seed_count=2,
            finalist_count=1,
            max_generations=0,
            budget_usd=0.20,
        )
    )

    assert result["stopped_reason"] == "configuration_error"
    assert result["generated_count"] == 0
    assert result["finalist_count"] == 0
    assert result["config"]["search_mode"] == "light"
    assert result["config"]["search_provider"] == "deterministic"
    assert result["config"]["search_strict"] is True
    assert result["search_context"]["skipped_reason"] == "configuration_error"
    assert result["search_context"]["strict"] is True
    assert "search provider" in result["errors"][0]["message"]


def test_direct_runner_respects_explicit_search_provider_policy(monkeypatch) -> None:
    monkeypatch.setenv("MUSE_LIVE_SEARCH_APPROVED", "1")

    result = CreativeMiddlewareRunner.deterministic().run(
        CreativePlanRequest(
            goal="reversible team decisions",
            search_mode="light",
            search_provider="exa",
            search_strict=True,
            seed_count=2,
            finalist_count=1,
            max_generations=0,
            budget_usd=0.20,
        )
    )

    assert result["stopped_reason"] == "configuration_error"
    assert result["config"]["search_provider"] == "exa"
    assert result["search_context"]["provider_policy"] == "exa"
    assert result["search_context"]["strict"] is True


def test_live_openai_mode_returns_structured_configuration_error(
    monkeypatch,
) -> None:
    for name in (
        "OPENAI_API_KEY",
        "OPENAI_ECONOMY_MODEL",
        "OPENAI_STRONG_MODEL",
        "OPENAI_PRICING_FILE",
    ):
        monkeypatch.delenv(name, raising=False)

    result = run_muse_plan(
        {
            "goal": "Design a retry strategy for AI coding agents",
            "provider_mode": "live_openai",
            "effort": "deep",
        }
    )

    assert result["provider_mode"] == "live_openai"
    assert result["stopped_reason"] == "configuration_error"
    assert result["finalist_count"] == 0
    assert result["finalists"] == []
    assert result["errors"][0]["category"] == "configuration_error"
    assert "OPENAI_API_KEY" in result["errors"][0]["message"]
    assert result["agent_guidance"]["effort"] == "deep"
    assert result["config"]["search_mode"] == "off"
    assert result["search_context"]["mode"] == "off"
    assert result["search_context"]["used"] is False
    assert result["quality_warnings"] == []
    assert result["quality_summary"] == {
        "warning_count": 0,
        "finalist_warning_count": 0,
        "warnings": {},
    }


def test_middleware_uses_packaged_pricing_when_pricing_env_is_absent(
    monkeypatch,
) -> None:
    monkeypatch.delenv("OPENAI_PRICING_FILE", raising=False)

    pricing = middleware_module._load_pricing_table_from_environment()

    assert pricing.version == "example-v1"
    assert pricing.text_price("gpt-5.4-mini").input_per_million > 0


def test_configuration_error_includes_empty_quality_warning_fields() -> None:
    result = run_muse_plan(
        {
            "goal": "Design a retry strategy for AI coding agents",
            "provider_mode": "bogus",
        }
    )

    assert result["stopped_reason"] == "configuration_error"
    assert result["quality_warnings"] == []
    assert result["quality_summary"] == {
        "warning_count": 0,
        "finalist_warning_count": 0,
        "warnings": {},
    }


def test_configuration_error_includes_clear_quality_action_policy() -> None:
    result = run_muse_plan(
        {
            "goal": "Design a retry strategy for AI coding agents",
            "provider_mode": "bogus",
        }
    )

    assert result["stopped_reason"] == "configuration_error"
    assert result["quality_action_policy"] == {
        "status": "clear",
        "escalate_effort_to": None,
        "recommended_actions": [],
        "warning_actions": {},
    }
    assert result["quality_action_policy"] == (
        result["agent_guidance"]["quality_action_policy"]
    )
    assert result["suggested_next_call"] is None
    assert result["agent_guidance"]["suggested_next_call"] is None


def test_configuration_error_includes_blocked_agent_handoff() -> None:
    result = run_muse_plan(
        {
            "goal": "Design a retry strategy for AI coding agents",
            "provider_mode": "bogus",
        }
    )

    assert result["agent_handoff"] == {
        "status": "blocked",
        "recommended_action": "fix_configuration",
        "use_current_finalist": False,
        "selected_finalist_id": None,
        "suggested_next_call_available": False,
        "verification_required": True,
    }
    assert result["agent_handoff"] == result["agent_guidance"]["agent_handoff"]


def test_invalid_search_mode_error_preserves_response_shape() -> None:
    result = run_muse_plan(
        {
            "goal": "Design a retry strategy for AI coding agents",
            "provider_mode": "deterministic",
            "search_mode": "wide-open",
        }
    )

    assert result["stopped_reason"] == "configuration_error"
    assert result["config"]["search_mode"] == "wide-open"
    assert result["search_context"]["mode"] == "wide-open"
    assert result["search_context"]["used"] is False


def test_live_openai_runner_uses_injected_provider() -> None:
    provider = DeterministicCreativeProvider()
    runner = CreativeMiddlewareRunner.live_openai(
        provider=provider,
    )

    result = runner.run(
        CreativePlanRequest(
            goal="Design a planning hook for arbitrary repos",
            provider_mode="live_openai",
            seed_count=2,
            finalist_count=1,
            max_generations=0,
            budget_usd=0.20,
        )
    )

    assert result["provider_mode"] == "live_openai"
    assert result["finalist_count"] == 1
