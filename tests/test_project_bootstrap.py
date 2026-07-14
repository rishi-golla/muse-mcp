from __future__ import annotations

import json
from pathlib import Path

import pytest

from muse.project_bootstrap import run_project_bootstrap


def test_project_bootstrap_writes_generic_mcp_config_and_agents_md(
    tmp_path: Path,
) -> None:
    project = tmp_path / "repo"
    project.mkdir()

    report = run_project_bootstrap(project_path=project, environ={})

    encoded = json.dumps(report.model_dump(mode="json"))

    assert (project / ".mcp.json").exists()
    assert (project / "AGENTS.md").exists()
    assert report.project_path == str(project.resolve())
    assert report.host == "generic-json"
    assert report.instruction_target == "agents-md"
    assert report.dry_run is False
    assert report.planned_files == (".mcp.json", "AGENTS.md")
    assert report.written_files == (".mcp.json", "AGENTS.md")
    assert report.skipped_existing_files == ()
    assert report.doctor_status == "error"
    assert report.ready_for_manual_agent_test is False
    assert "muse-mcp-doctor --json" in "\n".join(report.next_steps)
    assert "deterministic" not in encoded.casefold()
    assert "provider_mode" not in encoded


def test_project_bootstrap_dry_run_writes_nothing(tmp_path: Path) -> None:
    project = tmp_path / "repo"
    project.mkdir()

    report = run_project_bootstrap(project_path=project, dry_run=True, environ={})

    assert report.dry_run is True
    assert report.planned_files == (".mcp.json", "AGENTS.md")
    assert report.written_files == ()
    assert not (project / ".mcp.json").exists()
    assert not (project / "AGENTS.md").exists()


def test_project_bootstrap_refuses_to_overwrite_existing_files(tmp_path: Path) -> None:
    project = tmp_path / "repo"
    project.mkdir()
    (project / "AGENTS.md").write_text("existing\n", encoding="utf-8")

    with pytest.raises(ValueError, match="refusing to overwrite existing files"):
        run_project_bootstrap(project_path=project, environ={})

    assert (project / "AGENTS.md").read_text(encoding="utf-8") == "existing\n"
    assert not (project / ".mcp.json").exists()


def test_project_bootstrap_force_overwrites_existing_targets(tmp_path: Path) -> None:
    project = tmp_path / "repo"
    project.mkdir()
    (project / "AGENTS.md").write_text("existing\n", encoding="utf-8")

    report = run_project_bootstrap(project_path=project, force=True, environ={})

    assert report.written_files == (".mcp.json", "AGENTS.md")
    assert "muse_plan" in (project / "AGENTS.md").read_text(encoding="utf-8")


def test_project_bootstrap_supports_codex_and_cursor_targets(tmp_path: Path) -> None:
    project = tmp_path / "repo"
    project.mkdir()

    report = run_project_bootstrap(
        project_path=project,
        host="codex",
        instruction_target="cursor-rules",
        include_env=True,
        environ={
            "OPENAI_API_KEY": "sk-test",
            "OPENAI_ECONOMY_MODEL": "gpt-5.4-mini",
            "OPENAI_STRONG_MODEL": "gpt-5.4",
        },
    )

    assert (project / ".codex" / "config.toml").exists()
    assert (project / ".cursor" / "rules" / "muse.mdc").exists()
    assert report.planned_files == (".codex/config.toml", ".cursor/rules/muse.mdc")
    assert report.doctor_status == "ok"
    assert report.ready_for_manual_agent_test is True
    assert "${OPENAI_API_KEY}" in (project / ".codex" / "config.toml").read_text(
        encoding="utf-8"
    )


def test_project_bootstrap_uses_local_preflight_without_openai_client(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project = tmp_path / "repo"
    project.mkdir()

    def fail_if_openai_client_is_constructed(*args, **kwargs):
        raise AssertionError("project bootstrap must not create an OpenAI client")

    monkeypatch.setattr("openai.OpenAI", fail_if_openai_client_is_constructed)

    report = run_project_bootstrap(project_path=project, environ={})

    assert report.doctor_status == "error"
    assert report.written_files == (".mcp.json", "AGENTS.md")
