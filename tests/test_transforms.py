from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from muse.models import IdeaGenome
from muse.operation import validate_transform_payload
from muse.providers import MeteredResponse
from muse.transforms import (
    OPERATOR_INSTRUCTIONS,
    OperatorName,
    TransformationRequest,
)


def parent(title: str = "Queue") -> IdeaGenome:
    return IdeaGenome(
        generation=0,
        title=title,
        core_mechanism=f"{title} mechanism.",
        problem_framing=f"{title} framing.",
        task_value=f"{title} value.",
    )


def test_transformation_request_records_structural_intent() -> None:
    source = IdeaGenome(
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
        parents=(source,),
        task_goal="Make waiting fairer without a visible queue.",
    )

    assert request.operator is OperatorName.INVERT
    assert request.parent_ids == (source.id,)
    assert "Reverse a foundational assumption" in request.instruction
    assert "Do not merely rename" in request.instruction


@pytest.mark.parametrize(
    "history",
    (
        ("invert", "reframe"),
        ("invert", "transfer", "extra", "reframe"),
        ("forged", "invert", "transfer", "reframe"),
    ),
)
def test_transform_validation_rejects_missing_extra_or_forged_unary_history(
    history: tuple[str, ...],
) -> None:
    source = parent().model_copy(
        update={"transformations": ("invert", "transfer")}
    )
    request = TransformationRequest.for_operator(
        operator=OperatorName.REFRAME,
        parents=(source,),
        task_goal="Improve access.",
    )
    candidate = parent("Child").model_copy(
        update={
            "generation": 1,
            "parent_ids": (source.id,),
            "transformations": history,
        }
    )
    response = MeteredResponse(
        value=candidate,
        provider="local",
        cost_usd=0.01,
        latency_ms=1,
    )

    with pytest.raises(ValueError, match="history"):
        validate_transform_payload(
            response,
            request=request,
            parents=(source,),
            candidate_ids=set(),
        )


def test_transform_validation_accepts_only_the_exact_combine_history() -> None:
    first = parent("First").model_copy(
        update={"transformations": ("invert", "invert")}
    )
    second = parent("Second").model_copy(
        update={"transformations": ("invert", "reframe", "subtract")}
    )
    request = TransformationRequest.for_operator(
        operator=OperatorName.COMBINE,
        parents=(first, second),
        task_goal="Improve access.",
    )
    expected = ("invert", "invert", "reframe", "subtract", "combine")

    for history in (
        expected[:-1],
        expected + ("extra",),
        ("forged",) + expected,
    ):
        candidate = parent("Child").model_copy(
            update={
                "generation": 1,
                "parent_ids": (first.id, second.id),
                "transformations": history,
            }
        )
        response = MeteredResponse(
            value=candidate,
            provider="local",
            cost_usd=0.01,
            latency_ms=1,
        )

        with pytest.raises(ValueError, match="history"):
            validate_transform_payload(
                response,
                request=request,
                parents=(first, second),
                candidate_ids=set(),
            )


def test_combine_requires_two_parents() -> None:
    source = parent()

    with pytest.raises(ValidationError, match="combine requires exactly two parents"):
        TransformationRequest.for_operator(
            operator=OperatorName.COMBINE,
            parents=(source,),
            task_goal="Improve access.",
        )


def test_operator_instructions_cover_every_operator_exactly() -> None:
    assert set(OPERATOR_INSTRUCTIONS) == set(OperatorName)


@pytest.mark.parametrize("operator", tuple(OperatorName))
def test_factory_builds_valid_request_for_every_operator(operator: OperatorName) -> None:
    first = parent("First")
    second = parent("Second")
    parents = (first, second) if operator is OperatorName.COMBINE else (first,)

    request = TransformationRequest.for_operator(
        operator=operator,
        parents=parents,
        task_goal="Improve access.",
    )

    assert request.operator is operator
    assert request.parent_ids == tuple(item.id for item in parents)
    assert OPERATOR_INSTRUCTIONS[operator] in request.instruction


@pytest.mark.parametrize(
    ("operator", "parent_ids", "message"),
    (
        (OperatorName.COMBINE, (uuid4(),), "combine requires exactly two parents"),
        (
            OperatorName.INVERT,
            (uuid4(), uuid4()),
            "invert requires exactly one parent",
        ),
    ),
)
def test_direct_construction_rejects_invalid_operator_cardinality(
    operator: OperatorName,
    parent_ids: tuple[UUID, ...],
    message: str,
) -> None:
    with pytest.raises(ValidationError, match=message):
        TransformationRequest(
            operator=operator,
            parent_ids=parent_ids,
            task_goal="Improve access.",
            instruction="Change the structure.",
        )


def test_deserialization_rejects_invalid_operator_cardinality() -> None:
    with pytest.raises(ValidationError, match="subtract requires exactly one parent"):
        TransformationRequest.model_validate(
            {
                "operator": "subtract",
                "parent_ids": [str(uuid4()), str(uuid4())],
                "task_goal": "Improve access.",
                "instruction": "Change the structure.",
            }
        )


def test_combine_rejects_duplicate_parent_ids() -> None:
    shared_id = uuid4()

    with pytest.raises(ValidationError, match="combine requires two distinct parents"):
        TransformationRequest(
            operator=OperatorName.COMBINE,
            parent_ids=(shared_id, shared_id),
            task_goal="Improve access.",
            instruction="Merge mechanisms.",
        )


def test_factory_rejects_duplicate_combine_parents() -> None:
    source = parent()

    with pytest.raises(ValidationError, match="combine requires two distinct parents"):
        TransformationRequest.for_operator(
            operator=OperatorName.COMBINE,
            parents=(source, source),
            task_goal="Improve access.",
        )


@pytest.mark.parametrize("field", ("task_goal", "instruction"))
def test_transformation_request_rejects_whitespace_text(field: str) -> None:
    values = {
        "operator": OperatorName.INVERT,
        "parent_ids": (uuid4(),),
        "task_goal": "Improve access.",
        "instruction": "Change the structure.",
    }
    values[field] = "   "

    with pytest.raises(ValidationError, match="text must not be blank"):
        TransformationRequest(**values)
