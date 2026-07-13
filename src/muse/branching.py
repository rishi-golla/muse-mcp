from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class BranchStrategy(StrEnum):
    CONSTRAINT_INVERSION = "constraint_inversion"
    FAILURE_FIRST = "failure_first"
    CROSS_DOMAIN_TRANSFER = "cross_domain_transfer"
    SYSTEMS_EFFECTS = "systems_effects"
    MINIMAL_MECHANISM = "minimal_mechanism"
    USER_CENTERED = "user_centered"


class BranchDirective(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    branch_index: int = Field(strict=True, ge=0)
    strategy: BranchStrategy
    instruction: str

    @field_validator("instruction")
    @classmethod
    def reject_blank_instruction(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("branch instruction must not be blank")
        return value


_STRATEGY_INSTRUCTIONS: dict[BranchStrategy, str] = {
    BranchStrategy.CONSTRAINT_INVERSION: (
        "Invert a core constraint or assumption and derive a mechanism that works under the "
        "reversed condition."
    ),
    BranchStrategy.FAILURE_FIRST: (
        "Start from a plausible failure mode, then design sensing, containment, and recovery "
        "into the mechanism."
    ),
    BranchStrategy.CROSS_DOMAIN_TRANSFER: (
        "Transfer a structural mechanism from a distant domain, mapping roles, signals, and "
        "feedback rather than surface language."
    ),
    BranchStrategy.SYSTEMS_EFFECTS: (
        "Model first- and second-order effects, then use feedback loops or safeguards to shape "
        "the system outcome."
    ),
    BranchStrategy.MINIMAL_MECHANISM: (
        "Remove everything except the irreducible mechanism; justify how the smallest viable "
        "structure still creates value."
    ),
    BranchStrategy.USER_CENTERED: (
        "Start from a user's concrete moment of friction, agency, and feedback, then make the "
        "mechanism adapt to that experience."
    ),
}


def branch_directives(seed_count: int) -> tuple[BranchDirective, ...]:
    if isinstance(seed_count, bool) or not isinstance(seed_count, int):
        raise TypeError("seed_count must be an integer")
    if seed_count < 0:
        raise ValueError("seed_count must not be negative")

    strategies = tuple(BranchStrategy)
    return tuple(
        BranchDirective(
            branch_index=index,
            strategy=strategy,
            instruction=_STRATEGY_INSTRUCTIONS[strategy],
        )
        for index in range(seed_count)
        for strategy in (strategies[index % len(strategies)],)
    )
