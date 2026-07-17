from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from enum import StrEnum
from typing import Self
from uuid import UUID, uuid4

from pydantic import AwareDatetime, Field, field_validator, model_validator

from muse.experimentation.candidates import Candidate, CandidateSelectionState
from muse.experimentation.evidence import (
    BeliefUpdate,
    EvidenceEnvelope,
    EvidenceValidationStatus,
    ExperimentSpec,
    ExperimentStatus,
    SelectionDecision,
)
from muse.experimentation.sessions import (
    AuthorizationGrant,
    CreativeSession,
    SessionProjection,
    SessionStatus,
)
from muse.models import FrozenModel, RequiredText


class EventKind(StrEnum):
    SESSION_STARTED = "session_started"
    SESSION_STATUS_CHANGED = "session_status_changed"
    SESSION_RESUMED = "session_resumed"
    CANDIDATE_ADDED = "candidate_added"
    CANDIDATE_UPDATED = "candidate_updated"
    EXPERIMENT_PROPOSED = "experiment_proposed"
    EXPERIMENT_AUTHORIZED = "experiment_authorized"
    EXPERIMENT_STATUS_CHANGED = "experiment_status_changed"
    EVIDENCE_ACCEPTED = "evidence_accepted"
    EVIDENCE_REJECTED = "evidence_rejected"
    EVIDENCE_SUPERSEDED = "evidence_superseded"
    BELIEF_UPDATED = "belief_updated"
    SELECTION_DECIDED = "selection_decided"
    MEMORY_WRITTEN = "memory_written"
    TASTE_WRITTEN = "taste_written"
    BUDGET_RESERVED = "budget_reserved"
    BUDGET_RECONCILED = "budget_reconciled"
    SESSION_STOPPED = "session_stopped"
    SESSION_FAILED = "session_failed"


class SessionStatusChange(FrozenModel):
    session_id: UUID
    status: SessionStatus
    reason: RequiredText


class SessionResume(FrozenModel):
    session_id: UUID
    reason: RequiredText


class ExperimentStatusChange(FrozenModel):
    session_id: UUID
    experiment_id: UUID
    status: ExperimentStatus


class EvidenceAccepted(FrozenModel):
    session_id: UUID
    evidence: EvidenceEnvelope

    @model_validator(mode="after")
    def require_valid_evidence(self) -> EvidenceAccepted:
        if self.evidence.validation_status is not EvidenceValidationStatus.VALID:
            raise ValueError("accepted payload requires valid evidence")
        return self


class EvidenceRejected(FrozenModel):
    session_id: UUID
    evidence: EvidenceEnvelope
    reason: RequiredText

    @model_validator(mode="after")
    def require_invalid_evidence(self) -> EvidenceRejected:
        if self.evidence.validation_status is not EvidenceValidationStatus.INVALID:
            raise ValueError("rejected payload requires invalid evidence")
        return self


class EvidenceSupersession(FrozenModel):
    session_id: UUID
    superseded_evidence_id: UUID
    replacement: EvidenceEnvelope

    @model_validator(mode="after")
    def require_linked_valid_correction(self) -> EvidenceSupersession:
        if self.replacement.corrects_evidence_id != self.superseded_evidence_id:
            raise ValueError("replacement must name the superseded evidence as correction target")
        if self.replacement.validation_status is not EvidenceValidationStatus.VALID:
            raise ValueError("replacement must contain valid evidence")
        return self


class SnapshotWrite(FrozenModel):
    session_id: UUID
    snapshot_id: UUID


class BudgetReservation(FrozenModel):
    session_id: UUID
    reservation_id: UUID
    cost_usd: float = Field(strict=True, ge=0.0)
    calls: int = Field(strict=True, ge=0)
    latency_ms: int = Field(strict=True, ge=0)
    human_minutes: int = Field(strict=True, ge=0)


class BudgetReconciliation(FrozenModel):
    session_id: UUID
    reservation_id: UUID
    actual_cost_usd: float = Field(strict=True, ge=0.0)
    actual_calls: int = Field(strict=True, ge=0)
    actual_latency_ms: int = Field(strict=True, ge=0)
    actual_human_minutes: int = Field(strict=True, ge=0)


class SessionTermination(FrozenModel):
    session_id: UUID
    reason: RequiredText


EventPayload = (
    CreativeSession
    | SessionStatusChange
    | SessionResume
    | Candidate
    | ExperimentSpec
    | AuthorizationGrant
    | ExperimentStatusChange
    | EvidenceAccepted
    | EvidenceRejected
    | EvidenceSupersession
    | BeliefUpdate
    | SelectionDecision
    | SnapshotWrite
    | BudgetReservation
    | BudgetReconciliation
    | SessionTermination
)


_PAYLOAD_TYPES: dict[EventKind, type[FrozenModel]] = {
    EventKind.SESSION_STARTED: CreativeSession,
    EventKind.SESSION_STATUS_CHANGED: SessionStatusChange,
    EventKind.SESSION_RESUMED: SessionResume,
    EventKind.CANDIDATE_ADDED: Candidate,
    EventKind.CANDIDATE_UPDATED: Candidate,
    EventKind.EXPERIMENT_PROPOSED: ExperimentSpec,
    EventKind.EXPERIMENT_AUTHORIZED: AuthorizationGrant,
    EventKind.EXPERIMENT_STATUS_CHANGED: ExperimentStatusChange,
    EventKind.EVIDENCE_ACCEPTED: EvidenceAccepted,
    EventKind.EVIDENCE_REJECTED: EvidenceRejected,
    EventKind.EVIDENCE_SUPERSEDED: EvidenceSupersession,
    EventKind.BELIEF_UPDATED: BeliefUpdate,
    EventKind.SELECTION_DECIDED: SelectionDecision,
    EventKind.MEMORY_WRITTEN: SnapshotWrite,
    EventKind.TASTE_WRITTEN: SnapshotWrite,
    EventKind.BUDGET_RESERVED: BudgetReservation,
    EventKind.BUDGET_RECONCILED: BudgetReconciliation,
    EventKind.SESSION_STOPPED: SessionTermination,
    EventKind.SESSION_FAILED: SessionTermination,
}


class PendingEvent(FrozenModel):
    kind: EventKind
    payload: EventPayload
    idempotency_key: RequiredText

    @model_validator(mode="before")
    @classmethod
    def validate_payload_for_kind(cls, value: object) -> object:
        if not isinstance(value, Mapping):
            return value
        values = dict(value)
        try:
            kind = EventKind(values.get("kind"))
        except (TypeError, ValueError):
            return values
        if "payload" not in values:
            return values
        payload_type = _PAYLOAD_TYPES[kind]
        try:
            values["payload"] = payload_type.model_validate(values["payload"])
        except (TypeError, ValueError) as error:
            raise ValueError(f"invalid payload for {kind.value}") from error
        return values

    @model_validator(mode="after")
    def require_exact_payload_type(self) -> PendingEvent:
        payload_type = _PAYLOAD_TYPES[self.kind]
        if type(self.payload) is not payload_type:
            raise ValueError(f"invalid payload for {self.kind.value}")
        return self


_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
_EVENT_SCHEMA_VERSION = 1


class SessionEvent(PendingEvent):
    session_id: UUID
    sequence: int = Field(strict=True, ge=1)
    timestamp: AwareDatetime
    schema_version: int = Field(default=_EVENT_SCHEMA_VERSION, strict=True, ge=1)
    event_id: UUID
    previous_event_hash: str | None
    event_hash: str

    @field_validator("timestamp")
    @classmethod
    def require_utc_timestamp(cls, value: datetime) -> datetime:
        if value.utcoffset() is None or value.utcoffset().total_seconds() != 0:
            raise ValueError("event timestamp must be UTC")
        return value

    @field_validator("previous_event_hash", "event_hash")
    @classmethod
    def require_sha256_hash(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.lower()
        if _SHA256_PATTERN.fullmatch(normalized) is None:
            raise ValueError("event hashes must be SHA-256 hex digests")
        return normalized

    @model_validator(mode="after")
    def verify_event_hash(self) -> SessionEvent:
        _verify_event_hash(self)
        return self

    @classmethod
    def create(
        cls,
        session_id: UUID,
        sequence: int,
        kind: EventKind,
        payload: EventPayload,
        *,
        idempotency_key: str | None = None,
        timestamp: datetime | None = None,
        schema_version: int = _EVENT_SCHEMA_VERSION,
        event_id: UUID | None = None,
        previous_event_hash: str | None = None,
    ) -> Self:
        pending = PendingEvent(
            kind=kind,
            payload=payload,
            idempotency_key=(
                f"{session_id}:{sequence}"
                if idempotency_key is None
                else idempotency_key
            ),
        )
        created_at = timestamp if timestamp is not None else datetime.now(UTC)
        created_event_id = event_id if event_id is not None else uuid4()
        normalized_previous = (
            None if previous_event_hash is None else previous_event_hash.lower()
        )
        event_hash = _calculate_event_hash(
            session_id=session_id,
            sequence=sequence,
            kind=pending.kind,
            payload=pending.payload,
            idempotency_key=pending.idempotency_key,
            timestamp=created_at,
            schema_version=schema_version,
            event_id=created_event_id,
            previous_event_hash=normalized_previous,
        )
        return cls(
            kind=pending.kind,
            payload=pending.payload,
            idempotency_key=pending.idempotency_key,
            session_id=session_id,
            sequence=sequence,
            timestamp=created_at,
            schema_version=schema_version,
            event_id=created_event_id,
            previous_event_hash=normalized_previous,
            event_hash=event_hash,
        )


def _calculate_event_hash(
    *,
    session_id: UUID,
    sequence: int,
    kind: EventKind,
    payload: EventPayload,
    idempotency_key: str,
    timestamp: datetime,
    schema_version: int,
    event_id: UUID,
    previous_event_hash: str | None,
) -> str:
    durable_fields = {
        "event_id": str(event_id),
        "idempotency_key": idempotency_key,
        "kind": kind.value,
        "payload": payload.model_dump(mode="json"),
        "previous_event_hash": previous_event_hash,
        "schema_version": schema_version,
        "sequence": sequence,
        "session_id": str(session_id),
        "timestamp": _canonical_timestamp(timestamp),
    }
    canonical = json.dumps(
        durable_fields,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _canonical_timestamp(value: datetime) -> str:
    if value.utcoffset() is None:
        return value.isoformat()
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _verify_event_hash(event: SessionEvent) -> None:
    expected = _calculate_event_hash(
        session_id=event.session_id,
        sequence=event.sequence,
        kind=event.kind,
        payload=event.payload,
        idempotency_key=event.idempotency_key,
        timestamp=event.timestamp,
        schema_version=event.schema_version,
        event_id=event.event_id,
        previous_event_hash=event.previous_event_hash,
    )
    if event.event_hash != expected:
        raise ValueError("event hash does not match canonical durable fields")


_TERMINAL_SESSION_STATUSES = frozenset(
    {SessionStatus.CONCLUDED, SessionStatus.STOPPED, SessionStatus.FAILED}
)
_TERMINAL_EXPERIMENT_STATUSES = frozenset(
    {ExperimentStatus.COMPLETED, ExperimentStatus.INCONCLUSIVE, ExperimentStatus.FAILED}
)


def reduce_events(events: Iterable[SessionEvent]) -> SessionProjection:
    projection: SessionProjection | None = None
    previous_event: SessionEvent | None = None
    expected_session_id: UUID | None = None

    for event in events:
        if event.schema_version != _EVENT_SCHEMA_VERSION:
            raise ValueError(f"unknown event schema version: {event.schema_version}")
        _verify_event_hash(event)
        expected_sequence = 1 if previous_event is None else previous_event.sequence + 1
        if event.sequence != expected_sequence:
            raise ValueError(
                f"event sequence must be contiguous from 1; expected {expected_sequence}"
            )
        if previous_event is None:
            if event.previous_event_hash is not None:
                raise ValueError("the first event cannot have a previous event hash")
            expected_session_id = event.session_id
        elif event.previous_event_hash != previous_event.event_hash:
            raise ValueError("previous event hash does not match the preceding event")
        if event.session_id != expected_session_id:
            raise ValueError("event stream contains mixed session IDs")
        if _payload_session_id(event.payload) != event.session_id:
            raise ValueError("event payload session ID does not match the event envelope")

        projection = reduce_session(projection, event)
        previous_event = event

    if projection is None:
        raise ValueError("event stream must contain at least one event")
    return projection


def reduce_session(
    projection: SessionProjection | None,
    event: SessionEvent,
) -> SessionProjection:
    if event.schema_version != _EVENT_SCHEMA_VERSION:
        raise ValueError(f"unknown event schema version: {event.schema_version}")
    _verify_event_hash(event)
    if _payload_session_id(event.payload) != event.session_id:
        raise ValueError("event payload session ID does not match the event envelope")
    if projection is not None and event.session_id != projection.session_id:
        raise ValueError("event stream contains mixed session IDs")

    if projection is None:
        if event.sequence != 1:
            raise ValueError("the first event must have sequence 1")
        if event.previous_event_hash is not None:
            raise ValueError("the first event cannot have a previous event hash")
        if event.kind is not EventKind.SESSION_STARTED:
            raise ValueError("the first event must start the session")
        session = event.payload
        if type(session) is not CreativeSession:
            raise ValueError("session start requires a creative session payload")
        if session.sequence != 0:
            raise ValueError("a newly started session must begin at sequence zero")
        if session.status is not SessionStatus.ACTIVE:
            raise ValueError("a newly started session must be active")
        return SessionProjection(
            session_id=session.id,
            status=session.status,
            sequence=event.sequence,
            candidate_ids=session.active_candidate_ids,
            experiment_ids=session.active_experiment_ids,
            active_candidate_ids=session.active_candidate_ids,
            active_experiment_ids=session.active_experiment_ids,
            memory_snapshot_id=session.memory_snapshot_id,
            taste_snapshot_id=session.taste_snapshot_id,
        )

    if event.sequence != projection.sequence + 1:
        raise ValueError("event sequence must advance exactly once")
    if event.kind is EventKind.SESSION_STARTED:
        raise ValueError("a session can only be started once")

    if projection.status in _TERMINAL_SESSION_STATUSES:
        if event.kind is not EventKind.SESSION_RESUMED:
            raise ValueError("a terminal session requires an explicit resume event")
        return projection.model_copy(
            update={"status": SessionStatus.ACTIVE, "sequence": event.sequence}
        )
    if event.kind is EventKind.SESSION_RESUMED:
        raise ValueError("a non-terminal session is not terminal and cannot be resumed")

    updates: dict[str, object] = {"sequence": event.sequence}
    if event.kind is EventKind.SESSION_STATUS_CHANGED:
        payload = event.payload
        if type(payload) is not SessionStatusChange:
            raise ValueError("invalid session status payload")
        if payload.status in {SessionStatus.STOPPED, SessionStatus.FAILED}:
            raise ValueError("stopped and failed states require explicit terminal events")
        updates["status"] = payload.status
    elif event.kind is EventKind.SESSION_STOPPED:
        updates["status"] = SessionStatus.STOPPED
    elif event.kind is EventKind.SESSION_FAILED:
        updates["status"] = SessionStatus.FAILED
    elif event.kind in {EventKind.CANDIDATE_ADDED, EventKind.CANDIDATE_UPDATED}:
        candidate = event.payload
        if type(candidate) is not Candidate:
            raise ValueError("invalid candidate payload")
        unknown_parent_ids = set(candidate.parent_ids).difference(projection.candidate_ids)
        if unknown_parent_ids:
            raise ValueError("candidate references an unknown parent")
        active_ids = projection.active_candidate_ids
        if event.kind is EventKind.CANDIDATE_ADDED:
            if candidate.selection_state is not CandidateSelectionState.ACTIVE:
                raise ValueError("a newly added candidate must be active")
            if candidate.id in projection.candidate_ids:
                raise ValueError("candidate has already been added")
            updates["candidate_ids"] = (*projection.candidate_ids, candidate.id)
            updates["active_candidate_ids"] = (*active_ids, candidate.id)
        elif candidate.id not in projection.candidate_ids:
            raise ValueError("cannot update an unknown candidate")
        elif candidate.selection_state is CandidateSelectionState.ACTIVE:
            if candidate.id not in active_ids:
                updates["active_candidate_ids"] = (*active_ids, candidate.id)
        else:
            updates["active_candidate_ids"] = tuple(
                candidate_id for candidate_id in active_ids if candidate_id != candidate.id
            )
        new_claim_ids = tuple(
            claim.id for claim in candidate.claims if claim.id not in projection.claim_ids
        )
        if new_claim_ids:
            updates["claim_ids"] = (*projection.claim_ids, *new_claim_ids)
    elif event.kind is EventKind.EXPERIMENT_PROPOSED:
        experiment = event.payload
        if type(experiment) is not ExperimentSpec:
            raise ValueError("invalid experiment payload")
        if experiment.status is not ExperimentStatus.PROPOSED:
            raise ValueError("a proposed experiment must have proposed status")
        unknown_candidate_ids = set(experiment.candidate_ids).difference(
            projection.candidate_ids
        )
        if unknown_candidate_ids:
            raise ValueError("experiment references an unknown candidate")
        if experiment.id in projection.experiment_ids:
            raise ValueError("experiment has already been proposed")
        updates["experiment_ids"] = (*projection.experiment_ids, experiment.id)
        updates["active_experiment_ids"] = (
            *projection.active_experiment_ids,
            experiment.id,
        )
    elif event.kind is EventKind.EXPERIMENT_STATUS_CHANGED:
        status_change = event.payload
        if type(status_change) is not ExperimentStatusChange:
            raise ValueError("invalid experiment status payload")
        if status_change.experiment_id not in projection.experiment_ids:
            raise ValueError("cannot change status for an unknown experiment")
        active_ids = projection.active_experiment_ids
        if status_change.status in _TERMINAL_EXPERIMENT_STATUSES:
            updates["active_experiment_ids"] = tuple(
                experiment_id
                for experiment_id in active_ids
                if experiment_id != status_change.experiment_id
            )
        elif status_change.experiment_id not in active_ids:
            updates["active_experiment_ids"] = (*active_ids, status_change.experiment_id)
    elif event.kind is EventKind.EXPERIMENT_AUTHORIZED:
        grant = event.payload
        if type(grant) is not AuthorizationGrant:
            raise ValueError("invalid experiment authorization payload")
        if grant.experiment_id not in projection.experiment_ids:
            raise ValueError("cannot authorize an unknown experiment")
        if grant.id in projection.authorization_grant_ids:
            raise ValueError("authorization grant identity has already been recorded")
        updates["authorization_grant_ids"] = (
            *projection.authorization_grant_ids,
            grant.id,
        )
    elif event.kind in {EventKind.EVIDENCE_ACCEPTED, EventKind.EVIDENCE_REJECTED}:
        payload = event.payload
        if type(payload) in {EvidenceAccepted, EvidenceRejected}:
            evidence = payload.evidence
        else:
            raise ValueError("invalid evidence payload")
        _require_known_evidence_graph(projection, evidence)
        if (
            event.kind is EventKind.EVIDENCE_ACCEPTED
            and evidence.corrects_evidence_id is not None
        ):
            raise ValueError("accepted correction requires an explicit supersession event")
        if evidence.id in projection.evidence_ids:
            raise ValueError("evidence identity has already been recorded")
        updates["evidence_ids"] = (*projection.evidence_ids, evidence.id)
    elif event.kind is EventKind.EVIDENCE_SUPERSEDED:
        supersession = event.payload
        if type(supersession) is not EvidenceSupersession:
            raise ValueError("invalid evidence supersession payload")
        replacement = supersession.replacement
        _require_known_evidence_graph(projection, replacement)
        if supersession.superseded_evidence_id not in projection.evidence_ids:
            raise ValueError("cannot supersede unknown evidence")
        if supersession.superseded_evidence_id in projection.superseded_evidence_ids:
            raise ValueError("evidence has already been superseded")
        if replacement.id in projection.evidence_ids:
            raise ValueError("replacement must have a new evidence identity")
        updates["evidence_ids"] = (*projection.evidence_ids, replacement.id)
        updates["superseded_evidence_ids"] = (
            *projection.superseded_evidence_ids,
            supersession.superseded_evidence_id,
        )
    elif event.kind is EventKind.BELIEF_UPDATED:
        belief = event.payload
        if type(belief) is not BeliefUpdate:
            raise ValueError("invalid belief update payload")
        if belief.evidence_id not in projection.evidence_ids:
            raise ValueError("belief update references unknown evidence")
        if belief.claim_id not in projection.claim_ids:
            raise ValueError("belief update references an unknown claim")
    elif event.kind is EventKind.SELECTION_DECIDED:
        selection = event.payload
        if type(selection) is not SelectionDecision:
            raise ValueError("invalid selection decision payload")
        if selection.experiment_id not in projection.experiment_ids:
            raise ValueError("selection references an unknown experiment")
        if set(selection.considered_candidate_ids).difference(projection.candidate_ids):
            raise ValueError("selection references an unknown candidate")
        if set(selection.supporting_evidence_ids).difference(projection.evidence_ids):
            raise ValueError("selection references unknown evidence")
    elif event.kind is EventKind.BUDGET_RESERVED:
        reservation = event.payload
        if type(reservation) is not BudgetReservation:
            raise ValueError("invalid budget reservation payload")
        if reservation.reservation_id in projection.budget_reservation_ids:
            raise ValueError("budget reservation identity has already been recorded")
        updates["budget_reservation_ids"] = (
            *projection.budget_reservation_ids,
            reservation.reservation_id,
        )
    elif event.kind is EventKind.BUDGET_RECONCILED:
        reconciliation = event.payload
        if type(reconciliation) is not BudgetReconciliation:
            raise ValueError("invalid budget reconciliation payload")
        if reconciliation.reservation_id not in projection.budget_reservation_ids:
            raise ValueError("cannot reconcile an unknown budget reservation")
        if reconciliation.reservation_id in projection.reconciled_budget_reservation_ids:
            raise ValueError("budget reservation has already been reconciled")
        updates["reconciled_budget_reservation_ids"] = (
            *projection.reconciled_budget_reservation_ids,
            reconciliation.reservation_id,
        )
    elif event.kind is EventKind.MEMORY_WRITTEN:
        snapshot = event.payload
        if type(snapshot) is not SnapshotWrite:
            raise ValueError("invalid memory snapshot payload")
        updates["memory_snapshot_id"] = snapshot.snapshot_id
    elif event.kind is EventKind.TASTE_WRITTEN:
        snapshot = event.payload
        if type(snapshot) is not SnapshotWrite:
            raise ValueError("invalid taste snapshot payload")
        updates["taste_snapshot_id"] = snapshot.snapshot_id

    return projection.model_copy(update=updates)


def _payload_session_id(payload: EventPayload) -> UUID:
    if type(payload) is CreativeSession:
        return payload.id
    return payload.session_id


def _require_known_evidence_graph(
    projection: SessionProjection,
    evidence: EvidenceEnvelope,
) -> None:
    if evidence.candidate_id not in projection.candidate_ids:
        raise ValueError("evidence references an unknown candidate")
    if evidence.experiment_id not in projection.experiment_ids:
        raise ValueError("evidence references an unknown experiment")
    if set(evidence.request.authorization_grant_ids).difference(
        projection.authorization_grant_ids
    ):
        raise ValueError("evidence references an unknown authorization grant")
