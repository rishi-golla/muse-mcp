from __future__ import annotations

import json
import os
from collections.abc import Mapping
from enum import StrEnum
from typing import Any

from openai import OpenAI
from pydantic import Field, ValidationError, model_validator

from muse.branching import BranchDirective, branch_directives
from muse.brave_search import BraveSearchProvider
from muse.context_provider import (
    ContextProvider,
    DeterministicContextProvider,
    RepoSignals,
    build_task_context,
)
from muse.deterministic import DeterministicCreativeProvider
from muse.engine import CreativeEngine
from muse.exa_search import ExaSearchProvider
from muse.live_config import (
    DEFAULT_MAX_RETRIES,
    DEFAULT_REPAIR_ATTEMPTS,
    LiveModelConfig,
    OpenAICredentials,
    PrivacyMode,
)
from muse.live_preflight import resolve_openai_pricing_table
from muse.live_search_config import BraveSearchCredentials, ExaSearchCredentials
from muse.models import (
    FrozenModel,
    IdeaGenome,
    RunConfig,
    RunResult,
    SpendRecord,
    TaskContext,
)
from muse.openai_provider import OpenAICreativeProvider
from muse.pricing import PricingTable
from muse.providers import IdeaEvaluator, IdeaSeeder, IdeaTransformer, TaskFramer
from muse.quality_warnings import (
    build_suggested_next_call,
    finalist_quality_warnings,
    quality_action_policy,
    summarize_quality_warnings,
)
from muse.reliability import CircuitBreaker, RetryPolicy
from muse.search import DeterministicSearchProvider, SearchProvider
from muse.search_context import (
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


class AgentMode(StrEnum):
    NORMAL = "normal"
    EXTENSIVE = "extensive"


def _default_run_call_ceiling(*, seed_count: int, max_generations: int) -> int:
    calls_per_operation = (DEFAULT_REPAIR_ATTEMPTS + 1) * (
        DEFAULT_MAX_RETRIES + 1
    )
    logical_operations = 1 + 2 * seed_count * (max_generations + 1)
    return logical_operations * calls_per_operation


EFFORT_PRESETS: dict[EffortPreset, dict[str, float | int]] = {
    EffortPreset.QUICK: {
        "budget_usd": 0.20,
        "seed_count": 2,
        "finalist_count": 1,
        "max_generations": 0,
        "max_calls": _default_run_call_ceiling(seed_count=2, max_generations=0),
    },
    EffortPreset.STANDARD: {
        "budget_usd": 0.35,
        "seed_count": 4,
        "finalist_count": 2,
        "max_generations": 1,
        "max_calls": _default_run_call_ceiling(seed_count=4, max_generations=1),
    },
    EffortPreset.DEEP: {
        "budget_usd": 0.75,
        "seed_count": 6,
        "finalist_count": 3,
        "max_generations": 2,
        "max_calls": _default_run_call_ceiling(seed_count=6, max_generations=2),
    },
}

MODE_EFFORTS: dict[AgentMode, EffortPreset] = {
    AgentMode.NORMAL: EffortPreset.STANDARD,
    AgentMode.EXTENSIVE: EffortPreset.DEEP,
}

EFFORT_MODES: dict[EffortPreset, AgentMode] = {
    EffortPreset.QUICK: AgentMode.NORMAL,
    EffortPreset.STANDARD: AgentMode.NORMAL,
    EffortPreset.DEEP: AgentMode.EXTENSIVE,
}


class CreativePlanRequest(FrozenModel):
    goal: str = Field(min_length=1)
    provider_mode: ProviderMode = ProviderMode.DETERMINISTIC
    privacy: PrivacyMode = PrivacyMode.RESEARCH
    repo_signals: RepoSignals | Mapping[str, object] = Field(default_factory=RepoSignals)
    mode: AgentMode = AgentMode.NORMAL
    effort: EffortPreset = EffortPreset.STANDARD
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
        if "effort" not in payload:
            mode = AgentMode(str(payload.get("mode", AgentMode.NORMAL.value)))
            payload["effort"] = MODE_EFFORTS[mode].value
        effort = EffortPreset(str(payload["effort"]))
        payload.setdefault("mode", EFFORT_MODES[effort].value)
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
    required_terms = result.framed_task.context.context_bundle.tags
    finalists = [
        _serialize_finalist(finalist, required_terms=required_terms)
        for finalist in result.finalists
    ]
    warnings_by_finalist = [
        tuple(finalist["quality_warnings"]) for finalist in finalists
    ]
    quality_summary = summarize_quality_warnings(warnings_by_finalist)
    quality_warnings = sorted(
        {
            warning
            for finalist_warnings in warnings_by_finalist
            for warning in finalist_warnings
        }
    )
    action_policy = quality_action_policy(
        quality_warnings,
        effort=request.effort.value,
    )
    suggested_next_call = build_suggested_next_call(
        action_policy,
        goal=request.goal,
        provider_mode=request.provider_mode.value,
        privacy=request.privacy.value,
        mode=request.mode.value,
        effort=request.effort.value,
        search_mode=request.search_mode.value,
        search_provider=request.search_provider.value,
        search_strict=request.search_strict,
        max_context_snippets=request.max_context_snippets,
    )
    agent_handoff = _agent_handoff(
        finalists=finalists,
        quality_action_policy=action_policy,
        suggested_next_call=suggested_next_call,
    )
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
            "mode": request.mode.value,
            "effort": request.effort.value,
            "budget_usd": request.budget_usd,
            "seed_count": request.seed_count,
            "branch_generation": {
                "strategies": [
                    directive.strategy.value
                    for directive in branch_directives(request.seed_count)
                ],
                "independent_call_count": _independent_branch_call_count(
                    result,
                    seed_count=request.seed_count,
                ),
            },
            "finalist_count": request.finalist_count,
            "max_generations": request.max_generations,
            "max_calls": request.max_calls,
            "privacy": request.privacy.value,
            "search_mode": request.search_mode.value,
            "search_provider": request.search_provider.value,
            "search_strict": request.search_strict,
        },
        "search_context": search_context.model_dump(mode="json"),
        "agent_guidance": _agent_guidance(
            request.mode,
            request.effort,
            quality_action_policy=action_policy,
            suggested_next_call=suggested_next_call,
            agent_handoff=agent_handoff,
        ),
        "spend_usd": spend_total,
        "errors": [error.model_dump(mode="json") for error in result.errors],
        "quality_warnings": quality_warnings,
        "quality_summary": quality_summary,
        "quality_action_policy": action_policy,
        "suggested_next_call": suggested_next_call,
        "agent_handoff": agent_handoff,
        "finalists": finalists,
    }


def _independent_branch_call_count(result: RunResult, *, seed_count: int) -> int:
    expected_schedule = branch_directives(seed_count)
    completed_indices: set[int] = set()
    for record in result.spend_records:
        if record.stage != "seeding" or record.operation_trace is None:
            continue
        evidenced_indices = _evidenced_branch_indices(
            record,
            expected_schedule=expected_schedule,
        )
        if evidenced_indices is None or completed_indices.intersection(
            evidenced_indices
        ):
            return 0
        completed_indices.update(evidenced_indices)
    return len(completed_indices)


def _evidenced_branch_indices(
    record: SpendRecord,
    *,
    expected_schedule: tuple[BranchDirective, ...],
) -> set[int] | None:
    operation_trace = record.operation_trace
    if operation_trace is None:
        return None
    if not hasattr(operation_trace, "request_json") or not hasattr(
        operation_trace, "response_json"
    ):
        return None
    try:
        request = json.loads(operation_trace.request_json)
        response = json.loads(operation_trace.response_json)
    except (TypeError, ValueError):
        return None
    if not isinstance(request, Mapping) or not isinstance(response, Mapping):
        return None
    if request.get("operation") != "seed":
        return None

    directives = request.get("branches")
    completed = response.get("branches")
    if (
        not isinstance(directives, list)
        or not directives
        or len(directives) > len(expected_schedule)
        or not isinstance(completed, list)
        or len(completed) != len(directives)
    ):
        return None

    requested: list[BranchDirective] = []
    for position, directive in enumerate(directives):
        if not isinstance(directive, Mapping) or not _valid_branch_request(
            directive,
            expected=expected_schedule[position],
        ):
            return None
        requested.append(expected_schedule[position])

    completed_indices: set[int] = set()
    nested_calls = 0
    nested_usage = (0, 0, 0, 0)
    failure_seen = False
    request_ids: list[str | None] = []
    for position, branch in enumerate(completed):
        if not isinstance(branch, Mapping):
            return None
        expected = requested[position]
        validated = _validated_branch_response(branch, expected=expected)
        if validated is None:
            return None
        succeeded, calls, usage, request_id = validated
        if failure_seen or (not succeeded and position != len(completed) - 1):
            return None
        if succeeded:
            completed_indices.add(expected.branch_index)
        else:
            failure_seen = True
        nested_calls += calls
        nested_usage = tuple(
            left + right for left, right in zip(nested_usage, usage, strict=True)
        )
        request_ids.append(request_id)

    record_usage = (
        record.usage.input_tokens,
        record.usage.cached_input_tokens,
        record.usage.output_tokens,
        record.usage.reasoning_tokens,
    )
    aggregate_calls = response.get("calls")
    if (
        isinstance(aggregate_calls, bool)
        or not isinstance(aggregate_calls, int)
        or aggregate_calls != record.calls
        or _trace_usage(response.get("usage")) != record_usage
        or response.get("request_ids") != request_ids
        or nested_calls != record.calls
        or nested_usage != record_usage
    ):
        return None
    return completed_indices


def _valid_branch_request(
    branch: Mapping[str, object],
    *,
    expected: BranchDirective,
) -> bool:
    branch_index = branch.get("branch_index")
    trace = branch.get("trace")
    if (
        isinstance(branch_index, bool)
        or not isinstance(branch_index, int)
        or branch_index != expected.branch_index
        or branch.get("strategy") != expected.strategy.value
        or not isinstance(trace, Mapping)
        or not trace
        or trace.get("operation") != "seed"
    ):
        return False
    domain = trace.get("domain")
    if not isinstance(domain, Mapping):
        return False
    directive = domain.get("branch_directive")
    if not isinstance(directive, Mapping):
        return False
    try:
        traced_directive = BranchDirective.model_validate(directive)
    except ValidationError:
        return False
    return traced_directive == expected


def _validated_branch_response(
    branch: Mapping[str, object],
    *,
    expected: BranchDirective,
) -> tuple[bool, int, tuple[int, int, int, int], str | None] | None:
    branch_index = branch.get("branch_index")
    trace = branch.get("trace")
    succeeded = branch.get("succeeded")
    request_id = branch.get("request_id")
    if (
        isinstance(branch_index, bool)
        or not isinstance(branch_index, int)
        or branch_index != expected.branch_index
        or branch.get("strategy") != expected.strategy.value
        or not isinstance(succeeded, bool)
        or not isinstance(trace, Mapping)
        or not trace
        or (request_id is not None and not isinstance(request_id, str))
        or trace.get("request_id") != request_id
    ):
        return None
    calls = trace.get("calls")
    usage = _trace_usage(trace.get("usage"))
    attempts = trace.get("attempts")
    if (
        isinstance(calls, bool)
        or not isinstance(calls, int)
        or calls < 1
        or usage is None
        or not isinstance(attempts, list)
        or len(attempts) > calls
    ):
        return None
    attempt_usage = (0, 0, 0, 0)
    for position, attempt in enumerate(attempts, start=1):
        if not isinstance(attempt, Mapping) or attempt.get("attempt") != position:
            return None
        attempt_request_id = attempt.get("request_id")
        if attempt_request_id is not None and not isinstance(attempt_request_id, str):
            return None
        item_usage = _trace_usage(attempt.get("usage"))
        if item_usage is None:
            return None
        attempt_usage = tuple(
            left + right
            for left, right in zip(attempt_usage, item_usage, strict=True)
        )
    error = trace.get("error")
    parsed = trace.get("parsed")
    if (
        attempt_usage != usage
        or (
            succeeded
            and (
                not attempts
                or error is not None
                or not isinstance(parsed, Mapping)
                or not parsed
            )
        )
        or (
            not succeeded
            and (not isinstance(error, str) or not error.strip() or parsed is not None)
        )
    ):
        return None
    return succeeded, calls, usage, request_id


def _trace_usage(value: object) -> tuple[int, int, int, int] | None:
    if not isinstance(value, Mapping):
        return None
    metrics = tuple(
        value.get(key)
        for key in ("input", "cached_input", "output", "reasoning")
    )
    if any(
        isinstance(metric, bool) or not isinstance(metric, int) or metric < 0
        for metric in metrics
    ):
        return None
    input_tokens, cached_input_tokens, output_tokens, reasoning_tokens = metrics
    if cached_input_tokens > input_tokens:
        return None
    return input_tokens, cached_input_tokens, output_tokens, reasoning_tokens


def run_muse_plan(request: CreativePlanRequest | Mapping[str, object]) -> dict[str, Any]:
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
    pricing, _source = resolve_openai_pricing_table()
    return pricing


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
    agent_handoff = _configuration_error_handoff()
    return {
        "run_id": None,
        "provider_mode": provider_mode,
        "stopped_reason": "configuration_error",
        "generated_count": 0,
        "finalist_count": 0,
        "context_tags": [],
        "context_sources": [],
        "config": {
            "mode": EFFORT_MODES[effort].value,
            "search_mode": search_mode,
            "search_provider": search_provider,
            "search_strict": search_strict,
        },
        "search_context": metadata.model_dump(mode="json"),
        "agent_guidance": _agent_guidance(
            EFFORT_MODES[effort],
            effort,
            quality_action_policy=_empty_quality_action_policy(effort),
            suggested_next_call=None,
            agent_handoff=agent_handoff,
        ),
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
        "quality_warnings": [],
        "quality_summary": _empty_quality_summary(),
        "quality_action_policy": _empty_quality_action_policy(effort),
        "suggested_next_call": None,
        "agent_handoff": agent_handoff,
        "finalists": [],
    }


def _agent_guidance(
    mode: AgentMode,
    effort: EffortPreset,
    *,
    quality_action_policy: dict[str, object] | None = None,
    suggested_next_call: dict[str, object] | None = None,
    agent_handoff: dict[str, object] | None = None,
) -> dict[str, Any]:
    return {
        "intended_use": "planning_middleware",
        "mode": mode.value,
        "effort": effort.value,
        "verification_required": True,
        "quality_action_policy": quality_action_policy
        or _empty_quality_action_policy(effort),
        "suggested_next_call": suggested_next_call,
        "agent_handoff": agent_handoff,
        "recommended_agent_loop": [
            "observe_repo_state",
            "call_muse_plan_with_current_repo_signals",
            "choose_one_bounded_action_from_a_finalist",
            "run_the_narrowest_relevant_verification",
            "stop_or_escalate_based_on_verification",
        ],
        "escalation_policy": (
            "Start with mode normal. Escalate to mode extensive when verification "
            "keeps failing, repo context is ambiguous, or the task is high-impact."
        ),
        "usage_warnings": [
            "Do not treat finalists as applied code.",
            "Do not skip repository-owned verification.",
            "Pass observed repo facts instead of asking muse to crawl the repo.",
            "Do not ask the human for seed counts, budgets, or repo-language flags.",
        ],
    }


def _agent_handoff(
    *,
    finalists: list[dict[str, Any]],
    quality_action_policy: dict[str, object],
    suggested_next_call: dict[str, object] | None,
) -> dict[str, object]:
    policy_status = str(quality_action_policy.get("status", "clear"))
    selected_finalist_id = finalists[0]["id"] if finalists else None
    if policy_status == "needs_retry":
        status = "retry_recommended"
        recommended_action = "retry_muse_plan"
        use_current_finalist = False
    elif policy_status == "review":
        status = "review"
        recommended_action = "review_current_finalist"
        use_current_finalist = bool(finalists)
    else:
        status = "ready"
        recommended_action = "apply_current_finalist"
        use_current_finalist = bool(finalists)

    return {
        "status": status,
        "recommended_action": recommended_action,
        "use_current_finalist": use_current_finalist,
        "selected_finalist_id": selected_finalist_id,
        "suggested_next_call_available": suggested_next_call is not None,
        "verification_required": True,
    }


def _configuration_error_handoff() -> dict[str, object]:
    return {
        "status": "blocked",
        "recommended_action": "fix_configuration",
        "use_current_finalist": False,
        "selected_finalist_id": None,
        "suggested_next_call_available": False,
        "verification_required": True,
    }


def _serialize_finalist(
    finalist: IdeaGenome,
    *,
    required_terms: tuple[str, ...] = (),
) -> dict[str, Any]:
    scores = finalist.scores.model_dump(mode="json") if finalist.scores else None
    payload = {
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
    payload["quality_warnings"] = list(
        finalist_quality_warnings(payload, required_terms=required_terms)
    )
    return payload


def _empty_quality_summary() -> dict[str, object]:
    return summarize_quality_warnings(())


def _empty_quality_action_policy(effort: EffortPreset) -> dict[str, object]:
    return quality_action_policy((), effort=effort.value)
