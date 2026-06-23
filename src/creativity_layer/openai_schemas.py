from __future__ import annotations

from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from creativity_layer.models import (
    EvaluationScores,
    FramedTask,
    IdeaGenome,
    InspirationKind,
    RequiredText,
    Score,
    TaskContext,
)
from creativity_layer.transforms import (
    TransformationRequest,
    expected_transformation_history,
)


class OpenAIOutputModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        allow_inf_nan=False,
    )


class OpenAIFrame(OpenAIOutputModel):
    assumptions: list[RequiredText]
    obvious_solution: RequiredText

    def to_domain(self, task: TaskContext) -> FramedTask:
        return FramedTask(
            context=task,
            assumptions=tuple(self.assumptions),
            obvious_solution=self.obvious_solution,
        )


class OpenAIIdea(OpenAIOutputModel):
    title: RequiredText
    core_mechanism: RequiredText
    problem_framing: RequiredText
    assumptions_challenged: list[RequiredText]
    task_value: RequiredText
    distinguishing_features: list[RequiredText]
    first_order_effects: list[RequiredText]
    second_order_effects: list[RequiredText]
    feasibility_assumptions: list[RequiredText]
    uncertainties: list[RequiredText]
    weaknesses: list[RequiredText]

    def _domain_fields(self) -> dict[str, object]:
        return {
            "title": self.title,
            "core_mechanism": self.core_mechanism,
            "problem_framing": self.problem_framing,
            "assumptions_challenged": tuple(self.assumptions_challenged),
            "task_value": self.task_value,
            "distinguishing_features": tuple(self.distinguishing_features),
            "first_order_effects": tuple(self.first_order_effects),
            "second_order_effects": tuple(self.second_order_effects),
            "feasibility_assumptions": tuple(self.feasibility_assumptions),
            "uncertainties": tuple(self.uncertainties),
            "weaknesses": tuple(self.weaknesses),
        }

    def to_seed(self, *, generation: int) -> IdeaGenome:
        return IdeaGenome(
            id=uuid4(),
            generation=generation,
            **self._domain_fields(),
            inspiration_kind=InspirationKind.INDEPENDENT,
        )

    def to_transform(
        self,
        *,
        request: TransformationRequest,
        parents: tuple[IdeaGenome, ...],
    ) -> IdeaGenome:
        return IdeaGenome(
            id=uuid4(),
            generation=max(parent.generation for parent in parents) + 1,
            **self._domain_fields(),
            parent_ids=request.parent_ids,
            transformations=expected_transformation_history(
                request.operator,
                parents,
            ),
            inspiration_kind=InspirationKind.SYNTHESIZED,
        )


class OpenAISeedBatch(OpenAIOutputModel):
    ideas: list[OpenAIIdea]

    def to_seeds(
        self,
        *,
        generation: int,
        expected_count: int,
    ) -> tuple[IdeaGenome, ...]:
        if len(self.ideas) != expected_count:
            raise ValueError("seed cardinality does not match requested seed_count")
        return tuple(idea.to_seed(generation=generation) for idea in self.ideas)


class OpenAIEvaluation(OpenAIOutputModel):
    originality: Score
    usefulness: Score
    coherence: Score
    feasibility: Score
    user_fit: Score

    def to_domain(self) -> EvaluationScores:
        return EvaluationScores.model_validate(self.model_dump())
