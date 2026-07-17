from __future__ import annotations

from uuid import UUID

import pytest
from pydantic import ValidationError

from muse.experimentation.candidates import CandidatePrediction
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


def test_raw_evidence_rejects_secret_bearing_data() -> None:
    with pytest.raises(ValidationError, match="secret"):
        _envelope(raw_observation={"api_key": "private"})


def test_evidence_request_and_envelope_experiment_ids_must_match() -> None:
    with pytest.raises(ValidationError, match="request experiment"):
        _envelope(experiment_id=UNCERTAINTY_ID)


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
