from __future__ import annotations

import sys
import tomllib
from pathlib import Path

from creativity_layer.agent_loop_proof import (
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


def test_agent_loop_proof_calls_mcp_and_repairs_sample_repo(tmp_path) -> None:
    result = run_agent_loop_proof(tmp_path / "workspace")

    assert result["passed"] is True
    assert result["initial_verification"]["exit_code"] != 0
    assert result["final_verification"]["exit_code"] == 0
    assert result["mcp_result"]["provider_mode"] == "deterministic"
    assert "python" in result["mcp_result"]["context_tags"]
    assert "pytest" in result["mcp_result"]["context_tags"]
    assert result["repo_signals"]["changed_files"] == ["retry_policy.py"]
    assert result["repo_signals"]["test_commands"] == ["python -m pytest -q"]
    assert result["repair"]["changed_files"] == ["retry_policy.py"]
    assert result["selected_plan"]["agent_workflow"]
    assert result["selected_plan"]["verification_strategy"]


def test_agent_loop_proof_console_script_and_docs_are_registered() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    proof_doc = Path("docs/integrations/agent-loop-proof.md")
    readme = Path("README.md").read_text(encoding="utf-8")

    assert pyproject["project"]["scripts"]["creativity-layer-agent-proof"] == (
        "creativity_layer.agent_loop_proof:main"
    )
    assert proof_doc.exists()

    proof_text = proof_doc.read_text(encoding="utf-8").casefold()
    assert "mcp" in proof_text
    assert "deterministic" in proof_text
    assert "bounded repair" in proof_text
    assert "creativity-layer-agent-proof" in proof_text
    assert "docs/integrations/agent-loop-proof.md" in readme
