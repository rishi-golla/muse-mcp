from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

Score = Annotated[float, Field(ge=0.0, le=1.0)]


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class InspirationKind(StrEnum):
    INDEPENDENT = "independent"
    INSPIRED = "inspired"
    SYNTHESIZED = "synthesized"
    ADAPTED = "adapted"


class TaskContext(FrozenModel):
    goal: str = Field(min_length=1)
    audience: str | None = None
    constraints: tuple[str, ...] = ()
    preferences: tuple[str, ...] = ()
    risk_tolerance: Score = 0.5

    @model_validator(mode="after")
    def reject_blank_goal(self) -> TaskContext:
        if not self.goal.strip():
            raise ValueError("goal must not be blank")
        return self


class EvaluationScores(FrozenModel):
    originality: Score
    usefulness: Score
    coherence: Score
    feasibility: Score
    user_fit: Score


class IdeaGenome(FrozenModel):
    id: UUID = Field(default_factory=uuid4)
    generation: int = Field(ge=0)
    title: str = Field(min_length=1)
    core_mechanism: str = Field(min_length=1)
    problem_framing: str = Field(min_length=1)
    assumptions_challenged: tuple[str, ...] = ()
    task_value: str = Field(min_length=1)
    distinguishing_features: tuple[str, ...] = ()
    inspiration_principles: tuple[str, ...] = ()
    source_urls: tuple[str, ...] = ()
    first_order_effects: tuple[str, ...] = ()
    second_order_effects: tuple[str, ...] = ()
    feasibility_assumptions: tuple[str, ...] = ()
    uncertainties: tuple[str, ...] = ()
    weaknesses: tuple[str, ...] = ()
    parent_ids: tuple[UUID, ...] = ()
    transformations: tuple[str, ...] = ()
    inspiration_kind: InspirationKind = InspirationKind.INDEPENDENT
    scores: EvaluationScores | None = None
    branch_cost_usd: float = Field(default=0.0, ge=0.0)
    branch_latency_ms: int = Field(default=0, ge=0)


class RunConfig(FrozenModel):
    max_cost_usd: float = Field(default=1.0, gt=0)
    max_calls: int = Field(default=20, gt=0)
    max_generations: int = Field(default=2, ge=0)
    seed_count: int = Field(default=4, ge=2)
    finalist_count: int = Field(default=3, ge=1)
    framing_reserve_usd: float = Field(default=0.05, ge=0)
    finalization_reserve_usd: float = Field(default=0.10, ge=0)
    random_seed: int = 0

    @model_validator(mode="after")
    def reservations_fit_budget(self) -> RunConfig:
        reserved = self.framing_reserve_usd + self.finalization_reserve_usd
        if reserved > self.max_cost_usd:
            raise ValueError("reserved cost exceeds maximum cost")
        if self.finalist_count > self.seed_count:
            raise ValueError("finalist_count cannot exceed seed_count")
        return self


class FramedTask(FrozenModel):
    context: TaskContext
    assumptions: tuple[str, ...]
    obvious_solution: str
    evaluation_dimensions: tuple[str, ...] = (
        "originality",
        "usefulness",
        "coherence",
        "feasibility",
        "user_fit",
    )


class SpendRecord(FrozenModel):
    stage: str
    provider: str
    cost_usd: float = Field(ge=0)
    latency_ms: int = Field(ge=0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class RunResult(FrozenModel):
    run_id: UUID = Field(default_factory=uuid4)
    framed_task: FramedTask
    finalists: tuple[IdeaGenome, ...]
    all_candidates: tuple[IdeaGenome, ...]
    spend_records: tuple[SpendRecord, ...]
    stopped_reason: str
