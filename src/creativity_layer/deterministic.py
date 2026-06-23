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
from creativity_layer.providers import MeteredResponse, OperationQuote
from creativity_layer.transforms import (
    OperatorName,
    TransformationRequest,
    expected_transformation_history,
)

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


def _structural_mechanism(
    request: TransformationRequest,
    parents: tuple[IdeaGenome, ...],
) -> str:
    parent = parents[0]
    goal = request.task_goal

    match request.operator:
        case OperatorName.INVERT:
            return (
                f"{parent.title} becomes an exception-triggered release loop: "
                f"the default advances {goal}, while evidence derived from "
                f"'{parent.problem_framing}' can pause or reverse it."
            )
        case OperatorName.TRANSFER:
            return (
                f"{parent.title} operates as a queueing-control system: signals "
                f"from '{parent.problem_framing}' set priority, scarce attention "
                f"becomes capacity, and feedback reallocates service toward {goal}."
            )
        case OperatorName.EXAGGERATE:
            return (
                f"{parent.title} makes progress toward '{parent.task_value}' the "
                f"dominant control signal: each outcome amplifies or suppresses "
                f"the next allocation until the system converges on {goal}."
            )
        case OperatorName.SUBTRACT:
            return (
                f"{parent.title} removes the central coordinator and replaces it "
                f"with local state transitions; participants react only to changes "
                f"in '{parent.problem_framing}' that affect {goal}."
            )
        case OperatorName.REFRAME:
            return (
                f"{parent.title} treats '{parent.problem_framing}' as a sensing "
                f"problem: probes create evidence, evidence updates shared state, "
                f"and the state selects the next action toward {goal}."
            )
        case OperatorName.CONTRADICT:
            return (
                f"{parent.title} runs two coupled control loops: one protects "
                f"the state implied by '{parent.problem_framing}', while the other "
                f"challenges it; action occurs only when both loops improve {goal}."
            )
        case OperatorName.PERSONALIZE:
            return (
                f"{parent.title} assigns each participant a private threshold "
                f"derived from '{parent.problem_framing}'; observed responses tune "
                f"those thresholds before the group advances {goal}."
            )
        case OperatorName.DISTILL:
            return (
                f"{parent.title} reduces to a signal-update-action cycle: detect "
                f"changes relevant to '{parent.problem_framing}', update confidence, "
                f"then trigger the smallest action that advances {goal}."
            )
        case OperatorName.COMBINE:
            first, second = parents
            return (
                f"{first.title} supplies state signals that regulate {second.title}; "
                f"{second.title} feeds outcome evidence back to adjust the first "
                f"system's thresholds, forming a closed control loop for {goal}."
            )


class DeterministicCreativeProvider:
    name = "deterministic-local"
    version = "1"

    def quote_seed(
        self,
        framed_task: FramedTask,
        config: RunConfig,
    ) -> OperationQuote:
        return OperationQuote(max_cost_usd=0.01, calls=1)

    def quote_transform(
        self,
        request: TransformationRequest,
        parents: tuple[IdeaGenome, ...],
    ) -> OperationQuote:
        return OperationQuote(max_cost_usd=0.01, calls=1)

    def quote_evaluation(self, framed_task: FramedTask) -> OperationQuote:
        return OperationQuote(max_cost_usd=0.005, calls=1)

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
                        (
                            framed_task.assumptions[
                                index % len(framed_task.assumptions)
                            ],
                        )
                        if framed_task.assumptions
                        else ()
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

        if request.operator is OperatorName.COMBINE:
            first, second = parents
            combined_title = f"{first.title} regulates {second.title}"
            combined_framings = (
                f"{first.problem_framing} interacts with "
                f"{second.problem_framing} through feedback."
            )
            combined_values = (
                f"{first.task_value} Outcomes then control how "
                f"{second.task_value.lower()}"
            )
        else:
            combined_title = parents[0].title
            combined_framings = parents[0].problem_framing
            combined_values = parents[0].task_value
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
            core_mechanism=_structural_mechanism(request, parents),
            problem_framing=f"{request.operator.value}: {combined_framings}",
            assumptions_challenged=combined_assumptions
            + (f"Operator applied: {request.operator.value}",),
            task_value=combined_values,
            distinguishing_features=combined_features + (request.instruction,),
            parent_ids=actual_parent_ids,
            transformations=expected_transformation_history(
                request.operator,
                parents,
            ),
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
