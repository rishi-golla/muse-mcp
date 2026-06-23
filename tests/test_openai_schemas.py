from uuid import UUID

import pytest
from pydantic import ValidationError

from creativity_layer.models import IdeaGenome, InspirationKind, TaskContext
from creativity_layer.openai_schemas import (
    OpenAIEvaluation,
    OpenAIFrame,
    OpenAIIdea,
    OpenAISeedBatch,
)
from creativity_layer.transforms import (
    OperatorName,
    TransformationRequest,
    expected_transformation_history,
)


def _idea_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "title": "Confidence garden",
        "core_mechanism": "Claims gain reversible confidence through evidence.",
        "problem_framing": "Decision-making is evidence accumulation.",
        "assumptions_challenged": ["Votes must be final"],
        "task_value": "Reduces premature consensus.",
        "distinguishing_features": ["reversible confidence"],
        "first_order_effects": [],
        "second_order_effects": [],
        "feasibility_assumptions": [],
        "uncertainties": [],
        "weaknesses": [],
    }
    payload.update(overrides)
    return payload


def _idea(**overrides: object) -> OpenAIIdea:
    return OpenAIIdea.model_validate(_idea_payload(**overrides))


def _parent(*, generation: int, transformations: tuple[str, ...] = ()) -> IdeaGenome:
    return IdeaGenome(
        generation=generation,
        title="Parent idea",
        core_mechanism="A parent mechanism.",
        problem_framing="A parent framing.",
        task_value="A parent value.",
        transformations=transformations,
    )


def test_openai_frame_converts_to_internal_frame() -> None:
    schema = OpenAIFrame(
        assumptions=["Meetings are required"],
        obvious_solution="Use a voting form",
    )

    framed = schema.to_domain(TaskContext(goal="Improve decisions"))

    assert framed.context.goal == "Improve decisions"
    assert framed.assumptions == ("Meetings are required",)


def test_openai_idea_converts_without_provider_controlled_identity() -> None:
    candidate = _idea().to_seed(generation=0)

    assert isinstance(candidate.id, UUID)
    assert candidate.generation == 0
    assert candidate.parent_ids == ()
    assert candidate.transformations == ()
    assert candidate.inspiration_kind is InspirationKind.INDEPENDENT


def test_openai_evaluation_converts_to_scores() -> None:
    scores = OpenAIEvaluation(
        originality=0.8,
        usefulness=0.7,
        coherence=0.9,
        feasibility=0.6,
        user_fit=0.75,
    ).to_domain()

    assert scores.originality == 0.8


@pytest.mark.parametrize(
    ("model", "payload"),
    [
        (
            OpenAIFrame,
            {"assumptions": ["Meetings are required"], "obvious_solution": " \t "},
        ),
        (OpenAIFrame, {"assumptions": ["\n"], "obvious_solution": "Use a form"}),
        (OpenAIIdea, _idea_payload(title=" ")),
        (
            OpenAIIdea,
            _idea_payload(distinguishing_features=["reversible confidence", ""]),
        ),
    ],
)
def test_output_schemas_reject_blank_required_text(
    model: type[OpenAIFrame] | type[OpenAIIdea],
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        model.model_validate(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("originality", -0.01),
        ("usefulness", 1.01),
        ("coherence", float("nan")),
        ("feasibility", float("inf")),
    ],
)
def test_openai_evaluation_rejects_invalid_scores(field: str, value: float) -> None:
    payload = {
        "originality": 0.8,
        "usefulness": 0.7,
        "coherence": 0.9,
        "feasibility": 0.6,
        "user_fit": 0.75,
        field: value,
    }

    with pytest.raises(ValidationError):
        OpenAIEvaluation.model_validate(payload)


@pytest.mark.parametrize(
    "trust_field",
    [
        "id",
        "generation",
        "parent_ids",
        "transformations",
        "inspiration_kind",
        "scores",
        "branch_cost_usd",
        "branch_latency_ms",
    ],
)
def test_openai_idea_forbids_provider_controlled_trust_fields(
    trust_field: str,
) -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        OpenAIIdea.model_validate(_idea_payload(**{trust_field: "provider-value"}))


def test_transform_conversion_uses_local_ancestry_and_history() -> None:
    first = _parent(generation=2, transformations=("invert",))
    second = _parent(generation=4, transformations=("transfer",))
    request = TransformationRequest.for_operator(
        operator=OperatorName.COMBINE,
        parents=(first, second),
        task_goal="Improve decisions",
    )

    candidate = _idea().to_transform(
        request=request,
        parents=(first, second),
    )

    assert candidate.generation == 5
    assert candidate.parent_ids == request.parent_ids
    assert candidate.transformations == expected_transformation_history(
        request.operator,
        (first, second),
    )
    assert candidate.inspiration_kind is InspirationKind.SYNTHESIZED
    assert candidate.id not in {first.id, second.id}


def test_seed_batch_cardinality_mismatch_is_rejected() -> None:
    batch = OpenAISeedBatch(ideas=[_idea()])

    with pytest.raises(
        ValueError,
        match="seed cardinality does not match requested seed_count",
    ):
        batch.to_seeds(generation=0, expected_count=2)


def test_seed_batch_converts_every_idea_without_truncation() -> None:
    batch = OpenAISeedBatch(
        ideas=[
            _idea(title="First"),
            _idea(title="Second"),
        ]
    )

    candidates = batch.to_seeds(generation=0, expected_count=2)

    assert tuple(candidate.title for candidate in candidates) == ("First", "Second")
    assert len({candidate.id for candidate in candidates}) == 2


@pytest.mark.parametrize(
    "model",
    [OpenAIFrame, OpenAIIdea, OpenAISeedBatch, OpenAIEvaluation],
)
def test_output_json_schemas_require_every_declared_field(
    model: type[OpenAIFrame]
    | type[OpenAIIdea]
    | type[OpenAISeedBatch]
    | type[OpenAIEvaluation],
) -> None:
    schema = model.model_json_schema()

    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"])
    assert all("default" not in definition for definition in schema["properties"].values())
