from __future__ import annotations

import json

from creativity_layer.deterministic import DeterministicCreativeProvider
from creativity_layer.middleware import (
    CreativeMiddlewareRunner,
    CreativePlanRequest,
    EffortPreset,
    ProviderMode,
    run_creative_plan,
)
from creativity_layer.search import DeterministicSearchProvider
from creativity_layer.search_context import SearchContextResolver


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
    assert result["search_context"]["mode"] == "off"
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

    result = run_creative_plan(
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
