from __future__ import annotations

import argparse
import json
from collections.abc import Sequence

from muse.agent_instructions import render_agent_instructions


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="muse-agent-instructions",
        description="Print project instructions for using Muse through MCP.",
    )
    parser.add_argument(
        "--target",
        choices=("agents-md", "cursor-rules", "claude-project", "generic"),
        required=True,
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    document = render_agent_instructions(target=args.target)
    if args.format == "json":
        print(json.dumps(document.model_dump(mode="json"), indent=2, sort_keys=True))
    else:
        print(f"# Recommended file: {document.recommended_file}")
        print()
        print(document.content, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
