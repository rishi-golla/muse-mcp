from __future__ import annotations

import argparse
import asyncio
import json
from collections.abc import Sequence
from typing import Any

from creativity_layer.mcp_server import build_mcp_server


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="creativity-layer-mcp-smoke",
        description="Invoke the creativity-layer MCP tool in-process.",
    )
    parser.add_argument("goal")
    parser.add_argument("--provider-mode", default="deterministic")
    parser.add_argument("--privacy", default="research")
    parser.add_argument("--budget-usd", type=float, default=0.35)
    parser.add_argument("--seed-count", type=int, default=4)
    parser.add_argument("--finalist-count", type=int, default=2)
    parser.add_argument("--generations", type=int, default=1)
    parser.add_argument("--repo-language", action="append", default=[])
    parser.add_argument("--repo-framework", action="append", default=[])
    parser.add_argument("--changed-file", action="append", default=[])
    parser.add_argument("--test-command", action="append", default=[])
    parser.add_argument("--ci-log", action="append", default=[])
    return parser


async def _call_smoke_tool(arguments: dict[str, Any]) -> dict[str, Any]:
    server = build_mcp_server()
    _content_blocks, structured_result = await server.call_tool(
        "creative_plan",
        arguments,
    )
    if not isinstance(structured_result, dict):
        raise RuntimeError("MCP smoke call did not return structured output")
    return structured_result


def run_smoke(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo_signals = {
        "detected_languages": args.repo_language,
        "detected_frameworks": args.repo_framework,
        "changed_files": args.changed_file,
        "test_commands": args.test_command,
        "ci_logs": args.ci_log,
    }
    payload = asyncio.run(
        _call_smoke_tool(
            {
                "goal": args.goal,
                "provider_mode": args.provider_mode,
                "privacy": args.privacy,
                "repo_signals": repo_signals,
                "budget_usd": args.budget_usd,
                "seed_count": args.seed_count,
                "finalist_count": args.finalist_count,
                "max_generations": args.generations,
            }
        )
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload.get("finalist_count", 0) > 0 else 1


def main(argv: Sequence[str] | None = None) -> int:
    return run_smoke(argv)


if __name__ == "__main__":
    raise SystemExit(main())
