from creativity_layer.models import IdeaGenome
from creativity_layer.transforms import OperatorName, TransformationRequest


def test_transformation_request_records_structural_intent() -> None:
    parent = IdeaGenome(
        generation=0,
        title="Queue",
        core_mechanism="People wait in arrival order.",
        problem_framing="Demand exceeds immediate capacity.",
        assumptions_challenged=(),
        task_value="Creates predictable access.",
        distinguishing_features=("arrival order",),
    )

    request = TransformationRequest.for_operator(
        operator=OperatorName.INVERT,
        parents=(parent,),
        task_goal="Make waiting fairer without a visible queue.",
    )

    assert request.operator is OperatorName.INVERT
    assert request.parent_ids == (parent.id,)
    assert "Reverse a foundational assumption" in request.instruction
    assert "Do not merely rename" in request.instruction


def test_combine_requires_two_parents() -> None:
    parent = IdeaGenome(
        generation=0,
        title="Queue",
        core_mechanism="People wait in arrival order.",
        problem_framing="Demand exceeds immediate capacity.",
        task_value="Creates predictable access.",
    )

    try:
        TransformationRequest.for_operator(
            operator=OperatorName.COMBINE,
            parents=(parent,),
            task_goal="Improve access.",
        )
    except ValueError as error:
        assert str(error) == "combine requires exactly two parents"
    else:
        raise AssertionError("combine accepted one parent")
