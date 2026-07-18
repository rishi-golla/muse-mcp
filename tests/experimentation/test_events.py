from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from muse.experimentation.candidates import (
    Candidate,
    CandidatePrediction,
    CandidateSelectionState,
    Claim,
    ClaimSupportState,
    ClaimType,
    OperationalContract,
    SourceExposure,
)
from muse.experimentation.events import (
    BudgetReconciliation,
    BudgetReservation,
    EventKind,
    EvidenceAccepted,
    EvidenceRejected,
    EvidenceSupersession,
    ExperimentStatusChange,
    PendingEvent,
    SessionEvent,
    SessionResume,
    SessionStatusChange,
    SessionTermination,
    SnapshotWrite,
    reduce_events,
    reduce_session,
)
from muse.experimentation.evidence import (
    BeliefUpdate,
    DecisionRuleSpec,
    EvidenceCapability,
    EvidenceEnvelope,
    EvidenceRequest,
    EvidenceValidationStatus,
    ExperimentSpec,
    ExperimentStatus,
    MeasurementSpec,
    SelectionDecision,
)
from muse.experimentation.sessions import (
    AuthorizationGrant,
    AuthorizationGrantExperiment,
    AuthorizationPolicy,
    ClaimOwnership,
    CreativeSession,
    EvidenceHistoryEntry,
    ExperimentCandidates,
    ExperimentStatusRecord,
    Objective,
    PrivacyPolicy,
    SessionBudgets,
    SessionProjection,
    SessionStatus,
    SideEffectClass,
)

SESSION_ID = UUID("00000000-0000-0000-0000-000000000001")
CANDIDATE_ID = UUID("00000000-0000-0000-0000-000000000002")
CANDIDATE_2_ID = UUID("00000000-0000-0000-0000-000000000006")
CANDIDATE_3_ID = UUID("00000000-0000-0000-0000-00000000000a")
EXPERIMENT_ID = UUID("00000000-0000-0000-0000-000000000003")
EXPERIMENT_2_ID = UUID("00000000-0000-0000-0000-00000000000b")
EVIDENCE_ID = UUID("00000000-0000-0000-0000-000000000004")
REPLACEMENT_EVIDENCE_ID = UUID("00000000-0000-0000-0000-000000000005")
THIRD_EVIDENCE_ID = UUID("00000000-0000-0000-0000-000000000007")
CLAIM_ID = UUID("00000000-0000-0000-0000-000000000008")
GRANT_ID = UUID("00000000-0000-0000-0000-000000000009")


def _session(**overrides: object) -> CreativeSession:
    values: dict[str, object] = {
        "id": SESSION_ID,
        "goal": "Design a safer coordination mechanism",
        "objectives": (Objective(name="usefulness", direction="maximize", priority=1),),
        "privacy": PrivacyPolicy(mode="private", retention_days=30),
        "authorization": AuthorizationPolicy(),
        "budgets": SessionBudgets(
            max_cost_usd=1.0,
            max_provider_calls=10,
            max_latency_ms=60_000,
            max_human_minutes=5,
        ),
        "schema_version": 1,
        "policy_version": "evidence-v1",
    }
    values.update(overrides)
    return CreativeSession.model_validate(values)


def _candidate(**overrides: object) -> Candidate:
    values: dict[str, object] = {
        "id": CANDIDATE_ID,
        "session_id": SESSION_ID,
        "generation": 0,
        "branch_strategy": "constraint inversion",
        "source_exposure": SourceExposure.INDEPENDENT,
        "title": "Reversible coordination",
        "mechanism": "Stage changes behind explicit authorization",
        "problem_framing": "Coordination must remain inspectable",
        "expected_value": "Safer reversible progress",
        "operational_contract": OperationalContract(
            inputs_required=("goal",),
            outputs_produced=("decision",),
            workflow=("inspect", "decide"),
            decision_policy="Prefer verified constraints",
            integration_points=("agent",),
            verification_strategy="Replay recorded evidence",
            failure_modes=("insufficient evidence",),
        ),
    }
    values.update(overrides)
    return Candidate.model_validate(values)


def _evidence(
    *,
    evidence_id: UUID = EVIDENCE_ID,
    status: EvidenceValidationStatus = EvidenceValidationStatus.VALID,
    corrects_evidence_id: UUID | None = None,
    correction_sequence: int = 0,
    authorization_grant_ids: tuple[UUID, ...] = (),
    candidate_id: UUID = CANDIDATE_ID,
    experiment_id: UUID = EXPERIMENT_ID,
) -> EvidenceEnvelope:
    request = EvidenceRequest(
        experiment_id=experiment_id,
        candidate_id=candidate_id,
        capability=EvidenceCapability.OBSERVATIONAL,
        adapter_id="local-observer",
        adapter_contract_version=1,
        authorization_grant_ids=authorization_grant_ids,
    )
    return EvidenceEnvelope(
        id=evidence_id,
        request=request,
        experiment_id=experiment_id,
        candidate_id=candidate_id,
        raw_observation={"result": "observed"},
        validation_status=status,
        corrects_evidence_id=corrects_evidence_id,
        correction_sequence=correction_sequence,
    )


def _authorization_grant(
    *,
    grant_id: UUID = GRANT_ID,
    experiment_id: UUID = EXPERIMENT_ID,
) -> AuthorizationGrant:
    return AuthorizationGrant(
        id=grant_id,
        session_id=SESSION_ID,
        experiment_id=experiment_id,
        side_effect=SideEffectClass.READ_ONLY_LOCAL,
        allowed_actions=("Observe local result",),
        expires_at=datetime(2026, 7, 18, tzinfo=UTC),
        issuer="operator",
        integrity_hash=f"sha256:{grant_id}",
    )


def _experiment() -> ExperimentSpec:
    return ExperimentSpec(
        id=EXPERIMENT_ID,
        session_id=SESSION_ID,
        target_uncertainty_ids=(UUID("40000000-0000-0000-0000-000000000001"),),
        candidate_ids=(CANDIDATE_ID, CANDIDATE_2_ID),
        hypothesis="Reversible coordination reduces unapproved side effects",
        predictions=(
            CandidatePrediction(
                candidate_id=CANDIDATE_ID,
                expected="Fewer unapproved side effects",
            ),
            CandidatePrediction(
                candidate_id=CANDIDATE_2_ID,
                expected="No reduction in unapproved side effects",
            ),
        ),
        capability=EvidenceCapability.OBSERVATIONAL,
        procedure=("Observe both candidates under the same conditions",),
        measurements=(MeasurementSpec(name="unapproved effects", unit="count"),),
        decision_rule=DecisionRuleSpec(
            kind="lower_is_better",
            measurement="unapproved effects",
            inconclusive_margin=0.0,
        ),
        stopping_conditions=("Both candidates have one observation",),
        authorization_requirements=(SideEffectClass.READ_ONLY_LOCAL,),
        adapter_id="local-observer",
        adapter_contract_version=1,
    )
def _event(
    sequence: int,
    kind: EventKind,
    payload: object,
    previous: SessionEvent | None = None,
    *,
    session_id: UUID = SESSION_ID,
) -> SessionEvent:
    return SessionEvent.create(
        session_id,
        sequence,
        kind,
        payload,
        idempotency_key=f"event-{sequence}",
        timestamp=datetime(2026, 7, 17, 12, sequence, tzinfo=UTC),
        event_id=UUID(f"00000000-0000-0000-0000-{sequence:012d}"),
        previous_event_hash=None if previous is None else previous.event_hash,
    )


def _introduced_graph() -> tuple[SessionEvent, SessionEvent, SessionEvent, SessionEvent]:
    started = _event(1, EventKind.SESSION_STARTED, _session())
    first_candidate = _event(2, EventKind.CANDIDATE_ADDED, _candidate(), started)
    second_candidate = _event(
        3,
        EventKind.CANDIDATE_ADDED,
        _candidate(id=CANDIDATE_2_ID, title="Comparison candidate"),
        first_candidate,
    )
    proposed = _event(
        4,
        EventKind.EXPERIMENT_PROPOSED,
        _experiment(),
        second_candidate,
    )
    return started, first_candidate, second_candidate, proposed


def _projection_with_known_graph(**overrides: object) -> SessionProjection:
    values: dict[str, object] = {
        "session_id": SESSION_ID,
        "status": SessionStatus.ACTIVE,
        "sequence": 1,
        "candidate_ids": (CANDIDATE_ID,),
        "experiment_ids": (EXPERIMENT_ID,),
        "active_experiment_ids": (EXPERIMENT_ID,),
        "experiment_candidates": (
            ExperimentCandidates(
                experiment_id=EXPERIMENT_ID,
                candidate_ids=(CANDIDATE_ID,),
            ),
        ),
    }
    values.update(overrides)
    return SessionProjection.model_validate(values)


def _evidence_lineage() -> tuple[
    EvidenceHistoryEntry, EvidenceHistoryEntry, EvidenceHistoryEntry
]:
    initial = EvidenceHistoryEntry(
        evidence_id=EVIDENCE_ID,
        experiment_id=EXPERIMENT_ID,
        candidate_id=CANDIDATE_ID,
        correction_sequence=0,
    )
    replacement = EvidenceHistoryEntry(
        evidence_id=REPLACEMENT_EVIDENCE_ID,
        experiment_id=EXPERIMENT_ID,
        candidate_id=CANDIDATE_ID,
        correction_sequence=1,
        corrects_evidence_id=EVIDENCE_ID,
    )
    third = EvidenceHistoryEntry(
        evidence_id=THIRD_EVIDENCE_ID,
        experiment_id=EXPERIMENT_ID,
        candidate_id=CANDIDATE_ID,
        correction_sequence=2,
        corrects_evidence_id=REPLACEMENT_EVIDENCE_ID,
    )
    return initial, replacement, third


def test_pending_event_requires_idempotency_key_and_validates_payload_by_kind() -> None:
    with pytest.raises(ValidationError, match="idempotency_key"):
        PendingEvent.model_validate(
            {"kind": EventKind.CANDIDATE_ADDED, "payload": _candidate()}
        )

    with pytest.raises(ValidationError, match="payload"):
        PendingEvent(
            kind=EventKind.CANDIDATE_ADDED,
            payload=_session(),
            idempotency_key="candidate-add",
        )

    with pytest.raises(ValidationError, match="blank"):
        SessionEvent.create(
            SESSION_ID,
            1,
            EventKind.SESSION_STARTED,
            _session(),
            idempotency_key="",
        )


def test_every_event_kind_has_an_explicit_payload_contract() -> None:
    valid_payloads = {
        EventKind.SESSION_STARTED: _session(),
        EventKind.SESSION_STATUS_CHANGED: SessionStatusChange(
            session_id=SESSION_ID,
            status=SessionStatus.AWAITING_EVIDENCE,
            reason="Await evidence",
        ),
        EventKind.SESSION_RESUMED: SessionResume(
            session_id=SESSION_ID,
            reason="New evidence is available",
        ),
        EventKind.CANDIDATE_ADDED: _candidate(),
        EventKind.CANDIDATE_UPDATED: _candidate(
            selection_state=CandidateSelectionState.REJECTED
        ),
        EventKind.EXPERIMENT_PROPOSED: _experiment(),
        EventKind.EXPERIMENT_AUTHORIZED: AuthorizationGrant(
            session_id=SESSION_ID,
            experiment_id=EXPERIMENT_ID,
            side_effect=SideEffectClass.READ_ONLY_LOCAL,
            allowed_actions=("Observe local result",),
            expires_at=datetime(2026, 7, 18, tzinfo=UTC),
            issuer="operator",
            integrity_hash="sha256:grant",
        ),
        EventKind.EXPERIMENT_STATUS_CHANGED: ExperimentStatusChange(
            session_id=SESSION_ID,
            experiment_id=EXPERIMENT_ID,
            status=ExperimentStatus.RUNNING,
        ),
        EventKind.EVIDENCE_ACCEPTED: EvidenceAccepted(
            session_id=SESSION_ID,
            evidence=_evidence(),
        ),
        EventKind.EVIDENCE_REJECTED: EvidenceRejected(
            session_id=SESSION_ID,
            evidence=_evidence(status=EvidenceValidationStatus.INVALID),
            reason="Malformed observation",
        ),
        EventKind.EVIDENCE_SUPERSEDED: EvidenceSupersession(
            session_id=SESSION_ID,
            superseded_evidence_id=EVIDENCE_ID,
            replacement=_evidence(
                evidence_id=REPLACEMENT_EVIDENCE_ID,
                corrects_evidence_id=EVIDENCE_ID,
                correction_sequence=1,
            ),
        ),
        EventKind.BELIEF_UPDATED: BeliefUpdate(
            session_id=SESSION_ID,
            evidence_id=EVIDENCE_ID,
            claim_id=UUID("40000000-0000-0000-0000-000000000002"),
            prior_state=ClaimSupportState.UNTESTED,
            updated_state=ClaimSupportState.SUPPORTED,
            interpretation="Observed evidence supports the claim",
        ),
        EventKind.SELECTION_DECIDED: SelectionDecision(
            session_id=SESSION_ID,
            experiment_id=EXPERIMENT_ID,
            considered_candidate_ids=(CANDIDATE_ID, CANDIDATE_2_ID),
            selected_candidate_id=CANDIDATE_ID,
            resulting_state=CandidateSelectionState.SELECTED,
            supporting_evidence_ids=(EVIDENCE_ID,),
            rationale="Verified evidence favors the candidate",
        ),
        EventKind.MEMORY_WRITTEN: SnapshotWrite(
            session_id=SESSION_ID,
            snapshot_id=UUID("40000000-0000-0000-0000-000000000003"),
        ),
        EventKind.TASTE_WRITTEN: SnapshotWrite(
            session_id=SESSION_ID,
            snapshot_id=UUID("40000000-0000-0000-0000-000000000004"),
        ),
        EventKind.BUDGET_RESERVED: BudgetReservation(
            session_id=SESSION_ID,
            reservation_id=UUID("40000000-0000-0000-0000-000000000005"),
            cost_usd=0.25,
            calls=1,
            latency_ms=500,
            human_minutes=0,
        ),
        EventKind.BUDGET_RECONCILED: BudgetReconciliation(
            session_id=SESSION_ID,
            reservation_id=UUID("40000000-0000-0000-0000-000000000005"),
            actual_cost_usd=0.20,
            actual_calls=1,
            actual_latency_ms=450,
            actual_human_minutes=0,
        ),
        EventKind.SESSION_STOPPED: SessionTermination(
            session_id=SESSION_ID,
            reason="Operator stopped the session",
        ),
        EventKind.SESSION_FAILED: SessionTermination(
            session_id=SESSION_ID,
            reason="Unrecoverable adapter failure",
        ),
    }

    assert set(valid_payloads) == set(EventKind)
    for kind, payload in valid_payloads.items():
        pending = PendingEvent(
            kind=kind,
            payload=payload,
            idempotency_key=f"payload-{kind.value}",
        )
        assert type(pending.payload) is type(payload)


def test_session_event_hash_covers_every_durable_field() -> None:
    event = _event(1, EventKind.SESSION_STARTED, _session())

    for field, replacement in (
        ("session_id", UUID("10000000-0000-0000-0000-000000000001")),
        ("sequence", 2),
        ("kind", EventKind.CANDIDATE_ADDED),
        ("payload", _candidate()),
        ("idempotency_key", "different-key"),
        ("timestamp", datetime(2026, 7, 17, 13, 0, tzinfo=UTC)),
        ("event_id", UUID("10000000-0000-0000-0000-000000000002")),
        ("previous_event_hash", "a" * 64),
    ):
        tampered = event.model_copy(update={field: replacement})
        with pytest.raises(ValueError, match="event hash"):
            reduce_events((tampered,))

    serialized = event.model_dump()
    serialized["schema_version"] = 2
    with pytest.raises(ValidationError, match="event hash"):
        SessionEvent.model_validate(serialized)


def test_event_replay_is_deterministic_and_sequence_checked() -> None:
    started = _event(1, EventKind.SESSION_STARTED, _session())
    added = _event(2, EventKind.CANDIDATE_ADDED, _candidate(), started)
    events = (started, added)

    first = reduce_events(events)
    restored = tuple(SessionEvent.model_validate(event.model_dump()) for event in events)
    second = reduce_events(restored)

    assert first == second
    assert first.sequence == 2
    assert first.active_candidate_ids == (CANDIDATE_ID,)


def test_projection_history_fields_have_backward_compatible_defaults() -> None:
    projection = SessionProjection(
        session_id=SESSION_ID,
        status=SessionStatus.ACTIVE,
        sequence=0,
    )

    assert projection.candidate_ids == ()
    assert projection.experiment_ids == ()
    assert projection.evidence_ids == ()
    assert projection.superseded_evidence_ids == ()
    assert projection.claim_ids == ()
    assert projection.authorization_grant_ids == ()
    assert projection.budget_reservation_ids == ()
    assert projection.reconciled_budget_reservation_ids == ()
    assert projection.terminal_experiment_ids == ()
    assert projection.experiment_candidates == ()
    assert projection.claim_ownership == ()
    assert projection.authorization_grants == ()
    assert projection.evidence_history == ()
    assert projection.experiment_statuses == ()

    restored_legacy = SessionProjection(
        session_id=SESSION_ID,
        status=SessionStatus.ACTIVE,
        sequence=2,
        active_candidate_ids=(CANDIDATE_ID,),
        active_experiment_ids=(EXPERIMENT_ID,),
    )
    assert restored_legacy.candidate_ids == (CANDIDATE_ID,)
    assert restored_legacy.experiment_ids == (EXPERIMENT_ID,)
    assert restored_legacy.experiment_statuses == (
        ExperimentStatusRecord(
            experiment_id=EXPERIMENT_ID,
            status=ExperimentStatus.PROPOSED,
        ),
    )


def test_projection_infers_ordered_proposed_status_for_legacy_active_experiments() -> None:
    projection = SessionProjection.model_validate(
        {
            "session_id": SESSION_ID,
            "status": SessionStatus.ACTIVE,
            "sequence": 2,
            "experiment_ids": (EXPERIMENT_ID, EXPERIMENT_2_ID),
            "active_experiment_ids": (EXPERIMENT_ID, EXPERIMENT_2_ID),
        }
    )

    assert projection.experiment_statuses == (
        ExperimentStatusRecord(
            experiment_id=EXPERIMENT_ID,
            status=ExperimentStatus.PROPOSED,
        ),
        ExperimentStatusRecord(
            experiment_id=EXPERIMENT_2_ID,
            status=ExperimentStatus.PROPOSED,
        ),
    )
    assert SessionProjection.model_validate(projection.model_dump()) == projection


@pytest.mark.parametrize(
    "experiment_statuses",
    [
        (
            ExperimentStatusRecord(
                experiment_id=EXPERIMENT_ID,
                status=ExperimentStatus.PROPOSED,
            ),
            ExperimentStatusRecord(
                experiment_id=EXPERIMENT_ID,
                status=ExperimentStatus.PROPOSED,
            ),
        ),
        (
            ExperimentStatusRecord(
                experiment_id=EXPERIMENT_ID,
                status=ExperimentStatus.PROPOSED,
            ),
            ExperimentStatusRecord(
                experiment_id=EXPERIMENT_ID,
                status=ExperimentStatus.RUNNING,
            ),
        ),
    ],
)
def test_projection_restore_rejects_duplicate_experiment_status_records(
    experiment_statuses: tuple[ExperimentStatusRecord, ...],
) -> None:
    with pytest.raises(ValidationError, match="experiment status"):
        SessionProjection.model_validate(
            {
                "session_id": SESSION_ID,
                "status": SessionStatus.ACTIVE,
                "sequence": 2,
                "experiment_ids": (EXPERIMENT_ID,),
                "active_experiment_ids": (EXPERIMENT_ID,),
                "experiment_statuses": experiment_statuses,
            }
        )


def test_projection_restore_rejects_unknown_experiment_status_reference() -> None:
    with pytest.raises(ValidationError, match="unknown experiment"):
        SessionProjection.model_validate(
            {
                "session_id": SESSION_ID,
                "status": SessionStatus.ACTIVE,
                "sequence": 2,
                "experiment_statuses": (
                    ExperimentStatusRecord(
                        experiment_id=EXPERIMENT_ID,
                        status=ExperimentStatus.PROPOSED,
                    ),
                ),
            }
        )


def test_projection_restore_rejects_known_experiment_without_lifecycle_status() -> None:
    with pytest.raises(ValidationError, match="must have an experiment status"):
        SessionProjection.model_validate(
            {
                "session_id": SESSION_ID,
                "status": SessionStatus.ACTIVE,
                "sequence": 2,
                "experiment_ids": (EXPERIMENT_ID,),
            }
        )


@pytest.mark.parametrize(
    "status",
    [
        ExperimentStatus.AUTHORIZED,
        ExperimentStatus.RUNNING,
        ExperimentStatus.COMPLETED,
        ExperimentStatus.INCONCLUSIVE,
        ExperimentStatus.FAILED,
    ],
)
def test_projection_restore_rejects_post_proposal_status_without_authorization_history(
    status: ExperimentStatus,
) -> None:
    is_terminal = status in {
        ExperimentStatus.COMPLETED,
        ExperimentStatus.INCONCLUSIVE,
        ExperimentStatus.FAILED,
    }

    with pytest.raises(ValidationError, match="authorization history"):
        SessionProjection.model_validate(
            {
                "session_id": SESSION_ID,
                "status": SessionStatus.ACTIVE,
                "sequence": 2,
                "experiment_ids": (EXPERIMENT_ID,),
                "active_experiment_ids": () if is_terminal else (EXPERIMENT_ID,),
                "terminal_experiment_ids": (EXPERIMENT_ID,) if is_terminal else (),
                "experiment_statuses": (
                    ExperimentStatusRecord(
                        experiment_id=EXPERIMENT_ID,
                        status=status,
                    ),
                ),
            }
        )


def test_projection_restore_rejects_proposed_status_with_authorization_history() -> None:
    with pytest.raises(ValidationError, match="proposed experiment status"):
        SessionProjection.model_validate(
            {
                "session_id": SESSION_ID,
                "status": SessionStatus.ACTIVE,
                "sequence": 2,
                "experiment_ids": (EXPERIMENT_ID,),
                "active_experiment_ids": (EXPERIMENT_ID,),
                "authorization_grant_ids": (GRANT_ID,),
                "authorization_grants": (
                    AuthorizationGrantExperiment(
                        grant_id=GRANT_ID,
                        experiment_id=EXPERIMENT_ID,
                    ),
                ),
                "experiment_statuses": (
                    ExperimentStatusRecord(
                        experiment_id=EXPERIMENT_ID,
                        status=ExperimentStatus.PROPOSED,
                    ),
                ),
            }
        )


@pytest.mark.parametrize(
    ("active_experiment_ids", "terminal_experiment_ids", "status"),
    [
        ((EXPERIMENT_ID,), (), ExperimentStatus.COMPLETED),
        ((), (EXPERIMENT_ID,), ExperimentStatus.RUNNING),
        ((), (), ExperimentStatus.AUTHORIZED),
        ((), (), ExperimentStatus.FAILED),
    ],
)
def test_projection_restore_rejects_contradictory_experiment_lifecycle(
    active_experiment_ids: tuple[UUID, ...],
    terminal_experiment_ids: tuple[UUID, ...],
    status: ExperimentStatus,
) -> None:
    with pytest.raises(ValidationError, match="experiment status"):
        SessionProjection.model_validate(
            {
                "session_id": SESSION_ID,
                "status": SessionStatus.ACTIVE,
                "sequence": 2,
                "experiment_ids": (EXPERIMENT_ID,),
                "active_experiment_ids": active_experiment_ids,
                "terminal_experiment_ids": terminal_experiment_ids,
                "experiment_statuses": (
                    ExperimentStatusRecord(
                        experiment_id=EXPERIMENT_ID,
                        status=status,
                    ),
                ),
            }
        )


def test_projection_deduplicates_all_identity_history_preserving_order() -> None:
    projection = SessionProjection(
        session_id=SESSION_ID,
        status=SessionStatus.ACTIVE,
        sequence=2,
        candidate_ids=(CANDIDATE_ID, CANDIDATE_ID, CANDIDATE_2_ID),
        experiment_ids=(EXPERIMENT_ID, EXPERIMENT_ID),
        evidence_ids=(EVIDENCE_ID, EVIDENCE_ID),
        claim_ids=(CLAIM_ID, CLAIM_ID),
        authorization_grant_ids=(GRANT_ID, GRANT_ID),
        budget_reservation_ids=(CANDIDATE_ID, CANDIDATE_ID),
        active_candidate_ids=(CANDIDATE_ID, CANDIDATE_ID),
        active_experiment_ids=(EXPERIMENT_ID, EXPERIMENT_ID),
    )

    assert projection.candidate_ids == (CANDIDATE_ID, CANDIDATE_2_ID)
    assert projection.experiment_ids == (EXPERIMENT_ID,)
    assert projection.evidence_ids == (EVIDENCE_ID,)
    assert projection.claim_ids == (CLAIM_ID,)
    assert projection.authorization_grant_ids == (GRANT_ID,)
    assert projection.budget_reservation_ids == (CANDIDATE_ID,)
    assert projection.active_candidate_ids == (CANDIDATE_ID,)
    assert projection.active_experiment_ids == (EXPERIMENT_ID,)


@pytest.mark.parametrize(
    "overrides",
    [
        {"terminal_experiment_ids": (EXPERIMENT_ID,)},
        {
            "experiment_ids": (EXPERIMENT_ID,),
            "active_experiment_ids": (EXPERIMENT_ID,),
            "terminal_experiment_ids": (EXPERIMENT_ID,),
        },
        {"superseded_evidence_ids": (EVIDENCE_ID,)},
        {"reconciled_budget_reservation_ids": (CANDIDATE_ID,)},
    ],
)
def test_projection_rejects_orphan_or_contradictory_history(
    overrides: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        SessionProjection(
            session_id=SESSION_ID,
            status=SessionStatus.ACTIVE,
            sequence=1,
            **overrides,
        )


def test_projection_rejects_conflicting_relationship_ownership() -> None:
    with pytest.raises(ValidationError, match="claim ownership"):
        SessionProjection(
            session_id=SESSION_ID,
            status=SessionStatus.ACTIVE,
            sequence=1,
            candidate_ids=(CANDIDATE_ID, CANDIDATE_2_ID),
            claim_ids=(CLAIM_ID,),
            claim_ownership=(
                ClaimOwnership(claim_id=CLAIM_ID, candidate_id=CANDIDATE_ID),
                ClaimOwnership(claim_id=CLAIM_ID, candidate_id=CANDIDATE_2_ID),
            ),
        )


def test_projection_rejects_evidence_candidate_outside_its_experiment() -> None:
    with pytest.raises(ValidationError, match="evidence candidate"):
        SessionProjection(
            session_id=SESSION_ID,
            status=SessionStatus.ACTIVE,
            sequence=1,
            candidate_ids=(CANDIDATE_ID, CANDIDATE_2_ID),
            experiment_ids=(EXPERIMENT_ID,),
            active_experiment_ids=(EXPERIMENT_ID,),
            evidence_ids=(EVIDENCE_ID,),
            experiment_candidates=(
                ExperimentCandidates(
                    experiment_id=EXPERIMENT_ID,
                    candidate_ids=(CANDIDATE_2_ID,),
                ),
            ),
            evidence_history=(
                EvidenceHistoryEntry(
                    evidence_id=EVIDENCE_ID,
                    experiment_id=EXPERIMENT_ID,
                    candidate_id=CANDIDATE_ID,
                    correction_sequence=0,
                ),
            ),
        )


def test_projection_relationships_round_trip_deterministically() -> None:
    projection = SessionProjection(
        session_id=SESSION_ID,
        status=SessionStatus.ACTIVE,
        sequence=4,
        candidate_ids=(CANDIDATE_ID, CANDIDATE_2_ID),
        experiment_ids=(EXPERIMENT_ID,),
        active_experiment_ids=(EXPERIMENT_ID,),
        evidence_ids=(EVIDENCE_ID,),
        claim_ids=(CLAIM_ID,),
        authorization_grant_ids=(GRANT_ID,),
        experiment_statuses=(
            ExperimentStatusRecord(
                experiment_id=EXPERIMENT_ID,
                status=ExperimentStatus.AUTHORIZED,
            ),
        ),
        experiment_candidates=(
            ExperimentCandidates(
                experiment_id=EXPERIMENT_ID,
                candidate_ids=(CANDIDATE_ID, CANDIDATE_2_ID),
            ),
        ),
        claim_ownership=(
            ClaimOwnership(claim_id=CLAIM_ID, candidate_id=CANDIDATE_ID),
        ),
        authorization_grants=(
            AuthorizationGrantExperiment(
                grant_id=GRANT_ID,
                experiment_id=EXPERIMENT_ID,
            ),
        ),
        evidence_history=(
            EvidenceHistoryEntry(
                evidence_id=EVIDENCE_ID,
                experiment_id=EXPERIMENT_ID,
                candidate_id=CANDIDATE_ID,
                correction_sequence=0,
            ),
        ),
    )

    restored = SessionProjection.model_validate(projection.model_dump())

    assert restored == projection


def test_projection_restore_rejects_superseded_evidence_without_correction() -> None:
    initial, _, _ = _evidence_lineage()

    with pytest.raises(ValidationError, match="exactly one correction child"):
        SessionProjection.model_validate(
            {
                "session_id": SESSION_ID,
                "status": SessionStatus.ACTIVE,
                "sequence": 1,
                "candidate_ids": (CANDIDATE_ID,),
                "experiment_ids": (EXPERIMENT_ID,),
                "active_experiment_ids": (EXPERIMENT_ID,),
                "evidence_ids": (EVIDENCE_ID,),
                "superseded_evidence_ids": (EVIDENCE_ID,),
                "evidence_history": (initial,),
            }
        )


def test_projection_restore_rejects_unrecorded_correction_target() -> None:
    initial, replacement, _ = _evidence_lineage()

    with pytest.raises(ValidationError, match="correction target must be superseded"):
        SessionProjection.model_validate(
            {
                "session_id": SESSION_ID,
                "status": SessionStatus.ACTIVE,
                "sequence": 2,
                "candidate_ids": (CANDIDATE_ID,),
                "experiment_ids": (EXPERIMENT_ID,),
                "active_experiment_ids": (EXPERIMENT_ID,),
                "evidence_ids": (EVIDENCE_ID, REPLACEMENT_EVIDENCE_ID),
                "evidence_history": (initial, replacement),
            }
        )


def test_projection_restore_rejects_multiple_children_for_one_target() -> None:
    initial, replacement, _ = _evidence_lineage()
    competing_replacement = EvidenceHistoryEntry(
        evidence_id=THIRD_EVIDENCE_ID,
        experiment_id=EXPERIMENT_ID,
        candidate_id=CANDIDATE_ID,
        correction_sequence=1,
        corrects_evidence_id=EVIDENCE_ID,
    )

    with pytest.raises(ValidationError, match="multiple correction children"):
        SessionProjection.model_validate(
            {
                "session_id": SESSION_ID,
                "status": SessionStatus.ACTIVE,
                "sequence": 3,
                "candidate_ids": (CANDIDATE_ID,),
                "experiment_ids": (EXPERIMENT_ID,),
                "active_experiment_ids": (EXPERIMENT_ID,),
                "evidence_ids": (
                    EVIDENCE_ID,
                    REPLACEMENT_EVIDENCE_ID,
                    THIRD_EVIDENCE_ID,
                ),
                "superseded_evidence_ids": (EVIDENCE_ID,),
                "evidence_history": (initial, replacement, competing_replacement),
            }
        )


def test_projection_restore_rejects_correction_before_target() -> None:
    initial, replacement, _ = _evidence_lineage()

    with pytest.raises(ValidationError, match="after its target"):
        SessionProjection.model_validate(
            {
                "session_id": SESSION_ID,
                "status": SessionStatus.ACTIVE,
                "sequence": 2,
                "candidate_ids": (CANDIDATE_ID,),
                "experiment_ids": (EXPERIMENT_ID,),
                "active_experiment_ids": (EXPERIMENT_ID,),
                "evidence_ids": (EVIDENCE_ID, REPLACEMENT_EVIDENCE_ID),
                "superseded_evidence_ids": (EVIDENCE_ID,),
                "evidence_history": (replacement, initial),
            }
        )


def test_projection_restore_rejects_lineage_order_mismatch() -> None:
    initial, replacement, third = _evidence_lineage()

    with pytest.raises(ValidationError, match="supersession order"):
        SessionProjection.model_validate(
            {
                "session_id": SESSION_ID,
                "status": SessionStatus.ACTIVE,
                "sequence": 3,
                "candidate_ids": (CANDIDATE_ID,),
                "experiment_ids": (EXPERIMENT_ID,),
                "active_experiment_ids": (EXPERIMENT_ID,),
                "evidence_ids": (
                    EVIDENCE_ID,
                    REPLACEMENT_EVIDENCE_ID,
                    THIRD_EVIDENCE_ID,
                ),
                "superseded_evidence_ids": (
                    REPLACEMENT_EVIDENCE_ID,
                    EVIDENCE_ID,
                ),
                "evidence_history": (initial, replacement, third),
            }
        )


@pytest.mark.parametrize(
    ("superseded_evidence_ids", "evidence_history", "message"),
    [
        (
            (EVIDENCE_ID, EVIDENCE_ID),
            _evidence_lineage()[:2],
            "duplicate superseded evidence",
        ),
        (
            (EVIDENCE_ID,),
            (*_evidence_lineage()[:2], _evidence_lineage()[1]),
            "duplicate evidence history",
        ),
    ],
)
def test_projection_restore_rejects_duplicate_lineage_records_before_normalizing(
    superseded_evidence_ids: tuple[UUID, ...],
    evidence_history: tuple[EvidenceHistoryEntry, ...],
    message: str,
) -> None:
    with pytest.raises(ValidationError, match=message):
        SessionProjection.model_validate(
            {
                "session_id": SESSION_ID,
                "status": SessionStatus.ACTIVE,
                "sequence": 3,
                "candidate_ids": (CANDIDATE_ID,),
                "experiment_ids": (EXPERIMENT_ID,),
                "evidence_ids": (EVIDENCE_ID, REPLACEMENT_EVIDENCE_ID),
                "superseded_evidence_ids": superseded_evidence_ids,
                "evidence_history": evidence_history,
            }
        )


def test_projection_restore_rejects_conflicting_duplicate_evidence_history() -> None:
    initial, replacement, _ = _evidence_lineage()
    conflicting_replacement = EvidenceHistoryEntry(
        evidence_id=REPLACEMENT_EVIDENCE_ID,
        experiment_id=EXPERIMENT_ID,
        candidate_id=CANDIDATE_ID,
        correction_sequence=0,
    )

    with pytest.raises(ValidationError, match="evidence history relationship conflicts"):
        SessionProjection.model_validate(
            {
                "session_id": SESSION_ID,
                "status": SessionStatus.ACTIVE,
                "sequence": 3,
                "candidate_ids": (CANDIDATE_ID,),
                "experiment_ids": (EXPERIMENT_ID,),
                "evidence_ids": (EVIDENCE_ID, REPLACEMENT_EVIDENCE_ID),
                "superseded_evidence_ids": (EVIDENCE_ID,),
                "evidence_history": (
                    initial,
                    replacement,
                    conflicting_replacement,
                ),
            }
        )


def test_projection_restore_round_trips_valid_multi_step_lineage() -> None:
    initial, replacement, third = _evidence_lineage()
    projection = SessionProjection.model_validate(
        {
            "session_id": SESSION_ID,
            "status": SessionStatus.ACTIVE,
            "sequence": 3,
            "candidate_ids": (CANDIDATE_ID,),
            "experiment_ids": (EXPERIMENT_ID,),
            "active_experiment_ids": (EXPERIMENT_ID,),
            "evidence_ids": (
                EVIDENCE_ID,
                REPLACEMENT_EVIDENCE_ID,
                THIRD_EVIDENCE_ID,
            ),
            "superseded_evidence_ids": (
                EVIDENCE_ID,
                REPLACEMENT_EVIDENCE_ID,
            ),
            "evidence_history": (initial, replacement, third),
        }
    )

    restored = SessionProjection.model_validate(projection.model_dump())

    assert restored == projection
    assert restored.evidence_history == (initial, replacement, third)
    assert restored.superseded_evidence_ids == (
        EVIDENCE_ID,
        REPLACEMENT_EVIDENCE_ID,
    )


@pytest.mark.parametrize("sequences", [(2,), (1, 3), (1, 1)])
def test_sequence_starts_at_one_without_gaps_or_repeats(
    sequences: tuple[int, ...],
) -> None:
    started = _event(sequences[0], EventKind.SESSION_STARTED, _session())
    events = [started]
    if len(sequences) > 1:
        events.append(
            _event(
                sequences[1],
                EventKind.CANDIDATE_ADDED,
                _candidate(),
                started,
            )
        )

    with pytest.raises(ValueError, match="sequence"):
        reduce_events(tuple(events))


def test_candidate_update_rejects_a_candidate_that_was_never_added() -> None:
    started = _event(1, EventKind.SESSION_STARTED, _session())
    unknown_update = _event(
        2,
        EventKind.CANDIDATE_UPDATED,
        _candidate(),
        started,
    )

    with pytest.raises(ValueError, match="unknown candidate"):
        reduce_events((started, unknown_update))


def test_candidate_add_rejects_an_unknown_parent_reference() -> None:
    started = _event(1, EventKind.SESSION_STARTED, _session())
    child = _event(
        2,
        EventKind.CANDIDATE_ADDED,
        _candidate(parent_ids=(UUID("50000000-0000-0000-0000-000000000001"),)),
        started,
    )

    with pytest.raises(ValueError, match="unknown parent"):
        reduce_events((started, child))


def test_candidate_add_records_claim_identities_for_belief_updates() -> None:
    started = _event(1, EventKind.SESSION_STARTED, _session())
    candidate = _candidate(
        claims=(
            Claim(
                id=CLAIM_ID,
                candidate_id=CANDIDATE_ID,
                claim_type=ClaimType.FEASIBILITY,
                statement="The candidate is feasible",
                first_order_effects=("Safer coordination",),
                second_order_effects=("Higher operator trust",),
            ),
        )
    )
    added = _event(2, EventKind.CANDIDATE_ADDED, candidate, started)

    assert reduce_events((started, added)).claim_ids == (CLAIM_ID,)


def test_candidate_update_cannot_move_an_existing_claim_to_another_candidate() -> None:
    claim = Claim(
        id=CLAIM_ID,
        candidate_id=CANDIDATE_ID,
        claim_type=ClaimType.FEASIBILITY,
        statement="The candidate is feasible",
        first_order_effects=("Safer coordination",),
        second_order_effects=("Higher operator trust",),
    )
    started = _event(1, EventKind.SESSION_STARTED, _session())
    first = _event(
        2,
        EventKind.CANDIDATE_ADDED,
        _candidate(claims=(claim,)),
        started,
    )
    second = _event(
        3,
        EventKind.CANDIDATE_ADDED,
        _candidate(id=CANDIDATE_2_ID, title="Second candidate"),
        first,
    )
    moved_claim = claim.model_copy(update={"candidate_id": CANDIDATE_2_ID})
    invalid_update = _event(
        4,
        EventKind.CANDIDATE_UPDATED,
        _candidate(
            id=CANDIDATE_2_ID,
            title="Second candidate",
            claims=(moved_claim,),
        ),
        second,
    )

    with pytest.raises(ValueError, match="claim ownership"):
        reduce_events((started, first, second, invalid_update))


def test_known_candidate_history_survives_inactive_updates_and_dump_replay() -> None:
    started = _event(1, EventKind.SESSION_STARTED, _session())
    added = _event(2, EventKind.CANDIDATE_ADDED, _candidate(), started)
    rejected = _event(
        3,
        EventKind.CANDIDATE_UPDATED,
        _candidate(selection_state=CandidateSelectionState.REJECTED),
        added,
    )
    updated_while_inactive = _event(
        4,
        EventKind.CANDIDATE_UPDATED,
        _candidate(
            title="Reversible coordination, revised",
            selection_state=CandidateSelectionState.REJECTED,
        ),
        rejected,
    )

    projection = reduce_events((started, added, rejected, updated_while_inactive))
    restored = SessionProjection.model_validate(projection.model_dump())

    assert projection.candidate_ids == (CANDIDATE_ID,)
    assert projection.active_candidate_ids == ()
    assert restored == projection


def test_experiment_status_rejects_an_experiment_that_was_never_proposed() -> None:
    started = _event(1, EventKind.SESSION_STARTED, _session())
    unknown_status = _event(
        2,
        EventKind.EXPERIMENT_STATUS_CHANGED,
        ExperimentStatusChange(
            session_id=SESSION_ID,
            experiment_id=EXPERIMENT_ID,
            status=ExperimentStatus.RUNNING,
        ),
        started,
    )

    with pytest.raises(ValueError, match="unknown experiment"):
        reduce_events((started, unknown_status))


def test_terminal_experiment_status_is_retained_outside_active_ids() -> None:
    projection = SessionProjection(
        session_id=SESSION_ID,
        status=SessionStatus.ACTIVE,
        sequence=1,
        experiment_ids=(EXPERIMENT_ID,),
        active_experiment_ids=(EXPERIMENT_ID,),
        authorization_grant_ids=(GRANT_ID,),
        authorization_grants=(
            AuthorizationGrantExperiment(
                grant_id=GRANT_ID,
                experiment_id=EXPERIMENT_ID,
            ),
        ),
        experiment_statuses=(
            ExperimentStatusRecord(
                experiment_id=EXPERIMENT_ID,
                status=ExperimentStatus.RUNNING,
            ),
        ),
    )
    completed = _event(
        2,
        EventKind.EXPERIMENT_STATUS_CHANGED,
        ExperimentStatusChange(
            session_id=SESSION_ID,
            experiment_id=EXPERIMENT_ID,
            status=ExperimentStatus.COMPLETED,
        ),
    )

    result = reduce_session(projection, completed)

    assert result.active_experiment_ids == ()
    assert result.terminal_experiment_ids == (EXPERIMENT_ID,)
    assert result.experiment_statuses == (
        ExperimentStatusRecord(
            experiment_id=EXPERIMENT_ID,
            status=ExperimentStatus.COMPLETED,
        ),
    )


@pytest.mark.parametrize("status", [ExperimentStatus.AUTHORIZED, ExperimentStatus.RUNNING])
def test_terminal_experiment_cannot_reopen_without_an_explicit_resume_event(
    status: ExperimentStatus,
) -> None:
    projection = SessionProjection(
        session_id=SESSION_ID,
        status=SessionStatus.ACTIVE,
        sequence=2,
        experiment_ids=(EXPERIMENT_ID,),
        terminal_experiment_ids=(EXPERIMENT_ID,),
        authorization_grant_ids=(GRANT_ID,),
        authorization_grants=(
            AuthorizationGrantExperiment(
                grant_id=GRANT_ID,
                experiment_id=EXPERIMENT_ID,
            ),
        ),
        experiment_statuses=(
            ExperimentStatusRecord(
                experiment_id=EXPERIMENT_ID,
                status=ExperimentStatus.COMPLETED,
            ),
        ),
    )
    reopen = _event(
        3,
        EventKind.EXPERIMENT_STATUS_CHANGED,
        ExperimentStatusChange(
            session_id=SESSION_ID,
            experiment_id=EXPERIMENT_ID,
            status=status,
        ),
    )

    with pytest.raises(ValueError, match="cannot change status for a terminal experiment"):
        reduce_session(projection, reopen)


def test_proposed_experiment_cannot_run_without_authorization_event() -> None:
    projection = SessionProjection(
        session_id=SESSION_ID,
        status=SessionStatus.ACTIVE,
        sequence=1,
        experiment_ids=(EXPERIMENT_ID,),
        active_experiment_ids=(EXPERIMENT_ID,),
    )
    running = _event(
        2,
        EventKind.EXPERIMENT_STATUS_CHANGED,
        ExperimentStatusChange(
            session_id=SESSION_ID,
            experiment_id=EXPERIMENT_ID,
            status=ExperimentStatus.RUNNING,
        ),
    )

    with pytest.raises(ValueError, match="invalid experiment status transition"):
        reduce_session(projection, running)


@pytest.mark.parametrize(
    "status",
    [ExperimentStatus.PROPOSED, ExperimentStatus.AUTHORIZED],
)
def test_running_experiment_cannot_regress_or_synthesize_authorization(
    status: ExperimentStatus,
) -> None:
    projection = SessionProjection(
        session_id=SESSION_ID,
        status=SessionStatus.ACTIVE,
        sequence=3,
        experiment_ids=(EXPERIMENT_ID,),
        active_experiment_ids=(EXPERIMENT_ID,),
        authorization_grant_ids=(GRANT_ID,),
        authorization_grants=(
            AuthorizationGrantExperiment(
                grant_id=GRANT_ID,
                experiment_id=EXPERIMENT_ID,
            ),
        ),
        experiment_statuses=(
            ExperimentStatusRecord(
                experiment_id=EXPERIMENT_ID,
                status=ExperimentStatus.RUNNING,
            ),
        ),
    )
    invalid_change = _event(
        4,
        EventKind.EXPERIMENT_STATUS_CHANGED,
        ExperimentStatusChange(
            session_id=SESSION_ID,
            experiment_id=EXPERIMENT_ID,
            status=status,
        ),
    )

    with pytest.raises(ValueError, match="invalid experiment status transition"):
        reduce_session(projection, invalid_change)


@pytest.mark.parametrize(
    "terminal_status",
    [
        ExperimentStatus.COMPLETED,
        ExperimentStatus.INCONCLUSIVE,
        ExperimentStatus.FAILED,
    ],
)
def test_authorized_experiment_runs_and_reaches_terminal_status(
    terminal_status: ExperimentStatus,
) -> None:
    started, first_candidate, second_candidate, proposed = _introduced_graph()
    authorized = _event(
        5,
        EventKind.EXPERIMENT_AUTHORIZED,
        _authorization_grant(),
        proposed,
    )
    running = _event(
        6,
        EventKind.EXPERIMENT_STATUS_CHANGED,
        ExperimentStatusChange(
            session_id=SESSION_ID,
            experiment_id=EXPERIMENT_ID,
            status=ExperimentStatus.RUNNING,
        ),
        authorized,
    )
    terminal = _event(
        7,
        EventKind.EXPERIMENT_STATUS_CHANGED,
        ExperimentStatusChange(
            session_id=SESSION_ID,
            experiment_id=EXPERIMENT_ID,
            status=terminal_status,
        ),
        running,
    )

    projection = reduce_events(
        (
            started,
            first_candidate,
            second_candidate,
            proposed,
            authorized,
            running,
            terminal,
        )
    )
    restored = SessionProjection.model_validate(projection.model_dump())

    assert projection.experiment_statuses == (
        ExperimentStatusRecord(
            experiment_id=EXPERIMENT_ID,
            status=terminal_status,
        ),
    )
    assert projection.active_experiment_ids == ()
    assert projection.terminal_experiment_ids == (EXPERIMENT_ID,)
    assert restored == projection


def test_authorized_experiment_can_fail_before_running() -> None:
    projection = _projection_with_known_graph()
    authorized = reduce_session(
        projection,
        _event(2, EventKind.EXPERIMENT_AUTHORIZED, _authorization_grant()),
    )
    failed = _event(
        3,
        EventKind.EXPERIMENT_STATUS_CHANGED,
        ExperimentStatusChange(
            session_id=SESSION_ID,
            experiment_id=EXPERIMENT_ID,
            status=ExperimentStatus.FAILED,
        ),
    )

    result = reduce_session(authorized, failed)

    assert result.experiment_statuses[0].status is ExperimentStatus.FAILED


def test_multiple_distinct_grants_keep_experiment_authorized() -> None:
    projection = _projection_with_known_graph()
    first = reduce_session(
        projection,
        _event(2, EventKind.EXPERIMENT_AUTHORIZED, _authorization_grant()),
    )
    second_grant_id = UUID("00000000-0000-0000-0000-00000000000c")
    second = reduce_session(
        first,
        _event(
            3,
            EventKind.EXPERIMENT_AUTHORIZED,
            _authorization_grant(grant_id=second_grant_id),
        ),
    )

    assert first.experiment_statuses == (
        ExperimentStatusRecord(
            experiment_id=EXPERIMENT_ID,
            status=ExperimentStatus.AUTHORIZED,
        ),
    )
    assert second.authorization_grant_ids == (GRANT_ID, second_grant_id)
    assert second.experiment_statuses == (
        ExperimentStatusRecord(
            experiment_id=EXPERIMENT_ID,
            status=ExperimentStatus.AUTHORIZED,
        ),
    )


def test_experiment_proposal_rejects_unknown_candidate_references() -> None:
    projection = SessionProjection(
        session_id=SESSION_ID,
        status=SessionStatus.ACTIVE,
        sequence=1,
        candidate_ids=(CANDIDATE_ID,),
        active_candidate_ids=(CANDIDATE_ID,),
    )
    proposed = _event(2, EventKind.EXPERIMENT_PROPOSED, _experiment())

    with pytest.raises(ValueError, match="unknown candidate"):
        reduce_session(projection, proposed)


def test_experiment_authorization_rejects_an_unknown_experiment() -> None:
    projection = SessionProjection(
        session_id=SESSION_ID,
        status=SessionStatus.ACTIVE,
        sequence=1,
    )
    authorized = _event(
        2,
        EventKind.EXPERIMENT_AUTHORIZED,
        AuthorizationGrant(
            session_id=SESSION_ID,
            experiment_id=EXPERIMENT_ID,
            side_effect=SideEffectClass.READ_ONLY_LOCAL,
            allowed_actions=("Observe local result",),
            expires_at=datetime(2026, 7, 18, tzinfo=UTC),
            issuer="operator",
            integrity_hash="sha256:grant",
        ),
    )

    with pytest.raises(ValueError, match="unknown experiment"):
        reduce_session(projection, authorized)


def test_terminal_experiment_cannot_receive_new_authorization() -> None:
    projection = SessionProjection(
        session_id=SESSION_ID,
        status=SessionStatus.ACTIVE,
        sequence=2,
        experiment_ids=(EXPERIMENT_ID,),
        terminal_experiment_ids=(EXPERIMENT_ID,),
        authorization_grant_ids=(GRANT_ID,),
        authorization_grants=(
            AuthorizationGrantExperiment(
                grant_id=GRANT_ID,
                experiment_id=EXPERIMENT_ID,
            ),
        ),
        experiment_statuses=(
            ExperimentStatusRecord(
                experiment_id=EXPERIMENT_ID,
                status=ExperimentStatus.COMPLETED,
            ),
        ),
    )
    authorized = _event(
        3,
        EventKind.EXPERIMENT_AUTHORIZED,
        AuthorizationGrant(
            session_id=SESSION_ID,
            experiment_id=EXPERIMENT_ID,
            side_effect=SideEffectClass.READ_ONLY_LOCAL,
            allowed_actions=("Observe local result",),
            expires_at=datetime(2026, 7, 18, tzinfo=UTC),
            issuer="operator",
            integrity_hash="sha256:grant",
        ),
    )

    with pytest.raises(ValueError, match="terminal experiment"):
        reduce_session(projection, authorized)


def test_authorization_is_recorded_and_evidence_requires_known_grants() -> None:
    projection = _projection_with_known_graph()
    grant = AuthorizationGrant(
        id=GRANT_ID,
        session_id=SESSION_ID,
        experiment_id=EXPERIMENT_ID,
        side_effect=SideEffectClass.READ_ONLY_LOCAL,
        allowed_actions=("Observe local result",),
        expires_at=datetime(2026, 7, 18, tzinfo=UTC),
        issuer="operator",
        integrity_hash="sha256:grant",
    )
    authorized = _event(2, EventKind.EXPERIMENT_AUTHORIZED, grant)
    with_grant = reduce_session(projection, authorized)
    evidence = _event(
        2,
        EventKind.EVIDENCE_ACCEPTED,
        EvidenceAccepted(
            session_id=SESSION_ID,
            evidence=_evidence(authorization_grant_ids=(GRANT_ID,)),
        ),
    )

    assert with_grant.authorization_grant_ids == (GRANT_ID,)
    with pytest.raises(ValueError, match="authorization grant"):
        reduce_session(projection, evidence)


def test_authorization_rejects_a_duplicate_grant_identity() -> None:
    projection = SessionProjection(
        session_id=SESSION_ID,
        status=SessionStatus.ACTIVE,
        sequence=1,
        experiment_ids=(EXPERIMENT_ID,),
        active_experiment_ids=(EXPERIMENT_ID,),
        authorization_grant_ids=(GRANT_ID,),
    )
    duplicate = _event(
        2,
        EventKind.EXPERIMENT_AUTHORIZED,
        AuthorizationGrant(
            id=GRANT_ID,
            session_id=SESSION_ID,
            experiment_id=EXPERIMENT_ID,
            side_effect=SideEffectClass.READ_ONLY_LOCAL,
            allowed_actions=("Observe local result",),
            expires_at=datetime(2026, 7, 18, tzinfo=UTC),
            issuer="operator",
            integrity_hash="sha256:grant",
        ),
    )

    with pytest.raises(ValueError, match="already been recorded"):
        reduce_session(projection, duplicate)


def test_evidence_grants_must_belong_to_the_same_experiment() -> None:
    projection = SessionProjection(
        session_id=SESSION_ID,
        status=SessionStatus.ACTIVE,
        sequence=1,
        candidate_ids=(CANDIDATE_ID,),
        experiment_ids=(EXPERIMENT_ID, EXPERIMENT_2_ID),
        active_experiment_ids=(EXPERIMENT_ID, EXPERIMENT_2_ID),
        authorization_grant_ids=(GRANT_ID,),
        experiment_statuses=(
            ExperimentStatusRecord(
                experiment_id=EXPERIMENT_ID,
                status=ExperimentStatus.PROPOSED,
            ),
            ExperimentStatusRecord(
                experiment_id=EXPERIMENT_2_ID,
                status=ExperimentStatus.AUTHORIZED,
            ),
        ),
        experiment_candidates=(
            ExperimentCandidates(
                experiment_id=EXPERIMENT_ID,
                candidate_ids=(CANDIDATE_ID,),
            ),
            ExperimentCandidates(
                experiment_id=EXPERIMENT_2_ID,
                candidate_ids=(CANDIDATE_ID,),
            ),
        ),
        authorization_grants=(
            AuthorizationGrantExperiment(
                grant_id=GRANT_ID,
                experiment_id=EXPERIMENT_2_ID,
            ),
        ),
    )
    cross_joined = _event(
        2,
        EventKind.EVIDENCE_ACCEPTED,
        EvidenceAccepted(
            session_id=SESSION_ID,
            evidence=_evidence(authorization_grant_ids=(GRANT_ID,)),
        ),
    )

    with pytest.raises(ValueError, match="same experiment"):
        reduce_session(projection, cross_joined)


def test_evidence_candidate_must_belong_to_its_experiment() -> None:
    projection = SessionProjection(
        session_id=SESSION_ID,
        status=SessionStatus.ACTIVE,
        sequence=1,
        candidate_ids=(CANDIDATE_ID, CANDIDATE_2_ID),
        experiment_ids=(EXPERIMENT_ID,),
        active_experiment_ids=(EXPERIMENT_ID,),
        experiment_candidates=(
            ExperimentCandidates(
                experiment_id=EXPERIMENT_ID,
                candidate_ids=(CANDIDATE_2_ID,),
            ),
        ),
    )
    cross_joined = _event(
        2,
        EventKind.EVIDENCE_ACCEPTED,
        EvidenceAccepted(session_id=SESSION_ID, evidence=_evidence()),
    )

    with pytest.raises(ValueError, match="candidate.*experiment"):
        reduce_session(projection, cross_joined)


@pytest.mark.parametrize(
    ("candidate_ids", "experiment_ids", "match"),
    [
        ((), (EXPERIMENT_ID,), "unknown candidate"),
        ((CANDIDATE_ID,), (), "unknown experiment"),
    ],
)
def test_evidence_rejects_unknown_candidate_or_experiment_references(
    candidate_ids: tuple[UUID, ...],
    experiment_ids: tuple[UUID, ...],
    match: str,
) -> None:
    projection = SessionProjection(
        session_id=SESSION_ID,
        status=SessionStatus.ACTIVE,
        sequence=1,
        candidate_ids=candidate_ids,
        experiment_ids=experiment_ids,
        active_experiment_ids=experiment_ids,
    )
    accepted = _event(
        2,
        EventKind.EVIDENCE_ACCEPTED,
        EvidenceAccepted(session_id=SESSION_ID, evidence=_evidence()),
    )

    with pytest.raises(ValueError, match=match):
        reduce_session(projection, accepted)


def test_evidence_rejects_a_duplicate_recorded_identity() -> None:
    projection = _projection_with_known_graph(
        evidence_ids=(EVIDENCE_ID,),
    )
    duplicate = _event(
        2,
        EventKind.EVIDENCE_ACCEPTED,
        EvidenceAccepted(session_id=SESSION_ID, evidence=_evidence()),
    )

    with pytest.raises(ValueError, match="already been recorded"):
        reduce_session(projection, duplicate)


def test_evidence_correction_requires_the_explicit_supersession_event() -> None:
    projection = _projection_with_known_graph(
        evidence_ids=(EVIDENCE_ID,),
    )
    correction_as_acceptance = _event(
        2,
        EventKind.EVIDENCE_ACCEPTED,
        EvidenceAccepted(
            session_id=SESSION_ID,
            evidence=_evidence(
                evidence_id=REPLACEMENT_EVIDENCE_ID,
                corrects_evidence_id=EVIDENCE_ID,
                correction_sequence=1,
            ),
        ),
    )

    with pytest.raises(ValueError, match="supersession event"):
        reduce_session(projection, correction_as_acceptance)


def test_rejected_evidence_correction_requires_explicit_supersession() -> None:
    projection = _projection_with_known_graph(
        evidence_ids=(EVIDENCE_ID,),
    )
    correction_as_rejection = _event(
        2,
        EventKind.EVIDENCE_REJECTED,
        EvidenceRejected(
            session_id=SESSION_ID,
            evidence=_evidence(
                evidence_id=REPLACEMENT_EVIDENCE_ID,
                status=EvidenceValidationStatus.INVALID,
                corrects_evidence_id=EVIDENCE_ID,
                correction_sequence=1,
            ),
            reason="Correction was invalid",
        ),
    )

    with pytest.raises(ValueError, match="supersession event"):
        reduce_session(projection, correction_as_rejection)


@pytest.mark.parametrize(("evidence_ids", "claim_ids", "match"), [
    ((), (CLAIM_ID,), "unknown evidence"),
    ((EVIDENCE_ID,), (), "unknown claim"),
])
def test_belief_update_requires_known_evidence_and_claim(
    evidence_ids: tuple[UUID, ...],
    claim_ids: tuple[UUID, ...],
    match: str,
) -> None:
    projection = SessionProjection(
        session_id=SESSION_ID,
        status=SessionStatus.ACTIVE,
        sequence=1,
        evidence_ids=evidence_ids,
        claim_ids=claim_ids,
    )
    belief = _event(
        2,
        EventKind.BELIEF_UPDATED,
        BeliefUpdate(
            session_id=SESSION_ID,
            evidence_id=EVIDENCE_ID,
            claim_id=CLAIM_ID,
            prior_state=ClaimSupportState.UNTESTED,
            updated_state=ClaimSupportState.SUPPORTED,
            interpretation="Evidence supports the claim",
        ),
    )

    with pytest.raises(ValueError, match=match):
        reduce_session(projection, belief)


def test_belief_evidence_and_claim_must_share_candidate_ownership() -> None:
    projection = SessionProjection(
        session_id=SESSION_ID,
        status=SessionStatus.ACTIVE,
        sequence=1,
        candidate_ids=(CANDIDATE_ID, CANDIDATE_2_ID),
        experiment_ids=(EXPERIMENT_ID,),
        active_experiment_ids=(EXPERIMENT_ID,),
        evidence_ids=(EVIDENCE_ID,),
        claim_ids=(CLAIM_ID,),
        claim_ownership=(
            ClaimOwnership(claim_id=CLAIM_ID, candidate_id=CANDIDATE_2_ID),
        ),
        evidence_history=(
            EvidenceHistoryEntry(
                evidence_id=EVIDENCE_ID,
                experiment_id=EXPERIMENT_ID,
                candidate_id=CANDIDATE_ID,
                correction_sequence=0,
            ),
        ),
    )
    belief = _event(
        2,
        EventKind.BELIEF_UPDATED,
        BeliefUpdate(
            session_id=SESSION_ID,
            evidence_id=EVIDENCE_ID,
            claim_id=CLAIM_ID,
            prior_state=ClaimSupportState.UNTESTED,
            updated_state=ClaimSupportState.SUPPORTED,
            interpretation="Cross-joined evidence",
        ),
    )

    with pytest.raises(ValueError, match="same candidate"):
        reduce_session(projection, belief)


def test_selection_requires_known_experiment_candidates_and_evidence() -> None:
    projection = SessionProjection(
        session_id=SESSION_ID,
        status=SessionStatus.ACTIVE,
        sequence=1,
        candidate_ids=(CANDIDATE_ID, CANDIDATE_2_ID),
        experiment_ids=(EXPERIMENT_ID,),
        active_experiment_ids=(EXPERIMENT_ID,),
    )
    selection = _event(
        2,
        EventKind.SELECTION_DECIDED,
        SelectionDecision(
            session_id=SESSION_ID,
            experiment_id=EXPERIMENT_ID,
            considered_candidate_ids=(CANDIDATE_ID, CANDIDATE_2_ID),
            selected_candidate_id=CANDIDATE_ID,
            resulting_state=CandidateSelectionState.SELECTED,
            supporting_evidence_ids=(EVIDENCE_ID,),
            rationale="Verified evidence favors the candidate",
        ),
    )

    with pytest.raises(ValueError, match="unknown evidence"):
        reduce_session(projection, selection)


@pytest.mark.parametrize("cross_join", ["candidate", "evidence"])
def test_selection_relationships_must_belong_to_the_decision_experiment(
    cross_join: str,
) -> None:
    considered = (
        (CANDIDATE_ID, CANDIDATE_3_ID)
        if cross_join == "candidate"
        else (CANDIDATE_ID, CANDIDATE_2_ID)
    )
    evidence_experiment_id = (
        EXPERIMENT_2_ID if cross_join == "evidence" else EXPERIMENT_ID
    )
    projection = SessionProjection(
        session_id=SESSION_ID,
        status=SessionStatus.ACTIVE,
        sequence=1,
        candidate_ids=(CANDIDATE_ID, CANDIDATE_2_ID, CANDIDATE_3_ID),
        experiment_ids=(EXPERIMENT_ID, EXPERIMENT_2_ID),
        active_experiment_ids=(EXPERIMENT_ID, EXPERIMENT_2_ID),
        evidence_ids=(EVIDENCE_ID,),
        experiment_candidates=(
            ExperimentCandidates(
                experiment_id=EXPERIMENT_ID,
                candidate_ids=(CANDIDATE_ID, CANDIDATE_2_ID),
            ),
            ExperimentCandidates(
                experiment_id=EXPERIMENT_2_ID,
                candidate_ids=(CANDIDATE_2_ID, CANDIDATE_3_ID),
            ),
        ),
        evidence_history=(
            EvidenceHistoryEntry(
                evidence_id=EVIDENCE_ID,
                experiment_id=evidence_experiment_id,
                candidate_id=(
                    CANDIDATE_2_ID
                    if evidence_experiment_id == EXPERIMENT_2_ID
                    else CANDIDATE_ID
                ),
                correction_sequence=0,
            ),
        ),
    )
    selection = _event(
        2,
        EventKind.SELECTION_DECIDED,
        SelectionDecision(
            session_id=SESSION_ID,
            experiment_id=EXPERIMENT_ID,
            considered_candidate_ids=considered,
            selected_candidate_id=considered[0],
            resulting_state=CandidateSelectionState.SELECTED,
            supporting_evidence_ids=(EVIDENCE_ID,),
            rationale="Cross-joined selection",
        ),
    )

    with pytest.raises(ValueError, match=cross_join):
        reduce_session(projection, selection)


def test_hash_chain_rejects_wrong_previous_hash() -> None:
    started = _event(1, EventKind.SESSION_STARTED, _session())
    added = SessionEvent.create(
        SESSION_ID,
        2,
        EventKind.CANDIDATE_ADDED,
        _candidate(),
        idempotency_key="event-2",
        timestamp=datetime(2026, 7, 17, 12, 2, tzinfo=UTC),
        event_id=UUID("00000000-0000-0000-0000-000000000002"),
        previous_event_hash="f" * 64,
    )

    with pytest.raises(ValueError, match="previous event hash"):
        reduce_events((started, added))


def test_replay_rejects_mixed_session_ids_in_envelope_or_payload() -> None:
    other_session_id = UUID("10000000-0000-0000-0000-000000000001")
    started = _event(1, EventKind.SESSION_STARTED, _session())
    wrong_envelope = _event(
        2,
        EventKind.CANDIDATE_ADDED,
        _candidate(session_id=other_session_id),
        started,
        session_id=other_session_id,
    )
    wrong_payload = _event(
        2,
        EventKind.CANDIDATE_ADDED,
        _candidate(session_id=other_session_id),
        started,
    )

    with pytest.raises(ValueError, match="mixed session IDs"):
        reduce_events((started, wrong_envelope))
    with pytest.raises(ValueError, match="payload session ID"):
        reduce_events((started, wrong_payload))


def test_single_event_reducer_rejects_mixed_session_identity() -> None:
    other_session_id = UUID("10000000-0000-0000-0000-000000000001")
    mismatched_start = _event(
        1,
        EventKind.SESSION_STARTED,
        _session(),
        session_id=other_session_id,
    )

    with pytest.raises(ValueError, match="payload session ID"):
        reduce_session(None, mismatched_start)


def test_single_event_reducer_requires_first_sequence_to_be_one() -> None:
    sequence_two_start = _event(2, EventKind.SESSION_STARTED, _session())

    with pytest.raises(ValueError, match="sequence"):
        reduce_session(None, sequence_two_start)


def test_single_event_reducer_rejects_previous_hash_on_first_event() -> None:
    chained_start = SessionEvent.create(
        SESSION_ID,
        1,
        EventKind.SESSION_STARTED,
        _session(),
        idempotency_key="event-1",
        previous_event_hash="a" * 64,
    )

    with pytest.raises(ValueError, match="previous event hash"):
        reduce_session(None, chained_start)


def test_unknown_schema_versions_are_rejected_even_with_a_valid_hash() -> None:
    event = SessionEvent.create(
        SESSION_ID,
        1,
        EventKind.SESSION_STARTED,
        _session(),
        idempotency_key="event-1",
        schema_version=2,
    )

    with pytest.raises(ValueError, match="schema version"):
        reduce_events((event,))


@pytest.mark.parametrize("terminal_kind", [EventKind.SESSION_STOPPED, EventKind.SESSION_FAILED])
def test_terminal_sessions_require_an_explicit_resume_event(
    terminal_kind: EventKind,
) -> None:
    started = _event(1, EventKind.SESSION_STARTED, _session())
    terminated = _event(
        2,
        terminal_kind,
        SessionTermination(session_id=SESSION_ID, reason="Operator decision"),
        started,
    )
    illegal = _event(
        3,
        EventKind.SESSION_STATUS_CHANGED,
        SessionStatusChange(
            session_id=SESSION_ID,
            status=SessionStatus.ACTIVE,
            reason="Continue",
        ),
        terminated,
    )
    resumed = _event(
        3,
        EventKind.SESSION_RESUMED,
        SessionResume(session_id=SESSION_ID, reason="Operator approved resumption"),
        terminated,
    )

    with pytest.raises(ValueError, match="explicit resume"):
        reduce_events((started, terminated, illegal))
    assert reduce_events((started, terminated, resumed)).status is SessionStatus.ACTIVE


def test_resume_is_illegal_for_a_non_terminal_session() -> None:
    started = _event(1, EventKind.SESSION_STARTED, _session())
    resumed = _event(
        2,
        EventKind.SESSION_RESUMED,
        SessionResume(session_id=SESSION_ID, reason="No terminal state"),
        started,
    )

    with pytest.raises(ValueError, match="not terminal"):
        reduce_events((started, resumed))


@pytest.mark.parametrize(
    ("initial_status", "initial_kind"),
    [
        (EvidenceValidationStatus.VALID, EventKind.EVIDENCE_ACCEPTED),
        (EvidenceValidationStatus.INVALID, EventKind.EVIDENCE_REJECTED),
    ],
)
def test_evidence_supersession_preserves_accepted_or_rejected_history(
    initial_status: EvidenceValidationStatus,
    initial_kind: EventKind,
) -> None:
    initial = _evidence(status=initial_status)
    replacement = _evidence(
        evidence_id=REPLACEMENT_EVIDENCE_ID,
        corrects_evidence_id=EVIDENCE_ID,
        correction_sequence=1,
    )
    graph = _introduced_graph()
    initial_payload = (
        EvidenceAccepted(session_id=SESSION_ID, evidence=initial)
        if initial_kind is EventKind.EVIDENCE_ACCEPTED
        else EvidenceRejected(
            session_id=SESSION_ID,
            evidence=initial,
            reason="Initial evidence was invalid",
        )
    )
    recorded = _event(
        5,
        initial_kind,
        initial_payload,
        graph[-1],
    )
    superseded = _event(
        6,
        EventKind.EVIDENCE_SUPERSEDED,
        EvidenceSupersession(
            session_id=SESSION_ID,
            superseded_evidence_id=EVIDENCE_ID,
            replacement=replacement,
        ),
        recorded,
    )
    events = (*graph, recorded, superseded)

    projection = reduce_events(events)
    restored = SessionProjection.model_validate(projection.model_dump())

    assert projection.sequence == 6
    assert projection.evidence_ids == (EVIDENCE_ID, REPLACEMENT_EVIDENCE_ID)
    assert projection.superseded_evidence_ids == (EVIDENCE_ID,)
    assert events[4].payload.evidence == initial
    assert events[5].payload.replacement.corrects_evidence_id == initial.id
    assert restored == projection


def test_evidence_supersession_rejects_an_unknown_target() -> None:
    projection = _projection_with_known_graph()
    superseded = _event(
        2,
        EventKind.EVIDENCE_SUPERSEDED,
        EvidenceSupersession(
            session_id=SESSION_ID,
            superseded_evidence_id=EVIDENCE_ID,
            replacement=_evidence(
                evidence_id=REPLACEMENT_EVIDENCE_ID,
                corrects_evidence_id=EVIDENCE_ID,
                correction_sequence=1,
            ),
        ),
    )

    with pytest.raises(ValueError, match="unknown evidence"):
        reduce_session(projection, superseded)


def test_evidence_supersession_requires_the_next_correction_sequence() -> None:
    projection = _projection_with_known_graph(
        evidence_ids=(EVIDENCE_ID,),
        evidence_history=(
            EvidenceHistoryEntry(
                evidence_id=EVIDENCE_ID,
                experiment_id=EXPERIMENT_ID,
                candidate_id=CANDIDATE_ID,
                correction_sequence=0,
            ),
        ),
    )
    invalid_sequence = _event(
        2,
        EventKind.EVIDENCE_SUPERSEDED,
        EvidenceSupersession(
            session_id=SESSION_ID,
            superseded_evidence_id=EVIDENCE_ID,
            replacement=_evidence(
                evidence_id=REPLACEMENT_EVIDENCE_ID,
                corrects_evidence_id=EVIDENCE_ID,
                correction_sequence=7,
            ),
        ),
    )

    with pytest.raises(ValueError, match="correction sequence"):
        reduce_session(projection, invalid_sequence)


def test_evidence_supersession_supports_valid_multi_step_correction_history() -> None:
    projection = _projection_with_known_graph(
        evidence_ids=(EVIDENCE_ID,),
        evidence_history=(
            EvidenceHistoryEntry(
                evidence_id=EVIDENCE_ID,
                experiment_id=EXPERIMENT_ID,
                candidate_id=CANDIDATE_ID,
                correction_sequence=0,
            ),
        ),
    )
    first = _event(
        2,
        EventKind.EVIDENCE_SUPERSEDED,
        EvidenceSupersession(
            session_id=SESSION_ID,
            superseded_evidence_id=EVIDENCE_ID,
            replacement=_evidence(
                evidence_id=REPLACEMENT_EVIDENCE_ID,
                corrects_evidence_id=EVIDENCE_ID,
                correction_sequence=1,
            ),
        ),
    )
    after_first = reduce_session(projection, first)
    second = _event(
        3,
        EventKind.EVIDENCE_SUPERSEDED,
        EvidenceSupersession(
            session_id=SESSION_ID,
            superseded_evidence_id=REPLACEMENT_EVIDENCE_ID,
            replacement=_evidence(
                evidence_id=THIRD_EVIDENCE_ID,
                corrects_evidence_id=REPLACEMENT_EVIDENCE_ID,
                correction_sequence=2,
            ),
        ),
    )

    after_second = reduce_session(after_first, second)

    assert after_second.evidence_ids == (
        EVIDENCE_ID,
        REPLACEMENT_EVIDENCE_ID,
        THIRD_EVIDENCE_ID,
    )
    assert after_second.superseded_evidence_ids == (
        EVIDENCE_ID,
        REPLACEMENT_EVIDENCE_ID,
    )
    assert tuple(entry.correction_sequence for entry in after_second.evidence_history) == (
        0,
        1,
        2,
    )
    assert SessionProjection.model_validate(after_second.model_dump()) == after_second


def test_evidence_supersession_requires_a_new_replacement_identity() -> None:
    projection = _projection_with_known_graph(
        evidence_ids=(EVIDENCE_ID, REPLACEMENT_EVIDENCE_ID),
        evidence_history=(
            EvidenceHistoryEntry(
                evidence_id=EVIDENCE_ID,
                experiment_id=EXPERIMENT_ID,
                candidate_id=CANDIDATE_ID,
                correction_sequence=0,
            ),
            EvidenceHistoryEntry(
                evidence_id=REPLACEMENT_EVIDENCE_ID,
                experiment_id=EXPERIMENT_ID,
                candidate_id=CANDIDATE_ID,
                correction_sequence=0,
            ),
        ),
    )
    duplicate_replacement = _event(
        2,
        EventKind.EVIDENCE_SUPERSEDED,
        EvidenceSupersession(
            session_id=SESSION_ID,
            superseded_evidence_id=EVIDENCE_ID,
            replacement=_evidence(
                evidence_id=REPLACEMENT_EVIDENCE_ID,
                corrects_evidence_id=EVIDENCE_ID,
                correction_sequence=1,
            ),
        ),
    )

    with pytest.raises(ValueError, match="new evidence identity"):
        reduce_session(projection, duplicate_replacement)


def test_evidence_cannot_supersede_the_same_history_twice() -> None:
    projection = _projection_with_known_graph(
        evidence_ids=(EVIDENCE_ID, REPLACEMENT_EVIDENCE_ID),
        superseded_evidence_ids=(EVIDENCE_ID,),
        evidence_history=(
            EvidenceHistoryEntry(
                evidence_id=EVIDENCE_ID,
                experiment_id=EXPERIMENT_ID,
                candidate_id=CANDIDATE_ID,
                correction_sequence=0,
            ),
            EvidenceHistoryEntry(
                evidence_id=REPLACEMENT_EVIDENCE_ID,
                experiment_id=EXPERIMENT_ID,
                candidate_id=CANDIDATE_ID,
                correction_sequence=1,
                corrects_evidence_id=EVIDENCE_ID,
            ),
        ),
    )
    contradictory = _event(
        2,
        EventKind.EVIDENCE_SUPERSEDED,
        EvidenceSupersession(
            session_id=SESSION_ID,
            superseded_evidence_id=EVIDENCE_ID,
            replacement=_evidence(
                evidence_id=UUID("00000000-0000-0000-0000-000000000007"),
                corrects_evidence_id=EVIDENCE_ID,
                correction_sequence=1,
            ),
        ),
    )

    with pytest.raises(ValueError, match="already been superseded"):
        reduce_session(projection, contradictory)


def test_evidence_event_payloads_enforce_validation_and_correction_links() -> None:
    with pytest.raises(ValidationError, match="valid evidence"):
        EvidenceAccepted(
            session_id=SESSION_ID,
            evidence=_evidence(status=EvidenceValidationStatus.INVALID),
        )
    with pytest.raises(ValidationError, match="invalid evidence"):
        EvidenceRejected(
            session_id=SESSION_ID,
            evidence=_evidence(),
            reason="Malformed observation",
        )
    with pytest.raises(ValidationError, match="correction target"):
        EvidenceSupersession(
            session_id=SESSION_ID,
            superseded_evidence_id=UUID("20000000-0000-0000-0000-000000000001"),
            replacement=_evidence(
                evidence_id=REPLACEMENT_EVIDENCE_ID,
                corrects_evidence_id=EVIDENCE_ID,
                correction_sequence=1,
            ),
        )


def test_budget_reconciliation_requires_and_preserves_a_recorded_reservation() -> None:
    reservation_id = UUID("30000000-0000-0000-0000-000000000003")
    projection = SessionProjection(
        session_id=SESSION_ID,
        status=SessionStatus.ACTIVE,
        sequence=1,
    )
    reconciliation = _event(
        2,
        EventKind.BUDGET_RECONCILED,
        BudgetReconciliation(
            session_id=SESSION_ID,
            reservation_id=reservation_id,
            actual_cost_usd=0.20,
            actual_calls=1,
            actual_latency_ms=450,
            actual_human_minutes=0,
        ),
    )

    with pytest.raises(ValueError, match="unknown budget reservation"):
        reduce_session(projection, reconciliation)

    reservation = _event(
        2,
        EventKind.BUDGET_RESERVED,
        BudgetReservation(
            session_id=SESSION_ID,
            reservation_id=reservation_id,
            cost_usd=0.25,
            calls=1,
            latency_ms=500,
            human_minutes=0,
        ),
    )
    reserved = reduce_session(projection, reservation)
    reconciled_event = _event(
        3,
        EventKind.BUDGET_RECONCILED,
        reconciliation.payload,
    )
    reconciled = reduce_session(reserved, reconciled_event)

    assert reconciled.budget_reservation_ids == (reservation_id,)
    assert reconciled.reconciled_budget_reservation_ids == (reservation_id,)

    duplicate_reservation = _event(4, EventKind.BUDGET_RESERVED, reservation.payload)
    with pytest.raises(ValueError, match="already been recorded"):
        reduce_session(reconciled, duplicate_reservation)

    duplicate_reconciliation = _event(
        4,
        EventKind.BUDGET_RECONCILED,
        reconciliation.payload,
    )
    with pytest.raises(ValueError, match="already been reconciled"):
        reduce_session(reconciled, duplicate_reconciliation)


def test_snapshot_and_budget_events_update_only_durable_projection_fields() -> None:
    memory_id = UUID("30000000-0000-0000-0000-000000000001")
    taste_id = UUID("30000000-0000-0000-0000-000000000002")
    reservation_id = UUID("30000000-0000-0000-0000-000000000003")
    started = _event(1, EventKind.SESSION_STARTED, _session())
    memory = _event(
        2,
        EventKind.MEMORY_WRITTEN,
        SnapshotWrite(session_id=SESSION_ID, snapshot_id=memory_id),
        started,
    )
    taste = _event(
        3,
        EventKind.TASTE_WRITTEN,
        SnapshotWrite(session_id=SESSION_ID, snapshot_id=taste_id),
        memory,
    )
    reserved = _event(
        4,
        EventKind.BUDGET_RESERVED,
        BudgetReservation(
            session_id=SESSION_ID,
            reservation_id=reservation_id,
            cost_usd=0.25,
            calls=1,
            latency_ms=500,
            human_minutes=0,
        ),
        taste,
    )
    reconciled = _event(
        5,
        EventKind.BUDGET_RECONCILED,
        BudgetReconciliation(
            session_id=SESSION_ID,
            reservation_id=reservation_id,
            actual_cost_usd=0.20,
            actual_calls=1,
            actual_latency_ms=450,
            actual_human_minutes=0,
        ),
        reserved,
    )

    projection = reduce_events((started, memory, taste, reserved, reconciled))

    assert projection.memory_snapshot_id == memory_id
    assert projection.taste_snapshot_id == taste_id
    assert projection.sequence == 5


def test_session_event_requires_utc_timestamp() -> None:
    with pytest.raises(ValidationError, match="UTC"):
        SessionEvent.create(
            SESSION_ID,
            1,
            EventKind.SESSION_STARTED,
            _session(),
            idempotency_key="event-1",
            timestamp=datetime.fromisoformat("2026-07-17T12:00:00+05:00"),
        )
