from __future__ import annotations

import asyncio
import os
from collections.abc import Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from time import perf_counter
from typing import Any

from muse.mcp_server import build_mcp_server
from muse.quality_warnings import finalist_quality_warnings


@dataclass(frozen=True)
class DogfoodCase:
    name: str
    goal: str
    repo_signals: Mapping[str, tuple[str, ...]]
    required_terms: tuple[str, ...]


@dataclass(frozen=True)
class SearchVariant:
    name: str
    search_mode: str
    search_provider: str = "auto"
    search_strict: bool = False


DEFAULT_DOGFOOD_CASES: tuple[DogfoodCase, ...] = (
    DogfoodCase(
        name="agent-retry-python",
        goal="Design a better retry strategy for AI coding agents after failed tests",
        repo_signals={
            "file_paths": ("pyproject.toml", "src/agent/runner.py", "tests/test_runner.py"),
            "changed_files": ("src/agent/runner.py",),
            "test_commands": ("python -m pytest tests/test_runner.py",),
            "ci_logs": ("pytest failed after retry loop change",),
            "detected_languages": ("Python",),
            "detected_frameworks": ("pytest",),
        },
        required_terms=("pytest", "retry", "failed tests", "verification"),
    ),
    DogfoodCase(
        name="typescript-monorepo-flaky-ci",
        goal="Design a debugging workflow for a TypeScript monorepo with flaky CI",
        repo_signals={
            "file_paths": (
                "pnpm-workspace.yaml",
                "apps/web/package.json",
                "packages/ui/package.json",
            ),
            "changed_files": ("packages/ui/src/Button.tsx",),
            "test_commands": (
                "pnpm test --filter apps/web -- --shard=2/4",
                "pnpm tsc --build",
            ),
            "ci_logs": ("Vitest shard 2 failed after Playwright smoke tests",),
            "dependency_hints": ("apps/web depends on packages/ui",),
            "detected_languages": ("TypeScript",),
            "detected_frameworks": ("Vitest", "Playwright"),
        },
        required_terms=("typescript", "package graph", "shard", "affected packages"),
    ),
    DogfoodCase(
        name="agent-middleware-arbitrary-repo",
        goal="Design a novel backend middleware for agent task planning in arbitrary repos",
        repo_signals={
            "file_paths": ("src/middleware/planner.py", "tests/test_planner.py"),
            "changed_files": ("src/middleware/planner.py",),
            "test_commands": ("python -m pytest tests/test_planner.py",),
            "detected_languages": ("Python",),
            "detected_frameworks": ("pytest",),
        },
        required_terms=("middleware", "agent", "repo", "integration"),
    ),
    DogfoodCase(
        name="interactive-portfolio-nextjs",
        goal=(
            "Design a non-AI-slop interactive personal website that is 3D and "
            "space themed"
        ),
        repo_signals={
            "file_paths": ("app/page.tsx", "components/Scene.tsx", "package.json"),
            "changed_files": ("app/page.tsx",),
            "test_commands": ("pnpm lint", "pnpm test"),
            "detected_languages": ("TypeScript",),
            "detected_frameworks": ("Next.js", "Three.js"),
        },
        required_terms=("3d", "space", "next.js", "three.js"),
    ),
)


DEFAULT_SEARCH_VARIANTS: tuple[SearchVariant, ...] = (
    SearchVariant(name="search-off", search_mode="off"),
    SearchVariant(name="search-light", search_mode="light"),
    SearchVariant(name="search-deep", search_mode="deep"),
)


def run_dogfood_quality_suite(
    *,
    provider_mode: str = "deterministic",
    effort: str = "quick",
    privacy: str = "research",
    budget_usd: float | None = None,
    search_provider: str = "auto",
    search_strict: bool = False,
    case_names: Sequence[str] | None = None,
    variant_names: Sequence[str] | None = None,
    approve_search: bool = True,
) -> dict[str, Any]:
    cases = _select_cases(case_names)
    variants = _select_variants(
        variant_names,
        search_provider=search_provider,
        search_strict=search_strict,
    )

    runs: list[dict[str, Any]] = []
    with _temporary_search_approval(approve_search):
        for case in cases:
            for variant in variants:
                runs.append(
                    _run_case_variant(
                        case=case,
                        variant=variant,
                        provider_mode=provider_mode,
                        effort=effort,
                        privacy=privacy,
                        budget_usd=budget_usd,
                    )
                )

    failing_runs = tuple(run for run in runs if run["quality_gates"])
    return {
        "summary": {
            "case_count": len(cases),
            "variant_count": len(variants),
            "run_count": len(runs),
            "failing_run_count": len(failing_runs),
            "spend_usd": round(sum(run["spend_usd"] for run in runs), 10),
        },
        "cases": [_case_summary(case) for case in cases],
        "variants": [_variant_summary(variant) for variant in variants],
        "runs": runs,
    }


def evaluate_quality_gates(
    case: DogfoodCase,
    variant: SearchVariant,
    result: Mapping[str, Any],
) -> tuple[str, ...]:
    gates: list[str] = []
    finalists = _as_sequence(result.get("finalists"))
    finalist = _as_mapping(finalists[0]) if finalists else {}
    search_context = _as_mapping(result.get("search_context"))

    if result.get("errors") or str(result.get("stopped_reason")) in {
        "configuration_error",
        "provider_error",
    }:
        gates.append("provider_error")
    if not finalists:
        gates.append("missing_finalist")
    if finalist:
        gates.extend(
            finalist_quality_warnings(
                finalist,
                required_terms=case.required_terms,
            )
        )
    if variant.search_mode != "off" and search_context.get("used") is not True:
        gates.append("search_expected_but_unused")

    return tuple(dict.fromkeys(gates))


def _run_case_variant(
    *,
    case: DogfoodCase,
    variant: SearchVariant,
    provider_mode: str,
    effort: str,
    privacy: str,
    budget_usd: float | None,
) -> dict[str, Any]:
    arguments: dict[str, Any] = {
        "goal": case.goal,
        "provider_mode": provider_mode,
        "privacy": privacy,
        "effort": effort,
        "search_mode": variant.search_mode,
        "search_provider": variant.search_provider,
        "search_strict": variant.search_strict,
        "repo_signals": {
            key: list(value) for key, value in case.repo_signals.items()
        },
    }
    if budget_usd is not None:
        arguments["budget_usd"] = budget_usd

    started = perf_counter()
    result = asyncio.run(_call_muse_plan(arguments))
    latency_ms = round((perf_counter() - started) * 1000, 3)
    quality_gates = evaluate_quality_gates(case, variant, result)
    return {
        "case": case.name,
        "variant": variant.name,
        "provider_mode": str(result.get("provider_mode", provider_mode)),
        "stopped_reason": str(result.get("stopped_reason", "")),
        "generated_count": int(result.get("generated_count", 0)),
        "finalist_count": int(result.get("finalist_count", 0)),
        "spend_usd": float(result.get("spend_usd", 0.0)),
        "latency_ms": latency_ms,
        "search_context": result.get("search_context", {}),
        "quality_gates": list(quality_gates),
        "errors": result.get("errors", []),
        "finalists": result.get("finalists", []),
    }


async def _call_muse_plan(arguments: Mapping[str, Any]) -> dict[str, Any]:
    server = build_mcp_server()
    _content_blocks, structured_result = await server.call_tool(
        "muse_plan",
        dict(arguments),
    )
    if not isinstance(structured_result, dict):
        raise RuntimeError("muse_plan did not return structured output")
    return structured_result


def _select_cases(names: Sequence[str] | None) -> tuple[DogfoodCase, ...]:
    if not names:
        return DEFAULT_DOGFOOD_CASES
    wanted = set(names)
    selected = tuple(case for case in DEFAULT_DOGFOOD_CASES if case.name in wanted)
    missing = sorted(wanted - {case.name for case in selected})
    if missing:
        raise ValueError(f"unknown dogfood case(s): {', '.join(missing)}")
    return selected


def _select_variants(
    names: Sequence[str] | None,
    *,
    search_provider: str,
    search_strict: bool,
) -> tuple[SearchVariant, ...]:
    base_variants = DEFAULT_SEARCH_VARIANTS if not names else tuple(
        variant for variant in DEFAULT_SEARCH_VARIANTS if variant.name in set(names)
    )
    if names:
        missing = sorted(set(names) - {variant.name for variant in base_variants})
        if missing:
            raise ValueError(f"unknown search variant(s): {', '.join(missing)}")
    return tuple(
        SearchVariant(
            name=variant.name,
            search_mode=variant.search_mode,
            search_provider=search_provider,
            search_strict=search_strict,
        )
        for variant in base_variants
    )


def _case_summary(case: DogfoodCase) -> dict[str, Any]:
    return {
        "name": case.name,
        "goal": case.goal,
        "required_terms": list(case.required_terms),
    }


def _variant_summary(variant: SearchVariant) -> dict[str, Any]:
    return {
        "name": variant.name,
        "search_mode": variant.search_mode,
        "search_provider": variant.search_provider,
        "search_strict": variant.search_strict,
    }


def _as_sequence(value: object) -> Sequence[object]:
    return value if isinstance(value, Sequence) and not isinstance(value, str) else ()


def _as_mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


@contextmanager
def _temporary_search_approval(enabled: bool):
    previous = os.environ.get("MUSE_LIVE_SEARCH_APPROVED")
    if enabled:
        os.environ["MUSE_LIVE_SEARCH_APPROVED"] = "1"
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("MUSE_LIVE_SEARCH_APPROVED", None)
        else:
            os.environ["MUSE_LIVE_SEARCH_APPROVED"] = previous
