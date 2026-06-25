import pytest

from creativity_layer.inspiration import SourceAbstraction
from creativity_layer.models import IdeaGenome
from creativity_layer.novelty import CopyingClassification, score_novelty


def idea(
    *,
    title: str = "Evidence garden",
    core_mechanism: str = "A shared board turns each claim into a living evidence card.",
    problem_framing: str = "Teams lose decisions when evidence arrives after meetings.",
    task_value: str = "Keep decisions current without asking people to reread threads.",
    distinguishing_features: tuple[str, ...] = (
        "Evidence cards expire unless refreshed.",
        "Disagreements are attached to claims.",
    ),
) -> IdeaGenome:
    return IdeaGenome(
        generation=0,
        title=title,
        core_mechanism=core_mechanism,
        problem_framing=problem_framing,
        task_value=task_value,
        distinguishing_features=distinguishing_features,
    )


def source(
    *,
    mechanism: str = "A shared board turns each claim into a living evidence card.",
    principle: str = "Use living evidence cards to keep claims current.",
) -> SourceAbstraction:
    return SourceAbstraction(
        source_id="src-1",
        source_url="https://example.com/evidence-garden",
        mechanism=mechanism,
        constraints=("Use bounded evidence.",),
        tensions=("Source context may differ.",),
        domain="coordination",
        confidence=0.8,
        principle=principle,
    )


def test_identical_source_mechanism_is_likely_copying() -> None:
    candidate = idea()

    score = score_novelty(
        candidate,
        peers=(),
        obvious_solution="Hold another status meeting.",
        sources=(source(),),
        branch_is_search_isolated=False,
        prior_art_failed=False,
    )

    assert score.classification is CopyingClassification.LIKELY_COPYING
    assert score.source_similarity_risk >= 0.8


def test_distinct_source_mechanism_in_non_isolated_branch_is_inspired() -> None:
    candidate = idea(
        core_mechanism="A rotating facilitator converts stale decisions into timed experiments.",
        distinguishing_features=("Experiment owners report measured reversibility.",),
    )

    score = score_novelty(
        candidate,
        peers=(),
        obvious_solution="Hold another status meeting.",
        sources=(
            source(
                mechanism="A marketplace ranks repairs by part scarcity.",
                principle="Prioritize constrained repairs before easy work.",
            ),
        ),
        branch_is_search_isolated=False,
        prior_art_failed=False,
    )

    assert score.source_similarity_risk < 0.5
    assert score.classification is CopyingClassification.INSPIRED
    assert score.branch_isolation_confidence < 1.0


def test_multiple_distinct_sources_in_non_isolated_branch_are_inspired() -> None:
    candidate = idea(
        core_mechanism="A rotating facilitator converts stale decisions into timed experiments.",
        distinguishing_features=("Experiment owners report measured reversibility.",),
    )

    score = score_novelty(
        candidate,
        peers=(),
        obvious_solution="Hold another status meeting.",
        sources=(
            source(
                mechanism="A marketplace ranks repairs by part scarcity.",
                principle="Prioritize constrained repairs before easy work.",
            ),
            source(
                mechanism="A camera rig estimates soil moisture from leaf curl.",
                principle="Infer hidden resource stress from visible posture changes.",
            ),
        ),
        branch_is_search_isolated=False,
        prior_art_failed=False,
    )

    assert score.source_similarity_risk < 0.5
    assert score.classification is CopyingClassification.INSPIRED


def test_source_similarity_considers_copied_wording_across_candidate_fields() -> None:
    candidate = idea(
        title="Timed experiments",
        core_mechanism="Refresh stale decisions.",
        problem_framing="Teams need reversible choices.",
        task_value="Measured reversibility.",
        distinguishing_features=("Facilitator records experiment owners.",),
    )

    score = score_novelty(
        candidate,
        peers=(),
        obvious_solution="Hold another status meeting.",
        sources=(
            source(
                mechanism="A marketplace ranks repairs by part scarcity.",
                principle="Timed experiments refresh stale decisions with measured reversibility.",
            ),
        ),
        branch_is_search_isolated=False,
        prior_art_failed=False,
    )

    assert score.source_similarity_risk >= 0.4


def test_search_isolated_branch_without_source_overlap_is_independent() -> None:
    candidate = idea(
        core_mechanism="People precommit reversible choices before seeing group votes.",
        distinguishing_features=("Vote order is hidden until commitments are recorded.",),
    )

    score = score_novelty(
        candidate,
        peers=(),
        obvious_solution="Hold another status meeting.",
        sources=(source(mechanism="A queue balances warehouse pick paths."),),
        branch_is_search_isolated=True,
        prior_art_failed=False,
    )

    assert score.classification is CopyingClassification.INDEPENDENT
    assert score.branch_isolation_confidence == 1.0


def test_prior_art_failure_lowers_coverage_confidence() -> None:
    score = score_novelty(
        idea(),
        peers=(),
        obvious_solution="Hold another status meeting.",
        sources=(),
        branch_is_search_isolated=True,
        prior_art_failed=True,
    )

    assert score.coverage_confidence < 0.5


def test_score_novelty_accepts_planned_positional_signature() -> None:
    score = score_novelty(
        idea(),
        (),
        "Hold another status meeting.",
        (),
        True,
        False,
    )

    assert score.classification is CopyingClassification.INDEPENDENT


def test_peer_and_baseline_distances_shrink_with_overlap() -> None:
    candidate = idea()
    close_peer = idea(title="Evidence cards")
    distant_peer = idea(
        title="Constraint auction",
        core_mechanism="A budget auction allocates scarce expert time.",
        problem_framing="Teams cannot decide which specialist should unblock work.",
        task_value="Spend expert attention on the highest leverage bottleneck.",
        distinguishing_features=("Bids must include a rollback plan.",),
    )

    close_score = score_novelty(
        candidate,
        peers=(close_peer,),
        obvious_solution="A shared board turns each claim into a living evidence card.",
        sources=(),
        branch_is_search_isolated=True,
        prior_art_failed=False,
    )
    distant_score = score_novelty(
        candidate,
        peers=(distant_peer,),
        obvious_solution="Hold another status meeting.",
        sources=(),
        branch_is_search_isolated=True,
        prior_art_failed=False,
    )

    assert close_score.peer_distance < distant_score.peer_distance
    assert close_score.baseline_distance < distant_score.baseline_distance
    assert close_score.prior_art_distance == pytest.approx(1.0)
