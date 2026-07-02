from uuid import UUID

import pytest
from openai.lib._pydantic import to_strict_json_schema
from pydantic import ValidationError

from muse.models import (
    FramedTask,
    IdeaGenome,
    InspirationKind,
    ProviderIdentity,
    RunConfig,
    RunProviders,
    RunResult,
    TaskContext,
)
from muse.openai_schemas import (
    OpenAIEvaluation,
    OpenAIFrame,
    OpenAIIdea,
    OpenAISeedBatch,
)
from muse.transforms import (
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
        "inputs_required": ["task goal", "repo state"],
        "outputs_produced": ["candidate plan", "verification gate"],
        "agent_workflow": ["collect evidence", "choose action", "verify"],
        "decision_policy": "Stop when verification repeats the same failure.",
        "integration_points": ["planning middleware"],
        "verification_strategy": "Run the narrowest relevant check first.",
        "failure_modes": ["ambiguous evidence"],
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


def _run_fingerprint(candidate: IdeaGenome) -> str:
    identity = ProviderIdentity(name="test", version="1")
    return RunResult(
        config=RunConfig(
            max_generations=0,
            seed_count=2,
            finalist_count=1,
            framing_reserve_usd=0.0,
            finalization_reserve_usd=0.0,
        ),
        providers=RunProviders(
            framer=identity,
            seeder=identity,
            transformer=identity,
            evaluator=identity,
        ),
        operator_schedule=(),
        framed_task=FramedTask(
            context=TaskContext(goal="Improve decisions"),
            assumptions=(),
            obvious_solution="Use a form",
        ),
        finalists=(candidate,),
        all_candidates=(candidate,),
        spend_records=(),
        stopped_reason="generation_limit",
    ).reproducibility_fingerprint


def _schema_keywords(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value).union(*(_schema_keywords(item) for item in value.values()))
    if isinstance(value, list):
        return set().union(*(_schema_keywords(item) for item in value))
    return set()


def test_openai_frame_converts_to_internal_frame() -> None:
    schema = OpenAIFrame(
        assumptions=["Meetings are required"],
        obvious_solution="Use a voting form",
    )

    framed = schema.to_domain(TaskContext(goal="Improve decisions"))

    assert framed.context.goal == "Improve decisions"
    assert framed.assumptions == ("Meetings are required",)


def test_openai_idea_converts_without_provider_controlled_identity() -> None:
    candidate = _idea().to_seed()

    assert isinstance(candidate.id, UUID)
    assert candidate.generation == 0
    assert candidate.parent_ids == ()
    assert candidate.transformations == ()
    assert candidate.inspiration_kind is InspirationKind.INDEPENDENT


def test_seed_conversion_is_deterministic_for_candidates_and_run_fingerprints() -> None:
    schema = _idea()

    first = schema.to_seed()
    second = schema.to_seed()

    assert first == second
    assert _run_fingerprint(first) == _run_fingerprint(second)


def test_openai_idea_requires_operational_contract_fields() -> None:
    payload = _idea_payload()
    payload.pop("inputs_required")

    with pytest.raises(ValidationError):
        OpenAIIdea.model_validate(payload)


def test_openai_idea_operational_contract_converts_to_domain() -> None:
    candidate = _idea(
        inputs_required=["failed test output", "changed files"],
        outputs_produced=["failure classification", "next action"],
        agent_workflow=["collect evidence", "choose action", "verify"],
        decision_policy="Stop after two identical failed attempts.",
        integration_points=["post-test-failure hook"],
        verification_strategy="Run targeted test before full suite.",
        failure_modes=["ambiguous logs"],
    ).to_seed()

    assert candidate.inputs_required == ("failed test output", "changed files")
    assert candidate.outputs_produced == ("failure classification", "next action")
    assert candidate.agent_workflow == ("collect evidence", "choose action", "verify")
    assert candidate.decision_policy == "Stop after two identical failed attempts."
    assert candidate.integration_points == ("post-test-failure hook",)
    assert candidate.verification_strategy == "Run targeted test before full suite."
    assert candidate.failure_modes == ("ambiguous logs",)


@pytest.mark.parametrize(
    "variant",
    [
        "A  B",
        "A\tB",
        "Ａ B",
    ],
)
def test_canonical_equivalent_text_produces_equal_schemas_candidates_and_ids(
    variant: str,
) -> None:
    canonical = _idea(
        title="A B",
        core_mechanism="Use A B.",
        assumptions_challenged=["A B"],
    )
    equivalent = _idea(
        title=variant,
        core_mechanism=f"Use {variant}.",
        assumptions_challenged=[variant],
    )

    canonical_candidate = canonical.to_seed()
    equivalent_candidate = equivalent.to_seed()

    assert equivalent == canonical
    assert equivalent.title == "A B"
    assert equivalent.core_mechanism == "Use A B."
    assert equivalent.assumptions_challenged == ["A B"]
    assert equivalent_candidate == canonical_candidate
    assert equivalent_candidate.id == canonical_candidate.id
    assert equivalent_candidate.title == "A B"
    assert equivalent_candidate.assumptions_challenged == ("A B",)


def test_genuinely_different_text_produces_distinct_schema_candidate_and_id() -> None:
    first = _idea(title="A B")
    second = _idea(title="A C")

    first_candidate = first.to_seed()
    second_candidate = second.to_seed()

    assert first != second
    assert first_candidate != second_candidate
    assert first_candidate.id != second_candidate.id
    assert second_candidate.title == "A C"


def test_openai_evaluation_converts_to_scores() -> None:
    scores = OpenAIEvaluation(
        originality=0.8,
        usefulness=0.7,
        coherence=0.9,
        feasibility=0.6,
        user_fit=0.75,
        operational_specificity=0.85,
        workflow_fit=0.95,
    ).to_domain()

    assert scores.originality == 0.8
    assert scores.operational_specificity == 0.85


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


@pytest.mark.parametrize("parents_order", ["missing", "reversed"])
def test_transform_conversion_rejects_parent_request_mismatch(
    parents_order: str,
) -> None:
    first = _parent(generation=2, transformations=("invert",))
    second = _parent(generation=4, transformations=("transfer",))
    request = TransformationRequest.for_operator(
        operator=OperatorName.COMBINE,
        parents=(first, second),
        task_goal="Improve decisions",
    )
    parents = (first,) if parents_order == "missing" else (second, first)

    with pytest.raises(ValueError, match="transform parents do not match request"):
        _idea().to_transform(request=request, parents=parents)


def test_transform_conversion_is_deterministic() -> None:
    parent = _parent(generation=2, transformations=("invert",))
    request = TransformationRequest.for_operator(
        operator=OperatorName.REFRAME,
        parents=(parent,),
        task_goal="Improve decisions",
    )
    schema = _idea()

    first = schema.to_transform(request=request, parents=(parent,))
    second = schema.to_transform(request=request, parents=(parent,))

    assert first == second
    assert _run_fingerprint(first) == _run_fingerprint(second)


def test_seed_batch_cardinality_mismatch_is_rejected() -> None:
    batch = OpenAISeedBatch(ideas=[_idea()])

    with pytest.raises(
        ValueError,
        match="seed cardinality does not match requested seed_count",
    ):
        batch.to_seeds(expected_count=2)


def test_seed_batch_converts_every_idea_without_truncation() -> None:
    batch = OpenAISeedBatch(
        ideas=[
            _idea(title="First"),
            _idea(title="Second"),
        ]
    )

    candidates = batch.to_seeds(expected_count=2)

    assert tuple(candidate.title for candidate in candidates) == ("First", "Second")
    assert len({candidate.id for candidate in candidates}) == 2


@pytest.mark.parametrize(
    "overrides",
    [
        {},
        {
            "title": "  Confidence   garden ",
            "core_mechanism": "Claims gain reversible confidence through   evidence.",
        },
        {
            "title": "Ｃonfidence	garden",
            "core_mechanism": "Claims gain reversible confidence through  evidence.",
        },
    ],
)
def test_seed_batch_rejects_duplicate_normalized_ideas(
    overrides: dict[str, object],
) -> None:
    second = _idea(**overrides)
    batch = OpenAISeedBatch(ideas=[_idea(), second])

    with pytest.raises(ValueError, match="duplicate normalized ideas"):
        batch.to_seeds(expected_count=2)


@pytest.mark.parametrize(
    ("model", "payload"),
    [
        (
            OpenAIFrame,
            {"assumptions": ["valid"] * 21, "obvious_solution": "Use a form"},
        ),
        (
            OpenAIFrame,
            {"assumptions": ["x" * 1_001], "obvious_solution": "Use a form"},
        ),
        (
            OpenAIFrame,
            {"assumptions": ["same", " same "], "obvious_solution": "Use a form"},
        ),
        (
            OpenAIFrame,
            {"assumptions": [], "obvious_solution": "x" * 4_001},
        ),
        (OpenAIIdea, _idea_payload(title="x" * 201)),
        (OpenAIIdea, _idea_payload(core_mechanism="x" * 4_001)),
        (OpenAIIdea, _idea_payload(weaknesses=["x"] * 21)),
        (OpenAIIdea, _idea_payload(weaknesses=["x" * 1_001])),
        (OpenAIIdea, _idea_payload(weaknesses=["same", " same "])),
        (OpenAISeedBatch, {"ideas": [_idea_payload()] * 21}),
    ],
)
def test_output_schemas_bound_content_after_parse(
    model: type[OpenAIFrame] | type[OpenAIIdea] | type[OpenAISeedBatch],
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        model.model_validate(payload)


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


@pytest.mark.parametrize(
    "model",
    [OpenAIFrame, OpenAIIdea, OpenAISeedBatch, OpenAIEvaluation],
)
def test_output_json_schemas_avoid_unsupported_validation_keywords(
    model: type[OpenAIFrame]
    | type[OpenAIIdea]
    | type[OpenAISeedBatch]
    | type[OpenAIEvaluation],
) -> None:
    schema = model.model_json_schema()

    assert _schema_keywords(schema).isdisjoint(
        {"minLength", "maxLength", "minimum", "maximum", "pattern"}
    )
    assert to_strict_json_schema(model)["additionalProperties"] is False
