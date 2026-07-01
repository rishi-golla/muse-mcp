from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class VerificationResult:
    command: tuple[str, ...]
    exit_code: int
    stdout: str
    stderr: str

    @property
    def combined_output(self) -> str:
        return "\n".join(part for part in (self.stdout, self.stderr) if part)


def create_sample_retry_repo(repo_path: Path) -> Path:
    repo_path.mkdir(parents=True, exist_ok=True)
    (repo_path / "retry_policy.py").write_text(
        "\n".join(
            [
                "def next_retry_delay(attempt: int) -> int:",
                "    return 1",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (repo_path / "test_retry_policy.py").write_text(
        "\n".join(
            [
                "from retry_policy import next_retry_delay",
                "",
                "",
                "def test_retry_delay_increases():",
                "    assert next_retry_delay(3) > next_retry_delay(1)",
                "",
                "",
                "def test_retry_delay_is_capped():",
                "    assert next_retry_delay(10) <= 30",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return repo_path


def run_verification(repo_path: Path) -> VerificationResult:
    command = (sys.executable, "-m", "pytest", "-q")
    completed = subprocess.run(
        command,
        cwd=repo_path,
        capture_output=True,
        check=False,
        text=True,
        timeout=30,
    )
    return VerificationResult(
        command=command,
        exit_code=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )
