from __future__ import annotations

import json
from enum import StrEnum

from muse.models import FrozenModel


class HostConfigFormat(StrEnum):
    JSON = "json"
    TOML = "toml"


class HostConfigSnippet(FrozenModel):
    host: str
    format: HostConfigFormat
    content: str
    install_hint: str


LIVE_ENV_PLACEHOLDERS = {
    "OPENAI_API_KEY": "${OPENAI_API_KEY}",
    "OPENAI_ECONOMY_MODEL": "${OPENAI_ECONOMY_MODEL}",
    "OPENAI_STRONG_MODEL": "${OPENAI_STRONG_MODEL}",
    "OPENAI_EMBEDDING_MODEL": "text-embedding-3-small",
}


def render_mcp_config(
    *,
    host: str,
    include_env: bool = False,
) -> HostConfigSnippet:
    normalized_host = host.casefold()
    if normalized_host == "codex":
        return _codex_config(include_env=include_env)
    if normalized_host == "claude-code":
        return _json_config(host="claude-code", include_env=include_env)
    if normalized_host == "generic-json":
        return _json_config(host="generic-json", include_env=include_env)
    raise ValueError("host must be one of: codex, claude-code, generic-json")


def _codex_config(*, include_env: bool) -> HostConfigSnippet:
    lines = [
        "[mcp_servers.muse]",
        'command = "muse-mcp"',
        "args = []",
        "enabled = true",
        'enabled_tools = ["muse_plan"]',
        "startup_timeout_sec = 10",
        "tool_timeout_sec = 120",
    ]
    if include_env:
        lines.extend(
            [
                "",
                "[mcp_servers.muse.env]",
                'OPENAI_API_KEY = "${OPENAI_API_KEY}"',
                'OPENAI_ECONOMY_MODEL = "${OPENAI_ECONOMY_MODEL}"',
                'OPENAI_STRONG_MODEL = "${OPENAI_STRONG_MODEL}"',
                'OPENAI_EMBEDDING_MODEL = "text-embedding-3-small"',
            ]
        )
    return HostConfigSnippet(
        host="codex",
        format=HostConfigFormat.TOML,
        content="\n".join(lines) + "\n",
        install_hint="Paste this into ~/.codex/config.toml or a project .codex/config.toml.",
    )


def _json_config(*, host: str, include_env: bool) -> HostConfigSnippet:
    server: dict[str, object] = {
        "command": "muse-mcp",
        "args": [],
    }
    if include_env:
        server["env"] = dict(LIVE_ENV_PLACEHOLDERS)
    payload = {
        "mcpServers": {
            "muse": server,
        }
    }
    hint = (
        "Paste this into a project .mcp.json file."
        if host == "claude-code"
        else "Paste this into any MCP client that accepts mcpServers JSON."
    )
    return HostConfigSnippet(
        host=host,
        format=HostConfigFormat.JSON,
        content=json.dumps(payload, indent=2, sort_keys=False) + "\n",
        install_hint=hint,
    )
