from __future__ import annotations

from muse.models import IdeaGenome


def _require_scores(candidate: IdeaGenome) -> None:
    if candidate.scores is None:
        raise ValueError(f"candidate {candidate.id} has no evaluation scores")


def _validate_candidates(candidates: tuple[IdeaGenome, ...]) -> None:
    candidate_ids = [candidate.id for candidate in candidates]
    if len(candidate_ids) != len(set(candidate_ids)):
        raise ValueError("duplicate candidate id")
    for candidate in candidates:
        _require_scores(candidate)


def _dominates(left: IdeaGenome, right: IdeaGenome) -> bool:
    _require_scores(left)
    _require_scores(right)
    assert left.scores is not None
    assert right.scores is not None

    left_values = (
        left.scores.originality,
        left.scores.usefulness,
        left.scores.operational_specificity,
        left.scores.workflow_fit,
    )
    right_values = (
        right.scores.originality,
        right.scores.usefulness,
        right.scores.operational_specificity,
        right.scores.workflow_fit,
    )
    return all(a >= b for a, b in zip(left_values, right_values, strict=True)) and any(
        a > b for a, b in zip(left_values, right_values, strict=True)
    )


class PopulationManager:
    def __init__(self, minimum_wildcard_coherence: float = 0.5) -> None:
        self._minimum_wildcard_coherence = minimum_wildcard_coherence

    def pareto_frontier(
        self,
        candidates: tuple[IdeaGenome, ...],
    ) -> tuple[IdeaGenome, ...]:
        _validate_candidates(candidates)
        return tuple(
            candidate
            for candidate in candidates
            if not any(
                other.id != candidate.id and _dominates(other, candidate)
                for other in candidates
            )
        )

    def select(
        self,
        candidates: tuple[IdeaGenome, ...],
        *,
        finalist_count: int,
    ) -> tuple[IdeaGenome, ...]:
        if finalist_count < 1:
            raise ValueError("finalist_count must be positive")
        if not candidates:
            raise ValueError("candidates must not be empty")
        _validate_candidates(candidates)

        frontier = sorted(
            self.pareto_frontier(candidates),
            key=self._balanced_rank,
            reverse=True,
        )
        remaining = sorted(
            (candidate for candidate in candidates if candidate not in frontier),
            key=self._balanced_rank,
            reverse=True,
        )
        wildcard = max(
            (
                candidate
                for candidate in candidates
                if candidate.scores is not None
                and candidate.scores.coherence >= self._minimum_wildcard_coherence
            ),
            key=lambda candidate: (
                candidate.scores.originality if candidate.scores is not None else -1,
                str(candidate.id),
            ),
            default=None,
        )

        selected = list((frontier + remaining)[:finalist_count])
        if wildcard is not None and wildcard not in selected and finalist_count > 1:
            if len(selected) >= finalist_count:
                selected[-1] = wildcard
            else:
                selected.append(wildcard)
        return tuple(selected)

    @staticmethod
    def _balanced_rank(candidate: IdeaGenome) -> tuple[float, float, float, str]:
        assert candidate.scores is not None
        joint = min(
            candidate.scores.originality,
            candidate.scores.usefulness,
            candidate.scores.operational_specificity,
            candidate.scores.workflow_fit,
        )
        total = (
            candidate.scores.originality
            + candidate.scores.usefulness
            + candidate.scores.operational_specificity
            + candidate.scores.workflow_fit
        )
        return joint, total, candidate.scores.coherence, str(candidate.id)
