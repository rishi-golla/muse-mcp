from __future__ import annotations

import json
import tomllib
from pathlib import Path

from muse.agent_instructions import render_agent_instructions
from muse.agent_instructions_cli import main


def test_render_agents_md_instructions_include_muse_workflow_contract() -> None:
    document = render_agent_instructions(target="agents-md")

    assert document.target == "agents-md"
    assert document.recommended_file == "AGENTS.md"
    assert "muse_plan" in document.content
    assert "repo_signals" in document.content
    assert "automatically" in document.content
    assert 'mode: "normal"' in document.content
    assert 'mode: "extensive"' in document.content
    assert "Do not ask the human for seed counts" in document.content
    assert "Do not ask Muse to crawl the repo" in document.content
    assert "Do not treat finalists as applied code" in document.content
    assert "run repository-owned verification" in document.content
    assert "provider_mode" not in document.content
    assert "deterministic" not in document.content.casefold()


def test_render_cursor_rules_instructions_are_cursor_friendly() -> None:
    document = render_agent_instructions(target="cursor-rules")

    assert document.recommended_file == ".cursor/rules/muse.mdc"
    assert "Always call the Muse MCP tool" in document.content
    assert 'mode: "normal"' in document.content
    assert 'mode: "extensive"' in document.content


def test_render_generic_instructions_are_host_neutral() -> None:
    document = render_agent_instructions(target="generic")

    assert document.recommended_file == "project instructions"
    assert "When a task needs creative planning" in document.content
    assert "muse_plan" in document.content


def test_agent_instructions_cli_prints_text(capsys) -> None:
    exit_code = main(["--target", "agents-md"])

    output = capsys.readouterr()
    assert exit_code == 0
    assert "AGENTS.md" in output.out
    assert "muse_plan" in output.out
    assert output.err == ""


def test_agent_instructions_cli_prints_json(capsys) -> None:
    exit_code = main(["--target", "generic", "--format", "json"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["target"] == "generic"
    assert payload["recommended_file"] == "project instructions"
    assert "muse_plan" in payload["content"]


def test_package_exposes_agent_instructions_console_script() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    assert pyproject["project"]["scripts"]["muse-agent-instructions"] == (
        "muse.agent_instructions_cli:main"
    )
