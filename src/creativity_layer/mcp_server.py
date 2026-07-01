from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from mcp.server.fastmcp import FastMCP

from creativity_layer.middleware import run_creative_plan
from creativity_layer.runtime_defaults import RuntimeDefaults

SERVER_NAME = "creativity-layer"


def creative_plan(
    goal: str,
    repo_signals: Mapping[str, object] | None = None,
    provider_mode: str | None = None,
    privacy: str | None = None,
    budget_usd: float | None = None,
    seed_count: int | None = None,
    finalist_count: int | None = None,
    max_generations: int | None = None,
    max_calls: int = 20,
    max_context_snippets: int = 8,
    effort: str | None = None,
) -> dict[str, Any]:
    """Generate an operational creative plan for an agent's current task.

    Use quick for cheap normal coding loops, standard when a first repair fails,
    and deep for deliberate planning before high-impact edits.
    """
    defaults = RuntimeDefaults.from_environment()
    request: dict[str, Any] = {
        "goal": goal,
        "provider_mode": provider_mode or defaults.provider_mode,
        "privacy": privacy or defaults.privacy,
        "effort": effort or defaults.effort,
        "repo_signals": repo_signals or {},
        "max_calls": max_calls,
        "max_context_snippets": max_context_snippets,
    }
    if budget_usd is None and defaults.budget_usd is not None:
        budget_usd = defaults.budget_usd
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
