from __future__ import annotations

import sys

from creativity_layer.agent_loop_proof import create_sample_retry_repo, run_verification


def test_sample_repo_starts_with_failing_verification(tmp_path) -> None:
    repo_path = create_sample_retry_repo(tmp_path / "sample-repo")

    result = run_verification(repo_path)

    assert result.exit_code != 0
    assert result.command == (sys.executable, "-m", "pytest", "-q")
    assert "test_retry_delay_increases" in result.combined_output
