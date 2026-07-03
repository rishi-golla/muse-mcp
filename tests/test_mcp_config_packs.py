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
    server = config["mcp_servers"]["muse"]

    assert server["command"] == "muse-mcp"
    assert server["args"] == []
    assert server["enabled"] is True
    assert server["enabled_tools"] == ["muse_plan"]
    assert server["tool_timeout_sec"] >= 60


def test_claude_code_config_pack_is_valid_mcp_json() -> None:
    config = json.loads(
        _read_text(CONFIG_ROOT / "claude-code" / ".mcp.json"),
    )
    server = config["mcpServers"]["muse"]

    assert server["command"] == "muse-mcp"
    assert server["args"] == []
    assert "OPENAI_API_KEY" in server["env"]
    assert server["env"]["OPENAI_API_KEY"] == "${OPENAI_API_KEY}"
    assert server["env"]["OPENAI_PRICING_FILE"] == "${OPENAI_PRICING_FILE}"


def test_codex_optional_env_example_is_valid_when_uncommented() -> None:
    text = _read_text(CONFIG_ROOT / "codex" / "config.toml")
    uncommented = text + "\n" + "\n".join(
        line.removeprefix("# ")
        for line in text.splitlines()
        if line.startswith("# [mcp_servers.") or line.startswith("# OPENAI_")
    )
    config = tomllib.loads(uncommented)
    env = config["mcp_servers"]["muse"]["env"]

    assert env["OPENAI_API_KEY"] == "${OPENAI_API_KEY}"
    assert env["OPENAI_PRICING_FILE"] == "${OPENAI_PRICING_FILE}"


def test_generic_mcp_json_pack_is_valid_and_provider_env_free() -> None:
    config = json.loads(
        _read_text(CONFIG_ROOT / "generic-mcp" / "mcp.json"),
    )
    server = config["mcpServers"]["muse"]

    assert server["command"] == "muse-mcp"
    assert server["args"] == []
    assert "env" not in server


def test_docs_describe_live_first_provider_posture() -> None:
    readme = _read_text(ROOT / "README.md")
    guide = _read_text(ROOT / "docs" / "integrations" / "mcp-agent-hosts.md")
    playbook = _read_text(ROOT / "docs" / "integrations" / "agent-dogfood-playbook.md")
    combined = "\n".join((readme, guide, playbook)).casefold()

    assert "live-first" in combined
    assert "muse_provider_mode" in combined
    assert "muse_effort" in combined
    assert "muse_privacy" in combined
    assert "muse_budget_usd" in combined
    assert "internal maintainer fixture" in combined
    assert "muse_enable_test_provider" in combined
    assert "--provider-mode deterministic" not in combined


def test_docs_describe_opt_in_search_context() -> None:
    readme = _read_text(ROOT / "README.md")
    guide = _read_text(ROOT / "docs" / "integrations" / "mcp-agent-hosts.md")
    playbook = _read_text(ROOT / "docs" / "integrations" / "agent-dogfood-playbook.md")
    combined = "\n".join((readme, guide, playbook)).casefold()

    assert "search_mode" in combined
    assert "muse_search_mode" in combined
    assert "search_provider" in combined
    assert "muse_search_provider" in combined
    assert "search_strict" in combined
    assert "muse_search_strict" in combined
    assert "--search-provider" in combined
    assert "--search-strict" in combined
    assert "strict search" in combined
    assert "muse_live_search_approved" in combined
    assert "default is `off`" in combined
    assert "opt-in search" in combined
    assert "--search-mode" in combined


def test_config_packs_do_not_contain_real_secrets() -> None:
    docs_to_scan = [
        ROOT / "README.md",
        ROOT / "docs" / "integrations" / "mcp-agent-hosts.md",
    ]
    combined = "\n".join(
        [
            *(
                path.read_text(encoding="utf-8")
                for path in CONFIG_ROOT.rglob("*")
                if path.is_file()
            ),
            *(path.read_text(encoding="utf-8") for path in docs_to_scan),
        ]
    )

    assert "sk-" not in combined
    assert "gho_" not in combined
    assert "your-api-key" not in combined.casefold()


def test_agent_host_guide_links_config_packs_and_smoke_workflow() -> None:
    guide = _read_text(ROOT / "docs" / "integrations" / "mcp-agent-hosts.md")

    assert "config-packs/codex/config.toml" in guide
    assert "config-packs/claude-code/.mcp.json" in guide
    assert "config-packs/generic-mcp/mcp.json" in guide
    assert "muse-mcp-config --host codex" in guide
    assert "muse-mcp-config --host claude-code --include-env" in guide
    assert "muse-agent-instructions --target agents-md" in guide
    assert "muse-agent-instructions --target cursor-rules" in guide
    assert "muse-external-dogfood" in guide
    assert "ready_for_manual_agent_test" in guide
    assert "docs/integrations/agent-dogfood-playbook.md" in guide
    assert "muse-mcp-smoke" in guide
    assert '"provider_mode": "live_openai"' in guide
    assert "muse_plan" in guide


def test_readme_links_agent_host_guide() -> None:
    readme = _read_text(ROOT / "README.md")

    assert "docs/integrations/mcp-agent-hosts.md" in readme
    assert "docs/integrations/agent-dogfood-playbook.md" in readme
    assert "muse-mcp-config --host codex" in readme
    assert "muse-agent-instructions --target agents-md" in readme
    assert "muse-external-dogfood" in readme


def test_agent_dogfood_playbook_describes_coding_loop_usage() -> None:
    playbook = _read_text(ROOT / "docs" / "integrations" / "agent-dogfood-playbook.md")

    assert "quick" in playbook
    assert "standard" in playbook
    assert "deep" in playbook
    assert "before-edit" in playbook
    assert "after-failure" in playbook
    assert "after-fix" in playbook
    assert "muse_plan" in playbook
    assert "repo_signals" in playbook


def test_docs_describe_v3l_dogfood_quality_suite() -> None:
    readme = _read_text(ROOT / "README.md")
    playbook = _read_text(ROOT / "docs" / "integrations" / "agent-dogfood-playbook.md")
    combined = "\n".join((readme, playbook)).casefold()

    assert "v3-l" in combined
    assert "last v3 validation slice" in combined
    assert "muse-dogfood-quality" in combined
    assert "--fail-on-gates" in combined
    assert "search-off" in combined
    assert "search-light" in combined
    assert "search-deep" in combined
    assert "deterministic output can intentionally fail quality gates" in combined


def test_dogfood_playbook_describes_v4b_live_quality_pressure() -> None:
    playbook = _read_text(ROOT / "docs" / "integrations" / "agent-dogfood-playbook.md")
    normalized = playbook.casefold()

    assert "v4-b" in normalized
    assert "live prompt pressure" in normalized
    assert "dogfood quality gates" in normalized
    assert "generic_title" in playbook
    assert "generic_mechanism" in playbook
    assert "missing_required_terms" in playbook


def test_docs_describe_v4c_quality_warning_fields() -> None:
    readme = _read_text(ROOT / "README.md")
    playbook = _read_text(ROOT / "docs" / "integrations" / "agent-dogfood-playbook.md")
    combined = "\n".join((readme, playbook)).casefold()

    assert "v4-c" in combined
    assert "quality_warnings" in combined
    assert "quality_summary" in combined
    assert "advisory" in combined


def test_docs_describe_v4d_quality_action_policy() -> None:
    readme = _read_text(ROOT / "README.md")
    playbook = _read_text(ROOT / "docs" / "integrations" / "agent-dogfood-playbook.md")
    combined = "\n".join((readme, playbook)).casefold()

    assert "v4-d" in combined
    assert "quality_action_policy" in combined
    assert "escalate_effort_to" in combined
    assert "recommended_actions" in combined


def test_docs_describe_v4e_suggested_next_call() -> None:
    playbook = _read_text(ROOT / "docs" / "integrations" / "agent-dogfood-playbook.md")
    normalized = playbook.casefold()

    assert "v4-e" in normalized
    assert "suggested_next_call" in playbook
    assert "repo_signal_requests" in playbook
    assert "automatic" in normalized


def test_docs_describe_v4f_agent_handoff() -> None:
    playbook = _read_text(ROOT / "docs" / "integrations" / "agent-dogfood-playbook.md")
    normalized = playbook.casefold()

    assert "v4-f" in normalized
    assert "agent_handoff" in playbook
    assert "recommended_action" in playbook
    assert "selected_finalist_id" in playbook
