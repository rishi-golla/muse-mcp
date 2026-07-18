from __future__ import annotations

import unicodedata
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import Field, field_validator, model_validator

from muse.models import FrozenModel, RequiredText


class SourceExposure(StrEnum):
    INDEPENDENT = "independent"
    INSPIRED = "inspired"
    SYNTHESIZED = "synthesized"
    ADAPTED = "adapted"


class CandidateSelectionState(StrEnum):
    ACTIVE = "active"
    SELECTED = "selected"
    REJECTED = "rejected"


class ClaimType(StrEnum):
    CAUSAL = "causal"
    FEASIBILITY = "feasibility"
    VALUE = "value"
    CONSTRAINT = "constraint"


class ClaimSupportState(StrEnum):
    UNTESTED = "untested"
    SUPPORTED = "supported"
    CONTRADICTED = "contradicted"
    INCONCLUSIVE = "inconclusive"


class Reducibility(StrEnum):
    EXPERIMENTAL = "experimental"
    OBSERVATIONAL = "observational"
    HUMAN_JUDGMENT = "human_judgment"
    IRREDUCIBLE = "irreducible"


def _identity_key(value: str) -> str:
    return unicodedata.normalize("NFC", value.strip()).casefold()


def _deduplicate_text(values: tuple[str, ...]) -> tuple[str, ...]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        key = _identity_key(value)
        if key not in seen:
            seen.add(key)
            unique.append(value)
    return tuple(unique)


def _deduplicate_uuids(values: tuple[UUID, ...]) -> tuple[UUID, ...]:
    return tuple(dict.fromkeys(values))


class OperationalContract(FrozenModel):
    inputs_required: tuple[RequiredText, ...] = Field(min_length=1)
    outputs_produced: tuple[RequiredText, ...] = Field(min_length=1)
    workflow: tuple[RequiredText, ...] = Field(min_length=1)
    decision_policy: RequiredText
    integration_points: tuple[RequiredText, ...] = Field(min_length=1)
    verification_strategy: RequiredText
    failure_modes: tuple[RequiredText, ...] = Field(min_length=1)

    @field_validator(
        "inputs_required",
        "outputs_produced",
        "workflow",
        "integration_points",
        "failure_modes",
    )
    @classmethod
    def deduplicate_text_members(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return _deduplicate_text(values)


class Claim(FrozenModel):
    id: UUID = Field(default_factory=uuid4)
    candidate_id: UUID
    claim_type: ClaimType
    statement: RequiredText
    first_order_effects: tuple[RequiredText, ...] = Field(min_length=1)
    second_order_effects: tuple[RequiredText, ...] = Field(min_length=1)
    support_state: ClaimSupportState = ClaimSupportState.UNTESTED

    @field_validator("first_order_effects", "second_order_effects")
    @classmethod
    def deduplicate_effects(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return _deduplicate_text(values)


class CandidatePrediction(FrozenModel):
    candidate_id: UUID
    expected: RequiredText


class Uncertainty(FrozenModel):
    id: UUID = Field(default_factory=uuid4)
    session_id: UUID
    description: RequiredText
    candidate_ids: tuple[UUID, ...] = ()
    hard_constraint: RequiredText | None = None
    reducibility: Reducibility

    @field_validator("candidate_ids")
    @classmethod
    def deduplicate_candidate_ids(cls, values: tuple[UUID, ...]) -> tuple[UUID, ...]:
        return _deduplicate_uuids(values)

    @model_validator(mode="after")
    def require_competition_or_constraint(self) -> Uncertainty:
        if len(self.candidate_ids) < 2 and self.hard_constraint is None:
            raise ValueError(
                "uncertainty must reference at least two candidates or one hard constraint"
            )
        return self


class Candidate(FrozenModel):
    id: UUID = Field(default_factory=uuid4)
    session_id: UUID
    generation: int = Field(strict=True, ge=0)
    branch_strategy: RequiredText
    source_exposure: SourceExposure
    title: RequiredText
    mechanism: RequiredText
    problem_framing: RequiredText
    expected_value: RequiredText
    assumptions: tuple[RequiredText, ...] = ()
    operational_contract: OperationalContract
    parent_ids: tuple[UUID, ...] = ()
    claims: tuple[Claim, ...] = ()
    failed_hard_constraints: tuple[RequiredText, ...] = ()
    selection_state: CandidateSelectionState = CandidateSelectionState.ACTIVE

    @field_validator("assumptions", "failed_hard_constraints")
    @classmethod
    def deduplicate_text_members(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return _deduplicate_text(values)

    @field_validator("parent_ids")
    @classmethod
    def deduplicate_parent_ids(cls, values: tuple[UUID, ...]) -> tuple[UUID, ...]:
        return _deduplicate_uuids(values)

    @field_validator("claims")
    @classmethod
    def deduplicate_claims(cls, values: tuple[Claim, ...]) -> tuple[Claim, ...]:
        seen: set[UUID] = set()
        unique: list[Claim] = []
        for claim in values:
            if claim.id not in seen:
                seen.add(claim.id)
                unique.append(claim)
        return tuple(unique)

    @model_validator(mode="after")
    def enforce_decision_graph_invariants(self) -> Candidate:
        if any(claim.candidate_id != self.id for claim in self.claims):
            raise ValueError("all claims must belong to the candidate")
        if (
            self.selection_state is CandidateSelectionState.SELECTED
            and self.failed_hard_constraints
        ):
            raise ValueError("a selected candidate cannot have a failed hard constraint")
        return self
