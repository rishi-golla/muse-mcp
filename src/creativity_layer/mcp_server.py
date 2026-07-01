from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from mcp.server.fastmcp import FastMCP

from creativity_layer.middleware import CreativePlanRequest, run_creative_plan

SERVER_NAME = "creativity-layer"


def creative_plan(
    goal: str,
    repo_signals: Mapping[str, object] | None = None,
    provider_mode: str = "deterministic",
    privacy: str = "research",
    budget_usd: float = 0.35,
    seed_count: int = 4,
    finalist_count: int = 2,
    max_generations: int = 1,
    max_calls: int = 20,
    max_context_snippets: int = 8,
) -> dict[str, Any]:
    """Generate an operational creative plan for an agent's current task."""
    request = CreativePlanRequest(
        goal=goal,
        provider_mode=provider_mode,
        privacy=privacy,
        repo_signals=repo_signals or {},
        budget_usd=budget_usd,
        seed_count=seed_count,
        finalist_count=finalist_count,
        max_generations=max_generations,
        max_calls=max_calls,
        max_context_snippets=max_context_snippets,
    )
    return run_creative_plan(request)


def build_mcp_server() -> FastMCP:
    server = FastMCP(SERVER_NAME)
    server.tool()(creative_plan)
    return server


def main() -> None:
    build_mcp_server().run()


if __name__ == "__main__":
    main()
