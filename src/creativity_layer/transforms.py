from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from pydantic import Field

from creativity_layer.models import FrozenModel, IdeaGenome


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
    task_goal: str = Field(min_length=1)
    instruction: str = Field(min_length=1)

    @classmethod
    def for_operator(
        cls,
        *,
        operator: OperatorName,
        parents: tuple[IdeaGenome, ...],
        task_goal: str,
    ) -> TransformationRequest:
        if operator is OperatorName.COMBINE and len(parents) != 2:
            raise ValueError("combine requires exactly two parents")
        if operator is not OperatorName.COMBINE and len(parents) != 1:
            raise ValueError(f"{operator.value} requires exactly one parent")

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
