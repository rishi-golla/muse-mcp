from creativity_layer.deterministic import DeterministicCreativeProvider
from creativity_layer.models import RunConfig, TaskContext
from creativity_layer.transforms import OperatorName, TransformationRequest


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
    assert [item.title for item in first.value] == [item.title for item in second.value]
    assert first.cost_usd == 0.01


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
