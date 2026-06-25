from __future__ import annotations

from dataclasses import dataclass

from creativity_layer.engine import CreativeEngine
from creativity_layer.inspiration import SourceAbstraction, abstract_sources
from creativity_layer.models import IdeaGenome, InspirationKind, RunConfig, RunResult, TaskContext
from creativity_layer.search import SearchProvider, SearchPurpose, SearchQuery


@dataclass(frozen=True)
class SearchAwareEngine:
    creative_provider: object
    search_provider: SearchProvider

    def run(self, task: TaskContext, config: RunConfig) -> RunResult:
        result = CreativeEngine(
            framer=self.creative_provider,
            seeder=self.creative_provider,
            transformer=self.creative_provider,
            evaluator=self.creative_provider,
        ).run(task, config)

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
        updated_by_id = {candidate.id: candidate for candidate in updated_candidates}
        updated_finalists = tuple(updated_by_id[candidate.id] for candidate in result.finalists)

        payload = result.model_dump(mode="json")
        payload["all_candidates"] = [
            candidate.model_dump(mode="json") for candidate in updated_candidates
        ]
        payload["finalists"] = [
            candidate.model_dump(mode="json") for candidate in updated_finalists
        ]
        payload["reproducibility_fingerprint"] = ""
        return RunResult.model_validate(payload)


def _isolate_seed_branches(
    candidates: tuple[IdeaGenome, ...],
    abstractions: tuple[SourceAbstraction, ...],
) -> tuple[IdeaGenome, ...]:
    seed_ids = tuple(candidate.id for candidate in candidates if candidate.generation == 0)
    independent_seed_ids = frozenset(seed_ids[: max(1, (len(seed_ids) + 1) // 2)])
    updated: list[IdeaGenome] = []
    for index, candidate in enumerate(candidates):
        if candidate.id in independent_seed_ids:
            updated.append(
                _candidate_with_provenance(
                    candidate,
                    inspiration_kind=InspirationKind.INDEPENDENT,
                    source_urls=(),
                    inspiration_principles=(),
                )
            )
        elif candidate.generation == 0 and abstractions:
            abstraction = abstractions[index % len(abstractions)]
            updated.append(
                _candidate_with_provenance(
                    candidate,
                    inspiration_kind=InspirationKind.INSPIRED,
                    source_urls=(abstraction.source_url,),
                    inspiration_principles=(abstraction.principle,),
                )
            )
        else:
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
