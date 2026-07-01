from __future__ import annotations

import json
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG_ROOT = ROOT / "docs" / "integrations" / "config-packs"


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_codex_config_pack_is_valid_toml_and_scopes_tool() -> None:
    config = tomllib.loads(
        _read_text(CONFIG_ROOT / "codex" / "config.toml"),
    )
    server = config["mcp_servers"]["creativity-layer"]

    assert server["command"] == "creativity-layer-mcp"
    assert server["args"] == []
    assert server["enabled"] is True
    assert server["enabled_tools"] == ["creative_plan"]
    assert server["tool_timeout_sec"] >= 60


def test_claude_code_config_pack_is_valid_mcp_json() -> None:
    config = json.loads(
        _read_text(CONFIG_ROOT / "claude-code" / ".mcp.json"),
    )
    server = config["mcpServers"]["creativity-layer"]

    assert server["command"] == "creativity-layer-mcp"
    assert server["args"] == []
    assert "OPENAI_API_KEY" in server["env"]
    assert server["env"]["OPENAI_API_KEY"].startswith("<")


def test_generic_mcp_json_pack_is_valid_and_deterministic_by_default() -> None:
    config = json.loads(
        _read_text(CONFIG_ROOT / "generic-mcp" / "mcp.json"),
    )
    server = config["mcpServers"]["creativity-layer"]

    assert server["command"] == "creativity-layer-mcp"
    assert server["args"] == []
    assert "env" not in server


def test_config_packs_do_not_contain_real_secrets() -> None:
    combined = "\n".join(
        path.read_text(encoding="utf-8")
        for path in CONFIG_ROOT.rglob("*")
        if path.is_file()
    )

    assert "sk-" not in combined
    assert "gho_" not in combined
    assert "your-api-key" not in combined.casefold()


def test_agent_host_guide_links_config_packs_and_smoke_workflow() -> None:
    guide = _read_text(ROOT / "docs" / "integrations" / "mcp-agent-hosts.md")

    assert "config-packs/codex/config.toml" in guide
    assert "config-packs/claude-code/.mcp.json" in guide
    assert "config-packs/generic-mcp/mcp.json" in guide
    assert "creativity-layer-mcp-smoke" in guide
    assert '"provider_mode": "live_openai"' in guide
    assert "creative_plan" in guide


def test_readme_links_agent_host_guide() -> None:
    readme = _read_text(ROOT / "README.md")

    assert "docs/integrations/mcp-agent-hosts.md" in readme
