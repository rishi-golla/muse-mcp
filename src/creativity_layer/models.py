from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated
from uuid import UUID, uuid4

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)


def reject_blank_text(value: str) -> str:
    if not value.strip():
        raise ValueError("text must not be blank")
    return value


Score = Annotated[float, Field(strict=True, ge=0.0, le=1.0)]
RequiredText = Annotated[str, Field(min_length=1), AfterValidator(reject_blank_text)]


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)


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
    generation: int = Field(strict=True, ge=0)
    title: RequiredText
    core_mechanism: RequiredText
    problem_framing: RequiredText
    assumptions_challenged: tuple[str, ...] = ()
    task_value: RequiredText
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
    branch_cost_usd: float = Field(default=0.0, strict=True, ge=0.0)
    branch_latency_ms: float = Field(default=0.0, strict=True, ge=0.0)


class RunConfig(FrozenModel):
    max_cost_usd: float = Field(default=1.0, strict=True, gt=0)
    max_calls: int = Field(default=20, strict=True, gt=0)
    max_generations: int = Field(default=2, strict=True, ge=0)
    seed_count: int = Field(default=4, strict=True, ge=2)
    finalist_count: int = Field(default=3, strict=True, ge=1)
    framing_reserve_usd: float = Field(default=0.05, strict=True, ge=0)
    finalization_reserve_usd: float = Field(default=0.10, strict=True, ge=0)
    random_seed: int = Field(default=0, strict=True)

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


class TokenUsage(FrozenModel):
    input_tokens: int = Field(default=0, strict=True, ge=0)
    cached_input_tokens: int = Field(default=0, strict=True, ge=0)
    output_tokens: int = Field(default=0, strict=True, ge=0)
    reasoning_tokens: int = Field(default=0, strict=True, ge=0)

    @model_validator(mode="after")
    def cached_tokens_fit_input(self) -> TokenUsage:
        if self.cached_input_tokens > self.input_tokens:
            raise ValueError("cached input tokens cannot exceed input tokens")
        return self


class CostEstimate(FrozenModel):
    estimated_cost_usd: Decimal = Field(ge=0)
    pricing_version: RequiredText
    is_estimated: bool = True


class OperationTrace(FrozenModel):
    request: dict[str, object] = Field(default_factory=dict)
    response: dict[str, object] = Field(default_factory=dict)


class SpendRecord(FrozenModel):
    stage: RequiredText
    provider: RequiredText
    model: RequiredText | None = None
    cost_usd: float = Field(strict=True, ge=0)
    latency_ms: int = Field(strict=True, ge=0)
    usage: TokenUsage = Field(default_factory=TokenUsage)
    pricing_version: RequiredText | None = None
    cost_is_estimated: bool = False
    request_id: RequiredText | None = None
    operation_trace: OperationTrace | None = None
    created_at: AwareDatetime = Field(default_factory=lambda: datetime.now(UTC))


class ProviderIdentity(FrozenModel):
    name: RequiredText
    version: RequiredText


class RunProviders(FrozenModel):
    framer: ProviderIdentity
    seeder: ProviderIdentity
    transformer: ProviderIdentity
    evaluator: ProviderIdentity


class RunError(FrozenModel):
    stage: RequiredText
    provider: RequiredText
    category: RequiredText
    message: RequiredText
    cost_incurred: bool


FINGERPRINT_PATTERN = re.compile(r"[0-9a-fA-F]{64}\Z")


class RunResult(FrozenModel):
    run_id: UUID = Field(default_factory=uuid4)
    config: RunConfig
    providers: RunProviders
    operator_schedule: tuple[RequiredText, ...]
    framed_task: FramedTask
    finalists: tuple[IdeaGenome, ...]
    all_candidates: tuple[IdeaGenome, ...]
    spend_records: tuple[SpendRecord, ...]
    errors: tuple[RunError, ...] = ()
    stopped_reason: str
    reproducibility_fingerprint: str = ""

    @model_validator(mode="after")
    def set_reproducibility_fingerprint(self) -> RunResult:
        expected = compute_reproducibility_fingerprint(self)
        supplied = self.reproducibility_fingerprint
        if supplied:
            if FINGERPRINT_PATTERN.fullmatch(supplied) is None:
                raise ValueError("reproducibility_fingerprint must be a SHA-256 hex digest")
            normalized = supplied.lower()
            if normalized != expected:
                raise ValueError(
                    "reproducibility_fingerprint does not match canonical payload"
                )
        else:
            normalized = expected
        object.__setattr__(
            self,
            "reproducibility_fingerprint",
            normalized,
        )
        return self


def canonical_run_payload(result: RunResult) -> dict[str, object]:
    payload = result.model_dump(
        mode="json",
        exclude={"run_id", "reproducibility_fingerprint"},
    )
    for record in payload["spend_records"]:
        record.pop("created_at", None)
    return payload


def compute_reproducibility_fingerprint(result: RunResult) -> str:
    canonical = json.dumps(
        canonical_run_payload(result),
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
