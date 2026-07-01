from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from mcp.server.fastmcp import FastMCP

from creativity_layer.middleware import run_creative_plan

SERVER_NAME = "creativity-layer"


def creative_plan(
    goal: str,
    repo_signals: Mapping[str, object] | None = None,
    provider_mode: str = "deterministic",
    privacy: str = "research",
    effort: str = "quick",
    budget_usd: float | None = None,
    seed_count: int | None = None,
    finalist_count: int | None = None,
    max_generations: int | None = None,
    max_calls: int = 20,
    max_context_snippets: int = 8,
) -> dict[str, Any]:
    """Generate an operational creative plan for an agent's current task.

    Use quick for cheap normal coding loops, standard when a first repair fails,
    and deep for deliberate planning before high-impact edits.
    """
    request: dict[str, Any] = {
        "goal": goal,
        "provider_mode": provider_mode,
        "privacy": privacy,
        "effort": effort,
        "repo_signals": repo_signals or {},
        "max_calls": max_calls,
        "max_context_snippets": max_context_snippets,
    }
    for key, value in (
        ("budget_usd", budget_usd),
        ("seed_count", seed_count),
        ("finalist_count", finalist_count),
        ("max_generations", max_generations),
    ):
        if value is not None:
            request[key] = value
    return run_creative_plan(request)


def build_mcp_server() -> FastMCP:
    server = FastMCP(SERVER_NAME)
    server.tool()(creative_plan)
    return server


def main() -> None:
    build_mcp_server().run()


if __name__ == "__main__":
    main()
