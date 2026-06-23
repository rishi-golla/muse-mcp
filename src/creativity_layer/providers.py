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


class TaskFramer(Protocol):
    def frame(self, task: TaskContext) -> FramedTask: ...


class IdeaSeeder(Protocol):
    def seed(
        self,
        framed_task: FramedTask,
        config: RunConfig,
    ) -> MeteredResponse[tuple[IdeaGenome, ...]]: ...


class IdeaTransformer(Protocol):
    def transform(
        self,
        request: TransformationRequest,
        parents: tuple[IdeaGenome, ...],
    ) -> MeteredResponse[IdeaGenome]: ...


class IdeaEvaluator(Protocol):
    def evaluate(
        self,
        candidate: IdeaGenome,
        framed_task: FramedTask,
    ) -> MeteredResponse[EvaluationScores]: ...
