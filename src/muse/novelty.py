from __future__ import annotations

import re
from collections.abc import Iterable
from enum import StrEnum

from muse.inspiration import SourceAbstraction
from muse.models import FrozenModel, IdeaGenome, Score

TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


class CopyingClassification(StrEnum):
    INDEPENDENT = "independent"
    INSPIRED = "inspired"
    SYNTHESIZED = "synthesized"
    ADAPTED = "adapted"
    LIKELY_COPYING = "likely_copying"


class NoveltyScore(FrozenModel):
    peer_distance: Score
    baseline_distance: Score
    source_similarity_risk: Score
    prior_art_distance: Score
    coverage_confidence: Score
    branch_isolation_confidence: Score
    estimated_originality: Score
    classification: CopyingClassification


def score_novelty(
    candidate: IdeaGenome,
    peers: Iterable[IdeaGenome],
    obvious_solution: str,
    sources: Iterable[SourceAbstraction],
    branch_is_search_isolated: bool,
    prior_art_failed: bool,
) -> NoveltyScore:
    peer_similarity = _max_similarity(_idea_text(candidate), (_idea_text(peer) for peer in peers))
    baseline_similarity = _max_similarity(
        obvious_solution,
        _candidate_comparison_texts(candidate),
    )
    source_list = tuple(sources)
    source_similarity_risk = _source_similarity_risk(candidate, source_list)

    peer_distance = 1.0 - peer_similarity
    baseline_distance = 1.0 - baseline_similarity
    prior_art_distance = 1.0 - source_similarity_risk
    branch_isolation_confidence = 1.0 if branch_is_search_isolated else 0.35
    coverage_confidence = 0.35 if prior_art_failed else (0.8 if source_list else 0.6)
    estimated_originality = _clamp(
        (
            peer_distance
            + baseline_distance
            + prior_art_distance
            + branch_isolation_confidence
        )
        / 4
    )

    return NoveltyScore(
        peer_distance=_clamp(peer_distance),
        baseline_distance=_clamp(baseline_distance),
        source_similarity_risk=_clamp(source_similarity_risk),
        prior_art_distance=_clamp(prior_art_distance),
        coverage_confidence=coverage_confidence,
        branch_isolation_confidence=branch_isolation_confidence,
        estimated_originality=estimated_originality,
        classification=_classify(
            source_similarity_risk=source_similarity_risk,
            source_count=len(source_list),
            branch_is_search_isolated=branch_is_search_isolated,
        ),
    )


def _classify(
    *,
    source_similarity_risk: float,
    source_count: int,
    branch_is_search_isolated: bool,
) -> CopyingClassification:
    if source_similarity_risk >= 0.8:
        return CopyingClassification.LIKELY_COPYING
    if branch_is_search_isolated:
        return CopyingClassification.INDEPENDENT
    if source_count == 0:
        return CopyingClassification.INDEPENDENT
    if source_similarity_risk >= 0.65:
        return CopyingClassification.ADAPTED
    if source_count > 1 and source_similarity_risk >= 0.5:
        return CopyingClassification.SYNTHESIZED
    return CopyingClassification.INSPIRED


def _source_similarity_risk(
    candidate: IdeaGenome,
    sources: tuple[SourceAbstraction, ...],
) -> float:
    source_texts = tuple(
        text
        for source in sources
        for text in (source.mechanism, source.principle)
    )
    return _max_similarity_over_groups(_candidate_comparison_texts(candidate), source_texts)


def _candidate_comparison_texts(candidate: IdeaGenome) -> tuple[str, ...]:
    fields = (
        candidate.title,
        candidate.core_mechanism,
        candidate.problem_framing,
        candidate.task_value,
        " ".join(candidate.distinguishing_features),
    )
    return (*fields, " ".join(fields))


def _idea_text(idea: IdeaGenome) -> str:
    return " ".join(_candidate_comparison_texts(idea))


def _max_similarity_over_groups(left_texts: Iterable[str], right_texts: Iterable[str]) -> float:
    return max(
        (
            _lexical_similarity(left, right)
            for left in left_texts
            for right in right_texts
        ),
        default=0.0,
    )


def _max_similarity(text: str, comparisons: Iterable[str]) -> float:
    return max((_lexical_similarity(text, comparison) for comparison in comparisons), default=0.0)


def _lexical_similarity(left: str, right: str) -> float:
    left_tokens = set(TOKEN_PATTERN.findall(left.casefold()))
    right_tokens = set(TOKEN_PATTERN.findall(right.casefold()))
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def _clamp(value: float) -> float:
    return min(1.0, max(0.0, value))
