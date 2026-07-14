from __future__ import annotations

from typing import Protocol

from pydantic import Field

from muse.models import (
    EvaluationScores,
    FramedTask,
    FrozenModel,
    IdeaGenome,
    OperationTrace,
    RequiredText,
    RunConfig,
    TaskContext,
    TokenUsage,
)
from muse.transforms import TransformationRequest


class ItemMetering(FrozenModel):
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


class MeteredResponse[T](FrozenModel):
    value: T
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
    item_metering: tuple[ItemMetering, ...] = ()


class MeteredProviderFailure(RuntimeError):
    """A sanitized provider failure with metering for completed work."""

    def __init__(
        self,
        message: str,
        *,
        partial_response: MeteredResponse[object],
    ) -> None:
        super().__init__(message)
        self.partial_response = partial_response


class OperationQuote(FrozenModel):
    """Upper bound for one accountable provider operation."""

    max_cost_usd: float = Field(strict=True, ge=0)
    calls: int = Field(default=1, strict=True, ge=1)


class TaskFramer(Protocol):
    name: str
    version: str

    def quote_frame(self, task: TaskContext) -> OperationQuote: ...

    def frame(self, task: TaskContext) -> MeteredResponse[FramedTask]: ...


class IdeaSeeder(Protocol):
    name: str
    version: str

    def quote_seed(
        self,
        framed_task: FramedTask,
        config: RunConfig,
    ) -> OperationQuote: ...

    def seed(
        self,
        framed_task: FramedTask,
        config: RunConfig,
    ) -> MeteredResponse[tuple[IdeaGenome, ...]]: ...


class IdeaTransformer(Protocol):
    name: str
    version: str

    def quote_transform(
        self,
        request: TransformationRequest,
        parents: tuple[IdeaGenome, ...],
    ) -> OperationQuote: ...

    def transform(
        self,
        request: TransformationRequest,
        parents: tuple[IdeaGenome, ...],
        framed_task: FramedTask,
    ) -> MeteredResponse[IdeaGenome]: ...


class IdeaEvaluator(Protocol):
    name: str
    version: str

    def quote_evaluation(self, framed_task: FramedTask) -> OperationQuote: ...

    def evaluate(
        self,
        candidate: IdeaGenome,
        framed_task: FramedTask,
    ) -> MeteredResponse[EvaluationScores]: ...
