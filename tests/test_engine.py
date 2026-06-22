from __future__ import annotations

from decimal import Decimal

from pytest import MonkeyPatch

import creativity_layer.engine as engine_module
from creativity_layer import CreativeEngine as ExportedCreativeEngine
from creativity_layer.budget import BudgetController
from creativity_layer.deterministic import DeterministicCreativeProvider
from creativity_layer.engine import CreativeEngine
from creativity_layer.models import (
    EvaluationScores,
    FramedTask,
    IdeaGenome,
    RunConfig,
    TaskContext,
)
from creativity_layer.population import PopulationManager
from creativity_layer.providers import MeteredResponse, OperationQuote
from creativity_layer.transforms import TransformationRequest


class CountingProvider(DeterministicCreativeProvider):
    def __init__(self) -> None:
        self.seed_calls = 0
        self.transform_calls = 0

    def seed(
        self,
        framed_task: FramedTask,
        config: RunConfig,
    ) -> MeteredResponse[tuple[IdeaGenome, ...]]:
        self.seed_calls += 1
        return super().seed(framed_task, config)

    def transform(
        self,
        request: TransformationRequest,
        parents: tuple[IdeaGenome, ...],
    ) -> MeteredResponse[IdeaGenome]:
        self.transform_calls += 1
        return super().transform(request, parents)


class AdversarialProvider(DeterministicCreativeProvider):
    def __init__(
        self,
        *,
        seed_quote: OperationQuote | None = None,
        transform_quote: OperationQuote | None = None,
        evaluation_quote: OperationQuote | None = None,
        seed_cost_usd: float = 0.01,
        transform_cost_usd: float = 0.01,
        evaluation_cost_usd: float = 0.005,
        seed_cardinality: int | None = None,
        raise_seed: bool = False,
        raise_transform: bool = False,
        raise_evaluation_at: int | None = None,
        duplicate_transform_id: bool = False,
        duplicate_seed_ids: bool = False,
        raise_seed_quote: bool = False,
        raise_transform_quote: bool = False,
    ) -> None:
        self.seed_quote = seed_quote or OperationQuote(max_cost_usd=0.01, calls=1)
        self.transform_quote = transform_quote or OperationQuote(
            max_cost_usd=0.01,
            calls=1,
        )
        self.evaluation_quote = evaluation_quote or OperationQuote(
            max_cost_usd=0.005,
            calls=1,
        )
        self.seed_cost_usd = seed_cost_usd
        self.transform_cost_usd = transform_cost_usd
        self.evaluation_cost_usd = evaluation_cost_usd
        self.seed_cardinality = seed_cardinality
        self.raise_seed = raise_seed
        self.raise_transform = raise_transform
        self.raise_evaluation_at = raise_evaluation_at
        self.duplicate_transform_id = duplicate_transform_id
        self.duplicate_seed_ids = duplicate_seed_ids
        self.raise_seed_quote = raise_seed_quote
        self.raise_transform_quote = raise_transform_quote
        self.seed_calls = 0
        self.transform_calls = 0
        self.evaluation_calls = 0

    def quote_seed(
        self,
        framed_task: FramedTask,
        config: RunConfig,
    ) -> OperationQuote:
        if self.raise_seed_quote:
            raise RuntimeError("seed quote failed")
        return self.seed_quote

    def quote_transform(
        self,
        request: TransformationRequest,
        parents: tuple[IdeaGenome, ...],
    ) -> OperationQuote:
        if self.raise_transform_quote:
            raise RuntimeError("transform quote failed")
        return self.transform_quote

    def quote_evaluation(self, framed_task: FramedTask) -> OperationQuote:
        return self.evaluation_quote

    def seed(
        self,
        framed_task: FramedTask,
        config: RunConfig,
    ) -> MeteredResponse[tuple[IdeaGenome, ...]]:
        self.seed_calls += 1
        if self.raise_seed:
            raise RuntimeError("seed failed")
        response = super().seed(framed_task, config)
        cardinality = (
            config.seed_count
            if self.seed_cardinality is None
            else self.seed_cardinality
        )
        values = list(response.value)
        if cardinality > len(values):
            expanded_config = config.model_copy(
                update={
                    "seed_count": cardinality,
                    "finalist_count": min(config.finalist_count, cardinality),
                }
            )
            values = list(super().seed(framed_task, expanded_config).value)
        values = values[:cardinality]
        if self.duplicate_seed_ids and len(values) > 1:
            values[1] = values[1].model_copy(update={"id": values[0].id})
        return response.model_copy(
            update={
                "value": tuple(values),
                "cost_usd": self.seed_cost_usd,
            }
        )

    def transform(
        self,
        request: TransformationRequest,
        parents: tuple[IdeaGenome, ...],
    ) -> MeteredResponse[IdeaGenome]:
        self.transform_calls += 1
        if self.raise_transform:
            raise RuntimeError("transform failed")
        response = super().transform(request, parents)
        value = (
            response.value.model_copy(update={"id": parents[0].id})
            if self.duplicate_transform_id
            else response.value
        )
        return response.model_copy(
            update={"value": value, "cost_usd": self.transform_cost_usd}
        )

    def evaluate(
        self,
        candidate: IdeaGenome,
        framed_task: FramedTask,
    ) -> MeteredResponse[EvaluationScores]:
        self.evaluation_calls += 1
        if self.raise_evaluation_at == self.evaluation_calls:
            raise RuntimeError("evaluation failed")
        response = super().evaluate(candidate, framed_task)
        return response.model_copy(update={"cost_usd": self.evaluation_cost_usd})


class RecordingPopulation(PopulationManager):
    def __init__(self) -> None:
        super().__init__()
        self.selection_inputs: list[tuple[IdeaGenome, ...]] = []

    def select(
        self,
        candidates: tuple[IdeaGenome, ...],
        *,
        finalist_count: int,
    ) -> tuple[IdeaGenome, ...]:
        self.selection_inputs.append(candidates)
        return super().select(candidates, finalist_count=finalist_count)


class TrackingBudget(BudgetController):
    instances: list[TrackingBudget] = []

    def __init__(self, config: RunConfig) -> None:
        super().__init__(config)
        self.instances.append(self)


def build_engine(provider: DeterministicCreativeProvider) -> CreativeEngine:
    return CreativeEngine(
        framer=provider,
        seeder=provider,
        transformer=provider,
        evaluator=provider,
    )


def test_package_exports_creative_engine() -> None:
    assert ExportedCreativeEngine is CreativeEngine


def test_engine_runs_seed_transform_evaluate_select_loop() -> None:
    provider = DeterministicCreativeProvider()
    engine = build_engine(provider)

    result = engine.run(
        TaskContext(
            goal="Invent a calmer way for distributed teams to make decisions.",
            constraints=("No meetings",),
        ),
        RunConfig(
            max_cost_usd=1,
            max_calls=20,
            max_generations=1,
            seed_count=3,
            finalist_count=2,
            framing_reserve_usd=0,
            finalization_reserve_usd=0.05,
        ),
    )

    assert len(result.finalists) == 2
    assert len(result.all_candidates) == 6
    assert any(candidate.generation == 1 for candidate in result.all_candidates)
    assert all(candidate.scores is not None for candidate in result.all_candidates)
    assert result.stopped_reason == "generation_limit"
    assert sum(record.cost_usd for record in result.spend_records) <= 1


def test_engine_returns_current_frontier_when_budget_cannot_transform() -> None:
    provider = DeterministicCreativeProvider()
    engine = build_engine(provider)

    result = engine.run(
        TaskContext(goal="Invent a new decision process."),
        RunConfig(
            max_cost_usd=0.04,
            max_calls=10,
            max_generations=2,
            seed_count=2,
            finalist_count=1,
            framing_reserve_usd=0,
            finalization_reserve_usd=0,
        ),
    )

    assert len(result.finalists) == 1
    assert result.stopped_reason == "budget_exhausted"


def test_engine_does_not_start_seed_batch_without_all_required_calls() -> None:
    provider = CountingProvider()
    engine = build_engine(provider)

    result = engine.run(
        TaskContext(goal="Invent a new decision process."),
        RunConfig(
            max_cost_usd=1,
            max_calls=2,
            max_generations=1,
            seed_count=2,
            finalist_count=1,
            framing_reserve_usd=0,
            finalization_reserve_usd=0,
        ),
    )

    assert provider.seed_calls == 0
    assert result.all_candidates == ()
    assert result.finalists == ()
    assert result.spend_records == ()
    assert result.stopped_reason == "budget_exhausted"


def test_engine_does_not_start_seed_batch_without_all_required_cost() -> None:
    provider = CountingProvider()
    engine = build_engine(provider)

    result = engine.run(
        TaskContext(goal="Invent a new decision process."),
        RunConfig(
            max_cost_usd=0.019,
            max_calls=10,
            max_generations=1,
            seed_count=2,
            finalist_count=1,
            framing_reserve_usd=0,
            finalization_reserve_usd=0,
        ),
    )

    assert provider.seed_calls == 0
    assert result.all_candidates == ()
    assert result.finalists == ()
    assert result.spend_records == ()
    assert result.stopped_reason == "budget_exhausted"


def test_engine_does_not_transform_without_two_reserved_calls() -> None:
    provider = CountingProvider()
    engine = build_engine(provider)

    result = engine.run(
        TaskContext(goal="Invent a new decision process."),
        RunConfig(
            max_cost_usd=1,
            max_calls=4,
            max_generations=1,
            seed_count=2,
            finalist_count=1,
            framing_reserve_usd=0,
            finalization_reserve_usd=0,
        ),
    )

    assert provider.seed_calls == 1
    assert provider.transform_calls == 0
    assert len(result.all_candidates) == 2
    assert len(result.spend_records) == 3
    assert result.stopped_reason == "budget_exhausted"


def test_engine_uses_quotes_and_accepts_exact_seed_budget_boundaries() -> None:
    provider = AdversarialProvider(
        seed_quote=OperationQuote(max_cost_usd=0.02, calls=1),
        evaluation_quote=OperationQuote(max_cost_usd=0.01, calls=1),
        seed_cost_usd=0.02,
        evaluation_cost_usd=0.01,
    )

    result = build_engine(provider).run(
        TaskContext(goal="Invent a new decision process."),
        RunConfig(
            max_cost_usd=0.09,
            max_calls=3,
            max_generations=0,
            seed_count=2,
            finalist_count=1,
            framing_reserve_usd=0,
            finalization_reserve_usd=0.05,
        ),
    )

    assert len(result.all_candidates) == 2
    assert sum(record.cost_usd for record in result.spend_records) == 0.04
    assert result.stopped_reason == "generation_limit"


def test_engine_rejects_wrong_seed_cardinality_before_evaluation() -> None:
    provider = AdversarialProvider(seed_cardinality=1)

    result = build_engine(provider).run(
        TaskContext(goal="Invent a new decision process."),
        RunConfig(
            max_cost_usd=1,
            max_calls=10,
            max_generations=1,
            seed_count=2,
            finalist_count=1,
            framing_reserve_usd=0,
            finalization_reserve_usd=0,
        ),
    )

    assert provider.evaluation_calls == 0
    assert result.all_candidates == ()
    assert result.finalists == ()
    assert [record.stage for record in result.spend_records] == ["seeding"]
    assert result.stopped_reason == "provider_error"


def test_engine_rejects_empty_seed_batch_before_evaluation() -> None:
    provider = AdversarialProvider(seed_cardinality=0)

    result = build_engine(provider).run(
        TaskContext(goal="Invent a new decision process."),
        RunConfig(
            max_cost_usd=1,
            max_calls=10,
            max_generations=1,
            seed_count=2,
            finalist_count=1,
            framing_reserve_usd=0,
            finalization_reserve_usd=0,
        ),
    )

    assert provider.evaluation_calls == 0
    assert result.all_candidates == ()
    assert result.finalists == ()
    assert [record.stage for record in result.spend_records] == ["seeding"]
    assert result.stopped_reason == "provider_error"


def test_engine_handles_seed_exception_without_fabricating_spend() -> None:
    provider = AdversarialProvider(raise_seed=True)

    result = build_engine(provider).run(
        TaskContext(goal="Invent a new decision process."),
        RunConfig(
            max_cost_usd=1,
            max_calls=10,
            max_generations=1,
            seed_count=2,
            finalist_count=1,
            framing_reserve_usd=0,
            finalization_reserve_usd=0,
        ),
    )

    assert result.all_candidates == ()
    assert result.spend_records == ()
    assert result.stopped_reason == "provider_error"


def test_engine_handles_seed_cost_above_quote_without_partial_accounting() -> None:
    provider = AdversarialProvider(seed_cost_usd=0.011)

    result = build_engine(provider).run(
        TaskContext(goal="Invent a new decision process."),
        RunConfig(
            max_cost_usd=1,
            max_calls=10,
            max_generations=1,
            seed_count=2,
            finalist_count=1,
            framing_reserve_usd=0,
            finalization_reserve_usd=0,
        ),
    )

    assert result.all_candidates == ()
    assert result.spend_records == ()
    assert result.stopped_reason == "provider_error"


def test_engine_preserves_completed_seed_evaluations_when_later_evaluation_fails() -> None:
    provider = AdversarialProvider(raise_evaluation_at=2)

    result = build_engine(provider).run(
        TaskContext(goal="Invent a new decision process."),
        RunConfig(
            max_cost_usd=1,
            max_calls=10,
            max_generations=1,
            seed_count=2,
            finalist_count=1,
            framing_reserve_usd=0,
            finalization_reserve_usd=0,
        ),
    )

    assert len(result.all_candidates) == 1
    assert len(result.finalists) == 1
    assert [record.stage for record in result.spend_records] == [
        "seeding",
        "evaluation",
    ]
    assert result.stopped_reason == "provider_error"


def test_engine_handles_evaluation_cost_above_quote_without_charging_that_call() -> None:
    provider = AdversarialProvider(evaluation_cost_usd=0.006)

    result = build_engine(provider).run(
        TaskContext(goal="Invent a new decision process."),
        RunConfig(
            max_cost_usd=1,
            max_calls=10,
            max_generations=1,
            seed_count=2,
            finalist_count=1,
            framing_reserve_usd=0,
            finalization_reserve_usd=0,
        ),
    )

    assert result.all_candidates == ()
    assert [record.stage for record in result.spend_records] == ["seeding"]
    assert result.stopped_reason == "provider_error"


def test_engine_preserves_seed_frontier_when_transform_raises() -> None:
    provider = AdversarialProvider(raise_transform=True)

    result = build_engine(provider).run(
        TaskContext(goal="Invent a new decision process."),
        RunConfig(
            max_cost_usd=1,
            max_calls=10,
            max_generations=1,
            seed_count=2,
            finalist_count=1,
            framing_reserve_usd=0,
            finalization_reserve_usd=0,
        ),
    )

    assert len(result.all_candidates) == 2
    assert len(result.finalists) == 1
    assert [record.stage for record in result.spend_records] == [
        "seeding",
        "evaluation",
        "evaluation",
    ]
    assert result.stopped_reason == "provider_error"


def test_engine_rejects_transform_cost_above_its_quote_without_charging_it() -> None:
    provider = AdversarialProvider(transform_cost_usd=0.011)

    result = build_engine(provider).run(
        TaskContext(goal="Invent a new decision process."),
        RunConfig(
            max_cost_usd=1,
            max_calls=10,
            max_generations=1,
            seed_count=2,
            finalist_count=1,
            framing_reserve_usd=0,
            finalization_reserve_usd=0,
        ),
    )

    assert len(result.all_candidates) == 2
    assert [record.stage for record in result.spend_records] == [
        "seeding",
        "evaluation",
        "evaluation",
    ]
    assert result.stopped_reason == "provider_error"


def test_engine_charges_transform_but_not_failed_descendant_evaluation() -> None:
    provider = AdversarialProvider(raise_evaluation_at=3)

    result = build_engine(provider).run(
        TaskContext(goal="Invent a new decision process."),
        RunConfig(
            max_cost_usd=1,
            max_calls=10,
            max_generations=1,
            seed_count=2,
            finalist_count=1,
            framing_reserve_usd=0,
            finalization_reserve_usd=0,
        ),
    )

    assert len(result.all_candidates) == 2
    assert [record.stage for record in result.spend_records] == [
        "seeding",
        "evaluation",
        "evaluation",
        "transformation",
    ]
    assert result.stopped_reason == "provider_error"


def test_engine_never_inserts_duplicate_candidate_ids() -> None:
    provider = AdversarialProvider(duplicate_transform_id=True)

    result = build_engine(provider).run(
        TaskContext(goal="Invent a new decision process."),
        RunConfig(
            max_cost_usd=1,
            max_calls=10,
            max_generations=1,
            seed_count=2,
            finalist_count=1,
            framing_reserve_usd=0,
            finalization_reserve_usd=0,
        ),
    )

    ids = [candidate.id for candidate in result.all_candidates]
    assert len(ids) == len(set(ids)) == 2
    assert provider.evaluation_calls == 2
    assert [record.stage for record in result.spend_records][-1] == "transformation"
    assert result.stopped_reason == "provider_error"


def test_engine_accepts_one_transform_at_exact_cost_call_and_reserve_boundary() -> None:
    provider = DeterministicCreativeProvider()

    result = build_engine(provider).run(
        TaskContext(goal="Invent a new decision process."),
        RunConfig(
            max_cost_usd=0.085,
            max_calls=5,
            max_generations=1,
            seed_count=2,
            finalist_count=1,
            framing_reserve_usd=0,
            finalization_reserve_usd=0.05,
        ),
    )

    assert len(result.all_candidates) == 3
    assert sum(record.cost_usd for record in result.spend_records) == 0.035
    assert len(result.spend_records) == 5
    assert result.stopped_reason == "budget_exhausted"


def test_engine_releases_unused_reservation_after_provider_error(
    monkeypatch: MonkeyPatch,
) -> None:
    TrackingBudget.instances.clear()
    monkeypatch.setattr(engine_module, "BudgetController", TrackingBudget)
    provider = AdversarialProvider(raise_transform=True)

    result = build_engine(provider).run(
        TaskContext(goal="Invent a new decision process."),
        RunConfig(
            max_cost_usd=1,
            max_calls=10,
            max_generations=1,
            seed_count=2,
            finalist_count=1,
            framing_reserve_usd=0,
            finalization_reserve_usd=0,
        ),
    )

    budget = TrackingBudget.instances[-1]
    assert result.stopped_reason == "provider_error"
    assert budget._reserved_cost == Decimal("0")
    assert budget._reserved_calls == 0


def test_engine_uses_quoted_call_counts_before_invoking_seed_provider() -> None:
    provider = AdversarialProvider(
        seed_quote=OperationQuote(max_cost_usd=0.01, calls=2),
    )

    result = build_engine(provider).run(
        TaskContext(goal="Invent a new decision process."),
        RunConfig(
            max_cost_usd=1,
            max_calls=3,
            max_generations=0,
            seed_count=2,
            finalist_count=1,
            framing_reserve_usd=0,
            finalization_reserve_usd=0,
        ),
    )

    assert provider.seed_calls == 0
    assert result.spend_records == ()
    assert result.stopped_reason == "budget_exhausted"


def test_engine_rejects_oversized_seed_batch_before_evaluation() -> None:
    provider = AdversarialProvider(seed_cardinality=3)

    result = build_engine(provider).run(
        TaskContext(goal="Invent a new decision process."),
        RunConfig(
            max_cost_usd=1,
            max_calls=10,
            max_generations=0,
            seed_count=2,
            finalist_count=1,
            framing_reserve_usd=0,
            finalization_reserve_usd=0,
        ),
    )

    assert provider.evaluation_calls == 0
    assert result.all_candidates == ()
    assert [record.stage for record in result.spend_records] == ["seeding"]
    assert result.stopped_reason == "provider_error"


def test_engine_rejects_duplicate_seed_ids_before_evaluation() -> None:
    provider = AdversarialProvider(duplicate_seed_ids=True)

    result = build_engine(provider).run(
        TaskContext(goal="Invent a new decision process."),
        RunConfig(
            max_cost_usd=1,
            max_calls=10,
            max_generations=0,
            seed_count=2,
            finalist_count=1,
            framing_reserve_usd=0,
            finalization_reserve_usd=0,
        ),
    )

    assert provider.evaluation_calls == 0
    assert result.all_candidates == ()
    assert [record.stage for record in result.spend_records] == ["seeding"]
    assert result.stopped_reason == "provider_error"


def test_engine_handles_seed_quote_exception_without_invoking_provider() -> None:
    provider = AdversarialProvider(raise_seed_quote=True)

    result = build_engine(provider).run(
        TaskContext(goal="Invent a new decision process."),
        RunConfig(
            max_cost_usd=1,
            max_calls=10,
            max_generations=0,
            seed_count=2,
            finalist_count=1,
            framing_reserve_usd=0,
            finalization_reserve_usd=0,
        ),
    )

    assert provider.seed_calls == 0
    assert result.spend_records == ()
    assert result.stopped_reason == "provider_error"


def test_engine_handles_transform_quote_exception_with_seed_frontier() -> None:
    provider = AdversarialProvider(raise_transform_quote=True)

    result = build_engine(provider).run(
        TaskContext(goal="Invent a new decision process."),
        RunConfig(
            max_cost_usd=1,
            max_calls=10,
            max_generations=1,
            seed_count=2,
            finalist_count=1,
            framing_reserve_usd=0,
            finalization_reserve_usd=0,
        ),
    )

    assert provider.transform_calls == 0
    assert len(result.all_candidates) == 2
    assert result.stopped_reason == "provider_error"


def test_engine_advances_to_generation_two_without_duplicate_ids() -> None:
    provider = DeterministicCreativeProvider()

    result = build_engine(provider).run(
        TaskContext(goal="Invent a new decision process."),
        RunConfig(
            max_cost_usd=1,
            max_calls=30,
            max_generations=2,
            seed_count=3,
            finalist_count=2,
            framing_reserve_usd=0,
            finalization_reserve_usd=0.05,
        ),
    )

    ids = [candidate.id for candidate in result.all_candidates]
    assert len(ids) == len(set(ids))
    assert {candidate.generation for candidate in result.all_candidates} == {0, 1, 2}
    assert sum(candidate.generation == 2 for candidate in result.all_candidates) == 3
    assert result.stopped_reason == "generation_limit"


def test_engine_selects_parents_only_from_the_highest_completed_generation() -> None:
    provider = DeterministicCreativeProvider()
    population = RecordingPopulation()
    engine = CreativeEngine(
        framer=provider,
        seeder=provider,
        transformer=provider,
        evaluator=provider,
        population=population,
    )

    result = engine.run(
        TaskContext(goal="Invent a new decision process."),
        RunConfig(
            max_cost_usd=1,
            max_calls=30,
            max_generations=2,
            seed_count=3,
            finalist_count=2,
            framing_reserve_usd=0,
            finalization_reserve_usd=0.05,
        ),
    )

    parent_selections = population.selection_inputs[:-1]
    assert [len(items) for items in parent_selections] == [3, 3]
    assert [{item.generation for item in items} for items in parent_selections] == [
        {0},
        {1},
    ]
    assert len(result.all_candidates) == 9


def test_engine_with_zero_generations_returns_evaluated_seeds() -> None:
    provider = DeterministicCreativeProvider()

    result = build_engine(provider).run(
        TaskContext(goal="Invent a new decision process."),
        RunConfig(
            max_cost_usd=1,
            max_calls=10,
            max_generations=0,
            seed_count=2,
            finalist_count=1,
            framing_reserve_usd=0,
            finalization_reserve_usd=0,
        ),
    )

    assert len(result.all_candidates) == 2
    assert all(candidate.generation == 0 for candidate in result.all_candidates)
    assert all(candidate.scores is not None for candidate in result.all_candidates)
    assert result.stopped_reason == "generation_limit"


def test_engine_repeated_runs_have_identical_creative_results() -> None:
    provider = DeterministicCreativeProvider()
    config = RunConfig(
        max_cost_usd=1,
        max_calls=20,
        max_generations=1,
        seed_count=3,
        finalist_count=2,
        framing_reserve_usd=0,
        finalization_reserve_usd=0.05,
    )
    task = TaskContext(goal="Invent a new decision process.")

    first = build_engine(provider).run(task, config)
    second = build_engine(provider).run(task, config)

    assert [
        candidate.model_dump(mode="json") for candidate in first.all_candidates
    ] == [candidate.model_dump(mode="json") for candidate in second.all_candidates]
    assert [candidate.id for candidate in first.finalists] == [
        candidate.id for candidate in second.finalists
    ]
    assert [
        (record.stage, record.provider, record.cost_usd, record.latency_ms)
        for record in first.spend_records
    ] == [
        (record.stage, record.provider, record.cost_usd, record.latency_ms)
        for record in second.spend_records
    ]
