from __future__ import annotations

import argparse
import json
from collections.abc import Sequence

from muse.live_preflight import (
    LivePreflightReport,
    LivePreflightStatus,
    check_live_openai_environment,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="muse-mcp-doctor",
        description="Check local Muse MCP live OpenAI configuration without provider calls.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the preflight report as JSON.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = check_live_openai_environment()
    if args.json:
        print(json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True))
    else:
        _print_human_report(report)
    return 0 if report.ok else 1


def _print_human_report(report: LivePreflightReport) -> None:
    print(f"Muse MCP live preflight: {report.status.value}")
    if report.pricing_source:
        print(f"Pricing: {report.pricing_source}")
    for check in report.checks:
        prefix = "OK" if check.status is LivePreflightStatus.OK else "ERROR"
        print(f"{prefix}: {check.name}: {check.message}")
    if report.action_items:
        print("Actions:")
        for item in report.action_items:
            print(f"- {item}")


if __name__ == "__main__":
    raise SystemExit(main())
