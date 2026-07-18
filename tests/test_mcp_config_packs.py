from __future__ import annotations

import json
import tomllib
from pathlib import Path

from muse.mcp_config import render_mcp_config

ROOT = Path(__file__).resolve().parents[1]


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_codex_config_generator_returns_valid_toml_and_scopes_tool() -> None:
    snippet = render_mcp_config(host="codex")
    config = tomllib.loads(snippet.content)
    server = config["mcp_servers"]["muse"]

    assert snippet.host == "codex"
    assert snippet.format == "toml"
    assert server["command"] == "muse-mcp"
    assert server["args"] == []
    assert server["enabled"] is True
    assert server["enabled_tools"] == ["muse_plan"]
    assert server["tool_timeout_sec"] >= 60


def test_claude_code_config_generator_returns_valid_mcp_json() -> None:
    snippet = render_mcp_config(host="claude-code", include_env=True)
    config = json.loads(snippet.content)
    server = config["mcpServers"]["muse"]

    assert snippet.host == "claude-code"
    assert snippet.format == "json"
    assert server["command"] == "muse-mcp"
    assert server["args"] == []
    assert server["env"]["OPENAI_API_KEY"] == "${OPENAI_API_KEY}"
    assert server["env"]["OPENAI_ECONOMY_MODEL"] == "${OPENAI_ECONOMY_MODEL}"
    assert server["env"]["OPENAI_STRONG_MODEL"] == "${OPENAI_STRONG_MODEL}"


def test_generic_json_config_generator_is_provider_env_free() -> None:
    snippet = render_mcp_config(host="generic-json")
    config = json.loads(snippet.content)
    server = config["mcpServers"]["muse"]

    assert snippet.host == "generic-json"
    assert snippet.format == "json"
    assert server["command"] == "muse-mcp"
    assert server["args"] == []
    assert "env" not in server


def test_generated_configs_and_readme_do_not_contain_real_secrets() -> None:
    combined = "\n".join(
        (
            _read_text(ROOT / "README.md"),
            render_mcp_config(host="codex", include_env=True).content,
            render_mcp_config(host="claude-code", include_env=True).content,
            render_mcp_config(host="generic-json", include_env=True).content,
        )
    )

    assert "sk-" not in combined
    assert "gho_" not in combined
    assert "your-api-key" not in combined.casefold()
