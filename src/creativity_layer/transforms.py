from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from pydantic import Field, model_validator

from creativity_layer.models import FrozenModel, IdeaGenome, RequiredText


class OperatorName(StrEnum):
    INVERT = "invert"
    TRANSFER = "transfer"
    COMBINE = "combine"
    EXAGGERATE = "exaggerate"
    SUBTRACT = "subtract"
    REFRAME = "reframe"
    CONTRADICT = "contradict"
    PERSONALIZE = "personalize"
    DISTILL = "distill"


OPERATOR_INSTRUCTIONS: dict[OperatorName, str] = {
    OperatorName.INVERT: "Reverse a foundational assumption and trace the consequences.",
    OperatorName.TRANSFER: "Import an abstract mechanism from a distant domain.",
    OperatorName.COMBINE: "Merge compatible mechanisms, not surface descriptions.",
    OperatorName.EXAGGERATE: "Push one meaningful property to an extreme.",
    OperatorName.SUBTRACT: "Remove a supposedly essential component.",
    OperatorName.REFRAME: "Redefine the underlying problem before proposing an answer.",
    OperatorName.CONTRADICT: "Satisfy two goals that initially appear incompatible.",
    OperatorName.PERSONALIZE: "Reshape the mechanism around the current user and task.",
    OperatorName.DISTILL: "Remove borrowed surface traits while retaining useful principles.",
}


class TransformationRequest(FrozenModel):
    operator: OperatorName
    parent_ids: tuple[UUID, ...] = Field(min_length=1, max_length=2)
    task_goal: RequiredText
    instruction: RequiredText

    @model_validator(mode="after")
    def enforce_parent_cardinality(self) -> TransformationRequest:
        if self.operator is OperatorName.COMBINE:
            if len(self.parent_ids) != 2:
                raise ValueError("combine requires exactly two parents")
            if self.parent_ids[0] == self.parent_ids[1]:
                raise ValueError("combine requires two distinct parents")
        elif len(self.parent_ids) != 1:
            raise ValueError(f"{self.operator.value} requires exactly one parent")
        return self

    @classmethod
    def for_operator(
        cls,
        *,
        operator: OperatorName,
        parents: tuple[IdeaGenome, ...],
        task_goal: str,
    ) -> TransformationRequest:
        instruction = (
            f"{OPERATOR_INSTRUCTIONS[operator]} "
            "Change the idea's causal or structural mechanism. "
            "Do not merely rename, restyle, or reword the parent."
        )
        return cls(
            operator=operator,
            parent_ids=tuple(parent.id for parent in parents),
            task_goal=task_goal,
            instruction=instruction,
        )
