from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from uuid import UUID, uuid5

from creativity_layer.models import (
    EvaluationScores,
    FramedTask,
    IdeaGenome,
    InspirationKind,
    RunConfig,
    TaskContext,
)
from creativity_layer.providers import MeteredResponse
from creativity_layer.transforms import TransformationRequest

DETERMINISTIC_NAMESPACE = UUID("5c174f20-7173-54ec-8a72-10d7217bc63d")


def _stable_uuid(kind: str, payload: object) -> UUID:
    canonical_payload = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    )
    return uuid5(DETERMINISTIC_NAMESPACE, f"{kind}:{canonical_payload}")


def _unique(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


class DeterministicCreativeProvider:
    name = "deterministic-local"

    def frame(self, task: TaskContext) -> FramedTask:
        return FramedTask(
            context=task,
            assumptions=(
                "A decision requires a synchronous discussion.",
                "Every participant must respond to every proposal.",
            ),
            obvious_solution="Use an asynchronous voting tool.",
        )

    def seed(
        self,
        framed_task: FramedTask,
        config: RunConfig,
    ) -> MeteredResponse[tuple[IdeaGenome, ...]]:
        mechanisms = (
            (
                "Decision garden",
                "Proposals mature through evidence thresholds instead of deadlines.",
                "Treat decisions as claims that earn confidence over time.",
            ),
            (
                "Consent gradients",
                "People allocate reversible confidence rather than casting binary votes.",
                "Treat agreement as a changing field rather than a final event.",
            ),
            (
                "Silent delegation market",
                "Participants lend decision authority by topic and reclaim it at any time.",
                "Treat attention as a scarce resource that can be delegated.",
            ),
            (
                "Counterfactual ledger",
                "Teams record predictions and let outcomes settle recurring disputes.",
                "Treat decisions as testable forecasts rather than opinions.",
            ),
        )
        stable_context = {
            "task": framed_task.model_dump(mode="json"),
            "config": config.model_dump(mode="json"),
        }
        candidates = []
        for index in range(config.seed_count):
            title, mechanism, framing = mechanisms[index % len(mechanisms)]
            variant_number = index // len(mechanisms) + 1
            if variant_number > 1:
                title = f"{title} variant {variant_number}"
                mechanism = (
                    f"{mechanism} Structural variant {variant_number} routes the "
                    "mechanism through a distinct numbered pathway."
                )
                framing = (
                    f"{framing} Variant {variant_number} changes the structural "
                    "unit of coordination."
                )

            candidates.append(
                IdeaGenome(
                    id=_stable_uuid(
                        "seed",
                        {
                            **stable_context,
                            "index": index,
                            "title": title,
                            "mechanism": mechanism,
                            "framing": framing,
                        },
                    ),
                    generation=0,
                    title=title,
                    core_mechanism=mechanism,
                    problem_framing=framing,
                    assumptions_challenged=(
                        framed_task.assumptions[index % len(framed_task.assumptions)],
                    ),
                    task_value=f"Advances the goal: {framed_task.context.goal}",
                    distinguishing_features=(mechanism,),
                    inspiration_kind=InspirationKind.INDEPENDENT,
                )
            )
        return MeteredResponse(
            value=tuple(candidates),
            provider=self.name,
            cost_usd=0.01,
            latency_ms=1,
        )

    def transform(
        self,
        request: TransformationRequest,
        parents: tuple[IdeaGenome, ...],
    ) -> MeteredResponse[IdeaGenome]:
        actual_parent_ids = tuple(parent.id for parent in parents)
        if actual_parent_ids != request.parent_ids:
            raise ValueError(
                "actual parent IDs must exactly match request parent_ids"
            )

        combined_title = " + ".join(item.title for item in parents)
        combined_mechanisms = " + ".join(
            item.core_mechanism for item in parents
        )
        combined_framings = " + ".join(
            item.problem_framing for item in parents
        )
        combined_values = " + ".join(item.task_value for item in parents)
        combined_assumptions = _unique(
            assumption
            for parent in parents
            for assumption in parent.assumptions_challenged
        )
        combined_features = _unique(
            feature
            for parent in parents
            for feature in parent.distinguishing_features
        )
        prior_transformations = _unique(
            transformation
            for parent in parents
            for transformation in parent.transformations
        )
        child = IdeaGenome(
            id=_stable_uuid(
                "transform",
                {
                    "request": request.model_dump(mode="json"),
                    "parents": [
                        parent.model_dump(mode="json") for parent in parents
                    ],
                    "task_goal": request.task_goal,
                },
            ),
            generation=max(item.generation for item in parents) + 1,
            title=f"{request.operator.value.title()}: {combined_title}",
            core_mechanism=(
                f"{request.operator.value}: structurally transform "
                f"[{combined_mechanisms}] for '{request.task_goal}'."
            ),
            problem_framing=f"{request.operator.value}: {combined_framings}",
            assumptions_challenged=combined_assumptions
            + (f"Operator applied: {request.operator.value}",),
            task_value=combined_values,
            distinguishing_features=combined_features + (request.instruction,),
            parent_ids=actual_parent_ids,
            transformations=prior_transformations + (request.operator.value,),
            inspiration_kind=InspirationKind.SYNTHESIZED,
        )
        return MeteredResponse(
            value=child,
            provider=self.name,
            cost_usd=0.01,
            latency_ms=1,
        )

    def evaluate(
        self,
        candidate: IdeaGenome,
        framed_task: FramedTask,
    ) -> MeteredResponse[EvaluationScores]:
        digest = hashlib.sha256(
            f"{candidate.title}|{candidate.core_mechanism}|{framed_task.context.goal}".encode()
        ).digest()

        def score(offset: int, floor: float) -> float:
            return round(floor + (digest[offset] / 255) * (1 - floor), 4)

        scores = EvaluationScores(
            originality=score(0, 0.45),
            usefulness=score(1, 0.50),
            coherence=score(2, 0.65),
            feasibility=score(3, 0.45),
            user_fit=score(4, 0.50),
        )
        return MeteredResponse(
            value=scores,
            provider=self.name,
            cost_usd=0.005,
            latency_ms=1,
        )
