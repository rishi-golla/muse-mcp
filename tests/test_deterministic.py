import pytest
from pydantic import ValidationError

from creativity_layer.deterministic import DeterministicCreativeProvider
from creativity_layer.models import FramedTask, IdeaGenome, RunConfig, TaskContext
from creativity_layer.providers import OperationQuote
from creativity_layer.transforms import OperatorName, TransformationRequest


@pytest.mark.parametrize("calls", [0, 2, 3])
def test_operation_quote_rejects_call_counts_other_than_one(calls: int) -> None:
    with pytest.raises(ValidationError):
        OperationQuote(max_cost_usd=0.01, calls=calls)


def test_provider_returns_exact_typed_operation_quotes() -> None:
    provider = DeterministicCreativeProvider()
    task = TaskContext(goal="Invent a calmer decision process.")
    framed = provider.frame(task)
    config = RunConfig(seed_count=2, finalist_count=1)
    parent = provider.seed(framed, config).value[0]
    request = TransformationRequest.for_operator(
        operator=OperatorName.INVERT,
        parents=(parent,),
        task_goal=task.goal,
    )

    assert provider.quote_seed(framed, config) == OperationQuote(
        max_cost_usd=0.01,
        calls=1,
    )
    assert provider.quote_transform(request, (parent,)) == OperationQuote(
        max_cost_usd=0.01,
        calls=1,
    )
    assert provider.quote_evaluation(framed) == OperationQuote(
        max_cost_usd=0.005,
        calls=1,
    )


def test_provider_frames_and_seeds_reproducibly() -> None:
    provider = DeterministicCreativeProvider()
    task = TaskContext(
        goal="Invent a calmer way for distributed teams to make decisions.",
        constraints=("No meetings",),
    )

    framed = provider.frame(task)
    first = provider.seed(framed, RunConfig(seed_count=3, finalist_count=2))
    second = provider.seed(framed, RunConfig(seed_count=3, finalist_count=2))

    assert framed.obvious_solution == "Use an asynchronous voting tool."
    assert len(first.value) == 3
    assert first == second
    assert [item.id for item in first.value] == [item.id for item in second.value]
    assert first.cost_usd == 0.01


def test_provider_generates_the_exact_seed_count_with_unique_stable_ids() -> None:
    provider = DeterministicCreativeProvider()
    framed = provider.frame(TaskContext(goal="Invent a calmer decision process."))
    config = RunConfig(seed_count=7, finalist_count=2)

    first = provider.seed(framed, config)
    second = provider.seed(framed, config)

    assert len(first.value) == 7
    assert len({candidate.id for candidate in first.value}) == 7
    assert first == second


def test_provider_seeds_a_framed_task_without_assumptions() -> None:
    provider = DeterministicCreativeProvider()
    framed = FramedTask(
        context=TaskContext(goal="Invent a calmer decision process."),
        assumptions=(),
        obvious_solution="Use a standard voting process.",
    )

    response = provider.seed(
        framed,
        RunConfig(seed_count=2, finalist_count=1),
    )

    assert len(response.value) == 2
    assert all(not candidate.assumptions_challenged for candidate in response.value)


def test_provider_transforms_the_mechanism_and_records_ancestry() -> None:
    provider = DeterministicCreativeProvider()
    task = TaskContext(goal="Invent a calmer decision process.")
    framed = provider.frame(task)
    parent = provider.seed(
        framed,
        RunConfig(seed_count=2, finalist_count=1),
    ).value[0]
    request = TransformationRequest.for_operator(
        operator=OperatorName.INVERT,
        parents=(parent,),
        task_goal=task.goal,
    )

    child = provider.transform(request, (parent,)).value

    assert child.parent_ids == (parent.id,)
    assert child.generation == 1
    assert child.transformations == ("invert",)
    assert child.core_mechanism != parent.core_mechanism


def test_unary_transform_preserves_the_parent_history_exactly() -> None:
    provider = DeterministicCreativeProvider()
    task = TaskContext(goal="Invent a calmer decision process.")
    seeded = provider.seed(
        provider.frame(task),
        RunConfig(seed_count=2, finalist_count=1),
    ).value[0]
    parent = seeded.model_copy(
        update={"transformations": ("invert", "invert", "transfer")}
    )
    request = TransformationRequest.for_operator(
        operator=OperatorName.REFRAME,
        parents=(parent,),
        task_goal=task.goal,
    )

    child = provider.transform(request, (parent,)).value

    assert child.transformations == ("invert", "invert", "transfer", "reframe")


def test_combine_transform_merges_histories_in_parent_order() -> None:
    provider = DeterministicCreativeProvider()
    task = TaskContext(goal="Invent a calmer decision process.")
    seeded = provider.seed(
        provider.frame(task),
        RunConfig(seed_count=2, finalist_count=1),
    ).value
    parents = (
        seeded[0].model_copy(update={"transformations": ("invert", "invert")}),
        seeded[1].model_copy(
            update={
                "transformations": (
                    "invert",
                    "reframe",
                    "reframe",
                    "subtract",
                )
            }
        ),
    )
    request = TransformationRequest.for_operator(
        operator=OperatorName.COMBINE,
        parents=parents,
        task_goal=task.goal,
    )

    child = provider.transform(request, parents).value

    assert child.transformations == (
        "invert",
        "invert",
        "reframe",
        "subtract",
        "combine",
    )


def test_unary_transform_is_reproducible_and_sensitive_to_the_parent() -> None:
    provider = DeterministicCreativeProvider()
    task = TaskContext(goal="Invent a calmer decision process.")
    parents = provider.seed(
        provider.frame(task),
        RunConfig(seed_count=2, finalist_count=1),
    ).value
    first_request = TransformationRequest.for_operator(
        operator=OperatorName.INVERT,
        parents=(parents[0],),
        task_goal=task.goal,
    )
    second_request = TransformationRequest.for_operator(
        operator=OperatorName.INVERT,
        parents=(parents[1],),
        task_goal=task.goal,
    )

    first = provider.transform(first_request, (parents[0],))
    repeated = provider.transform(first_request, (parents[0],))
    second = provider.transform(second_request, (parents[1],))

    assert first == repeated
    assert first.value.id == repeated.value.id
    assert first != second
    assert parents[0].title in first.value.core_mechanism
    assert parents[1].title in second.value.core_mechanism


@pytest.mark.parametrize(
    "operator",
    tuple(operator for operator in OperatorName if operator is not OperatorName.COMBINE),
)
def test_each_unary_operator_changes_the_parent_causal_structure(
    operator: OperatorName,
) -> None:
    provider = DeterministicCreativeProvider()
    task = TaskContext(goal="Invent a calmer decision process.")
    parent = provider.seed(
        provider.frame(task),
        RunConfig(seed_count=2, finalist_count=1),
    ).value[0]
    request = TransformationRequest.for_operator(
        operator=operator,
        parents=(parent,),
        task_goal=task.goal,
    )

    mechanism = provider.transform(request, (parent,)).value.core_mechanism

    assert mechanism != parent.core_mechanism
    assert parent.core_mechanism not in mechanism
    assert parent.title in mechanism


def test_unary_operators_produce_distinct_mechanisms_for_the_same_parent() -> None:
    provider = DeterministicCreativeProvider()
    task = TaskContext(goal="Invent a calmer decision process.")
    parent = provider.seed(
        provider.frame(task),
        RunConfig(seed_count=2, finalist_count=1),
    ).value[0]

    mechanisms = {
        operator: provider.transform(
            TransformationRequest.for_operator(
                operator=operator,
                parents=(parent,),
                task_goal=task.goal,
            ),
            (parent,),
        ).value.core_mechanism
        for operator in OperatorName
        if operator is not OperatorName.COMBINE
    }

    assert len(set(mechanisms.values())) == len(mechanisms)


def test_combine_transform_incorporates_both_parents() -> None:
    provider = DeterministicCreativeProvider()
    task = TaskContext(goal="Invent a calmer decision process.")
    parents = provider.seed(
        provider.frame(task),
        RunConfig(seed_count=2, finalist_count=1),
    ).value
    request = TransformationRequest.for_operator(
        operator=OperatorName.COMBINE,
        parents=parents,
        task_goal=task.goal,
    )

    child = provider.transform(request, parents).value

    assert child.parent_ids == tuple(parent.id for parent in parents)
    for parent in parents:
        assert parent.title in child.core_mechanism
        assert parent.problem_framing in child.problem_framing
        assert set(parent.distinguishing_features) <= set(child.distinguishing_features)
    assert child.core_mechanism not in {
        parents[0].core_mechanism,
        parents[1].core_mechanism,
        f"{parents[0].core_mechanism} + {parents[1].core_mechanism}",
    }
    assert parents[0].core_mechanism not in child.core_mechanism
    assert parents[1].core_mechanism not in child.core_mechanism
    assert any(
        relationship in child.core_mechanism.lower()
        for relationship in ("feedback", "control", "regulates")
    )


@pytest.mark.parametrize(
    ("requested_parents", "actual_parents"),
    (
        ((0,), (1,)),
        ((0,), (0, 1)),
        ((0, 1), (0,)),
        ((0, 1), (1, 0)),
    ),
)
def test_transform_rejects_parent_ancestry_mismatches(
    requested_parents: tuple[int, ...],
    actual_parents: tuple[int, ...],
) -> None:
    provider = DeterministicCreativeProvider()
    task = TaskContext(goal="Invent a calmer decision process.")
    parents = provider.seed(
        provider.frame(task),
        RunConfig(seed_count=2, finalist_count=1),
    ).value
    operator = (
        OperatorName.COMBINE if len(requested_parents) == 2 else OperatorName.INVERT
    )
    request = TransformationRequest.for_operator(
        operator=operator,
        parents=tuple(parents[index] for index in requested_parents),
        task_goal=task.goal,
    )

    with pytest.raises(ValueError, match="parent"):
        provider.transform(
            request,
            tuple(parents[index] for index in actual_parents),
        )


def test_evaluation_is_reproducible_and_scores_stay_in_bounds() -> None:
    provider = DeterministicCreativeProvider()
    framed = provider.frame(TaskContext(goal="Invent a calmer decision process."))
    candidate: IdeaGenome = provider.seed(
        framed,
        RunConfig(seed_count=2, finalist_count=1),
    ).value[0]

    first = provider.evaluate(candidate, framed)
    second = provider.evaluate(candidate, framed)

    assert first == second
    assert all(
        0.0 <= score <= 1.0
        for score in first.value.model_dump().values()
    )
