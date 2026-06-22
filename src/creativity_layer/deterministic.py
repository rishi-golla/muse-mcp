from __future__ import annotations

import hashlib

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
        candidates = tuple(
            IdeaGenome(
                generation=0,
                title=title,
                core_mechanism=mechanism,
                problem_framing=framing,
                assumptions_challenged=(framed_task.assumptions[index % 2],),
                task_value=f"Advances the goal: {framed_task.context.goal}",
                distinguishing_features=(mechanism,),
                inspiration_kind=InspirationKind.INDEPENDENT,
            )
            for index, (title, mechanism, framing) in enumerate(
                mechanisms[: config.seed_count]
            )
        )
        return MeteredResponse(
            value=candidates,
            provider=self.name,
            cost_usd=0.01,
            latency_ms=1,
        )

    def transform(
        self,
        request: TransformationRequest,
        parents: tuple[IdeaGenome, ...],
    ) -> MeteredResponse[IdeaGenome]:
        parent = parents[0]
        combined_title = " + ".join(item.title for item in parents)
        child = IdeaGenome(
            generation=max(item.generation for item in parents) + 1,
            title=f"{request.operator.value.title()}: {combined_title}",
            core_mechanism=(
                f"{request.operator.value}: replace the parent mechanism with a "
                f"task-specific structural alternative for '{request.task_goal}'."
            ),
            problem_framing=f"{request.operator.value}: {parent.problem_framing}",
            assumptions_challenged=parent.assumptions_challenged
            + (f"Operator applied: {request.operator.value}",),
            task_value=parent.task_value,
            distinguishing_features=parent.distinguishing_features
            + (request.instruction,),
            parent_ids=request.parent_ids,
            transformations=parent.transformations + (request.operator.value,),
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
