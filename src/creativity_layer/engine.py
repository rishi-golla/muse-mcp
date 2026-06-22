from __future__ import annotations

from itertools import cycle

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
from creativity_layer.providers import IdeaEvaluator, IdeaSeeder, IdeaTransformer, TaskFramer
from creativity_layer.transforms import OperatorName, TransformationRequest

SEED_COST_USD = 0.01
TRANSFORM_COST_USD = 0.01
EVALUATION_COST_USD = 0.005


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
        framed = self._framer.frame(task)
        candidates = self._seed_and_evaluate(framed, config, budget)
        if candidates is None:
            return self._result(framed, (), budget, config, "budget_exhausted")

        stopped_reason = "generation_limit"
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
                tuple(candidates),
                finalist_count=min(config.seed_count, len(candidates)),
            )
            descendants: list[IdeaGenome] = []

            for parent in parents:
                try:
                    reservation = budget.reserve(
                        TRANSFORM_COST_USD + EVALUATION_COST_USD,
                        required_calls=2,
                        preserve_finalization=True,
                    )
                except BudgetExceeded:
                    stopped_reason = "budget_exhausted"
                    break

                with reservation:
                    request = TransformationRequest.for_operator(
                        operator=next(operators),
                        parents=(parent,),
                        task_goal=task.goal,
                    )
                    transformed = self._transformer.transform(request, (parent,))
                    reservation.charge(
                        "transformation",
                        transformed.provider,
                        transformed.cost_usd,
                        transformed.latency_ms,
                    )
                    descendants.append(
                        self._evaluate(transformed.value, framed, reservation)
                    )

            candidates.extend(descendants)
            if stopped_reason == "budget_exhausted":
                break

        return self._result(
            framed,
            tuple(candidates),
            budget,
            config,
            stopped_reason,
        )

    def _seed_and_evaluate(
        self,
        framed_task: FramedTask,
        config: RunConfig,
        budget: BudgetController,
    ) -> list[IdeaGenome] | None:
        try:
            reservation = budget.reserve(
                SEED_COST_USD + EVALUATION_COST_USD * config.seed_count,
                required_calls=config.seed_count + 1,
                preserve_finalization=True,
            )
        except BudgetExceeded:
            return None

        with reservation:
            seeded = self._seeder.seed(framed_task, config)
            reservation.charge(
                "seeding",
                seeded.provider,
                seeded.cost_usd,
                seeded.latency_ms,
            )
            return [
                self._evaluate(candidate, framed_task, reservation)
                for candidate in seeded.value
            ]

    def _evaluate(
        self,
        candidate: IdeaGenome,
        framed_task: FramedTask,
        reservation: BudgetReservation,
    ) -> IdeaGenome:
        response = self._evaluator.evaluate(candidate, framed_task)
        reservation.charge(
            "evaluation",
            response.provider,
            response.cost_usd,
            response.latency_ms,
        )
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
