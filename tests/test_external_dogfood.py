from __future__ import annotations

import json
from pathlib import Path

import pytest

from muse.external_dogfood import run_external_dogfood


def test_external_dogfood_creates_marked_sample_repo_with_muse_artifacts(
    tmp_path: Path,
) -> None:
    report = run_external_dogfood(
        workspace=tmp_path / "external-repo",
        host="generic-json",
        instruction_target="agents-md",
        environ={},
    )

    workspace = Path(report.workspace)
    created_files = set(report.created_files)

    assert (workspace / ".muse-external-dogfood").exists()
    assert (workspace / "pyproject.toml").exists()
    assert (workspace / "src" / "retry_policy.py").exists()
    assert (workspace / "tests" / "test_retry_policy.py").exists()
    assert (workspace / ".mcp.json").exists()
    assert (workspace / "AGENTS.md").exists()
    assert ".mcp.json" in created_files
    assert "AGENTS.md" in created_files
    assert report.host_config_path.endswith(".mcp.json")
    assert report.instructions_path.endswith("AGENTS.md")
    assert report.doctor_status == "error"
    assert report.pricing_source == "packaged:openai-pricing.example.json"
    assert report.mcp_smoke_status == "skipped"
    assert report.ready_for_manual_agent_test is False
    assert "muse-mcp-doctor --json" in "\n".join(report.next_steps)


def test_external_dogfood_report_is_json_safe_and_live_only(tmp_path: Path) -> None:
    report = run_external_dogfood(
        workspace=tmp_path / "external-repo",
        host="codex",
        instruction_target="cursor-rules",
        include_env=True,
        environ={
            "OPENAI_API_KEY": "sk-test",
            "OPENAI_ECONOMY_MODEL": "gpt-5.4-mini",
            "OPENAI_STRONG_MODEL": "gpt-5.4",
        },
    )

    payload = report.model_dump(mode="json")
    encoded = json.dumps(payload)

    assert payload["host"] == "codex"
    assert payload["instruction_target"] == "cursor-rules"
    assert payload["doctor_status"] == "ok"
    assert payload["ready_for_manual_agent_test"] is True
    assert "deterministic" not in encoded.casefold()
    assert "provider_mode" not in encoded


def test_external_dogfood_refuses_unmarked_existing_directory(tmp_path: Path) -> None:
    workspace = tmp_path / "real-repo"
    workspace.mkdir()
    (workspace / "README.md").write_text("do not replace\n", encoding="utf-8")

    with pytest.raises(ValueError, match="refusing to replace unmarked workspace"):
        run_external_dogfood(workspace=workspace, environ={})

    assert (workspace / "README.md").read_text(encoding="utf-8") == "do not replace\n"


def test_external_dogfood_force_replaces_marked_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "external-repo"
    run_external_dogfood(workspace=workspace, environ={})
    (workspace / "stale.txt").write_text("stale\n", encoding="utf-8")

    run_external_dogfood(workspace=workspace, force=True, environ={})

    assert not (workspace / "stale.txt").exists()
