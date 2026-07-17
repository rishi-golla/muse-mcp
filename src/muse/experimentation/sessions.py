from __future__ import annotations

import unicodedata
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import AwareDatetime, Field, field_validator, model_validator

from muse.models import FrozenModel, RequiredText


class SideEffectClass(StrEnum):
    READ_ONLY_LOCAL = "read_only_local"
    READ_ONLY_EXTERNAL = "read_only_external"
    REVERSIBLE_LOCAL_WRITE = "reversible_local_write"
    EXTERNAL_WRITE = "external_write"
    FINANCIAL = "financial"
    PARTICIPANT_INVOLVING = "participant_involving"
    IRREVERSIBLE = "irreversible"


class SessionStatus(StrEnum):
    ACTIVE = "active"
    AWAITING_EVIDENCE = "awaiting_evidence"
    AWAITING_HUMAN = "awaiting_human"
    CONCLUDED = "concluded"
    STOPPED = "stopped"
    FAILED = "failed"


class ExperimentStatus(StrEnum):
    PROPOSED = "proposed"
    AUTHORIZED = "authorized"
    RUNNING = "running"
    COMPLETED = "completed"
    INCONCLUSIVE = "inconclusive"
    FAILED = "failed"


class ObjectiveDirection(StrEnum):
    MAXIMIZE = "maximize"
    MINIMIZE = "minimize"


class Objective(FrozenModel):
    name: RequiredText
    direction: ObjectiveDirection
    priority: int = Field(strict=True, ge=1)


class SessionBudgets(FrozenModel):
    max_cost_usd: float = Field(strict=True, ge=0.0)
    max_provider_calls: int = Field(strict=True, ge=0)
    max_latency_ms: int = Field(strict=True, ge=0)
    max_human_minutes: int = Field(strict=True, ge=0)


class PrivacyPolicy(FrozenModel):
    mode: RequiredText
    retention_days: int = Field(strict=True, ge=0)


_FORBIDDEN_AUTOMATIC_SIDE_EFFECTS = frozenset(
    {
        SideEffectClass.EXTERNAL_WRITE,
        SideEffectClass.FINANCIAL,
        SideEffectClass.PARTICIPANT_INVOLVING,
        SideEffectClass.IRREVERSIBLE,
    }
)


def _identity_key(value: str) -> str:
    """Use NFC so canonically equivalent text has one comparison identity."""
    return unicodedata.normalize("NFC", value.strip()).casefold()


class AuthorizationPolicy(FrozenModel):
    automatic_side_effects: tuple[SideEffectClass, ...] = ()

    @model_validator(mode="after")
    def reject_forbidden_automatic_side_effects(self) -> AuthorizationPolicy:
        forbidden = _FORBIDDEN_AUTOMATIC_SIDE_EFFECTS.intersection(
            self.automatic_side_effects
        )
        if forbidden:
            raise ValueError("automatic authorization cannot permit high-impact side effects")
        return self


class AuthorizationGrant(FrozenModel):
    id: UUID = Field(default_factory=uuid4)
    session_id: UUID
    experiment_id: UUID
    side_effect: SideEffectClass
    allowed_actions: tuple[RequiredText, ...] = Field(min_length=1)
    expires_at: AwareDatetime
    issuer: RequiredText
    integrity_hash: RequiredText


class AuthorizationDenied(FrozenModel):
    session_id: UUID
    experiment_id: UUID
    side_effect: SideEffectClass
    reason: RequiredText


class CreativeSession(FrozenModel):
    id: UUID = Field(default_factory=uuid4)
    goal: RequiredText
    objectives: tuple[Objective, ...] = Field(min_length=1)
    hard_constraints: tuple[RequiredText, ...] = ()
    privacy: PrivacyPolicy
    authorization: AuthorizationPolicy
    budgets: SessionBudgets
    status: SessionStatus = SessionStatus.ACTIVE
    schema_version: int = Field(strict=True, ge=1)
    policy_version: RequiredText
    sequence: int = Field(default=0, strict=True, ge=0)
    active_candidate_ids: tuple[UUID, ...] = ()
    active_experiment_ids: tuple[UUID, ...] = ()
    memory_snapshot_id: UUID | None = None
    taste_snapshot_id: UUID | None = None

    @model_validator(mode="after")
    def require_unique_objectives_and_constraints(self) -> CreativeSession:
        objective_names = tuple(_identity_key(objective.name) for objective in self.objectives)
        if len(objective_names) != len(set(objective_names)):
            raise ValueError("objective names must be unique")

        objective_priorities = tuple(
            objective.priority for objective in self.objectives
        )
        if len(objective_priorities) != len(set(objective_priorities)):
            raise ValueError("objective priorities must be unique")

        normalized_constraints = tuple(
            _identity_key(constraint) for constraint in self.hard_constraints
        )
        if len(normalized_constraints) != len(set(normalized_constraints)):
            raise ValueError("hard constraints must be unique")
        return self


class ExperimentCandidates(FrozenModel):
    experiment_id: UUID
    candidate_ids: tuple[UUID, ...] = Field(min_length=1)

    @field_validator("candidate_ids")
    @classmethod
    def deduplicate_candidates(cls, values: tuple[UUID, ...]) -> tuple[UUID, ...]:
        return tuple(dict.fromkeys(values))


class ExperimentStatusRecord(FrozenModel):
    experiment_id: UUID
    status: ExperimentStatus


class ClaimOwnership(FrozenModel):
    claim_id: UUID
    candidate_id: UUID


class AuthorizationGrantExperiment(FrozenModel):
    grant_id: UUID
    experiment_id: UUID


class EvidenceHistoryEntry(FrozenModel):
    evidence_id: UUID
    experiment_id: UUID
    candidate_id: UUID
    correction_sequence: int = Field(strict=True, ge=0)
    corrects_evidence_id: UUID | None = None

    @model_validator(mode="after")
    def require_correction_link_for_positive_sequence(self) -> EvidenceHistoryEntry:
        if self.correction_sequence == 0 and self.corrects_evidence_id is not None:
            raise ValueError("initial evidence cannot name a correction target")
        if self.correction_sequence > 0 and self.corrects_evidence_id is None:
            raise ValueError("corrected evidence must name a correction target")
        if self.corrects_evidence_id == self.evidence_id:
            raise ValueError("evidence cannot correct itself")
        return self


class SessionProjection(FrozenModel):
    session_id: UUID
    status: SessionStatus
    sequence: int = Field(strict=True, ge=0)
    candidate_ids: tuple[UUID, ...] = ()
    experiment_ids: tuple[UUID, ...] = ()
    evidence_ids: tuple[UUID, ...] = ()
    superseded_evidence_ids: tuple[UUID, ...] = ()
    claim_ids: tuple[UUID, ...] = ()
    authorization_grant_ids: tuple[UUID, ...] = ()
    budget_reservation_ids: tuple[UUID, ...] = ()
    reconciled_budget_reservation_ids: tuple[UUID, ...] = ()
    terminal_experiment_ids: tuple[UUID, ...] = ()
    experiment_statuses: tuple[ExperimentStatusRecord, ...] = ()
    experiment_candidates: tuple[ExperimentCandidates, ...] = ()
    claim_ownership: tuple[ClaimOwnership, ...] = ()
    authorization_grants: tuple[AuthorizationGrantExperiment, ...] = ()
    evidence_history: tuple[EvidenceHistoryEntry, ...] = ()
    active_candidate_ids: tuple[UUID, ...] = ()
    active_experiment_ids: tuple[UUID, ...] = ()
    memory_snapshot_id: UUID | None = None
    taste_snapshot_id: UUID | None = None

    @model_validator(mode="after")
    def normalize_and_validate_history(self) -> SessionProjection:
        if len(self.superseded_evidence_ids) != len(
            set(self.superseded_evidence_ids)
        ):
            raise ValueError("duplicate superseded evidence is not allowed")

        raw_evidence_by_id: dict[UUID, EvidenceHistoryEntry] = {}
        for entry in self.evidence_history:
            existing = raw_evidence_by_id.get(entry.evidence_id)
            if existing is not None:
                if existing != entry:
                    raise ValueError("evidence history relationship conflicts")
                raise ValueError("duplicate evidence history is not allowed")
            raw_evidence_by_id[entry.evidence_id] = entry

        experiment_status_by_id: dict[UUID, ExperimentStatusRecord] = {}
        for record in self.experiment_statuses:
            existing = experiment_status_by_id.get(record.experiment_id)
            if existing is not None:
                if existing != record:
                    raise ValueError("experiment status records conflict")
                raise ValueError("duplicate experiment status record is not allowed")
            experiment_status_by_id[record.experiment_id] = record

        active_candidate_ids = tuple(dict.fromkeys(self.active_candidate_ids))
        active_experiment_ids = tuple(dict.fromkeys(self.active_experiment_ids))
        candidate_ids = tuple(
            dict.fromkeys((*self.candidate_ids, *active_candidate_ids))
        )
        experiment_ids = tuple(
            dict.fromkeys((*self.experiment_ids, *active_experiment_ids))
        )
        inferred_statuses = tuple(
            ExperimentStatusRecord(
                experiment_id=experiment_id,
                status=ExperimentStatus.PROPOSED,
            )
            for experiment_id in active_experiment_ids
            if experiment_id not in experiment_status_by_id
        )
        experiment_statuses = (*self.experiment_statuses, *inferred_statuses)
        experiment_status_by_id.update(
            (record.experiment_id, record) for record in inferred_statuses
        )
        object.__setattr__(self, "experiment_statuses", experiment_statuses)
        for field, values in (
            ("candidate_ids", candidate_ids),
            ("experiment_ids", experiment_ids),
            ("evidence_ids", tuple(dict.fromkeys(self.evidence_ids))),
            (
                "superseded_evidence_ids",
                tuple(dict.fromkeys(self.superseded_evidence_ids)),
            ),
            ("claim_ids", tuple(dict.fromkeys(self.claim_ids))),
            (
                "authorization_grant_ids",
                tuple(dict.fromkeys(self.authorization_grant_ids)),
            ),
            (
                "budget_reservation_ids",
                tuple(dict.fromkeys(self.budget_reservation_ids)),
            ),
            (
                "reconciled_budget_reservation_ids",
                tuple(dict.fromkeys(self.reconciled_budget_reservation_ids)),
            ),
            (
                "terminal_experiment_ids",
                tuple(dict.fromkeys(self.terminal_experiment_ids)),
            ),
            ("active_candidate_ids", active_candidate_ids),
            ("active_experiment_ids", active_experiment_ids),
        ):
            object.__setattr__(self, field, values)

        experiment_candidates_by_id: dict[UUID, ExperimentCandidates] = {}
        normalized_experiment_candidates: list[ExperimentCandidates] = []
        for relationship in self.experiment_candidates:
            existing = experiment_candidates_by_id.get(relationship.experiment_id)
            if existing is not None and existing != relationship:
                raise ValueError("experiment candidate relationship conflicts")
            if existing is None:
                experiment_candidates_by_id[relationship.experiment_id] = relationship
                normalized_experiment_candidates.append(relationship)

        claim_ownership_by_id: dict[UUID, ClaimOwnership] = {}
        normalized_claim_ownership: list[ClaimOwnership] = []
        for relationship in self.claim_ownership:
            existing = claim_ownership_by_id.get(relationship.claim_id)
            if existing is not None and existing != relationship:
                raise ValueError("claim ownership relationship conflicts")
            if existing is None:
                claim_ownership_by_id[relationship.claim_id] = relationship
                normalized_claim_ownership.append(relationship)

        grants_by_id: dict[UUID, AuthorizationGrantExperiment] = {}
        normalized_grants: list[AuthorizationGrantExperiment] = []
        for relationship in self.authorization_grants:
            existing = grants_by_id.get(relationship.grant_id)
            if existing is not None and existing != relationship:
                raise ValueError("authorization grant relationship conflicts")
            if existing is None:
                grants_by_id[relationship.grant_id] = relationship
                normalized_grants.append(relationship)

        evidence_by_id: dict[UUID, EvidenceHistoryEntry] = {}
        normalized_evidence: list[EvidenceHistoryEntry] = []
        for entry in self.evidence_history:
            existing = evidence_by_id.get(entry.evidence_id)
            if existing is not None and existing != entry:
                raise ValueError("evidence history relationship conflicts")
            if existing is None:
                evidence_by_id[entry.evidence_id] = entry
                normalized_evidence.append(entry)

        object.__setattr__(
            self, "experiment_candidates", tuple(normalized_experiment_candidates)
        )
        object.__setattr__(self, "claim_ownership", tuple(normalized_claim_ownership))
        object.__setattr__(self, "authorization_grants", tuple(normalized_grants))
        object.__setattr__(self, "evidence_history", tuple(normalized_evidence))

        if not set(self.terminal_experiment_ids).issubset(self.experiment_ids):
            raise ValueError("terminal experiments must be known experiments")
        if set(self.terminal_experiment_ids).intersection(self.active_experiment_ids):
            raise ValueError("terminal experiments cannot remain active")
        for record in self.experiment_statuses:
            if record.experiment_id not in self.experiment_ids:
                raise ValueError("experiment status references an unknown experiment")
            is_active = record.experiment_id in self.active_experiment_ids
            is_terminal = record.experiment_id in self.terminal_experiment_ids
            if record.status in {
                ExperimentStatus.COMPLETED,
                ExperimentStatus.INCONCLUSIVE,
                ExperimentStatus.FAILED,
            }:
                if is_active or not is_terminal:
                    raise ValueError(
                        "terminal experiment status must match terminal experiment IDs"
                    )
            elif not is_active or is_terminal:
                raise ValueError(
                    "nonterminal experiment status must match active experiment IDs"
                )
        if set(self.active_experiment_ids).difference(experiment_status_by_id):
            raise ValueError("active experiments must have an experiment status")
        if set(self.terminal_experiment_ids).difference(experiment_status_by_id):
            raise ValueError("terminal experiments must have an experiment status")
        if set(self.experiment_ids).difference(experiment_status_by_id):
            raise ValueError("known experiments must have an experiment status")
        if not set(self.superseded_evidence_ids).issubset(self.evidence_ids):
            raise ValueError("superseded evidence must be recorded evidence")
        if not set(self.reconciled_budget_reservation_ids).issubset(
            self.budget_reservation_ids
        ):
            raise ValueError("reconciled reservations must be recorded reservations")

        for relationship in self.experiment_candidates:
            if relationship.experiment_id not in self.experiment_ids:
                raise ValueError("experiment relationship references an unknown experiment")
            if not set(relationship.candidate_ids).issubset(self.candidate_ids):
                raise ValueError("experiment relationship references an unknown candidate")
        for relationship in self.claim_ownership:
            if relationship.claim_id not in self.claim_ids:
                raise ValueError("claim ownership references an unknown claim")
            if relationship.candidate_id not in self.candidate_ids:
                raise ValueError("claim ownership references an unknown candidate")
        for relationship in self.authorization_grants:
            if relationship.grant_id not in self.authorization_grant_ids:
                raise ValueError("grant relationship references an unknown grant")
            if relationship.experiment_id not in self.experiment_ids:
                raise ValueError("grant relationship references an unknown experiment")
        authorized_experiment_ids = {
            relationship.experiment_id for relationship in self.authorization_grants
        }
        for record in self.experiment_statuses:
            if (
                record.status is ExperimentStatus.PROPOSED
                and record.experiment_id in authorized_experiment_ids
            ):
                raise ValueError(
                    "proposed experiment status cannot have authorization history"
                )
            if (
                record.status is not ExperimentStatus.PROPOSED
                and record.experiment_id not in authorized_experiment_ids
            ):
                raise ValueError(
                    "post-proposal experiment status requires authorization history"
                )
        evidence_positions = {
            entry.evidence_id: position
            for position, entry in enumerate(self.evidence_history)
        }
        correction_children_by_target: dict[UUID, list[EvidenceHistoryEntry]] = {}
        correction_targets_in_history_order: list[UUID] = []
        for position, entry in enumerate(self.evidence_history):
            if entry.evidence_id not in self.evidence_ids:
                raise ValueError("evidence history references unknown evidence")
            if entry.experiment_id not in self.experiment_ids:
                raise ValueError("evidence history references an unknown experiment")
            if entry.candidate_id not in self.candidate_ids:
                raise ValueError("evidence history references an unknown candidate")
            experiment_relationship = experiment_candidates_by_id.get(
                entry.experiment_id
            )
            if (
                experiment_relationship is not None
                and entry.candidate_id not in experiment_relationship.candidate_ids
            ):
                raise ValueError("evidence candidate does not belong to its experiment")
            if entry.corrects_evidence_id is not None:
                target = evidence_by_id.get(entry.corrects_evidence_id)
                if target is None:
                    raise ValueError("evidence correction target must have history")
                if evidence_positions[target.evidence_id] >= position:
                    raise ValueError("evidence correction must appear after its target")
                if entry.correction_sequence != target.correction_sequence + 1:
                    raise ValueError("evidence correction sequence must follow its target")
                if (
                    entry.experiment_id != target.experiment_id
                    or entry.candidate_id != target.candidate_id
                ):
                    raise ValueError("evidence correction must preserve graph identity")
                correction_children_by_target.setdefault(target.evidence_id, []).append(
                    entry
                )
                correction_targets_in_history_order.append(target.evidence_id)

        for evidence_id in self.superseded_evidence_ids:
            if evidence_id not in correction_children_by_target:
                raise ValueError(
                    "superseded evidence must have exactly one correction child"
                )
        for children in correction_children_by_target.values():
            if len(children) > 1:
                raise ValueError(
                    "evidence target cannot have multiple correction children"
                )
        for evidence_id in correction_targets_in_history_order:
            if evidence_id not in self.superseded_evidence_ids:
                raise ValueError("evidence correction target must be superseded")
        if tuple(correction_targets_in_history_order) != self.superseded_evidence_ids:
            raise ValueError(
                "supersession order must match correction history order"
            )

        return self
