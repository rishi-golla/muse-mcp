from __future__ import annotations

import os
from collections.abc import Mapping
from enum import StrEnum
from pathlib import Path
from typing import Any

from openai import OpenAI
from pydantic import Field, ValidationError

from creativity_layer.context_provider import (
    ContextProvider,
    DeterministicContextProvider,
    RepoSignals,
    build_task_context,
)
from creativity_layer.deterministic import DeterministicCreativeProvider
from creativity_layer.engine import CreativeEngine
from creativity_layer.live_config import LiveModelConfig, OpenAICredentials, PrivacyMode
from creativity_layer.models import FrozenModel, IdeaGenome, RunConfig, RunResult, TaskContext
from creativity_layer.openai_provider import OpenAICreativeProvider
from creativity_layer.pricing import PricingTable
from creativity_layer.providers import IdeaEvaluator, IdeaSeeder, IdeaTransformer, TaskFramer
from creativity_layer.reliability import CircuitBreaker, RetryPolicy


class ProviderMode(StrEnum):
    DETERMINISTIC = "deterministic"
    LIVE_OPENAI = "live_openai"


class CreativePlanRequest(FrozenModel):
    goal: str = Field(min_length=1)
    provider_mode: ProviderMode = ProviderMode.DETERMINISTIC
    privacy: PrivacyMode = PrivacyMode.RESEARCH
    repo_signals: RepoSignals | Mapping[str, object] = Field(default_factory=RepoSignals)
    budget_usd: float = Field(default=0.35, strict=True, gt=0)
    seed_count: int = Field(default=4, strict=True, ge=2)
    finalist_count: int = Field(default=2, strict=True, ge=1)
    max_generations: int = Field(default=1, strict=True, ge=0)
    max_calls: int = Field(default=20, strict=True, gt=0)
    max_context_snippets: int = Field(default=8, strict=True, ge=1, le=20)
    random_seed: int = Field(default=0, strict=True)


class ConfigurationError(RuntimeError):
    pass


class CreativeMiddlewareRunner:
    def __init__(
        self,
        *,
        framer: TaskFramer,
        seeder: IdeaSeeder,
        transformer: IdeaTransformer,
        evaluator: IdeaEvaluator,
        context_provider: ContextProvider,
    ) -> None:
        self._framer = framer
        self._seeder = seeder
        self._transformer = transformer
        self._evaluator = evaluator
        self._context_provider = context_provider

    @classmethod
    def deterministic(cls) -> CreativeMiddlewareRunner:
        creative_provider = DeterministicCreativeProvider()
        return cls(
            framer=creative_provider,
            seeder=creative_provider,
            transformer=creative_provider,
            evaluator=creative_provider,
            context_provider=DeterministicContextProvider(),
        )

    @classmethod
    def live_openai(
        cls,
        *,
        provider: Any | None = None,
        privacy: PrivacyMode = PrivacyMode.RESEARCH,
    ) -> CreativeMiddlewareRunner:
        creative_provider = provider or _build_openai_provider_from_environment(
            privacy=privacy,
        )
        return cls(
            framer=creative_provider,
            seeder=creative_provider,
            transformer=creative_provider,
            evaluator=creative_provider,
            context_provider=DeterministicContextProvider(),
        )

    def run(self, request: CreativePlanRequest | Mapping[str, object]) -> dict[str, Any]:
        parsed_request = CreativePlanRequest.model_validate(request)
        repo_signals = RepoSignals.model_validate(parsed_request.repo_signals)
        task = build_task_context(
            task=TaskContext(goal=parsed_request.goal),
            repo_signals=repo_signals,
            provider=self._context_provider,
            max_snippets=parsed_request.max_context_snippets,
        )
        config = RunConfig(
            max_cost_usd=parsed_request.budget_usd,
            max_calls=parsed_request.max_calls,
            max_generations=parsed_request.max_generations,
            seed_count=parsed_request.seed_count,
            finalist_count=parsed_request.finalist_count,
            framing_reserve_usd=0.0,
            finalization_reserve_usd=0.0,
            random_seed=parsed_request.random_seed,
        )
        engine = CreativeEngine(
            framer=self._framer,
            seeder=self._seeder,
            transformer=self._transformer,
            evaluator=self._evaluator,
        )
        return _serialize_result(engine.run(task, config), parsed_request)


def _serialize_result(
    result: RunResult,
    request: CreativePlanRequest,
) -> dict[str, Any]:
    spend_total = round(sum(record.cost_usd for record in result.spend_records), 10)
    return {
        "run_id": str(result.run_id),
        "provider_mode": request.provider_mode.value,
        "stopped_reason": result.stopped_reason,
        "generated_count": len(result.all_candidates),
        "finalist_count": len(result.finalists),
        "context_tags": list(result.framed_task.context.context_bundle.tags),
        "context_sources": [
            snippet.source for snippet in result.framed_task.context.context_bundle.snippets
        ],
        "config": {
            "budget_usd": request.budget_usd,
            "seed_count": request.seed_count,
            "finalist_count": request.finalist_count,
            "max_generations": request.max_generations,
            "max_calls": request.max_calls,
            "privacy": request.privacy.value,
        },
        "spend_usd": spend_total,
        "errors": [error.model_dump(mode="json") for error in result.errors],
        "finalists": [_serialize_finalist(finalist) for finalist in result.finalists],
    }


def run_creative_plan(request: CreativePlanRequest | Mapping[str, object]) -> dict[str, Any]:
    try:
        parsed_request = CreativePlanRequest.model_validate(request)
        runner = _runner_for_request(parsed_request)
        return runner.run(parsed_request)
    except ValidationError as error:
        return _configuration_error_result(
            provider_mode=_provider_mode_from_raw(request),
            message=str(error),
        )
    except ConfigurationError as error:
        return _configuration_error_result(
            provider_mode=_provider_mode_from_raw(request),
            message=str(error),
        )


def _runner_for_request(request: CreativePlanRequest) -> CreativeMiddlewareRunner:
    if request.provider_mode is ProviderMode.DETERMINISTIC:
        return CreativeMiddlewareRunner.deterministic()
    if request.provider_mode is ProviderMode.LIVE_OPENAI:
        return CreativeMiddlewareRunner.live_openai(privacy=request.privacy)
    raise ConfigurationError(f"unsupported provider mode: {request.provider_mode}")


def _build_openai_provider_from_environment(
    *,
    privacy: PrivacyMode,
) -> OpenAICreativeProvider:
    try:
        credentials = OpenAICredentials.from_environment()
        config = LiveModelConfig.from_environment().model_copy(
            update={"default_budget_usd": 0.35, "privacy_mode": privacy},
        )
        pricing = _load_pricing_table_from_environment()
        _validate_live_pricing(config, pricing)
    except ValueError as error:
        raise ConfigurationError(str(error)) from error

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


def _load_pricing_table_from_environment() -> PricingTable:
    raw_path = os.getenv("OPENAI_PRICING_FILE")
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


def _provider_mode_from_raw(request: CreativePlanRequest | Mapping[str, object]) -> str:
    if isinstance(request, CreativePlanRequest):
        return request.provider_mode.value
    raw_mode = request.get("provider_mode") if isinstance(request, Mapping) else None
    return str(raw_mode or ProviderMode.DETERMINISTIC.value)


def _configuration_error_result(*, provider_mode: str, message: str) -> dict[str, Any]:
    return {
        "run_id": None,
        "provider_mode": provider_mode,
        "stopped_reason": "configuration_error",
        "generated_count": 0,
        "finalist_count": 0,
        "context_tags": [],
        "context_sources": [],
        "config": {},
        "spend_usd": 0.0,
        "errors": [
            {
                "stage": "configuration",
                "provider": provider_mode,
                "category": "configuration_error",
                "message": message,
                "cost_incurred": False,
            }
        ],
        "finalists": [],
    }


def _serialize_finalist(finalist: IdeaGenome) -> dict[str, Any]:
    scores = finalist.scores.model_dump(mode="json") if finalist.scores else None
    return {
        "id": str(finalist.id),
        "generation": finalist.generation,
        "title": finalist.title,
        "core_mechanism": finalist.core_mechanism,
        "problem_framing": finalist.problem_framing,
        "task_value": finalist.task_value,
        "inputs_required": list(finalist.inputs_required),
        "outputs_produced": list(finalist.outputs_produced),
        "agent_workflow": list(finalist.agent_workflow),
        "decision_policy": finalist.decision_policy,
        "integration_points": list(finalist.integration_points),
        "verification_strategy": finalist.verification_strategy,
        "failure_modes": list(finalist.failure_modes),
        "scores": scores,
        "branch_cost_usd": finalist.branch_cost_usd,
        "branch_latency_ms": finalist.branch_latency_ms,
    }
