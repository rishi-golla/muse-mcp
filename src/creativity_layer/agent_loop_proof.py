from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from creativity_layer.mcp_server import build_mcp_server


@dataclass(frozen=True)
class VerificationResult:
    command: tuple[str, ...]
    exit_code: int
    stdout: str
    stderr: str

    @property
    def combined_output(self) -> str:
        return "\n".join(part for part in (self.stdout, self.stderr) if part)

    def to_dict(self) -> dict[str, Any]:
        return {
            "command": list(self.command),
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "combined_output": self.combined_output,
        }


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


def _build_repo_signals(
    repo_path: Path,
    failed_verification: VerificationResult,
) -> dict[str, list[str]]:
    return {
        "file_paths": [
            path.name
            for path in sorted(repo_path.iterdir())
            if path.is_file() and path.suffix in {".py", ".toml"}
        ],
        "changed_files": ["retry_policy.py"],
        "test_commands": ["python -m pytest -q"],
        "ci_logs": [_safe_signal_text(failed_verification.combined_output)],
        "detected_languages": ["Python"],
        "detected_frameworks": ["pytest"],
    }


def _safe_signal_text(value: str) -> str:
    visible_text = "".join(
        " " if unicodedata.category(character).startswith("C") else character
        for character in value
    )
    return " ".join(visible_text.split())


async def _call_creative_plan(repo_signals: dict[str, list[str]]) -> dict[str, Any]:
    server = build_mcp_server()
    _content_blocks, structured_result = await server.call_tool(
        "creative_plan",
        {
            "goal": "Design a bounded retry-policy repair after failing tests",
            "provider_mode": "deterministic",
            "privacy": "research",
            "repo_signals": repo_signals,
            "budget_usd": 0.20,
            "seed_count": 2,
            "finalist_count": 1,
            "max_generations": 0,
        },
    )
    if not isinstance(structured_result, dict):
        raise RuntimeError("MCP creative_plan did not return structured output")
    return structured_result


def _apply_bounded_repair(repo_path: Path) -> dict[str, list[str] | str]:
    (repo_path / "retry_policy.py").write_text(
        "\n".join(
            [
                "def next_retry_delay(attempt: int) -> int:",
                "    normalized_attempt = max(1, attempt)",
                "    return min(30, 2 ** (normalized_attempt - 1))",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return {
        "changed_files": ["retry_policy.py"],
        "rationale": "Replace constant retry delay with capped exponential backoff.",
    }


def _select_first_plan(mcp_result: dict[str, Any]) -> dict[str, Any]:
    finalists = mcp_result.get("finalists", [])
    if not finalists:
        return {}
    finalist = finalists[0]
    if not isinstance(finalist, dict):
        return {}
    return {
        "title": finalist.get("title"),
        "agent_workflow": finalist.get("agent_workflow", []),
        "decision_policy": finalist.get("decision_policy"),
        "verification_strategy": finalist.get("verification_strategy"),
        "failure_modes": finalist.get("failure_modes", []),
    }


def run_agent_loop_proof(workspace: Path) -> dict[str, Any]:
    repo_path = create_sample_retry_repo(workspace / "sample-repo")
    initial_verification = run_verification(repo_path)
    repo_signals = _build_repo_signals(repo_path, initial_verification)
    mcp_result = asyncio.run(_call_creative_plan(repo_signals))
    repair = _apply_bounded_repair(repo_path)
    final_verification = run_verification(repo_path)

    return {
        "passed": initial_verification.exit_code != 0 and final_verification.exit_code == 0,
        "sample_repo": str(repo_path),
        "repo_signals": repo_signals,
        "mcp_result": mcp_result,
        "selected_plan": _select_first_plan(mcp_result),
        "repair": repair,
        "initial_verification": initial_verification.to_dict(),
        "final_verification": final_verification.to_dict(),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="creativity-layer-agent-proof",
        description="Run a deterministic local proof that an agent loop can consume MCP planning.",
    )
    parser.add_argument(
        "--workspace",
        type=Path,
        default=Path(".agent-proof-tmp"),
        help="Directory where the generated sample repo should be created.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = run_agent_loop_proof(args.workspace)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
