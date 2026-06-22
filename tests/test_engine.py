from creativity_layer import CreativeEngine as ExportedCreativeEngine
from creativity_layer.deterministic import DeterministicCreativeProvider
from creativity_layer.engine import CreativeEngine
from creativity_layer.models import FramedTask, RunConfig, TaskContext
from creativity_layer.providers import MeteredResponse


class CountingProvider(DeterministicCreativeProvider):
    def __init__(self) -> None:
        self.seed_calls = 0
        self.transform_calls = 0

    def seed(
        self,
        framed_task: FramedTask,
        config: RunConfig,
    ) -> MeteredResponse:
        self.seed_calls += 1
        return super().seed(framed_task, config)

    def transform(self, request, parents) -> MeteredResponse:
        self.transform_calls += 1
        return super().transform(request, parents)


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
