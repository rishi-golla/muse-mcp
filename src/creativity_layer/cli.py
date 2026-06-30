from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from openai import OpenAI
from pydantic import ValidationError

from creativity_layer.calibration_packets import ReviewPacketStore, build_review_packet
from creativity_layer.deterministic import DeterministicCreativeProvider
from creativity_layer.engine import CreativeEngine
from creativity_layer.live_config import (
    LiveModelConfig,
    OpenAICredentials,
    PrivacyMode,
)
from creativity_layer.models import RunConfig, RunResult, TaskContext
from creativity_layer.models import ContextBundle
from creativity_layer.openai_provider import OpenAICreativeProvider
from creativity_layer.pricing import PricingTable
from creativity_layer.privacy import TraceView
from creativity_layer.reliability import CircuitBreaker, RetryPolicy
from creativity_layer.search import DeterministicSearchProvider
from creativity_layer.search_pipeline import SearchAwareEngine
from creativity_layer.tracing import JsonTraceStore

COMMANDS = frozenset({"deterministic", "live", "compare", "review-packet"})


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="creativity-layer",
        description="Run the Creativity Layer research spine.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    deterministic = subparsers.add_parser(
        "deterministic",
        help="Run with the deterministic local provider.",
    )
    deterministic.add_argument("goal")
    deterministic.add_argument("--trace-dir", type=Path, default=Path(".traces"))
    deterministic.add_argument("--seed-count", type=int, default=4)
    deterministic.add_argument("--finalist-count", type=int, default=3)
    deterministic.add_argument("--generations", type=int, default=1)
    deterministic.add_argument("--max-cost-usd", type=float, default=1.0)
    deterministic.add_argument("--max-calls", type=int, default=30)
    deterministic.add_argument("--context-file", type=Path)

    compare = subparsers.add_parser(
        "compare",
        help="Compare deterministic baseline and no-network search-aware runs.",
    )
    compare.add_argument("goal")
    compare.add_argument("--trace-dir", type=Path, default=Path(".traces"))
    compare.add_argument("--seed-count", type=int, default=4)
    compare.add_argument("--finalist-count", type=int, default=2)
    compare.add_argument("--generations", type=int, default=0)
    compare.add_argument("--budget-usd", type=float, default=0.10)
    compare.add_argument("--context-file", type=Path)

    review_packet = subparsers.add_parser(
        "review-packet",
        help="Generate anonymized calibration review packets from trace files.",
    )
    review_packet.add_argument("--trace", type=Path, action="append", required=True)
    review_packet.add_argument("--output-dir", type=Path, default=Path(".review-packets"))
    review_packet.add_argument("--shuffle-seed", type=int, default=0)

    live = subparsers.add_parser(
        "live",
        help="Run with the live OpenAI provider.",
    )
    live.add_argument("goal")
    live.add_argument("--budget-usd", type=float, default=0.10)
    live.add_argument("--seed-count", type=int, default=4)
    live.add_argument("--finalist-count", type=int, default=2)
    live.add_argument("--generations", type=int, default=1)
    live.add_argument("--trace-dir", type=Path, default=Path(".traces"))
    live.add_argument(
        "--privacy",
        choices=tuple(mode.value for mode in PrivacyMode),
        default=PrivacyMode.RESEARCH.value,
    )
    live.add_argument("--economy-model")
    live.add_argument("--strong-model")
    live.add_argument("--embedding-model")
    live.add_argument("--timeout-seconds", type=float)
    live.add_argument("--max-retries", type=int)
    live.add_argument("--pricing-file", type=Path)
    live.add_argument("--context-file", type=Path)
    return parser


def _normalize_argv(argv: Sequence[str] | None) -> list[str]:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments and arguments[0] not in COMMANDS and arguments[0] not in {
        "-h",
        "--help",
    }:
        arguments.insert(0, "deterministic")
    return arguments


def _validation_message(error: ValidationError) -> str:
    message = error.errors()[0]["msg"]
    return message.removeprefix("Value error, ").removeprefix("Input should be ")


def _load_context_bundle(path: Path | None) -> ContextBundle:
    if path is None:
        return ContextBundle()
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except OSError as error:
        raise ValueError(f"could not read context file {path}: {error}") from error
    except json.JSONDecodeError as error:
        raise ValueError(f"could not read context file {path}: {error.msg}") from error
    try:
        return ContextBundle.model_validate(payload)
    except ValidationError as error:
        raise ValueError(
            f"invalid context file {path}: {_validation_message(error)}"
        ) from error


def _save_and_print_summary(
    result,
    *,
    trace_root: Path,
    trace_view: TraceView | None = None,
) -> int:
    resolved_trace_root = trace_root.resolve()
    try:
        trace_path = JsonTraceStore(
            resolved_trace_root,
            trace_view=trace_view,
        ).save(result)
    except OSError as error:
        print(
            f"error: could not write trace to {resolved_trace_root}: {error}",
            file=sys.stderr,
        )
        return 1

    def summary_value(value: object) -> object:
        if trace_view is None:
            return value
        return trace_view.sanitize(value)

    unevaluated_candidates = tuple(
        candidate for candidate in result.all_candidates if candidate.scores is None
    )
    print(
        json.dumps(
            {
                "run_id": str(result.run_id),
                "finalist_count": len(result.finalists),
                "generated_count": len(result.all_candidates),
                "unevaluated_count": len(unevaluated_candidates),
                "stopped_reason": result.stopped_reason,
                "trace_path": str(trace_path),
                "finalists": [
                    {
                        "title": summary_value(candidate.title),
                        "originality": candidate.scores.originality
                        if candidate.scores is not None
                        else None,
                        "usefulness": candidate.scores.usefulness
                        if candidate.scores is not None
                        else None,
                    }
                    for candidate in result.finalists
                ],
                "unevaluated_candidates": [
                    {"title": summary_value(candidate.title)}
                    for candidate in unevaluated_candidates
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


def _run_deterministic(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    try:
        task = TaskContext(
            goal=args.goal,
            context_bundle=_load_context_bundle(args.context_file),
        )
        config = RunConfig(
            max_cost_usd=args.max_cost_usd,
            max_calls=args.max_calls,
            max_generations=args.generations,
            seed_count=args.seed_count,
            finalist_count=args.finalist_count,
            framing_reserve_usd=0,
            finalization_reserve_usd=0,
        )
    except ValidationError as error:
        parser.error(_validation_message(error))
    except ValueError as error:
        parser.error(str(error))

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
    return _save_and_print_summary(result, trace_root=args.trace_dir)


def _save_compare_trace(result, *, trace_root: Path) -> Path:
    return JsonTraceStore(trace_root.resolve()).save(result)


def _run_compare(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    try:
        task = TaskContext(
            goal=args.goal,
            context_bundle=_load_context_bundle(args.context_file),
        )
        config = RunConfig(
            max_cost_usd=args.budget_usd,
            max_calls=30,
            max_generations=args.generations,
            seed_count=args.seed_count,
            finalist_count=args.finalist_count,
            framing_reserve_usd=0,
            finalization_reserve_usd=0,
        )
    except ValidationError as error:
        parser.error(_validation_message(error))
    except ValueError as error:
        parser.error(str(error))

    baseline_provider = DeterministicCreativeProvider()
    baseline_result = CreativeEngine(
        framer=baseline_provider,
        seeder=baseline_provider,
        transformer=baseline_provider,
        evaluator=baseline_provider,
    ).run(task, config)

    search_aware_result = SearchAwareEngine(
        creative_provider=DeterministicCreativeProvider(),
        search_provider=DeterministicSearchProvider(),
    ).run(task, config)

    try:
        baseline_trace_path = _save_compare_trace(
            baseline_result,
            trace_root=args.trace_dir,
        )
        search_aware_trace_path = _save_compare_trace(
            search_aware_result,
            trace_root=args.trace_dir,
        )
    except OSError as error:
        resolved_trace_root = args.trace_dir.resolve()
        print(
            f"error: could not write trace to {resolved_trace_root}: {error}",
            file=sys.stderr,
        )
        return 1

    print(
        json.dumps(
            {
                "baseline": {
                    "trace_path": str(baseline_trace_path),
                    "finalist_count": len(baseline_result.finalists),
                    "stopped_reason": baseline_result.stopped_reason,
                },
                "search_aware": {
                    "trace_path": str(search_aware_trace_path),
                    "finalist_count": len(search_aware_result.finalists),
                    "stopped_reason": search_aware_result.stopped_reason,
                    "novelty_mode": "provisional_no_network",
                },
            },
            indent=2,
        )
    )
    return 0


def _load_trace(path: Path) -> RunResult:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise ValueError(f"could not read trace {path}: {error}") from error
    except json.JSONDecodeError as error:
        raise ValueError(f"invalid trace {path}: {error.msg}") from error

    try:
        return RunResult.model_validate(payload)
    except ValidationError as error:
        raise ValueError(f"invalid trace {path}: {_validation_message(error)}") from error


def _run_review_packet(args: argparse.Namespace) -> int:
    results: list[RunResult] = []
    for trace_path in args.trace:
        try:
            results.append(_load_trace(trace_path))
        except ValueError as error:
            print(f"error: {error}", file=sys.stderr)
            return 2

    try:
        packets = [
            build_review_packet(result, shuffle_seed=args.shuffle_seed)
            for result in results
        ]
    except ValidationError as error:
        print(f"error: invalid trace: {_validation_message(error)}", file=sys.stderr)
        return 2

    store = ReviewPacketStore(args.output_dir.resolve())
    saved_packets = []
    try:
        for packet in packets:
            path = store.save(packet)
            saved_packets.append(
                {
                    "packet_id": packet.packet_id,
                    "path": str(path.resolve()),
                    "candidate_count": len(packet.candidates),
                }
            )
    except OSError as error:
        print(
            f"error: could not write review packet to {args.output_dir.resolve()}: {error}",
            file=sys.stderr,
        )
        return 1

    print(
        json.dumps(
            {
                "packet_count": len(saved_packets),
                "packets": saved_packets,
            },
            indent=2,
        )
    )
    return 0


def _configuration_error(parser: argparse.ArgumentParser, message: str) -> int:
    parser.print_usage(sys.stderr)
    print(f"{parser.prog}: error: {message}", file=sys.stderr)
    return 2


def _live_config_from_args(args: argparse.Namespace) -> LiveModelConfig:
    economy_model = args.economy_model or os.getenv("OPENAI_ECONOMY_MODEL")
    strong_model = args.strong_model or os.getenv("OPENAI_STRONG_MODEL")
    if (
        not economy_model
        or not economy_model.strip()
        or not strong_model
        or not strong_model.strip()
    ):
        raise ValueError("OPENAI_ECONOMY_MODEL and OPENAI_STRONG_MODEL are required")

    values: dict[str, object] = {
        "economy_model": economy_model.strip(),
        "strong_model": strong_model.strip(),
        "embedding_model": (
            args.embedding_model
            or os.getenv("OPENAI_EMBEDDING_MODEL")
            or "text-embedding-3-small"
        ),
        "default_budget_usd": args.budget_usd,
        "privacy_mode": PrivacyMode(args.privacy),
    }
    if args.timeout_seconds is not None:
        values["timeout_seconds"] = args.timeout_seconds
    if args.max_retries is not None:
        values["max_retries"] = args.max_retries
    return LiveModelConfig.model_validate(values)


def _load_pricing_table(args: argparse.Namespace) -> PricingTable:
    raw_path = args.pricing_file or os.getenv("OPENAI_PRICING_FILE")
    if raw_path is None:
        raise ValueError("OPENAI_PRICING_FILE is required")
    path = Path(raw_path)
    try:
        payload = path.read_text(encoding="utf-8")
    except OSError as error:
        raise ValueError(f"could not read pricing config {path}: {error}") from error
    try:
        return PricingTable.model_validate_json(payload)
    except ValueError as error:
        raise ValueError(f"invalid pricing config {path}: {error}") from error


def _validate_live_pricing(config: LiveModelConfig, pricing: PricingTable) -> None:
    try:
        pricing.text_price(config.economy_model)
        pricing.text_price(config.strong_model)
        pricing.embedding_price(config.embedding_model)
    except KeyError as error:
        raise ValueError(str(error).strip("'")) from error


def _build_openai_provider(
    *,
    credentials: OpenAICredentials,
    config: LiveModelConfig,
    pricing: PricingTable,
) -> OpenAICreativeProvider:
    client = OpenAI(
        api_key=credentials.api_key.get_secret_value(),
        timeout=config.timeout_seconds,
        max_retries=0,
    )
    return OpenAICreativeProvider(
        client=client,
        config=config,
        pricing=pricing,
        retry_policy=RetryPolicy(max_retries=config.max_retries),
        breaker=CircuitBreaker(failure_threshold=config.circuit_failure_threshold),
    )


def _run_live(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    try:
        credentials = OpenAICredentials.from_environment()
        live_config = _live_config_from_args(args)
        pricing = _load_pricing_table(args)
        _validate_live_pricing(live_config, pricing)
        task = TaskContext(
            goal=args.goal,
            context_bundle=_load_context_bundle(args.context_file),
        )
        config = RunConfig(
            max_cost_usd=args.budget_usd,
            max_generations=args.generations,
            seed_count=args.seed_count,
            finalist_count=args.finalist_count,
            framing_reserve_usd=0,
            finalization_reserve_usd=0,
        )
    except ValidationError as error:
        return _configuration_error(parser, _validation_message(error))
    except ValueError as error:
        return _configuration_error(parser, str(error))

    provider = _build_openai_provider(
        credentials=credentials,
        config=live_config,
        pricing=pricing,
    )
    engine = CreativeEngine(
        framer=provider,
        seeder=provider,
        transformer=provider,
        evaluator=provider,
    )
    result = engine.run(task, config)
    return _save_and_print_summary(
        result,
        trace_root=args.trace_dir,
        trace_view=TraceView(
            mode=live_config.privacy_mode,
            secret_values=(credentials.api_key.get_secret_value(),),
        ),
    )


def run_cli(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(_normalize_argv(argv))
    if args.command == "compare":
        return _run_compare(args, parser)
    if args.command == "live":
        return _run_live(args, parser)
    if args.command == "review-packet":
        return _run_review_packet(args)
    return _run_deterministic(args, parser)


def main(argv: Sequence[str] | None = None) -> int:
    return run_cli(argv)


if __name__ == "__main__":
    raise SystemExit(main())
