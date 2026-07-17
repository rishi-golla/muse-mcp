from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from muse.experimentation.candidates import (
    Candidate,
    CandidatePrediction,
    CandidateSelectionState,
    ClaimSupportState,
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
    AuthorizationPolicy,
    CreativeSession,
    Objective,
    PrivacyPolicy,
    SessionBudgets,
    SessionStatus,
    SideEffectClass,
)

SESSION_ID = UUID("00000000-0000-0000-0000-000000000001")
CANDIDATE_ID = UUID("00000000-0000-0000-0000-000000000002")
CANDIDATE_2_ID = UUID("00000000-0000-0000-0000-000000000006")
EXPERIMENT_ID = UUID("00000000-0000-0000-0000-000000000003")
EVIDENCE_ID = UUID("00000000-0000-0000-0000-000000000004")
REPLACEMENT_EVIDENCE_ID = UUID("00000000-0000-0000-0000-000000000005")


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
) -> EvidenceEnvelope:
    request = EvidenceRequest(
        experiment_id=EXPERIMENT_ID,
        candidate_id=CANDIDATE_ID,
        capability=EvidenceCapability.OBSERVATIONAL,
        adapter_id="local-observer",
        adapter_contract_version=1,
    )
    return EvidenceEnvelope(
        id=evidence_id,
        request=request,
        experiment_id=EXPERIMENT_ID,
        candidate_id=CANDIDATE_ID,
        raw_observation={"result": "observed"},
        validation_status=status,
        corrects_evidence_id=corrects_evidence_id,
        correction_sequence=correction_sequence,
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


def test_evidence_supersession_preserves_the_prior_event_history() -> None:
    initial = _evidence()
    replacement = _evidence(
        evidence_id=REPLACEMENT_EVIDENCE_ID,
        corrects_evidence_id=EVIDENCE_ID,
        correction_sequence=1,
    )
    started = _event(1, EventKind.SESSION_STARTED, _session())
    accepted = _event(
        2,
        EventKind.EVIDENCE_ACCEPTED,
        EvidenceAccepted(session_id=SESSION_ID, evidence=initial),
        started,
    )
    superseded = _event(
        3,
        EventKind.EVIDENCE_SUPERSEDED,
        EvidenceSupersession(
            session_id=SESSION_ID,
            superseded_evidence_id=EVIDENCE_ID,
            replacement=replacement,
        ),
        accepted,
    )
    events = (started, accepted, superseded)

    projection = reduce_events(events)

    assert projection.sequence == 3
    assert events[1].payload.evidence == initial
    assert events[2].payload.replacement.corrects_evidence_id == initial.id


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
