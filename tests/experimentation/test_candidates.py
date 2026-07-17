from __future__ import annotations

from uuid import UUID

import pytest
from pydantic import ValidationError

from muse.experimentation.candidates import (
    Candidate,
    CandidateSelectionState,
    Claim,
    ClaimType,
    OperationalContract,
    Reducibility,
    SourceExposure,
    Uncertainty,
)

SESSION_ID = UUID("00000000-0000-0000-0000-000000000001")
CANDIDATE_ID = UUID("00000000-0000-0000-0000-000000000010")
CANDIDATE_B = UUID("00000000-0000-0000-0000-000000000011")
PARENT_A = UUID("00000000-0000-0000-0000-000000000020")


def _operational_contract(**overrides: object) -> OperationalContract:
    values: dict[str, object] = {
        "inputs_required": ("handoff events",),
        "outputs_produced": ("ownership state",),
        "workflow": ("record transfer", "wait for acknowledgement", "escalate"),
        "decision_policy": "Escalate after the declared acknowledgement window.",
        "integration_points": ("event source",),
        "verification_strategy": "Replay acknowledged and expired handoffs.",
        "failure_modes": ("event loss",),
    }
    values.update(overrides)
    return OperationalContract.model_validate(values)


def _candidate(**overrides: object) -> Candidate:
    values: dict[str, object] = {
        "id": CANDIDATE_ID,
        "session_id": SESSION_ID,
        "generation": 0,
        "branch_strategy": "independent",
        "source_exposure": SourceExposure.INDEPENDENT,
        "title": "Adaptive handoff protocol",
        "mechanism": "Escalate ownership when acknowledgement evidence expires.",
        "problem_framing": "Handoffs fail when ownership is implicit.",
        "expected_value": "Make ownership transitions observable.",
        "assumptions": ("Acknowledgements can be observed",),
        "operational_contract": _operational_contract(),
    }
    values.update(overrides)
    return Candidate.model_validate(values)


def test_candidate_is_a_mechanism_with_decision_relevant_claims() -> None:
    candidate = _candidate()

    assert candidate.selection_state is CandidateSelectionState.ACTIVE


def test_candidate_parent_ids_are_unique_and_preserve_first_seen_order() -> None:
    candidate = _candidate(parent_ids=(PARENT_A, PARENT_A, CANDIDATE_B, PARENT_A))

    assert candidate.parent_ids == (PARENT_A, CANDIDATE_B)


def test_claims_must_belong_to_their_candidate() -> None:
    foreign_claim = Claim(
        candidate_id=CANDIDATE_B,
        claim_type=ClaimType.CAUSAL,
        statement="Expiry makes unowned handoffs less likely.",
        first_order_effects=("Earlier escalation",),
        second_order_effects=("Fewer unowned handoffs",),
    )

    with pytest.raises(ValidationError, match="belong to the candidate"):
        _candidate(claims=(foreign_claim,))


@pytest.mark.parametrize("missing_field", ["first_order_effects", "second_order_effects"])
def test_claim_consequences_must_be_complete(missing_field: str) -> None:
    values: dict[str, object] = {
        "candidate_id": CANDIDATE_ID,
        "claim_type": ClaimType.CAUSAL,
        "statement": "Expiry makes unowned handoffs less likely.",
        "first_order_effects": ("Earlier escalation",),
        "second_order_effects": ("Fewer unowned handoffs",),
    }
    values[missing_field] = ()

    with pytest.raises(ValidationError):
        Claim.model_validate(values)


def test_uncertainty_requires_competing_candidates_or_one_hard_constraint() -> None:
    with pytest.raises(ValidationError, match="at least two candidates"):
        Uncertainty(
            session_id=SESSION_ID,
            description="Does expiry reduce unowned handoffs?",
            candidate_ids=(CANDIDATE_ID,),
            reducibility=Reducibility.EXPERIMENTAL,
        )

    constraint_uncertainty = Uncertainty(
        session_id=SESSION_ID,
        description="Does the mechanism violate the retention policy?",
        candidate_ids=(CANDIDATE_ID,),
        hard_constraint="No event retained after expiry",
        reducibility=Reducibility.EXPERIMENTAL,
    )
    assert constraint_uncertainty.hard_constraint == "No event retained after expiry"


def test_selected_candidate_cannot_have_a_failed_hard_constraint() -> None:
    with pytest.raises(ValidationError, match="failed hard constraint"):
        _candidate(
            selection_state=CandidateSelectionState.SELECTED,
            failed_hard_constraints=("No event retained after expiry",),
        )


def test_text_tuples_deduplicate_unicode_equivalents_without_reordering() -> None:
    candidate = _candidate(
        assumptions=("Caf\u00e9", "Other", "Cafe\u0301", "OTHER"),
        operational_contract=_operational_contract(
            workflow=("Record", "record", "Escalate"),
        ),
    )

    assert candidate.assumptions == ("Caf\u00e9", "Other")
    assert candidate.operational_contract.workflow == ("Record", "Escalate")


def test_candidate_contracts_are_frozen_and_reject_extra_fields() -> None:
    candidate = _candidate()

    with pytest.raises(ValidationError, match="frozen"):
        candidate.title = "Mutated"

    with pytest.raises(ValidationError, match="Extra inputs"):
        Candidate.model_validate({**candidate.model_dump(), "repository_path": "private"})
