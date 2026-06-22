from uuid import UUID

import pytest
from pydantic import ValidationError

from creativity_layer.models import (
    EvaluationScores,
    IdeaGenome,
    InspirationKind,
    RunConfig,
    TaskContext,
)


def test_task_context_requires_a_non_blank_goal() -> None:
    with pytest.raises(ValidationError):
        TaskContext(goal="   ")


def test_idea_genome_records_ancestry_and_separate_scores() -> None:
    parent = IdeaGenome(
        generation=0,
        title="Borrow time",
        core_mechanism="Trade scheduling rights instead of fixed calendar slots.",
        problem_framing="Coordination is treated as ownership of time.",
        task_value="Reduces scheduling negotiation.",
        distinguishing_features=("transferable scheduling rights",),
    )

    child = IdeaGenome(
        generation=1,
        title="Time market",
        core_mechanism="Let participants exchange priority tokens.",
        problem_framing="Coordination is a constrained allocation market.",
        task_value="Makes urgency explicit.",
        distinguishing_features=("priority tokens",),
        parent_ids=(parent.id,),
        transformations=("transfer",),
        inspiration_kind=InspirationKind.SYNTHESIZED,
        scores=EvaluationScores(
            originality=0.9,
            usefulness=0.7,
            coherence=0.8,
            feasibility=0.6,
            user_fit=0.75,
        ),
    )

    assert isinstance(child.id, UUID)
    assert child.parent_ids == (parent.id,)
    assert child.scores.originality == 0.9
    assert child.scores.usefulness == 0.7


def test_run_config_rejects_impossible_reservations() -> None:
    with pytest.raises(ValidationError):
        RunConfig(
            max_cost_usd=1,
            max_calls=4,
            framing_reserve_usd=0.6,
            finalization_reserve_usd=0.5,
        )
