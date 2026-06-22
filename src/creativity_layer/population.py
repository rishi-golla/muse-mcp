from __future__ import annotations

from creativity_layer.models import IdeaGenome


def _require_scores(candidate: IdeaGenome) -> None:
    if candidate.scores is None:
        raise ValueError(f"candidate {candidate.id} has no evaluation scores")


def _dominates(left: IdeaGenome, right: IdeaGenome) -> bool:
    _require_scores(left)
    _require_scores(right)
    assert left.scores is not None
    assert right.scores is not None

    left_values = (left.scores.originality, left.scores.usefulness)
    right_values = (right.scores.originality, right.scores.usefulness)
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
        for candidate in candidates:
            _require_scores(candidate)
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
        for candidate in candidates:
            _require_scores(candidate)

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
            key=lambda candidate: candidate.scores.originality
            if candidate.scores is not None
            else -1,
        )

        selected = list((frontier + remaining)[:finalist_count])
        if wildcard not in selected:
            if len(selected) >= finalist_count:
                selected[-1] = wildcard
            else:
                selected.append(wildcard)
        return tuple(selected)

    @staticmethod
    def _balanced_rank(candidate: IdeaGenome) -> tuple[float, float, float]:
        assert candidate.scores is not None
        joint = min(candidate.scores.originality, candidate.scores.usefulness)
        total = candidate.scores.originality + candidate.scores.usefulness
        return joint, total, candidate.scores.coherence
