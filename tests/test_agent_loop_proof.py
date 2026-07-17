from __future__ import annotations

import sys
import tomllib
from pathlib import Path

from muse.agent_loop_proof import (
    create_sample_retry_repo,
    run_agent_loop_proof,
    run_verification,
)


def test_sample_repo_starts_with_failing_verification(tmp_path) -> None:
    repo_path = create_sample_retry_repo(tmp_path / "sample-repo")

    result = run_verification(repo_path)

    assert result.exit_code != 0
    assert result.command == (sys.executable, "-m", "pytest", "-q")
    assert "test_retry_delay_increases" in result.combined_output
    assert "pytest_asyncio" not in result.combined_output


def test_sample_repo_creation_removes_stale_generated_files(tmp_path) -> None:
    repo_path = create_sample_retry_repo(tmp_path / "sample-repo")
    (repo_path / "test_stale.py").write_text(
        "def test_stale_failure():\n    assert False\n",
        encoding="utf-8",
    )

    create_sample_retry_repo(repo_path)
    stale_files = sorted(path.name for path in repo_path.glob("test_stale.py"))

    assert stale_files == []


def test_agent_loop_proof_calls_mcp_and_repairs_sample_repo(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("MUSE_ENABLE_TEST_PROVIDER", "1")

    result = run_agent_loop_proof(tmp_path / "workspace")

    assert result["passed"] is True
    assert result["initial_verification"]["exit_code"] != 0
    assert result["final_verification"]["exit_code"] == 0
    assert result["mcp_result"]["provider_mode"] == "deterministic"
    assert result["mcp_result"]["errors"] == []
    assert result["mcp_result"]["finalist_count"] == 2
    assert "python" in result["mcp_result"]["context_tags"]
    assert "pytest" in result["mcp_result"]["context_tags"]
    assert result["repo_signals"]["changed_files"] == ["retry_policy.py"]
    assert result["repo_signals"]["test_commands"] == ["python -m pytest -q"]
    assert result["repair"]["changed_files"] == ["retry_policy.py"]
    assert result["selected_plan"]["agent_workflow"]
    assert result["selected_plan"]["verification_strategy"]


def test_agent_loop_proof_console_script_is_registered() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    assert pyproject["project"]["scripts"]["muse-agent-proof"] == (
        "muse.agent_loop_proof:main"
    )
