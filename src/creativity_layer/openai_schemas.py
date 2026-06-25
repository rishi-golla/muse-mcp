from __future__ import annotations

import json
import math
import unicodedata
from uuid import UUID, uuid5

from pydantic import BaseModel, ConfigDict, field_validator

from creativity_layer.models import (
    EvaluationScores,
    FramedTask,
    IdeaGenome,
    InspirationKind,
    TaskContext,
    reject_blank_text,
)
from creativity_layer.transforms import (
    TransformationRequest,
    expected_transformation_history,
)

OPENAI_ID_NAMESPACE = UUID("e8e3f5ca-dc80-5c06-a22a-2728f62d00d9")
MAX_TEXT_LENGTH = 4_000
MAX_TITLE_LENGTH = 200
MAX_LIST_ITEMS = 20
MAX_LIST_ITEM_LENGTH = 1_000


def _canonical_text(value: str, *, max_length: int) -> str:
    canonical = " ".join(unicodedata.normalize("NFKC", value).split())
    reject_blank_text(canonical)
    if len(canonical) > max_length:
        raise ValueError(f"text must not exceed {max_length} characters")
    return canonical


def _validate_text_list(value: list[str]) -> list[str]:
    if len(value) > MAX_LIST_ITEMS:
        raise ValueError(f"list must not contain more than {MAX_LIST_ITEMS} items")
    canonical_items = [
        _canonical_text(item, max_length=MAX_LIST_ITEM_LENGTH) for item in value
    ]
    normalized: set[str] = set()
    for item in canonical_items:
        if item in normalized:
            raise ValueError("list must not contain duplicate normalized entries")
        normalized.add(item)
    return canonical_items


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


class OpenAIOutputModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        allow_inf_nan=False,
    )


class OpenAIFrame(OpenAIOutputModel):
    assumptions: list[str]
    obvious_solution: str

    @field_validator("assumptions")
    @classmethod
    def validate_assumptions(cls, value: list[str]) -> list[str]:
        return _validate_text_list(value)

    @field_validator("obvious_solution")
    @classmethod
    def validate_obvious_solution(cls, value: str) -> str:
        return _canonical_text(value, max_length=MAX_TEXT_LENGTH)

    def to_domain(self, task: TaskContext) -> FramedTask:
        return FramedTask(
            context=task,
            assumptions=tuple(self.assumptions),
            obvious_solution=self.obvious_solution,
        )


class OpenAIIdea(OpenAIOutputModel):
    title: str
    core_mechanism: str
    problem_framing: str
    assumptions_challenged: list[str]
    task_value: str
    distinguishing_features: list[str]
    first_order_effects: list[str]
    second_order_effects: list[str]
    feasibility_assumptions: list[str]
    uncertainties: list[str]
    weaknesses: list[str]

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        return _canonical_text(value, max_length=MAX_TITLE_LENGTH)

    @field_validator(
        "core_mechanism",
        "problem_framing",
        "task_value",
    )
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        return _canonical_text(value, max_length=MAX_TEXT_LENGTH)

    @field_validator(
        "assumptions_challenged",
        "distinguishing_features",
        "first_order_effects",
        "second_order_effects",
        "feasibility_assumptions",
        "uncertainties",
        "weaknesses",
    )
    @classmethod
    def validate_text_lists(cls, value: list[str]) -> list[str]:
        return _validate_text_list(value)

    def canonical_content(self) -> str:
        return _canonical_json(self.model_dump())

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

    def to_seed(self) -> IdeaGenome:
        return IdeaGenome(
            id=uuid5(OPENAI_ID_NAMESPACE, self.canonical_content()),
            generation=0,
            **self._domain_fields(),
            inspiration_kind=InspirationKind.INDEPENDENT,
        )

    def to_transform(
        self,
        *,
        request: TransformationRequest,
        parents: tuple[IdeaGenome, ...],
    ) -> IdeaGenome:
        parent_ids = tuple(parent.id for parent in parents)
        if parent_ids != request.parent_ids:
            raise ValueError("transform parents do not match request")
        history = expected_transformation_history(request.operator, parents)
        identity_payload = {
            "content": json.loads(self.canonical_content()),
            "operator": request.operator.value,
            "task_goal": _canonical_text(
                request.task_goal,
                max_length=MAX_TEXT_LENGTH,
            ),
            "parent_ids": [str(parent_id) for parent_id in parent_ids],
            "history": list(history),
        }
        return IdeaGenome(
            id=uuid5(OPENAI_ID_NAMESPACE, _canonical_json(identity_payload)),
            generation=max(parent.generation for parent in parents) + 1,
            **self._domain_fields(),
            parent_ids=parent_ids,
            transformations=history,
            inspiration_kind=InspirationKind.SYNTHESIZED,
        )


class OpenAISeedBatch(OpenAIOutputModel):
    ideas: list[OpenAIIdea]

    @field_validator("ideas")
    @classmethod
    def validate_batch_size(cls, value: list[OpenAIIdea]) -> list[OpenAIIdea]:
        if len(value) > MAX_LIST_ITEMS:
            raise ValueError(f"list must not contain more than {MAX_LIST_ITEMS} items")
        return value

    def to_seeds(
        self,
        *,
        expected_count: int,
    ) -> tuple[IdeaGenome, ...]:
        if len(self.ideas) != expected_count:
            raise ValueError("seed cardinality does not match requested seed_count")
        content = [idea.canonical_content() for idea in self.ideas]
        if len(content) != len(set(content)):
            raise ValueError("seed batch contains duplicate normalized ideas")
        candidates = tuple(idea.to_seed() for idea in self.ideas)
        if len({candidate.id for candidate in candidates}) != len(candidates):
            raise ValueError("seed batch contains duplicate normalized ideas")
        return candidates


class OpenAIEvaluation(OpenAIOutputModel):
    originality: float
    usefulness: float
    coherence: float
    feasibility: float
    user_fit: float

    @field_validator("*")
    @classmethod
    def validate_score(cls, value: float) -> float:
        if not math.isfinite(value) or not 0.0 <= value <= 1.0:
            raise ValueError("score must be finite and between 0 and 1")
        return value

    def to_domain(self) -> EvaluationScores:
        return EvaluationScores.model_validate(self.model_dump())
