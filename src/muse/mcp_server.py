from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

from mcp.server.fastmcp import FastMCP

from muse.middleware import configuration_error_result, run_muse_plan
from muse.runtime_defaults import RuntimeDefaults

SERVER_NAME = "muse"


def muse_plan(
    goal: str,
    repo_signals: Mapping[str, object] | None = None,
    mode: str | None = None,
    provider_mode: str | None = None,
    privacy: str | None = None,
    max_context_snippets: int = 8,
    search_mode: str | None = None,
    search_provider: str | None = None,
    search_strict: bool | None = None,
) -> dict[str, Any]:
    """Generate an operational creative plan for an agent's current task.

    Use mode normal for most planning calls and extensive for high-impact or
    repeated-failure planning. Gather repo facts yourself and pass repo_signals.
    """
    try:
        defaults = RuntimeDefaults.resolve(
            provider_mode=provider_mode,
            privacy=privacy,
            mode=mode,
            search_mode=search_mode,
            search_provider=search_provider,
            search_strict=search_strict,
        )
    except ValueError as error:
        return configuration_error_result(
            provider_mode=provider_mode
            or os.getenv("MUSE_PROVIDER_MODE", "").strip()
            or "live_openai",
            message=str(error),
            search_provider=search_provider
            or os.getenv("MUSE_SEARCH_PROVIDER", "").strip()
            or "auto",
            search_strict=bool(search_strict),
        )
    request: dict[str, Any] = {
        "goal": goal,
        "provider_mode": defaults.provider_mode,
        "privacy": defaults.privacy,
        "mode": defaults.mode,
        "search_mode": defaults.search_mode,
        "search_provider": defaults.search_provider,
        "search_strict": defaults.search_strict,
        "repo_signals": repo_signals or {},
        "max_context_snippets": max_context_snippets,
    }
    return run_muse_plan(request)


def build_mcp_server() -> FastMCP:
    server = FastMCP(SERVER_NAME)
    server.tool()(muse_plan)
    return server


def main() -> None:
    build_mcp_server().run()


if __name__ == "__main__":
    main()
