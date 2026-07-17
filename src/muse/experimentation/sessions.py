from __future__ import annotations

import unicodedata
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import AwareDatetime, Field, model_validator

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
    active_candidate_ids: tuple[UUID, ...] = ()
    active_experiment_ids: tuple[UUID, ...] = ()
    memory_snapshot_id: UUID | None = None
    taste_snapshot_id: UUID | None = None

    @model_validator(mode="after")
    def retain_legacy_active_entity_history(self) -> SessionProjection:
        object.__setattr__(
            self,
            "candidate_ids",
            tuple(dict.fromkeys((*self.candidate_ids, *self.active_candidate_ids))),
        )
        object.__setattr__(
            self,
            "experiment_ids",
            tuple(dict.fromkeys((*self.experiment_ids, *self.active_experiment_ids))),
        )
        return self
