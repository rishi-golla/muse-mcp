from __future__ import annotations

from decimal import Decimal
from itertools import cycle
from uuid import UUID

from creativity_layer.budget import (
    BudgetController,
    BudgetExceeded,
    BudgetReservation,
)
from creativity_layer.models import (
    FramedTask,
    IdeaGenome,
    RunConfig,
    RunResult,
    TaskContext,
)
from creativity_layer.population import PopulationManager
from creativity_layer.providers import (
    IdeaEvaluator,
    IdeaSeeder,
    IdeaTransformer,
    MeteredResponse,
    OperationQuote,
    TaskFramer,
)
from creativity_layer.transforms import OperatorName, TransformationRequest


def _exceeds_quote(response: MeteredResponse[object], quote: OperationQuote) -> bool:
    return Decimal(str(response.cost_usd)) > Decimal(str(quote.max_cost_usd))


class CreativeEngine:
    def __init__(
        self,
        *,
        framer: TaskFramer,
        seeder: IdeaSeeder,
        transformer: IdeaTransformer,
        evaluator: IdeaEvaluator,
        population: PopulationManager | None = None,
    ) -> None:
        self._framer = framer
        self._seeder = seeder
        self._transformer = transformer
        self._evaluator = evaluator
        self._population = population or PopulationManager()

    def run(self, task: TaskContext, config: RunConfig) -> RunResult:
        budget = BudgetController(config)
        try:
            framed = self._framer.frame(task)
        except Exception:
            framed = FramedTask(
                context=task,
                assumptions=(),
                obvious_solution="Unavailable: task framing failed.",
            )
            return self._result(
                framed,
                (),
                budget,
                config,
                "provider_error",
            )
        candidates, stopped_reason = self._seed_and_evaluate(framed, config, budget)
        if stopped_reason is not None:
            return self._result(
                framed,
                tuple(candidates),
                budget,
                config,
                stopped_reason,
            )

        all_candidates = list(candidates)
        candidate_ids = {candidate.id for candidate in candidates}
        current_generation = tuple(candidates)
        attempted: set[tuple[tuple[UUID, ...], OperatorName]] = set()
        operators = cycle(
            (
                OperatorName.INVERT,
                OperatorName.REFRAME,
                OperatorName.SUBTRACT,
                OperatorName.CONTRADICT,
            )
        )

        for _generation in range(config.max_generations):
            parents = self._population.select(
                current_generation,
                finalist_count=min(config.seed_count, len(current_generation)),
            )
            descendants: list[IdeaGenome] = []

            for parent in parents:
                operator = next(operators)
                operation = ((parent.id,), operator)
                if operation in attempted:
                    continue
                attempted.add(operation)
                request = TransformationRequest.for_operator(
                    operator=operator,
                    parents=(parent,),
                    task_goal=task.goal,
                )
                descendant, stopped_reason = self._transform_and_evaluate(
                    request,
                    (parent,),
                    framed,
                    budget,
                    candidate_ids,
                )
                if descendant is not None:
                    descendants.append(descendant)
                    all_candidates.append(descendant)
                    candidate_ids.add(descendant.id)
                if stopped_reason is not None:
                    return self._result(
                        framed,
                        tuple(all_candidates),
                        budget,
                        config,
                        stopped_reason,
                    )

            if descendants:
                current_generation = tuple(descendants)

        return self._result(
            framed,
            tuple(all_candidates),
            budget,
            config,
            "generation_limit",
        )

    def _seed_and_evaluate(
        self,
        framed_task: FramedTask,
        config: RunConfig,
        budget: BudgetController,
    ) -> tuple[list[IdeaGenome], str | None]:
        try:
            seed_quote = self._seeder.quote_seed(framed_task, config)
            evaluation_quote = self._evaluator.quote_evaluation(framed_task)
            reservation = budget.reserve(
                seed_quote.max_cost_usd
                + evaluation_quote.max_cost_usd * config.seed_count,
                required_calls=seed_quote.calls
                + evaluation_quote.calls * config.seed_count,
                preserve_finalization=True,
            )
        except BudgetExceeded:
            return [], "budget_exhausted"
        except Exception:
            return [], "provider_error"

        with reservation:
            try:
                seeded = self._seeder.seed(framed_task, config)
            except Exception:
                return [], "provider_error"
            if _exceeds_quote(seeded, seed_quote):
                budget._record_audited_overage(
                    reservation,
                    "seeding",
                    seeded.provider,
                    seeded.cost_usd,
                    seeded.latency_ms,
                    quoted_cost_usd=seed_quote.max_cost_usd,
                )
                return [], "provider_error"
            try:
                reservation.charge(
                    "seeding",
                    seeded.provider,
                    seeded.cost_usd,
                    seeded.latency_ms,
                )
            except BudgetExceeded:
                return [], "provider_error"

            if len(seeded.value) != config.seed_count:
                return [], "provider_error"
            seed_ids = [candidate.id for candidate in seeded.value]
            if len(seed_ids) != len(set(seed_ids)):
                return [], "provider_error"

            evaluated: list[IdeaGenome] = []
            for candidate in seeded.value:
                result = self._evaluate(
                    candidate,
                    framed_task,
                    evaluation_quote,
                    reservation,
                    budget,
                )
                if result is None:
                    return [], "provider_error"
                evaluated.append(result)
            return evaluated, None

    def _transform_and_evaluate(
        self,
        request: TransformationRequest,
        parents: tuple[IdeaGenome, ...],
        framed_task: FramedTask,
        budget: BudgetController,
        candidate_ids: set[UUID],
    ) -> tuple[IdeaGenome | None, str | None]:
        try:
            transform_quote = self._transformer.quote_transform(request, parents)
            evaluation_quote = self._evaluator.quote_evaluation(framed_task)
            reservation = budget.reserve(
                transform_quote.max_cost_usd + evaluation_quote.max_cost_usd,
                required_calls=transform_quote.calls + evaluation_quote.calls,
                preserve_finalization=True,
            )
        except BudgetExceeded:
            return None, "budget_exhausted"
        except Exception:
            return None, "provider_error"

        with reservation:
            try:
                transformed = self._transformer.transform(request, parents)
            except Exception:
                return None, "provider_error"
            if _exceeds_quote(transformed, transform_quote):
                budget._record_audited_overage(
                    reservation,
                    "transformation",
                    transformed.provider,
                    transformed.cost_usd,
                    transformed.latency_ms,
                    quoted_cost_usd=transform_quote.max_cost_usd,
                )
                return None, "provider_error"
            try:
                reservation.charge(
                    "transformation",
                    transformed.provider,
                    transformed.cost_usd,
                    transformed.latency_ms,
                )
            except BudgetExceeded:
                return None, "provider_error"
            if transformed.value.id in candidate_ids:
                return None, "provider_error"

            evaluated = self._evaluate(
                transformed.value,
                framed_task,
                evaluation_quote,
                reservation,
                budget,
            )
            if evaluated is None:
                return None, "provider_error"
            return evaluated, None

    def _evaluate(
        self,
        candidate: IdeaGenome,
        framed_task: FramedTask,
        quote: OperationQuote,
        reservation: BudgetReservation,
        budget: BudgetController,
    ) -> IdeaGenome | None:
        try:
            response = self._evaluator.evaluate(candidate, framed_task)
        except Exception:
            return None
        if _exceeds_quote(response, quote):
            budget._record_audited_overage(
                reservation,
                "evaluation",
                response.provider,
                response.cost_usd,
                response.latency_ms,
                quoted_cost_usd=quote.max_cost_usd,
            )
            return None
        try:
            reservation.charge(
                "evaluation",
                response.provider,
                response.cost_usd,
                response.latency_ms,
            )
        except BudgetExceeded:
            return None
        return candidate.model_copy(update={"scores": response.value})

    def _result(
        self,
        framed_task: FramedTask,
        candidates: tuple[IdeaGenome, ...],
        budget: BudgetController,
        config: RunConfig,
        stopped_reason: str,
    ) -> RunResult:
        finalists = (
            self._population.select(
                candidates,
                finalist_count=min(config.finalist_count, len(candidates)),
            )
            if candidates
            else ()
        )
        return RunResult(
            framed_task=framed_task,
            finalists=finalists,
            all_candidates=candidates,
            spend_records=budget.records,
            stopped_reason=stopped_reason,
        )
