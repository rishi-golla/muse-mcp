from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from muse.engine import CreativeEngine
from muse.inspiration import SourceAbstraction, abstract_sources
from muse.models import IdeaGenome, InspirationKind, RunConfig, RunResult, TaskContext
from muse.novelty import CopyingClassification, score_novelty
from muse.search import SearchProvider, SearchPurpose, SearchQuery


@dataclass(frozen=True)
class SearchAwareEngine:
    creative_provider: object
    search_provider: SearchProvider
    reject_likely_copying: bool = False

    def run(self, task: TaskContext, config: RunConfig) -> RunResult:
        result = CreativeEngine(
            framer=self.creative_provider,
            seeder=self.creative_provider,
            transformer=self.creative_provider,
            evaluator=self.creative_provider,
        ).run(task, config)

        if not result.all_candidates:
            return result

        search_response = self.search_provider.search(
            SearchQuery(
                text=task.goal,
                purpose=SearchPurpose.NOVELTY,
                limit=max(1, config.seed_count // 2),
                freshness_bucket="static",
            )
        )
        abstractions = abstract_sources(search_response.results, task_goal=task.goal)
        updated_candidates = _isolate_seed_branches(result.all_candidates, abstractions)
        updated_candidates, updated_finalists = _score_finalists_for_copying(
            finalists=result.finalists,
            candidates=updated_candidates,
            abstractions=abstractions,
            obvious_solution=result.framed_task.obvious_solution,
            reject_likely_copying=self.reject_likely_copying,
        )

        payload = result.model_dump(mode="json")
        payload["all_candidates"] = [
            candidate.model_dump(mode="json") for candidate in updated_candidates
        ]
        payload["finalists"] = [
            candidate.model_dump(mode="json") for candidate in updated_finalists
        ]
        payload["reproducibility_fingerprint"] = ""
        return RunResult.model_validate(payload)


def _score_finalists_for_copying(
    *,
    finalists: tuple[IdeaGenome, ...],
    candidates: tuple[IdeaGenome, ...],
    abstractions: tuple[SourceAbstraction, ...],
    obvious_solution: str,
    reject_likely_copying: bool,
) -> tuple[tuple[IdeaGenome, ...], tuple[IdeaGenome, ...]]:
    updated_by_id = {candidate.id: candidate for candidate in candidates}
    rejected_ids = set()

    for finalist in finalists:
        candidate = updated_by_id[finalist.id]
        score = score_novelty(
            candidate,
            peers=tuple(peer for peer in candidates if peer.id != candidate.id),
            obvious_solution=obvious_solution,
            sources=abstractions,
            branch_is_search_isolated=(
                candidate.inspiration_kind is InspirationKind.INDEPENDENT
            ),
            prior_art_failed=False,
        )
        if score.classification is not CopyingClassification.LIKELY_COPYING:
            continue
        updated_by_id[candidate.id] = _candidate_with_provenance(
            candidate,
            inspiration_kind=InspirationKind.LIKELY_COPYING,
            source_urls=candidate.source_urls,
            inspiration_principles=candidate.inspiration_principles,
        )
        if reject_likely_copying:
            rejected_ids.add(candidate.id)

    updated_candidates = tuple(updated_by_id[candidate.id] for candidate in candidates)
    updated_finalists = tuple(
        updated_by_id[finalist.id]
        for finalist in finalists
        if finalist.id not in rejected_ids
    )
    return updated_candidates, updated_finalists


def _isolate_seed_branches(
    candidates: tuple[IdeaGenome, ...],
    abstractions: tuple[SourceAbstraction, ...],
) -> tuple[IdeaGenome, ...]:
    seed_ids = tuple(candidate.id for candidate in candidates if candidate.generation == 0)
    independent_seed_ids = frozenset(seed_ids[: max(1, (len(seed_ids) + 1) // 2)])
    seed_updated: list[IdeaGenome] = []
    for index, candidate in enumerate(candidates):
        if candidate.id in independent_seed_ids:
            seed_updated.append(
                _candidate_with_provenance(
                    candidate,
                    inspiration_kind=InspirationKind.INDEPENDENT,
                    source_urls=(),
                    inspiration_principles=(),
                )
            )
        elif candidate.generation == 0 and abstractions:
            abstraction = abstractions[index % len(abstractions)]
            seed_updated.append(
                _candidate_with_provenance(
                    candidate,
                    inspiration_kind=InspirationKind.INSPIRED,
                    source_urls=(abstraction.source_url,),
                    inspiration_principles=(abstraction.principle,),
                )
            )
        else:
            seed_updated.append(candidate)
    return _inherit_parent_provenance(tuple(seed_updated))


def _inherit_parent_provenance(
    candidates: tuple[IdeaGenome, ...],
) -> tuple[IdeaGenome, ...]:
    updated_by_id: dict[UUID, IdeaGenome] = {}
    updated: list[IdeaGenome] = []
    for candidate in candidates:
        parent_urls: list[str] = []
        parent_principles: list[str] = []
        for parent_id in candidate.parent_ids:
            parent = updated_by_id[parent_id]
            parent_urls.extend(parent.source_urls)
            parent_principles.extend(parent.inspiration_principles)

        source_urls = _unique((*parent_urls, *candidate.source_urls))
        inspiration_principles = _unique(
            (*parent_principles, *candidate.inspiration_principles)
        )
        if (
            candidate.generation > 0
            and (parent_urls or parent_principles)
            and (
                source_urls != candidate.source_urls
                or inspiration_principles != candidate.inspiration_principles
            )
        ):
            candidate = _candidate_with_provenance(
                candidate,
                inspiration_kind=candidate.inspiration_kind,
                source_urls=source_urls,
                inspiration_principles=inspiration_principles,
            )
        updated_by_id[candidate.id] = candidate
        updated.append(candidate)
    return tuple(updated)


def _candidate_with_provenance(
    candidate: IdeaGenome,
    *,
    inspiration_kind: InspirationKind,
    source_urls: tuple[str, ...],
    inspiration_principles: tuple[str, ...],
) -> IdeaGenome:
    payload = candidate.model_dump(mode="python")
    payload["inspiration_kind"] = inspiration_kind
    payload["source_urls"] = source_urls
    payload["inspiration_principles"] = inspiration_principles
    return IdeaGenome.model_validate(payload)


def _unique(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))
