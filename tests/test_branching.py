import pytest
from pydantic import ValidationError

from muse.branching import BranchDirective, BranchStrategy, branch_directives
from muse.models import IdeaGenome


def _idea_payload() -> dict[str, object]:
    return {
        "generation": 0,
        "title": "Constraint ledger",
        "core_mechanism": "Track constraints as explicit decision inputs.",
        "problem_framing": "Constraints are usually hidden in discussion.",
        "task_value": "Makes tradeoffs inspectable.",
    }


def test_branch_directives_schedule_six_distinct_causal_strategies_in_order() -> None:
    directives = branch_directives(seed_count=6)

    assert [(directive.branch_index, directive.strategy) for directive in directives] == [
        (0, BranchStrategy.CONSTRAINT_INVERSION),
        (1, BranchStrategy.FAILURE_FIRST),
        (2, BranchStrategy.CROSS_DOMAIN_TRANSFER),
        (3, BranchStrategy.SYSTEMS_EFFECTS),
        (4, BranchStrategy.MINIMAL_MECHANISM),
        (5, BranchStrategy.USER_CENTERED),
    ]
    assert [directive.instruction for directive in directives] == [
        "Invert a core constraint or assumption and derive a mechanism that works under the "
        "reversed condition.",
        "Start from a plausible failure mode, then design sensing, containment, and recovery "
        "into the mechanism.",
        "Transfer a structural mechanism from a distant domain, mapping roles, signals, and "
        "feedback rather than surface language.",
        "Model first- and second-order effects, then use feedback loops or safeguards to shape "
        "the system outcome.",
        "Remove everything except the irreducible mechanism; justify how the smallest viable "
        "structure still creates value.",
        "Start from a user's concrete moment of friction, agency, and feedback, then make the "
        "mechanism adapt to that experience.",
    ]


def test_branch_directives_reuse_strategies_deterministically_after_six() -> None:
    first = branch_directives(seed_count=8)
    second = branch_directives(seed_count=8)

    assert first == second
    assert [(directive.branch_index, directive.strategy) for directive in first[6:]] == [
        (6, BranchStrategy.CONSTRAINT_INVERSION),
        (7, BranchStrategy.FAILURE_FIRST),
    ]


def test_branch_directive_requires_a_non_negative_index_and_concrete_instruction() -> None:
    with pytest.raises(ValidationError):
        BranchDirective(
            branch_index=-1,
            strategy=BranchStrategy.CONSTRAINT_INVERSION,
            instruction="Valid instruction.",
        )

    with pytest.raises(ValidationError):
        BranchDirective(
            branch_index=0,
            strategy=BranchStrategy.CONSTRAINT_INVERSION,
            instruction="   ",
        )


def test_idea_genome_defaults_branch_strategy_for_legacy_payloads_and_serializes_it() -> None:
    idea = IdeaGenome.model_validate(_idea_payload())

    assert idea.branch_strategy is BranchStrategy.CONSTRAINT_INVERSION
    assert idea.model_dump(mode="json")["branch_strategy"] == "constraint_inversion"
    assert IdeaGenome.model_validate_json(idea.model_dump_json()) == idea


def test_idea_genome_preserves_explicit_branch_strategy_through_model_round_trip() -> None:
    idea = IdeaGenome(
        **_idea_payload(),
        branch_strategy=BranchStrategy.USER_CENTERED,
    )

    restored = IdeaGenome.model_validate(idea.model_dump(mode="json"))

    assert restored.branch_strategy is BranchStrategy.USER_CENTERED
