from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Mapping
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated
from uuid import UUID, uuid4

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_serializer,
    model_validator,
)

from muse.branching import BranchStrategy


def reject_blank_text(value: str) -> str:
    if not value.strip():
        raise ValueError("text must not be blank")
    if any(unicodedata.category(character).startswith("C") for character in value):
        raise ValueError("text must not contain Unicode control or format characters")
    return value


Score = Annotated[float, Field(strict=True, ge=0.0, le=1.0)]
RequiredText = Annotated[str, AfterValidator(reject_blank_text)]


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)


class InspirationKind(StrEnum):
    INDEPENDENT = "independent"
    INSPIRED = "inspired"
    SYNTHESIZED = "synthesized"
    ADAPTED = "adapted"
    LIKELY_COPYING = "likely_copying"


class ContextSensitivity(StrEnum):
    PUBLIC = "public"
    PRIVATE = "private"


class ContextSnippet(FrozenModel):
    source: RequiredText
    content: RequiredText
    title: str = ""
    metadata: Mapping[str, object] = Field(default_factory=dict)
    sensitivity: ContextSensitivity = ContextSensitivity.PRIVATE


class ContextBundle(FrozenModel):
    snippets: tuple[ContextSnippet, ...] = ()
    tags: tuple[str, ...] = ()


class TaskContext(FrozenModel):
    goal: str = Field(min_length=1)
    audience: str | None = None
    constraints: tuple[str, ...] = ()
    preferences: tuple[str, ...] = ()
    risk_tolerance: Score = 0.5
    context_bundle: ContextBundle = Field(default_factory=ContextBundle)

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
    operational_specificity: Score = 0.0
    workflow_fit: Score = 0.0


class IdeaGenome(FrozenModel):
    id: UUID = Field(default_factory=uuid4)
    generation: int = Field(strict=True, ge=0)
    title: RequiredText
    core_mechanism: RequiredText
    problem_framing: RequiredText
    assumptions_challenged: tuple[str, ...] = ()
    task_value: RequiredText
    distinguishing_features: tuple[str, ...] = ()
    inputs_required: tuple[str, ...] = ()
    outputs_produced: tuple[str, ...] = ()
    agent_workflow: tuple[str, ...] = ()
    decision_policy: str = ""
    integration_points: tuple[str, ...] = ()
    verification_strategy: str = ""
    failure_modes: tuple[str, ...] = ()
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
    branch_strategy: BranchStrategy = BranchStrategy.CONSTRAINT_INVERSION
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
    estimated_cost_usd: float = Field(strict=True, ge=0)
    pricing_version: RequiredText
    is_estimated: bool = Field(default=True, strict=True)


class OperationTrace(FrozenModel):
    request_json: str
    response_json: str

    @model_validator(mode="before")
    @classmethod
    def canonicalize_payload_aliases(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        payload = dict(value)
        for alias, field in (
            ("request", "request_json"),
            ("response", "response_json"),
        ):
            if alias not in payload:
                continue
            if field in payload:
                raise ValueError(f"operation trace cannot provide both {alias} and {field}")
            raw_payload = payload.pop(alias)
            _reject_trace_secrets(raw_payload)
            payload[field] = _canonical_json(raw_payload)
        return payload

    @classmethod
    def from_payload(
        cls,
        *,
        request: object,
        response: object,
    ) -> OperationTrace:
        _reject_trace_secrets(request)
        _reject_trace_secrets(response)
        return cls(
            request_json=_canonical_json(request),
            response_json=_canonical_json(response),
        )

    @field_validator("request_json", "response_json")
    @classmethod
    def require_canonical_json(cls, value: str) -> str:
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError) as error:
            raise ValueError("operation trace must contain valid JSON") from error
        if value != _canonical_json(parsed):
            raise ValueError("operation trace JSON must be canonical")
        _reject_trace_secrets(parsed)
        return value

    @model_serializer(mode="plain")
    def serialize_public_payloads(self) -> dict[str, object]:
        return {
            "request": json.loads(self.request_json),
            "response": json.loads(self.response_json),
        }


SAFE_TRACE_TOKEN_METRICS = frozenset(
    {
        "token_count",
        "input_tokens",
        "output_tokens",
        "cached_tokens",
        "reasoning_tokens",
    }
)
SECRET_TRACE_KEY_TERMS = frozenset(
    {
        "auth",
        "authorization",
        "credential",
        "privatekey",
        "apikey",
        "bearer",
        "accesstoken",
        "refreshtoken",
        "idtoken",
        "secret",
        "password",
        "passwd",
        "cookie",
        "token",
    }
)
SECRET_TRACE_VALUE = re.compile(
    r"(?:\bBearer\s+\S+|\bsk-[A-Za-z0-9_-]{10,})",
    re.IGNORECASE,
)


def _reject_trace_secrets(value: object) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if _is_secret_trace_key(str(key)):
                raise ValueError("operation trace contains a secret-bearing key")
            _reject_trace_secrets(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _reject_trace_secrets(item)
    elif isinstance(value, str) and SECRET_TRACE_VALUE.search(value):
        raise ValueError("operation trace contains an apparent secret value")


def _is_secret_trace_key(key: str) -> bool:
    normalized_unicode = unicodedata.normalize("NFKC", key).casefold()
    normalized = re.sub(r"[^a-z0-9]+", "_", normalized_unicode).strip("_")
    if normalized in SAFE_TRACE_TOKEN_METRICS:
        return False
    compact = normalized.replace("_", "")
    return any(term in compact for term in SECRET_TRACE_KEY_TERMS)


def _canonical_json(value: object) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as error:
        raise ValueError("operation trace payload must be JSON-safe") from error


class SpendRecord(FrozenModel):
    stage: RequiredText
    provider: RequiredText
    model: RequiredText | None = None
    cost_usd: float = Field(strict=True, ge=0)
    calls: int = Field(default=1, strict=True, ge=1)
    latency_ms: int = Field(strict=True, ge=0)
    usage: TokenUsage = Field(default_factory=TokenUsage)
    pricing_version: RequiredText | None = None
    cost_is_estimated: bool = Field(default=False, strict=True)
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
DEFAULT_IDEA_CONTRACT_VALUES = {
    "branch_strategy": "constraint_inversion",
    "inputs_required": [],
    "outputs_produced": [],
    "agent_workflow": [],
    "decision_policy": "",
    "integration_points": [],
    "verification_strategy": "",
    "failure_modes": [],
}
DEFAULT_SCORE_VALUES = {
    "operational_specificity": 0.0,
    "workflow_fit": 0.0,
}
DEFAULT_CONTEXT_BUNDLE = {
    "snippets": [],
    "tags": [],
}


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
        if record["model"] is None:
            record.pop("model")
        if record["calls"] == 1:
            record.pop("calls")
        if record["usage"] == {
            "input_tokens": 0,
            "cached_input_tokens": 0,
            "output_tokens": 0,
            "reasoning_tokens": 0,
        }:
            record.pop("usage")
        if record["pricing_version"] is None:
            record.pop("pricing_version")
        if record["cost_is_estimated"] is False:
            record.pop("cost_is_estimated")
        if record["request_id"] is None:
            record.pop("request_id")
        if record["operation_trace"] is None:
            record.pop("operation_trace")
    for candidates_key in ("finalists", "all_candidates"):
        for candidate in payload[candidates_key]:
            _prune_default_operational_fields(candidate)
    context = payload["framed_task"]["context"]
    if context.get("context_bundle") == DEFAULT_CONTEXT_BUNDLE:
        context.pop("context_bundle")
    return payload


def _prune_default_operational_fields(candidate: dict[str, object]) -> None:
    for field, default_value in DEFAULT_IDEA_CONTRACT_VALUES.items():
        if candidate.get(field) == default_value:
            candidate.pop(field)
    scores = candidate.get("scores")
    if not isinstance(scores, dict):
        return
    for field, default_value in DEFAULT_SCORE_VALUES.items():
        if scores.get(field) == default_value:
            scores.pop(field)


def compute_reproducibility_fingerprint(result: RunResult) -> str:
    canonical = json.dumps(
        canonical_run_payload(result),
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
