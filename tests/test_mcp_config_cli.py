from __future__ import annotations

import json
import tomllib
from pathlib import Path

from muse.mcp_config import HostConfigFormat, render_mcp_config
from muse.mcp_config_cli import main


def test_render_codex_config_outputs_valid_toml() -> None:
    snippet = render_mcp_config(host="codex", include_env=False)
    parsed = tomllib.loads(snippet.content)
    server = parsed["mcp_servers"]["muse"]

    assert snippet.format is HostConfigFormat.TOML
    assert server["command"] == "muse-mcp"
    assert server["args"] == []
    assert server["enabled_tools"] == ["muse_plan"]
    assert "env" not in server


def test_render_claude_code_config_can_include_live_env_placeholders() -> None:
    snippet = render_mcp_config(host="claude-code", include_env=True)
    parsed = json.loads(snippet.content)
    server = parsed["mcpServers"]["muse"]

    assert snippet.format is HostConfigFormat.JSON
    assert server["command"] == "muse-mcp"
    assert server["args"] == []
    assert server["env"]["OPENAI_API_KEY"] == "${OPENAI_API_KEY}"
    assert server["env"]["OPENAI_ECONOMY_MODEL"] == "${OPENAI_ECONOMY_MODEL}"
    assert "OPENAI_PRICING_FILE" not in server["env"]


def test_render_generic_json_config_omits_env_by_default() -> None:
    snippet = render_mcp_config(host="generic-json", include_env=False)
    parsed = json.loads(snippet.content)
    server = parsed["mcpServers"]["muse"]

    assert snippet.format is HostConfigFormat.JSON
    assert server == {"command": "muse-mcp", "args": []}


def test_mcp_config_cli_prints_snippet(capsys) -> None:
    exit_code = main(["--host", "codex"])

    output = capsys.readouterr()
    parsed = tomllib.loads(output.out)
    assert exit_code == 0
    assert parsed["mcp_servers"]["muse"]["command"] == "muse-mcp"
    assert output.err == ""


def test_mcp_config_cli_text_format_includes_install_hint(capsys) -> None:
    exit_code = main(["--host", "generic-json", "--format", "text"])

    output = capsys.readouterr()
    assert exit_code == 0
    assert "muse-mcp" in output.out
    assert "muse-mcp-doctor --json" in output.out
    assert "muse-mcp-smoke" in output.out


def test_package_exposes_mcp_config_console_script() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    assert pyproject["project"]["scripts"]["muse-mcp-config"] == (
        "muse.mcp_config_cli:main"
    )
