from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from muse.external_dogfood import run_external_dogfood


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="muse-external-dogfood",
        description="Create a throwaway external repo for testing Muse MCP onboarding.",
    )
    parser.add_argument(
        "--workspace",
        type=Path,
        default=Path(".muse-external-dogfood-repo"),
        help="Path to create or refresh for the external dogfood repo.",
    )
    parser.add_argument(
        "--host",
        choices=("codex", "claude-code", "generic-json"),
        default="generic-json",
    )
    parser.add_argument(
        "--instruction-target",
        choices=("agents-md", "cursor-rules", "claude-project", "generic"),
        default="agents-md",
    )
    parser.add_argument(
        "--include-env",
        action="store_true",
        help="Include live OpenAI env placeholders in generated MCP config.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace an existing marked dogfood workspace.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the report as JSON.",
    )
    parser.add_argument(
        "--strict-live",
        action="store_true",
        help="Exit non-zero when live OpenAI preflight is not ready.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = run_external_dogfood(
            workspace=args.workspace,
            host=args.host,
            instruction_target=args.instruction_target,
            include_env=args.include_env,
            force=args.force,
        )
    except ValueError as error:
        print(str(error))
        return 2

    if args.json:
        print(json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True))
    else:
        _print_text_report(report)

    if args.strict_live and not report.ready_for_manual_agent_test:
        return 1
    return 0


def _print_text_report(report) -> None:
    print(f"workspace: {report.workspace}")
    print(f"host_config_path: {report.host_config_path}")
    print(f"instructions_path: {report.instructions_path}")
    print(f"doctor_status: {report.doctor_status}")
    print(f"ready_for_manual_agent_test: {str(report.ready_for_manual_agent_test).lower()}")
    print("next_steps:")
    for step in report.next_steps:
        print(f"- {step}")


if __name__ == "__main__":
    raise SystemExit(main())
