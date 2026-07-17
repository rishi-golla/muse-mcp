from __future__ import annotations

from uuid import UUID

import pytest
from pydantic import ValidationError

from muse.experimentation.candidates import (
    CandidatePrediction,
    CandidateSelectionState,
)
from muse.experimentation.evidence import (
    DecisionRuleKind,
    DecisionRuleSpec,
    EvidenceCapability,
    EvidenceEnvelope,
    EvidenceRequest,
    EvidenceValidationStatus,
    ExperimentSpec,
    ExperimentStatus,
    Measurement,
    MeasurementSpec,
    SelectionDecision,
)

SESSION_ID = UUID("00000000-0000-0000-0000-000000000001")
UNCERTAINTY_ID = UUID("00000000-0000-0000-0000-000000000002")
EXPERIMENT_ID = UUID("00000000-0000-0000-0000-000000000003")
REQUEST_ID = UUID("00000000-0000-0000-0000-000000000004")
EVIDENCE_ID = UUID("00000000-0000-0000-0000-000000000005")
CANDIDATE_A = UUID("00000000-0000-0000-0000-000000000010")
CANDIDATE_B = UUID("00000000-0000-0000-0000-000000000011")


def _experiment(**overrides: object) -> ExperimentSpec:
    values: dict[str, object] = {
        "id": EXPERIMENT_ID,
        "session_id": SESSION_ID,
        "target_uncertainty_ids": (UNCERTAINTY_ID,),
        "candidate_ids": (CANDIDATE_A, CANDIDATE_B),
        "hypothesis": "Acknowledgement expiry reduces unowned handoffs.",
        "predictions": (
            CandidatePrediction(candidate_id=CANDIDATE_A, expected="fewer_unowned"),
            CandidatePrediction(candidate_id=CANDIDATE_B, expected="no_change"),
        ),
        "capability": EvidenceCapability.EXECUTABLE,
        "procedure": ("Replay the same handoff fixture for both candidates",),
        "measurements": (MeasurementSpec(name="unowned_count", unit="count"),),
        "decision_rule": DecisionRuleSpec(
            kind=DecisionRuleKind.LOWER_IS_BETTER,
            measurement="unowned_count",
            inconclusive_margin=0.0,
        ),
        "stopping_conditions": ("Both fixture runs complete",),
        "adapter_id": "executable-v1",
        "adapter_contract_version": 1,
    }
    values.update(overrides)
    return ExperimentSpec.model_validate(values)


def _request(**overrides: object) -> EvidenceRequest:
    values: dict[str, object] = {
        "id": REQUEST_ID,
        "experiment_id": EXPERIMENT_ID,
        "candidate_id": CANDIDATE_A,
        "capability": EvidenceCapability.EXECUTABLE,
        "adapter_id": "executable-v1",
        "adapter_contract_version": 1,
    }
    values.update(overrides)
    return EvidenceRequest.model_validate(values)


def _envelope(**overrides: object) -> EvidenceEnvelope:
    values: dict[str, object] = {
        "id": EVIDENCE_ID,
        "request": _request(),
        "experiment_id": EXPERIMENT_ID,
        "candidate_id": CANDIDATE_A,
        "raw_observation": {"candidate": str(CANDIDATE_A), "unowned_count": 1},
        "measurements": (Measurement(name="unowned_count", value=1, unit="count"),),
        "validation_status": EvidenceValidationStatus.VALID,
    }
    values.update(overrides)
    return EvidenceEnvelope.model_validate(values)


def test_experiment_preregisters_competing_predictions() -> None:
    spec = _experiment()

    assert spec.status is ExperimentStatus.PROPOSED


@pytest.mark.parametrize(
    "predictions",
    [(), (CandidatePrediction(candidate_id=CANDIDATE_A, expected="fewer"),)],
)
def test_experiment_rejects_missing_competing_predictions(
    predictions: tuple[CandidatePrediction, ...],
) -> None:
    with pytest.raises(ValidationError, match="predictions"):
        _experiment(predictions=predictions)


def test_experiment_requires_two_distinct_competing_candidates() -> None:
    duplicate_prediction = CandidatePrediction(
        candidate_id=CANDIDATE_A,
        expected="fewer_unowned",
    )

    with pytest.raises(ValidationError, match="distinct competing candidates"):
        _experiment(
            candidate_ids=(CANDIDATE_A, CANDIDATE_A),
            predictions=(duplicate_prediction, duplicate_prediction),
        )


@pytest.mark.parametrize(
    ("first_expected", "second_expected"),
    [("fewer", "FEWER"), ("Caf\u00e9", "Cafe\u0301")],
)
def test_experiment_requires_distinct_unicode_normalized_predictions(
    first_expected: str,
    second_expected: str,
) -> None:
    with pytest.raises(ValidationError, match="distinct competing expectations"):
        _experiment(
            predictions=(
                CandidatePrediction(candidate_id=CANDIDATE_A, expected=first_expected),
                CandidatePrediction(candidate_id=CANDIDATE_B, expected=second_expected),
            )
        )


def test_experiment_rejects_missing_decision_rule() -> None:
    values = _experiment().model_dump()
    del values["decision_rule"]

    with pytest.raises(ValidationError, match="decision_rule"):
        ExperimentSpec.model_validate(values)


def test_experiment_rejects_decision_rule_for_an_unregistered_measurement() -> None:
    with pytest.raises(ValidationError, match="registered measurement"):
        _experiment(
            decision_rule=DecisionRuleSpec(
                kind=DecisionRuleKind.LOWER_IS_BETTER,
                measurement="latency",
                inconclusive_margin=0.0,
            )
        )


@pytest.mark.parametrize("comparison", ["at_least", "at_most"])
def test_threshold_and_boolean_decision_rules_require_kind_parameters(
    comparison: str,
) -> None:
    threshold = DecisionRuleSpec.model_validate(
        {
            "kind": DecisionRuleKind.THRESHOLD,
            "measurement": "unowned_count",
            "inconclusive_margin": 0.0,
            "threshold": 1.0,
            "comparison": comparison,
        }
    )
    boolean = DecisionRuleSpec(
        kind=DecisionRuleKind.BOOLEAN,
        measurement="passed",
        inconclusive_margin=0.0,
        expected_boolean=True,
    )

    assert threshold.threshold == 1.0
    assert threshold.comparison == comparison
    assert boolean.expected_boolean is True


@pytest.mark.parametrize(
    ("kind", "parameters"),
    [
        (DecisionRuleKind.THRESHOLD, {}),
        (DecisionRuleKind.BOOLEAN, {}),
        (DecisionRuleKind.THRESHOLD, {"threshold": 1.0}),
        (
            DecisionRuleKind.THRESHOLD,
            {"threshold": 1.0, "comparison": "greater_than"},
        ),
        (DecisionRuleKind.THRESHOLD, {"expected_boolean": True}),
        (DecisionRuleKind.BOOLEAN, {"threshold": 1.0}),
        (
            DecisionRuleKind.BOOLEAN,
            {"expected_boolean": True, "comparison": "at_least"},
        ),
        (DecisionRuleKind.LOWER_IS_BETTER, {"threshold": 1.0}),
        (DecisionRuleKind.LOWER_IS_BETTER, {"comparison": "at_most"}),
        (DecisionRuleKind.HIGHER_IS_BETTER, {"expected_boolean": False}),
    ],
)
def test_decision_rule_parameters_are_mutually_exclusive_by_kind(
    kind: DecisionRuleKind,
    parameters: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        DecisionRuleSpec(
            kind=kind,
            measurement="unowned_count",
            inconclusive_margin=0.0,
            **parameters,
        )


@pytest.mark.parametrize("threshold", [True, 1, float("nan"), float("inf"), float("-inf")])
def test_threshold_is_a_finite_strict_float(threshold: object) -> None:
    with pytest.raises(ValidationError):
        DecisionRuleSpec(
            kind=DecisionRuleKind.THRESHOLD,
            measurement="unowned_count",
            inconclusive_margin=0.0,
            threshold=threshold,
            comparison="at_least",
        )


@pytest.mark.parametrize("expected_boolean", [1, "true"])
def test_expected_boolean_is_strict(expected_boolean: object) -> None:
    with pytest.raises(ValidationError):
        DecisionRuleSpec(
            kind=DecisionRuleKind.BOOLEAN,
            measurement="passed",
            inconclusive_margin=0.0,
            expected_boolean=expected_boolean,
        )


@pytest.mark.parametrize("value", [True, False, float("nan"), float("inf"), float("-inf")])
def test_measurements_reject_booleans_and_non_finite_values(value: object) -> None:
    with pytest.raises(ValidationError):
        Measurement(name="unowned_count", value=value, unit="count")


def test_raw_evidence_is_deeply_immutable_and_detached_from_input() -> None:
    observation = {"events": [{"kind": "handoff"}]}
    envelope = _envelope(raw_observation=observation)
    observation["events"][0]["kind"] = "mutated"

    assert envelope.raw_observation["events"][0]["kind"] == "handoff"  # type: ignore[index]
    with pytest.raises(TypeError):
        envelope.raw_observation["events"] = ()  # type: ignore[index]


def test_raw_evidence_serializes_as_json_safe_data() -> None:
    envelope = _envelope(raw_observation={"events": [{"kind": "handoff"}]})

    assert envelope.model_dump(mode="json")["raw_observation"] == {
        "events": [{"kind": "handoff"}]
    }


def test_raw_evidence_cannot_be_mutated_through_dict_primitives() -> None:
    envelope = _envelope(raw_observation={"events": [{"kind": "handoff"}]})
    nested = envelope.raw_observation["events"][0]  # type: ignore[index]

    with pytest.raises(TypeError):
        dict.__setitem__(nested, "kind", "mutated")
    assert envelope.model_dump(mode="json")["raw_observation"] == {
        "events": [{"kind": "handoff"}]
    }


def test_raw_evidence_is_json_safe_or_an_artifact_hash_but_not_both() -> None:
    with pytest.raises(ValidationError, match="raw observation or an artifact hash"):
        _envelope(raw_observation={"ok": True}, artifact_hash="sha256:evidence")

    artifact = _envelope(raw_observation=None, artifact_hash="sha256:evidence")
    assert artifact.artifact_hash == "sha256:evidence"

    with pytest.raises(ValidationError, match="JSON-safe"):
        _envelope(raw_observation={"bad": {1, 2}})


def test_provider_interpretation_cannot_masquerade_as_raw_evidence() -> None:
    with pytest.raises(ValidationError, match="interpretation"):
        _envelope(raw_observation={"provider_interpretation": "candidate A wins"})


@pytest.mark.parametrize(
    "raw_observation",
    [
        {"model_analysis": "candidate A wins"},
        {"llm-inference": "candidate A wins"},
        {"AI Rationale": "candidate A wins"},
        {"provider_conclusion": "candidate A wins"},
        {"model": "gpt", "analysis": "candidate A wins"},
        {"provider": "adapter-v1", "conclusion": "candidate A wins"},
    ],
)
def test_source_attributed_interpretation_cannot_be_raw_evidence(
    raw_observation: dict[str, str],
) -> None:
    with pytest.raises(ValidationError, match="interpretation"):
        _envelope(raw_observation=raw_observation)


@pytest.mark.parametrize(
    "raw_observation",
    [
        {
            "provider": "openai",
            "response": {"analysis": "candidate A wins"},
        },
        {
            "model": {"name": "gpt-5"},
            "output": {"conclusion": "candidate A wins"},
        },
    ],
)
def test_nested_interpretation_inherits_provider_or_model_provenance(
    raw_observation: dict[str, object],
) -> None:
    with pytest.raises(ValidationError, match="interpretation"):
        _envelope(raw_observation=raw_observation)


def test_generic_non_model_analysis_remains_valid_raw_evidence() -> None:
    envelope = _envelope(
        raw_observation={
            "analysis": "spectrometry",
            "detail_analysis": "mass-to-charge",
            "result": 2,
        }
    )

    assert envelope.model_dump(mode="json")["raw_observation"] == {
        "analysis": "spectrometry",
        "detail_analysis": "mass-to-charge",
        "result": 2,
    }


@pytest.mark.parametrize(
    "raw_observation",
    [
        {"physical_model": "bridge-v2", "analysis": "finite element stress"},
        {"modeling_analysis": "finite element stress", "result": 2},
    ],
)
def test_domain_model_analysis_is_not_provider_interpretation(
    raw_observation: dict[str, object],
) -> None:
    envelope = _envelope(raw_observation=raw_observation)

    assert envelope.model_dump(mode="json")["raw_observation"] == raw_observation


def test_raw_evidence_rejects_secret_bearing_data() -> None:
    with pytest.raises(ValidationError, match="secret"):
        _envelope(raw_observation={"api_key": "private"})


def test_evidence_request_and_envelope_experiment_ids_must_match() -> None:
    with pytest.raises(ValidationError, match="request experiment"):
        _envelope(experiment_id=UNCERTAINTY_ID)


def test_evidence_request_and_envelope_candidate_ids_must_match() -> None:
    with pytest.raises(ValidationError, match="request candidate"):
        _envelope(candidate_id=CANDIDATE_B)


def test_separate_candidate_envelopes_preserve_same_named_measurements() -> None:
    envelope_a = _envelope()
    request_b = _request(
        id=UUID("00000000-0000-0000-0000-000000000006"),
        candidate_id=CANDIDATE_B,
    )
    envelope_b = _envelope(
        id=UUID("00000000-0000-0000-0000-000000000007"),
        request=request_b,
        candidate_id=CANDIDATE_B,
        raw_observation={"candidate": str(CANDIDATE_B), "unowned_count": 3},
        measurements=(Measurement(name="unowned_count", value=3, unit="count"),),
    )

    assert envelope_a.candidate_id == CANDIDATE_A
    assert envelope_b.candidate_id == CANDIDATE_B
    assert envelope_a.measurements[0].name == envelope_b.measurements[0].name
    assert envelope_a.measurements[0].value == 1
    assert envelope_b.measurements[0].value == 3


@pytest.mark.parametrize(
    ("corrects_evidence_id", "correction_sequence"),
    [(EVIDENCE_ID, 1), (None, 1), (REQUEST_ID, 0)],
)
def test_evidence_rejects_invalid_correction_chains(
    corrects_evidence_id: UUID | None,
    correction_sequence: int,
) -> None:
    with pytest.raises(ValidationError, match="correction"):
        _envelope(
            corrects_evidence_id=corrects_evidence_id,
            correction_sequence=correction_sequence,
        )


def test_experiment_identity_tuples_deduplicate_without_reordering() -> None:
    spec = _experiment(
        target_uncertainty_ids=(UNCERTAINTY_ID, UNCERTAINTY_ID),
        stopping_conditions=("Complete", "complete", "Archive"),
    )

    assert spec.target_uncertainty_ids == (UNCERTAINTY_ID,)
    assert spec.stopping_conditions == ("Complete", "Archive")


def _selection_decision(**overrides: object) -> SelectionDecision:
    values: dict[str, object] = {
        "session_id": SESSION_ID,
        "experiment_id": EXPERIMENT_ID,
        "considered_candidate_ids": (CANDIDATE_A, CANDIDATE_B),
        "selected_candidate_id": CANDIDATE_A,
        "resulting_state": CandidateSelectionState.SELECTED,
        "supporting_evidence_ids": (EVIDENCE_ID,),
        "rationale": "Candidate A produced the lower preregistered measurement.",
    }
    values.update(overrides)
    return SelectionDecision.model_validate(values)


def test_selection_decision_requires_two_distinct_considered_candidates() -> None:
    with pytest.raises(ValidationError, match="distinct considered candidates"):
        _selection_decision(considered_candidate_ids=(CANDIDATE_A, CANDIDATE_A))


@pytest.mark.parametrize(
    "resulting_state",
    [None, CandidateSelectionState.ACTIVE, CandidateSelectionState.REJECTED],
)
def test_conclusive_selection_requires_selected_resulting_state(
    resulting_state: CandidateSelectionState | None,
) -> None:
    with pytest.raises(ValidationError, match="resulting state"):
        _selection_decision(resulting_state=resulting_state)


def test_inconclusive_selection_has_no_candidate_or_resulting_state() -> None:
    decision = _selection_decision(
        selected_candidate_id=None,
        resulting_state=None,
        inconclusive=True,
    )

    assert decision.selected_candidate_id is None
    assert decision.resulting_state is None
