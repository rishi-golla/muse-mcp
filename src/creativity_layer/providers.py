from __future__ import annotations

from typing import Protocol

from pydantic import Field

from creativity_layer.models import (
    EvaluationScores,
    FramedTask,
    FrozenModel,
    IdeaGenome,
    RequiredText,
    RunConfig,
    TaskContext,
)
from creativity_layer.transforms import TransformationRequest


class MeteredResponse[T](FrozenModel):
    value: T
    provider: RequiredText
    cost_usd: float = Field(strict=True, ge=0)
    latency_ms: int = Field(strict=True, ge=0)


class OperationQuote(FrozenModel):
    max_cost_usd: float = Field(strict=True, ge=0)
    calls: int = Field(strict=True, gt=0)


class TaskFramer(Protocol):
    def frame(self, task: TaskContext) -> FramedTask: ...


class IdeaSeeder(Protocol):
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
    def quote_transform(
        self,
        request: TransformationRequest,
        parents: tuple[IdeaGenome, ...],
    ) -> OperationQuote: ...

    def transform(
        self,
        request: TransformationRequest,
        parents: tuple[IdeaGenome, ...],
    ) -> MeteredResponse[IdeaGenome]: ...


class IdeaEvaluator(Protocol):
    def quote_evaluation(self, framed_task: FramedTask) -> OperationQuote: ...

    def evaluate(
        self,
        candidate: IdeaGenome,
        framed_task: FramedTask,
    ) -> MeteredResponse[EvaluationScores]: ...
