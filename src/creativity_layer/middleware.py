from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import Field

from creativity_layer.context_provider import (
    ContextProvider,
    DeterministicContextProvider,
    RepoSignals,
    build_task_context,
)
from creativity_layer.deterministic import DeterministicCreativeProvider
from creativity_layer.engine import CreativeEngine
from creativity_layer.models import FrozenModel, IdeaGenome, RunConfig, RunResult, TaskContext
from creativity_layer.providers import IdeaEvaluator, IdeaSeeder, IdeaTransformer, TaskFramer


class CreativePlanRequest(FrozenModel):
    goal: str = Field(min_length=1)
    repo_signals: RepoSignals | Mapping[str, object] = Field(default_factory=RepoSignals)
    budget_usd: float = Field(default=0.35, strict=True, gt=0)
    seed_count: int = Field(default=4, strict=True, ge=2)
    finalist_count: int = Field(default=2, strict=True, ge=1)
    max_generations: int = Field(default=1, strict=True, ge=0)
    max_calls: int = Field(default=20, strict=True, gt=0)
    max_context_snippets: int = Field(default=8, strict=True, ge=1, le=20)
    random_seed: int = Field(default=0, strict=True)


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
        },
        "spend_usd": spend_total,
        "errors": [error.model_dump(mode="json") for error in result.errors],
        "finalists": [_serialize_finalist(finalist) for finalist in result.finalists],
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
