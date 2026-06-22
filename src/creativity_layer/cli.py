from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from pydantic import ValidationError

from creativity_layer.deterministic import DeterministicCreativeProvider
from creativity_layer.engine import CreativeEngine
from creativity_layer.models import RunConfig, TaskContext
from creativity_layer.tracing import JsonTraceStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="creativity-layer",
        description="Run the deterministic Creativity Layer research spine.",
    )
    parser.add_argument("goal")
    parser.add_argument("--trace-dir", type=Path, default=Path(".traces"))
    parser.add_argument("--seed-count", type=int, default=4)
    parser.add_argument("--finalist-count", type=int, default=3)
    parser.add_argument("--generations", type=int, default=1)
    parser.add_argument("--max-cost-usd", type=float, default=1.0)
    parser.add_argument("--max-calls", type=int, default=30)
    return parser


def run_cli(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        task = TaskContext(goal=args.goal)
        config = RunConfig(
            max_cost_usd=args.max_cost_usd,
            max_calls=args.max_calls,
            max_generations=args.generations,
            seed_count=args.seed_count,
            finalist_count=args.finalist_count,
            framing_reserve_usd=0,
            finalization_reserve_usd=0.05,
        )
    except ValidationError as error:
        message = error.errors()[0]["msg"]
        message = message.removeprefix("Value error, ").removeprefix("Input should be ")
        parser.error(message)

    provider = DeterministicCreativeProvider()
    engine = CreativeEngine(
        framer=provider,
        seeder=provider,
        transformer=provider,
        evaluator=provider,
    )
    result = engine.run(
        task,
        config,
    )
    trace_root = args.trace_dir.resolve()
    try:
        trace_path = JsonTraceStore(trace_root).save(result)
    except OSError as error:
        print(
            f"error: could not write trace to {trace_root}: {error}",
            file=sys.stderr,
        )
        return 1

    print(
        json.dumps(
            {
                "run_id": str(result.run_id),
                "finalist_count": len(result.finalists),
                "stopped_reason": result.stopped_reason,
                "trace_path": str(trace_path),
                "finalists": [
                    {
                        "title": candidate.title,
                        "originality": candidate.scores.originality
                        if candidate.scores is not None
                        else None,
                        "usefulness": candidate.scores.usefulness
                        if candidate.scores is not None
                        else None,
                    }
                    for candidate in result.finalists
                ],
            },
            indent=2,
        )
    )
    has_usable_finalist = any(
        candidate.scores is not None for candidate in result.finalists
    )
    return int(
        result.stopped_reason == "provider_error" or not has_usable_finalist
    )


def main(argv: Sequence[str] | None = None) -> int:
    return run_cli(argv)


if __name__ == "__main__":
    raise SystemExit(main())
