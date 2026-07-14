from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from muse.project_bootstrap import run_project_bootstrap


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="muse-project-init",
        description="Write Muse MCP onboarding files into a project repository.",
    )
    parser.add_argument(
        "--project",
        type=Path,
        default=Path("."),
        help="Project directory to initialize. Defaults to the current directory.",
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
        "--dry-run",
        action="store_true",
        help="Preview files without writing them.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing generated target files.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the bootstrap report as JSON.",
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
        report = run_project_bootstrap(
            project_path=args.project,
            host=args.host,
            instruction_target=args.instruction_target,
            include_env=args.include_env,
            dry_run=args.dry_run,
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
    print(f"project_path: {report.project_path}")
    print(f"host: {report.host}")
    print(f"instruction_target: {report.instruction_target}")
    print(f"dry_run: {str(report.dry_run).lower()}")
    print(f"planned_files: {', '.join(report.planned_files)}")
    print(f"written_files: {', '.join(report.written_files)}")
    print(f"doctor_status: {report.doctor_status}")
    print(f"ready_for_manual_agent_test: {str(report.ready_for_manual_agent_test).lower()}")
    print("next_steps:")
    for step in report.next_steps:
        print(f"- {step}")


if __name__ == "__main__":
    raise SystemExit(main())
