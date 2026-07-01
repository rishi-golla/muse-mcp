from __future__ import annotations

import json

from creativity_layer.deterministic import DeterministicCreativeProvider
from creativity_layer.middleware import (
    CreativeMiddlewareRunner,
    CreativePlanRequest,
    ProviderMode,
    run_creative_plan,
)


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
    assert result["provider_mode"] == "deterministic"
    assert result["config"]["budget_usd"] == 0.35
    assert result["config"]["seed_count"] == 4
    assert result["config"]["finalist_count"] == 2
    assert result["config"]["max_generations"] == 1
    assert result["finalist_count"] == 2


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
        }
    )

    assert result["provider_mode"] == "live_openai"
    assert result["stopped_reason"] == "configuration_error"
    assert result["finalist_count"] == 0
    assert result["finalists"] == []
    assert result["errors"][0]["category"] == "configuration_error"
    assert "OPENAI_API_KEY" in result["errors"][0]["message"]


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
