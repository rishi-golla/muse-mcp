from __future__ import annotations

import argparse
from collections.abc import Sequence

from muse.mcp_config import render_mcp_config


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="muse-mcp-config",
        description="Print host-specific Muse MCP config snippets.",
    )
    parser.add_argument(
        "--host",
        choices=("codex", "claude-code", "generic-json"),
        required=True,
    )
    parser.add_argument(
        "--include-env",
        action="store_true",
        help="Include live OpenAI env placeholders in the generated config.",
    )
    parser.add_argument(
        "--format",
        choices=("snippet", "text"),
        default="snippet",
        help="Print only the config snippet or a short setup note.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    snippet = render_mcp_config(host=args.host, include_env=args.include_env)
    if args.format == "text":
        print(f"# Muse MCP config for {snippet.host}")
        print(snippet.install_hint)
        print()
        print(snippet.content, end="")
        print()
        print("Before starting the agent host, run: muse-mcp-doctor --json")
        print("After wiring the host, run: muse-mcp-smoke \"Design a retry strategy\"")
    else:
        print(snippet.content, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
