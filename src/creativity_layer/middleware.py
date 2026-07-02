from __future__ import annotations

import os
from collections.abc import Mapping
from enum import StrEnum
from pathlib import Path
from typing import Any

from openai import OpenAI
from pydantic import Field, ValidationError, model_validator

from creativity_layer.brave_search import BraveSearchProvider
from creativity_layer.context_provider import (
    ContextProvider,
    DeterministicContextProvider,
    RepoSignals,
    build_task_context,
)
from creativity_layer.deterministic import DeterministicCreativeProvider
from creativity_layer.engine import CreativeEngine
from creativity_layer.exa_search import ExaSearchProvider
from creativity_layer.live_config import LiveModelConfig, OpenAICredentials, PrivacyMode
from creativity_layer.live_search_config import BraveSearchCredentials, ExaSearchCredentials
from creativity_layer.models import FrozenModel, IdeaGenome, RunConfig, RunResult, TaskContext
from creativity_layer.openai_provider import OpenAICreativeProvider
from creativity_layer.pricing import PricingTable
from creativity_layer.providers import IdeaEvaluator, IdeaSeeder, IdeaTransformer, TaskFramer
from creativity_layer.reliability import CircuitBreaker, RetryPolicy
from creativity_layer.search import DeterministicSearchProvider, SearchProvider
from creativity_layer.search_context import (
    SearchContextMetadata,
    SearchContextMode,
    SearchContextResolver,
    SearchProviderPolicy,
)


class ProviderMode(StrEnum):
    DETERMINISTIC = "deterministic"
    LIVE_OPENAI = "live_openai"


class EffortPreset(StrEnum):
    QUICK = "quick"
    STANDARD = "standard"
    DEEP = "deep"


EFFORT_PRESETS: dict[EffortPreset, dict[str, float | int]] = {
    EffortPreset.QUICK: {
        "budget_usd": 0.20,
        "seed_count": 2,
        "finalist_count": 1,
        "max_generations": 0,
    },
    EffortPreset.STANDARD: {
        "budget_usd": 0.35,
        "seed_count": 4,
        "finalist_count": 2,
        "max_generations": 1,
    },
    EffortPreset.DEEP: {
        "budget_usd": 0.75,
        "seed_count": 6,
        "finalist_count": 3,
        "max_generations": 2,
    },
}


class CreativePlanRequest(FrozenModel):
    goal: str = Field(min_length=1)
    provider_mode: ProviderMode = ProviderMode.DETERMINISTIC
    privacy: PrivacyMode = PrivacyMode.RESEARCH
    repo_signals: RepoSignals | Mapping[str, object] = Field(default_factory=RepoSignals)
    effort: EffortPreset = EffortPreset.QUICK
    budget_usd: float = Field(strict=True, gt=0)
    seed_count: int = Field(strict=True, ge=2)
    finalist_count: int = Field(strict=True, ge=1)
    max_generations: int = Field(strict=True, ge=0)
    max_calls: int = Field(default=20, strict=True, gt=0)
    max_context_snippets: int = Field(default=8, strict=True, ge=1, le=20)
    search_mode: SearchContextMode = SearchContextMode.OFF
    search_provider: SearchProviderPolicy = SearchProviderPolicy.AUTO
    search_strict: bool = Field(default=False, strict=True)
    random_seed: int = Field(default=0, strict=True)

    @model_validator(mode="before")
    @classmethod
    def resolve_effort_defaults(cls, value: object) -> object:
        if not isinstance(value, Mapping):
            return value
        payload = dict(value)
        effort = EffortPreset(str(payload.get("effort", EffortPreset.QUICK.value)))
        for field, default_value in EFFORT_PRESETS[effort].items():
            payload.setdefault(field, default_value)
        return payload


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
        search_context_resolver: SearchContextResolver | None = None,
    ) -> None:
        self._framer = framer
        self._seeder = seeder
        self._transformer = transformer
        self._evaluator = evaluator
        self._context_provider = context_provider
        self._search_context_resolver = search_context_resolver

    @classmethod
    def deterministic(
        cls,
        *,
        search_context_resolver: SearchContextResolver | None = None,
    ) -> CreativeMiddlewareRunner:
        creative_provider = DeterministicCreativeProvider()
        return cls(
            framer=creative_provider,
            seeder=creative_provider,
            transformer=creative_provider,
            evaluator=creative_provider,
            context_provider=DeterministicContextProvider(),
            search_context_resolver=search_context_resolver,
        )

    @classmethod
    def live_openai(
        cls,
        *,
        provider: Any | None = None,
        privacy: PrivacyMode = PrivacyMode.RESEARCH,
        search_context_resolver: SearchContextResolver | None = None,
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
            search_context_resolver=search_context_resolver,
        )

    def run(self, request: CreativePlanRequest | Mapping[str, object]) -> dict[str, Any]:
        parsed_request = CreativePlanRequest.model_validate(request)
        repo_signals = RepoSignals.model_validate(parsed_request.repo_signals)
        search_context_resolver = self._search_context_resolver or (
            _search_context_resolver_for_request(parsed_request)
        )
        search_context = search_context_resolver.resolve(
            mode=parsed_request.search_mode,
            task=TaskContext(goal=parsed_request.goal),
            repo_signals=repo_signals,
            max_snippets=parsed_request.max_context_snippets,
            strict=parsed_request.search_strict,
        )
        if _strict_search_failed(parsed_request, search_context.metadata):
            return _configuration_error_result(
                provider_mode=parsed_request.provider_mode.value,
                message=_strict_search_error_message(search_context.metadata),
                effort=parsed_request.effort,
                search_mode=parsed_request.search_mode.value,
                search_provider=parsed_request.search_provider.value,
                search_strict=parsed_request.search_strict,
                search_context=search_context.metadata,
            )
        task = build_task_context(
            task=TaskContext(
                goal=parsed_request.goal,
                context_bundle=search_context.bundle,
            ),
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
        return _serialize_result(
            engine.run(task, config),
            parsed_request,
            search_context.metadata,
        )


def _serialize_result(
    result: RunResult,
    request: CreativePlanRequest,
    search_context: SearchContextMetadata,
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
            "effort": request.effort.value,
            "budget_usd": request.budget_usd,
            "seed_count": request.seed_count,
            "finalist_count": request.finalist_count,
            "max_generations": request.max_generations,
            "max_calls": request.max_calls,
            "privacy": request.privacy.value,
            "search_mode": request.search_mode.value,
            "search_provider": request.search_provider.value,
            "search_strict": request.search_strict,
        },
        "search_context": search_context.model_dump(mode="json"),
        "agent_guidance": _agent_guidance(request.effort),
        "spend_usd": spend_total,
        "errors": [error.model_dump(mode="json") for error in result.errors],
        "finalists": [_serialize_finalist(finalist) for finalist in result.finalists],
    }


def run_creative_plan(request: CreativePlanRequest | Mapping[str, object]) -> dict[str, Any]:
    parsed_request: CreativePlanRequest | None = None
    try:
        parsed_request = CreativePlanRequest.model_validate(request)
        runner = _runner_for_request(parsed_request)
        return runner.run(parsed_request)
    except ValidationError as error:
        return _configuration_error_result(
            provider_mode=_provider_mode_from_raw(request),
            message=str(error),
            search_mode=_search_mode_from_raw(request),
            search_provider=_search_provider_from_raw(request),
            search_strict=_search_strict_from_raw(request),
        )
    except ConfigurationError as error:
        return _configuration_error_result(
            provider_mode=_provider_mode_from_raw(request),
            message=str(error),
            effort=parsed_request.effort if parsed_request else EffortPreset.QUICK,
            search_mode=(
                parsed_request.search_mode.value
                if parsed_request
                else _search_mode_from_raw(request)
            ),
            search_provider=(
                parsed_request.search_provider.value
                if parsed_request
                else _search_provider_from_raw(request)
            ),
            search_strict=(
                parsed_request.search_strict
                if parsed_request
                else _search_strict_from_raw(request)
            ),
        )


def configuration_error_result(
    *,
    provider_mode: str,
    message: str,
    effort: EffortPreset = EffortPreset.QUICK,
    search_mode: str = SearchContextMode.OFF.value,
    search_provider: str = SearchProviderPolicy.AUTO.value,
    search_strict: bool = False,
) -> dict[str, Any]:
    return _configuration_error_result(
        provider_mode=provider_mode,
        message=message,
        effort=effort,
        search_mode=search_mode,
        search_provider=search_provider,
        search_strict=search_strict,
    )


def _runner_for_request(request: CreativePlanRequest) -> CreativeMiddlewareRunner:
    if request.provider_mode is ProviderMode.DETERMINISTIC:
        return CreativeMiddlewareRunner.deterministic()
    if request.provider_mode is ProviderMode.LIVE_OPENAI:
        return CreativeMiddlewareRunner.live_openai(
            privacy=request.privacy,
        )
    raise ConfigurationError(f"unsupported provider mode: {request.provider_mode}")


def _search_context_resolver_for_request(
    request: CreativePlanRequest,
) -> SearchContextResolver:
    if request.provider_mode is ProviderMode.DETERMINISTIC:
        return _deterministic_search_context_resolver(request.search_provider)
    return _build_search_context_resolver_from_environment(request.search_provider)


def _deterministic_search_context_resolver(
    policy: SearchProviderPolicy,
) -> SearchContextResolver:
    provider: SearchProvider | None = (
        DeterministicSearchProvider()
        if policy in {SearchProviderPolicy.AUTO, SearchProviderPolicy.DETERMINISTIC}
        else None
    )
    provider_policy = (
        SearchProviderPolicy.DETERMINISTIC
        if policy is SearchProviderPolicy.AUTO
        else policy
    )
    return SearchContextResolver(
        provider=provider,
        provider_policy=provider_policy,
    )


def _build_search_context_resolver_from_environment(
    policy: SearchProviderPolicy,
) -> SearchContextResolver:
    provider = _build_search_provider_from_environment(policy)
    provider_policy = _provider_policy_for_selected_provider(policy, provider)
    return SearchContextResolver(provider=provider, provider_policy=provider_policy)


def _build_search_provider_from_environment(
    policy: SearchProviderPolicy,
) -> SearchProvider | None:
    if policy is SearchProviderPolicy.DETERMINISTIC:
        return DeterministicSearchProvider()
    if policy is SearchProviderPolicy.EXA:
        return _maybe_exa_search_provider()
    if policy is SearchProviderPolicy.BRAVE:
        return _maybe_brave_search_provider()
    if os.getenv("EXA_API_KEY", "").strip():
        return _maybe_exa_search_provider()
    if os.getenv("BRAVE_SEARCH_API_KEY", "").strip():
        return _maybe_brave_search_provider()
    return None


def _maybe_exa_search_provider() -> SearchProvider | None:
    try:
        return ExaSearchProvider(credentials=ExaSearchCredentials.from_environment())
    except ValueError:
        return None


def _maybe_brave_search_provider() -> SearchProvider | None:
    try:
        return BraveSearchProvider(credentials=BraveSearchCredentials.from_environment())
    except ValueError:
        return None


def _provider_policy_for_selected_provider(
    policy: SearchProviderPolicy,
    provider: SearchProvider | None,
) -> SearchProviderPolicy:
    if policy is not SearchProviderPolicy.AUTO or provider is None:
        return policy
    if isinstance(provider, ExaSearchProvider):
        return SearchProviderPolicy.EXA
    if isinstance(provider, BraveSearchProvider):
        return SearchProviderPolicy.BRAVE
    if isinstance(provider, DeterministicSearchProvider):
        return SearchProviderPolicy.DETERMINISTIC
    return SearchProviderPolicy.AUTO


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


def _search_mode_from_raw(request: CreativePlanRequest | Mapping[str, object]) -> str:
    if isinstance(request, CreativePlanRequest):
        return request.search_mode.value
    raw_mode = request.get("search_mode") if isinstance(request, Mapping) else None
    return str(raw_mode or SearchContextMode.OFF.value)


def _search_provider_from_raw(request: CreativePlanRequest | Mapping[str, object]) -> str:
    if isinstance(request, CreativePlanRequest):
        return request.search_provider.value
    raw_provider = request.get("search_provider") if isinstance(request, Mapping) else None
    return str(raw_provider or SearchProviderPolicy.AUTO.value)


def _search_strict_from_raw(request: CreativePlanRequest | Mapping[str, object]) -> bool:
    if isinstance(request, CreativePlanRequest):
        return request.search_strict
    raw_value = request.get("search_strict") if isinstance(request, Mapping) else None
    return bool(raw_value) if isinstance(raw_value, bool) else False


def _strict_search_failed(
    request: CreativePlanRequest,
    search_context: SearchContextMetadata,
) -> bool:
    return (
        request.search_strict
        and request.search_mode is not SearchContextMode.OFF
        and not search_context.used
    )


def _strict_search_error_message(search_context: SearchContextMetadata) -> str:
    if search_context.errors:
        return search_context.errors[0]
    reason = search_context.skipped_reason or "unavailable"
    return f"strict search requested but search context was not available: {reason}"


def _configuration_error_result(
    *,
    provider_mode: str,
    message: str,
    effort: EffortPreset = EffortPreset.QUICK,
    search_mode: str = SearchContextMode.OFF.value,
    search_provider: str = SearchProviderPolicy.AUTO.value,
    search_strict: bool = False,
    search_context: SearchContextMetadata | None = None,
) -> dict[str, Any]:
    metadata = search_context or SearchContextMetadata(
        mode=search_mode,
        used=False,
        skipped_reason="configuration_error",
        provider_policy=search_provider,
        strict=search_strict,
        errors=(message,),
    )
    return {
        "run_id": None,
        "provider_mode": provider_mode,
        "stopped_reason": "configuration_error",
        "generated_count": 0,
        "finalist_count": 0,
        "context_tags": [],
        "context_sources": [],
        "config": {
            "search_mode": search_mode,
            "search_provider": search_provider,
            "search_strict": search_strict,
        },
        "search_context": metadata.model_dump(mode="json"),
        "agent_guidance": _agent_guidance(effort),
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


def _agent_guidance(effort: EffortPreset) -> dict[str, Any]:
    return {
        "intended_use": "planning_middleware",
        "effort": effort.value,
        "verification_required": True,
        "recommended_agent_loop": [
            "observe_repo_state",
            "call_creative_plan_with_current_repo_signals",
            "choose_one_bounded_action_from_a_finalist",
            "run_the_narrowest_relevant_verification",
            "stop_or_escalate_based_on_verification",
        ],
        "escalation_policy": (
            "Start with quick. Escalate to standard when verification keeps failing or "
            "repo context is ambiguous; use deep only for high-impact planning before edits."
        ),
        "usage_warnings": [
            "Do not treat finalists as applied code.",
            "Do not skip repository-owned verification.",
            "Pass observed repo facts instead of asking creativity-layer to crawl the repo.",
        ],
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
