from __future__ import annotations

import hashlib
import json
import os
import random
from pathlib import Path
from tempfile import NamedTemporaryFile

from pydantic import Field, model_validator

from creativity_layer.models import FrozenModel, IdeaGenome, RequiredText, RunResult

PACKET_VERSION = "review-packet-v1"


class ReviewTask(FrozenModel):
    goal: RequiredText
    audience: RequiredText | None = None
    constraints: tuple[RequiredText, ...] = ()
    preferences: tuple[RequiredText, ...] = ()
    risk_tolerance: float = Field(strict=True, ge=0.0, le=1.0)


class ReviewRubric(FrozenModel):
    originality_prompt: RequiredText
    usefulness_prompt: RequiredText
    coherence_prompt: RequiredText
    feasibility_prompt: RequiredText
    user_fit_prompt: RequiredText
    overall_prompt: RequiredText


class ReviewCandidate(FrozenModel):
    label: RequiredText
    title: RequiredText
    core_mechanism: RequiredText
    problem_framing: RequiredText
    task_value: RequiredText
    distinguishing_features: tuple[RequiredText, ...] = ()
    assumptions_challenged: tuple[RequiredText, ...] = ()
    first_order_effects: tuple[RequiredText, ...] = ()
    second_order_effects: tuple[RequiredText, ...] = ()
    feasibility_assumptions: tuple[RequiredText, ...] = ()
    uncertainties: tuple[RequiredText, ...] = ()
    weaknesses: tuple[RequiredText, ...] = ()
    inspiration_kind: RequiredText


class ReviewPacketMetadata(FrozenModel):
    run_id: RequiredText
    stopped_reason: RequiredText
    candidate_count: int = Field(strict=True, ge=1)
    shuffle_seed: int = Field(strict=True)


class ReviewPacket(FrozenModel):
    packet_id: RequiredText
    packet_version: RequiredText
    task: ReviewTask
    rubric: ReviewRubric
    candidates: tuple[ReviewCandidate, ...]
    metadata: ReviewPacketMetadata

    @model_validator(mode="after")
    def reject_empty_or_mismatched_candidates(self) -> ReviewPacket:
        if not self.candidates:
            raise ValueError("review packet must contain at least one candidate")
        if self.metadata.candidate_count != len(self.candidates):
            raise ValueError("candidate_count must match candidates")
        return self


class ReviewPacketStore:
    def __init__(self, root: Path) -> None:
        self._root = root

    def save(self, packet: ReviewPacket) -> Path:
        self._root.mkdir(parents=True, exist_ok=True)
        path = self._root / f"{packet.packet_id}.review-packet.json"
        temp_path: Path | None = None
        try:
            with NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="\n",
                dir=self._root,
                prefix=f".{packet.packet_id}.",
                suffix=".tmp",
                delete=False,
            ) as temp_file:
                temp_path = Path(temp_file.name)
                temp_file.write(json.dumps(packet.model_dump(mode="json"), indent=2))
                temp_file.flush()
                os.fsync(temp_file.fileno())

            os.replace(temp_path, path)
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)
        return path


DEFAULT_RUBRIC = ReviewRubric(
    originality_prompt="How novel is this candidate relative to obvious solutions?",
    usefulness_prompt="How useful is this candidate for the stated task?",
    coherence_prompt="How internally coherent and understandable is this candidate?",
    feasibility_prompt="How feasible is this candidate under the stated constraints?",
    user_fit_prompt="How well does this candidate fit the stated audience and preferences?",
    overall_prompt="Which candidate would you prefer overall for the stated task?",
)


def build_review_packet(result: RunResult, *, shuffle_seed: int = 0) -> ReviewPacket:
    candidates = tuple(
        _candidate_from_genome(candidate, label=label)
        for label, candidate in _labeled_shuffled_finalists(result, shuffle_seed)
    )
    return ReviewPacket(
        packet_id=_packet_id(result, shuffle_seed),
        packet_version=PACKET_VERSION,
        task=_review_task(result),
        rubric=DEFAULT_RUBRIC,
        candidates=candidates,
        metadata=ReviewPacketMetadata(
            run_id=str(result.run_id),
            stopped_reason=result.stopped_reason,
            candidate_count=len(candidates),
            shuffle_seed=shuffle_seed,
        ),
    )


def _labeled_shuffled_finalists(
    result: RunResult, shuffle_seed: int
) -> tuple[tuple[str, IdeaGenome], ...]:
    shuffled = list(result.finalists)
    seed_material = f"{PACKET_VERSION}:{result.reproducibility_fingerprint}:{shuffle_seed}"
    random.Random(seed_material).shuffle(shuffled)
    return tuple((chr(ord("A") + index), candidate) for index, candidate in enumerate(shuffled))


def _candidate_from_genome(candidate: IdeaGenome, *, label: str) -> ReviewCandidate:
    return ReviewCandidate(
        label=label,
        title=candidate.title,
        core_mechanism=candidate.core_mechanism,
        problem_framing=candidate.problem_framing,
        task_value=candidate.task_value,
        distinguishing_features=candidate.distinguishing_features,
        assumptions_challenged=candidate.assumptions_challenged,
        first_order_effects=candidate.first_order_effects,
        second_order_effects=candidate.second_order_effects,
        feasibility_assumptions=candidate.feasibility_assumptions,
        uncertainties=candidate.uncertainties,
        weaknesses=candidate.weaknesses,
        inspiration_kind=str(candidate.inspiration_kind),
    )


def _review_task(result: RunResult) -> ReviewTask:
    context = result.framed_task.context
    return ReviewTask(
        goal=context.goal,
        audience=context.audience,
        constraints=context.constraints,
        preferences=context.preferences,
        risk_tolerance=context.risk_tolerance,
    )


def _packet_id(result: RunResult, shuffle_seed: int) -> str:
    payload = {
        "packet_version": PACKET_VERSION,
        "run_fingerprint": result.reproducibility_fingerprint,
        "shuffle_seed": shuffle_seed,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
