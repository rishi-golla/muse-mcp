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
    parser.add_argument("--provider-mode")
    parser.add_argument("--privacy")
    parser.add_argument("--effort", choices=("quick", "standard", "deep"))
    parser.add_argument("--budget-usd", type=float)
    parser.add_argument("--seed-count", type=int)
    parser.add_argument("--finalist-count", type=int)
    parser.add_argument("--generations", type=int)
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
    arguments: dict[str, Any] = {
        "goal": args.goal,
        "repo_signals": repo_signals,
        **_optional_run_config(args),
    }
    for key, value in (
        ("provider_mode", args.provider_mode),
        ("privacy", args.privacy),
        ("effort", args.effort),
    ):
        if value is not None:
            arguments[key] = value
    payload = asyncio.run(
        _call_smoke_tool(
            arguments,
        )
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload.get("finalist_count", 0) > 0 else 1


def main(argv: Sequence[str] | None = None) -> int:
    return run_smoke(argv)


def _optional_run_config(args: argparse.Namespace) -> dict[str, float | int]:
    config: dict[str, float | int] = {}
    if args.budget_usd is not None:
        config["budget_usd"] = args.budget_usd
    if args.seed_count is not None:
        config["seed_count"] = args.seed_count
    if args.finalist_count is not None:
        config["finalist_count"] = args.finalist_count
    if args.generations is not None:
        config["max_generations"] = args.generations
    return config


if __name__ == "__main__":
    raise SystemExit(main())
