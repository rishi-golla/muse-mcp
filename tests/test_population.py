from itertools import permutations
from uuid import UUID

import pytest

from creativity_layer.models import EvaluationScores, IdeaGenome
from creativity_layer.population import PopulationManager


def candidate(
    title: str,
    *,
    originality: float,
    usefulness: float,
    coherence: float = 0.8,
) -> IdeaGenome:
    return IdeaGenome(
        generation=0,
        title=title,
        core_mechanism=f"{title} mechanism",
        problem_framing=f"{title} framing",
        task_value=f"{title} value",
        distinguishing_features=(title,),
        scores=EvaluationScores(
            originality=originality,
            usefulness=usefulness,
            coherence=coherence,
            feasibility=0.7,
            user_fit=0.7,
        ),
    )


def test_frontier_keeps_non_dominated_candidates() -> None:
    original = candidate("original", originality=0.95, usefulness=0.55)
    useful = candidate("useful", originality=0.60, usefulness=0.95)
    dominated = candidate("dominated", originality=0.50, usefulness=0.50)

    selected = PopulationManager().select(
        (original, useful, dominated),
        finalist_count=2,
    )

    assert {item.title for item in selected} == {"original", "useful"}


def test_wildcard_preserves_most_original_coherent_candidate() -> None:
    balanced = candidate("balanced", originality=0.75, usefulness=0.8)
    wildcard = candidate("wildcard", originality=0.99, usefulness=0.2, coherence=0.65)
    random_noise = candidate("noise", originality=1.0, usefulness=0.1, coherence=0.1)

    selected = PopulationManager(minimum_wildcard_coherence=0.6).select(
        (balanced, wildcard, random_noise),
        finalist_count=2,
    )

    assert [item.title for item in selected] == ["balanced", "wildcard"]


def test_selection_fills_capacity_after_the_frontier() -> None:
    best = candidate("best", originality=0.9, usefulness=0.9)
    second = candidate("second", originality=0.8, usefulness=0.8)
    third = candidate("third", originality=0.7, usefulness=0.7)

    selected = PopulationManager().select(
        (best, second, third),
        finalist_count=3,
    )

    assert [item.title for item in selected] == ["best", "second", "third"]


def test_frontier_rejects_duplicate_candidate_ids() -> None:
    first = candidate("first", originality=0.9, usefulness=0.8)
    duplicate = candidate("duplicate", originality=0.8, usefulness=0.9).model_copy(
        update={"id": first.id}
    )

    with pytest.raises(ValueError, match="duplicate candidate id"):
        PopulationManager().pareto_frontier((first, duplicate))


def test_selection_rejects_duplicate_candidate_ids() -> None:
    first = candidate("first", originality=0.9, usefulness=0.8)
    duplicate = candidate("duplicate", originality=0.8, usefulness=0.9).model_copy(
        update={"id": first.id}
    )

    with pytest.raises(ValueError, match="duplicate candidate id"):
        PopulationManager().select((first, duplicate), finalist_count=1)


def test_selection_proceeds_when_no_candidate_meets_wildcard_coherence() -> None:
    best = candidate("best", originality=0.9, usefulness=0.9, coherence=0.4)
    second = candidate("second", originality=0.8, usefulness=0.8, coherence=0.3)

    selected = PopulationManager(minimum_wildcard_coherence=0.6).select(
        (best, second),
        finalist_count=2,
    )

    assert [item.title for item in selected] == ["best", "second"]


def test_selection_is_deterministic_across_input_permutations() -> None:
    balanced_low = candidate("balanced low", originality=0.8, usefulness=0.8).model_copy(
        update={"id": UUID("00000000-0000-0000-0000-000000000001")}
    )
    balanced_high = candidate("balanced high", originality=0.8, usefulness=0.8).model_copy(
        update={"id": UUID("00000000-0000-0000-0000-000000000002")}
    )
    wildcard_low = candidate("wildcard low", originality=0.99, usefulness=0.2).model_copy(
        update={"id": UUID("00000000-0000-0000-0000-000000000003")}
    )
    wildcard_high = candidate("wildcard high", originality=0.99, usefulness=0.2).model_copy(
        update={"id": UUID("00000000-0000-0000-0000-000000000004")}
    )
    candidates = (balanced_low, balanced_high, wildcard_low, wildcard_high)

    selections = {
        tuple(item.id for item in PopulationManager().select(order, finalist_count=3))
        for order in permutations(candidates)
    }

    assert selections == {
        (
            balanced_high.id,
            balanced_low.id,
            wildcard_high.id,
        )
    }
