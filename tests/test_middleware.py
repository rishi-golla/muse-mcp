from __future__ import annotations

import json

from creativity_layer.middleware import CreativeMiddlewareRunner, CreativePlanRequest


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

    assert result["config"]["budget_usd"] == 0.35
    assert result["config"]["seed_count"] == 4
    assert result["config"]["finalist_count"] == 2
    assert result["config"]["max_generations"] == 1
    assert result["finalist_count"] == 2
