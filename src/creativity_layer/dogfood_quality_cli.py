from __future__ import annotations

import argparse
import json
from collections.abc import Sequence

from creativity_layer.dogfood_quality import run_dogfood_quality_suite


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="creativity-layer-dogfood-quality",
        description="Run the MCP dogfood quality suite.",
    )
    parser.add_argument("--provider-mode", default="deterministic")
    parser.add_argument("--effort", choices=("quick", "standard", "deep"), default="quick")
    parser.add_argument("--privacy", default="research")
    parser.add_argument("--budget-usd", type=float)
    parser.add_argument(
        "--search-provider",
        choices=("auto", "deterministic", "exa", "brave"),
        default="auto",
    )
    parser.add_argument(
        "--search-strict",
        dest="search_strict",
        action="store_true",
        default=False,
    )
    parser.add_argument("--case", dest="case_names", action="append")
    parser.add_argument("--variant", dest="variant_names", action="append")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-on-gates", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = run_dogfood_quality_suite(
        provider_mode=args.provider_mode,
        effort=args.effort,
        privacy=args.privacy,
        budget_usd=args.budget_usd,
        search_provider=args.search_provider,
        search_strict=args.search_strict,
        case_names=args.case_names,
        variant_names=args.variant_names,
    )
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        _print_text_report(report)
    if args.fail_on_gates and report["summary"]["failing_run_count"] > 0:
        return 1
    return 0


def _print_text_report(report: dict[str, object]) -> None:
    summary = report["summary"]
    if not isinstance(summary, dict):
        raise RuntimeError("dogfood report summary is not a dictionary")
    print(
        "Dogfood quality: "
        f"{summary['run_count']} runs, "
        f"{summary['failing_run_count']} with quality gates, "
        f"${summary['spend_usd']} spend"
    )
    for run in report["runs"]:
        if not isinstance(run, dict):
            continue
        gates = ", ".join(run["quality_gates"]) if run["quality_gates"] else "none"
        print(f"- {run['case']} / {run['variant']}: gates={gates}")


if __name__ == "__main__":
    raise SystemExit(main())
