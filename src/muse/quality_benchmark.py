from __future__ import annotations

import re
from collections.abc import Callable
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
from math import sqrt

from pydantic import AwareDatetime, Field, model_validator

from muse.models import FrozenModel, RequiredText
from muse.privacy import TraceView


class Preference(StrEnum):
    A = "a"
    B = "b"
    TIE = "tie"


class BenchmarkSystem(StrEnum):
    MUSE = "muse"
    BASELINE = "baseline"


class BenchmarkTask(FrozenModel):
    name: RequiredText
    domain: RequiredText
    prompt: RequiredText


class JudgeArtifact(FrozenModel):
    content: RequiredText


class BenchmarkArtifact(FrozenModel):
    content: RequiredText
    cost_usd: float = Field(strict=True, ge=0.0)
    latency_ms: float = Field(strict=True, ge=0.0)

    def for_judge(self) -> JudgeArtifact:
        return JudgeArtifact(content=self.content)


ArtifactGenerator = Callable[[BenchmarkTask], BenchmarkArtifact]


class PairwiseJudgment(FrozenModel):
    preference: Preference
    confidence: float = Field(strict=True, ge=0.0, le=1.0)
    rationale: RequiredText
    originality: Preference
    usefulness: Preference
    operational_specificity: Preference
    task_fit: Preference


class JudgeFailure(FrozenModel):
    error_type: RequiredText
    message: RequiredText


class JudgeAttempt(FrozenModel):
    judgment: PairwiseJudgment | None = None
    failure: JudgeFailure | None = None
    cost_usd: float = Field(strict=True, ge=0.0)
    latency_ms: float = Field(strict=True, ge=0.0)

    @model_validator(mode="after")
    def require_exactly_one_outcome(self) -> JudgeAttempt:
        if (self.judgment is None) == (self.failure is None):
            raise ValueError("judge attempt requires exactly one judgment or failure")
        return self


PairwiseJudge = Callable[[BenchmarkTask, JudgeArtifact, JudgeArtifact], JudgeAttempt]


class RunMetadata(FrozenModel):
    random_seed: int = Field(strict=True)
    repetitions: int = Field(strict=True, ge=1)
    corpus_version: RequiredText
    run_timestamp: AwareDatetime
    prompt_version: RequiredText
    config_version: RequiredText
    muse_adapter: RequiredText
    baseline_adapter: RequiredText
    judge_adapter: RequiredText
    blind_labels: tuple[RequiredText, ...] = ()
    system_identifiers: tuple[RequiredText, ...] = ()
    provider_labels: tuple[RequiredText, ...] = ()


class GenerationFailure(FrozenModel):
    system: BenchmarkSystem
    error_type: RequiredText
    message: RequiredText
    cost_usd: float = Field(default=0.0, strict=True, ge=0.0)
    latency_ms: float = Field(default=0.0, strict=True, ge=0.0)
    leaked_labels: tuple[RequiredText, ...] = ()


class GenerationAttempt(FrozenModel):
    artifact: BenchmarkArtifact | None = None
    failure: GenerationFailure | None = None

    @model_validator(mode="after")
    def require_exactly_one_outcome(self) -> GenerationAttempt:
        if (self.artifact is None) == (self.failure is None):
            raise ValueError("generation attempt requires exactly one artifact or failure")
        return self


class BenchmarkRecord(FrozenModel):
    task: BenchmarkTask
    repetition: int = Field(strict=True, ge=1)
    muse: GenerationAttempt
    baseline: GenerationAttempt
    candidate_a: JudgeArtifact | None = None
    candidate_b: JudgeArtifact | None = None
    muse_label: Preference | None = None
    judge_attempt: JudgeAttempt | None = None

    @model_validator(mode="after")
    def require_blinded_judgment_for_successful_generations(self) -> BenchmarkRecord:
        completed_generations = (
            self.muse.artifact is not None and self.baseline.artifact is not None
        )
        blinded_fields = (
            self.candidate_a,
            self.candidate_b,
            self.muse_label,
            self.judge_attempt,
        )
        if completed_generations and any(value is None for value in blinded_fields):
            raise ValueError("successful generations require a blinded judgment")
        if not completed_generations and any(value is not None for value in blinded_fields):
            raise ValueError("failed generations must not be scored")
        if self.muse_label == Preference.TIE:
            raise ValueError("muse label must identify candidate a or b")
        return self

    @property
    def judgment(self) -> PairwiseJudgment | None:
        if self.judge_attempt is None:
            return None
        return self.judge_attempt.judgment


class BenchmarkReport(FrozenModel):
    metadata: RunMetadata
    records: tuple[BenchmarkRecord, ...]
    generation_attempts: int = Field(strict=True, ge=0)
    generation_failures: int = Field(strict=True, ge=0)
    judge_attempts: int = Field(strict=True, ge=0)
    judge_failures: int = Field(strict=True, ge=0)
    judged_comparisons: int = Field(strict=True, ge=0)
    task_comparisons: int = Field(strict=True, ge=0)
    repetition_wins: int = Field(strict=True, ge=0)
    repetition_losses: int = Field(strict=True, ge=0)
    repetition_ties: int = Field(strict=True, ge=0)
    wins: int = Field(strict=True, ge=0)
    losses: int = Field(strict=True, ge=0)
    ties: int = Field(strict=True, ge=0)
    decisive_comparisons: int = Field(strict=True, ge=0)
    preference_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    wilson_lower: float | None = Field(default=None, ge=0.0, le=1.0)
    wilson_upper: float | None = Field(default=None, ge=0.0, le=1.0)
    generation_cost_usd: float = Field(strict=True, ge=0.0)
    generation_latency_ms: float = Field(strict=True, ge=0.0)
    judge_cost_usd: float = Field(strict=True, ge=0.0)
    judge_latency_ms: float = Field(strict=True, ge=0.0)
    total_cost_usd: float = Field(strict=True, ge=0.0)
    total_latency_ms: float = Field(strict=True, ge=0.0)

    @property
    def run_metadata(self) -> RunMetadata:
        return self.metadata


def _capture_generation(
    system: BenchmarkSystem,
    generator: ArtifactGenerator,
    task: BenchmarkTask,
    secret_values: tuple[str, ...],
) -> GenerationAttempt:
    try:
        artifact = generator(task)
        return GenerationAttempt(artifact=artifact)
    except Exception as error:
        return GenerationAttempt(
            failure=GenerationFailure(
                system=system,
                error_type=type(error).__name__,
                message=_sanitize_failure_message(error, secret_values),
            )
        )


def _sanitize_failure_message(error: Exception, secret_values: tuple[str, ...]) -> str:
    sanitized = TraceView(secret_values=secret_values).sanitize(str(error))
    message = " ".join(str(sanitized).split())
    return message[:200] or type(error).__name__


def _label_leaks(content: str, labels: tuple[str, ...]) -> tuple[str, ...]:
    leaks: list[str] = []
    for label in labels:
        pattern = rf"(?<![A-Za-z0-9_]){re.escape(label)}(?![A-Za-z0-9_])"
        if re.search(pattern, content, flags=re.IGNORECASE):
            leaks.append(label)
    return tuple(leaks)


def _reject_label_leak(
    system: BenchmarkSystem, attempt: GenerationAttempt, labels: tuple[str, ...]
) -> GenerationAttempt:
    if attempt.artifact is None:
        return attempt

    artifact = attempt.artifact
    leaked_labels = _label_leaks(artifact.content, labels)
    if not leaked_labels:
        return attempt

    return GenerationAttempt(
        failure=GenerationFailure(
            system=system,
            error_type="ArtifactLabelLeak",
            message="generated artifact contains a configured blind label",
            cost_usd=artifact.cost_usd,
            latency_ms=artifact.latency_ms,
            leaked_labels=leaked_labels,
        )
    )


def derive_candidate_assignment(
    random_seed: int, task: BenchmarkTask, repetition: int
) -> Preference:
    """Derive one stable A/B assignment without consuming shared RNG state."""
    if isinstance(random_seed, bool) or not isinstance(random_seed, int):
        raise ValueError("random_seed must be an integer")
    if isinstance(repetition, bool) or not isinstance(repetition, int) or repetition < 1:
        raise ValueError("repetition must be a positive integer")

    key = f"{random_seed}\x00{task.name}\x00{repetition}".encode()
    return Preference.A if sha256(key).digest()[0] & 1 else Preference.B


def _capture_judge(
    judge: PairwiseJudge,
    task: BenchmarkTask,
    candidate_a: JudgeArtifact,
    candidate_b: JudgeArtifact,
    secret_values: tuple[str, ...],
) -> JudgeAttempt:
    try:
        attempt = judge(task, candidate_a, candidate_b)
        if not isinstance(attempt, JudgeAttempt):
            raise TypeError("judge must return JudgeAttempt")
        return attempt
    except Exception as error:
        return JudgeAttempt(
            failure=JudgeFailure(
                error_type=type(error).__name__,
                message=_sanitize_failure_message(error, secret_values),
            ),
            cost_usd=0.0,
            latency_ms=0.0,
        )


def _wilson_bounds(wins: int, decisive_comparisons: int) -> tuple[float, float] | None:
    if decisive_comparisons == 0:
        return None

    z_score = 1.959963984540054
    rate = wins / decisive_comparisons
    denominator = 1 + z_score**2 / decisive_comparisons
    center = (rate + z_score**2 / (2 * decisive_comparisons)) / denominator
    margin = (
        z_score
        * sqrt(
            (rate * (1 - rate) + z_score**2 / (4 * decisive_comparisons))
            / decisive_comparisons
        )
        / denominator
    )
    return center - margin, center + margin


def run_quality_benchmark(
    corpus: BenchmarkCorpus,
    muse_generator: ArtifactGenerator,
    baseline_generator: ArtifactGenerator,
    judge: PairwiseJudge,
    *,
    repetitions: int = 1,
    random_seed: int = 0,
    run_timestamp: datetime,
    prompt_version: str,
    config_version: str,
    muse_adapter: str = "muse",
    baseline_adapter: str = "baseline",
    judge_adapter: str = "judge",
    blind_labels: tuple[str, ...] = (),
    system_identifiers: tuple[str, ...] = (),
    provider_labels: tuple[str, ...] = (),
    secret_values: tuple[str, ...] = (),
) -> BenchmarkReport:
    """Run reproducible, blinded pairwise comparisons over a benchmark corpus."""
    if isinstance(repetitions, bool) or not isinstance(repetitions, int) or repetitions < 1:
        raise ValueError("repetitions must be a positive integer")
    if isinstance(random_seed, bool) or not isinstance(random_seed, int):
        raise ValueError("random_seed must be an integer")

    metadata = RunMetadata(
        random_seed=random_seed,
        repetitions=repetitions,
        corpus_version=corpus.version,
        run_timestamp=run_timestamp,
        prompt_version=prompt_version,
        config_version=config_version,
        muse_adapter=muse_adapter,
        baseline_adapter=baseline_adapter,
        judge_adapter=judge_adapter,
        blind_labels=blind_labels,
        system_identifiers=system_identifiers,
        provider_labels=provider_labels,
    )
    blind_labels = tuple(
        dict.fromkeys(
            (
                *metadata.blind_labels,
                *metadata.system_identifiers,
                *metadata.provider_labels,
            )
        )
    )
    records: list[BenchmarkRecord] = []

    for task in corpus.tasks:
        for repetition in range(1, repetitions + 1):
            muse = _capture_generation(
                BenchmarkSystem.MUSE, muse_generator, task, secret_values
            )
            baseline = _capture_generation(
                BenchmarkSystem.BASELINE, baseline_generator, task, secret_values
            )
            muse = _reject_label_leak(BenchmarkSystem.MUSE, muse, blind_labels)
            baseline = _reject_label_leak(BenchmarkSystem.BASELINE, baseline, blind_labels)
            if muse.artifact is None or baseline.artifact is None:
                records.append(
                    BenchmarkRecord(task=task, repetition=repetition, muse=muse, baseline=baseline)
                )
                continue

            muse_label = derive_candidate_assignment(random_seed, task, repetition)
            if muse_label == Preference.A:
                candidate_a = muse.artifact.for_judge()
                candidate_b = baseline.artifact.for_judge()
            else:
                candidate_a = baseline.artifact.for_judge()
                candidate_b = muse.artifact.for_judge()

            judge_attempt = _capture_judge(
                judge, task, candidate_a, candidate_b, secret_values
            )
            records.append(
                BenchmarkRecord(
                    task=task,
                    repetition=repetition,
                    muse=muse,
                    baseline=baseline,
                    candidate_a=candidate_a,
                    candidate_b=candidate_b,
                    muse_label=muse_label,
                    judge_attempt=judge_attempt,
                )
            )

    outcomes_by_task: dict[str, list[Preference]] = {}
    for record in records:
        if record.judgment is None:
            continue
        if record.judgment.preference == Preference.TIE:
            outcome = Preference.TIE
        elif record.judgment.preference == record.muse_label:
            outcome = Preference.A
        else:
            outcome = Preference.B
        outcomes_by_task.setdefault(record.task.name, []).append(outcome)

    repetition_wins = sum(
        outcome == Preference.A for outcomes in outcomes_by_task.values() for outcome in outcomes
    )
    repetition_losses = sum(
        outcome == Preference.B for outcomes in outcomes_by_task.values() for outcome in outcomes
    )
    repetition_ties = sum(
        outcome == Preference.TIE for outcomes in outcomes_by_task.values() for outcome in outcomes
    )
    wins = losses = ties = 0
    for outcomes in outcomes_by_task.values():
        decisive_wins = sum(outcome == Preference.A for outcome in outcomes)
        decisive_losses = sum(outcome == Preference.B for outcome in outcomes)
        if decisive_wins > decisive_losses:
            wins += 1
        elif decisive_losses > decisive_wins:
            losses += 1
        else:
            ties += 1

    judged_comparisons = repetition_wins + repetition_losses + repetition_ties
    task_comparisons = len(outcomes_by_task)
    decisive_comparisons = wins + losses
    bounds = _wilson_bounds(wins, decisive_comparisons)
    attempts = tuple(attempt for record in records for attempt in (record.muse, record.baseline))
    generation_cost_usd = sum(
        attempt.artifact.cost_usd
        if attempt.artifact is not None
        else attempt.failure.cost_usd
        if attempt.failure is not None
        else 0.0
        for attempt in attempts
    )
    generation_latency_ms = sum(
        attempt.artifact.latency_ms
        if attempt.artifact is not None
        else attempt.failure.latency_ms
        if attempt.failure is not None
        else 0.0
        for attempt in attempts
    )
    judge_attempts = tuple(
        record.judge_attempt for record in records if record.judge_attempt is not None
    )
    judge_cost_usd = sum(attempt.cost_usd for attempt in judge_attempts)
    judge_latency_ms = sum(attempt.latency_ms for attempt in judge_attempts)

    return BenchmarkReport(
        metadata=metadata,
        records=tuple(records),
        generation_attempts=len(attempts),
        generation_failures=sum(attempt.failure is not None for attempt in attempts),
        judge_attempts=len(judge_attempts),
        judge_failures=sum(attempt.failure is not None for attempt in judge_attempts),
        judged_comparisons=judged_comparisons,
        task_comparisons=task_comparisons,
        repetition_wins=repetition_wins,
        repetition_losses=repetition_losses,
        repetition_ties=repetition_ties,
        wins=wins,
        losses=losses,
        ties=ties,
        decisive_comparisons=decisive_comparisons,
        preference_rate=wins / decisive_comparisons if decisive_comparisons else None,
        wilson_lower=bounds[0] if bounds is not None else None,
        wilson_upper=bounds[1] if bounds is not None else None,
        generation_cost_usd=generation_cost_usd,
        generation_latency_ms=generation_latency_ms,
        judge_cost_usd=judge_cost_usd,
        judge_latency_ms=judge_latency_ms,
        total_cost_usd=generation_cost_usd + judge_cost_usd,
        total_latency_ms=generation_latency_ms + judge_latency_ms,
    )


class BenchmarkCorpus(FrozenModel):
    version: RequiredText = "v1"
    tasks: tuple[BenchmarkTask, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def reject_duplicate_task_names(self) -> BenchmarkCorpus:
        names = tuple(task.name for task in self.tasks)
        if len(set(names)) != len(names):
            raise ValueError("benchmark task names must be unique")
        return self


DEFAULT_BENCHMARK_CORPUS = BenchmarkCorpus(
    tasks=(
        BenchmarkTask(
            name="failure-localization",
            domain="coding",
            prompt="Locate an intermittent integration-test failure in a Python service.",
        ),
        BenchmarkTask(
            name="dependency-migration",
            domain="coding",
            prompt="Plan a safe migration from a deprecated JavaScript package in a monorepo.",
        ),
        BenchmarkTask(
            name="query-performance",
            domain="coding",
            prompt="Investigate and remediate a slow database query on a growing table.",
        ),
        BenchmarkTask(
            name="cli-error-guidance",
            domain="coding",
            prompt="Improve CLI guidance when a required config file is missing.",
        ),
        BenchmarkTask(
            name="event-consumer-reliability",
            domain="coding",
            prompt="Handle duplicate events in an order-processing consumer.",
        ),
        BenchmarkTask(
            name="release-automation",
            domain="coding",
            prompt="Stage release automation for a TypeScript service across environments.",
        ),
        BenchmarkTask(
            name="onboarding-friction",
            domain="product",
            prompt="Reduce first-session friction in a collaboration product for small teams.",
        ),
        BenchmarkTask(
            name="pricing-packaging",
            domain="product",
            prompt="Package a new analytics capability for subscription customers.",
        ),
        BenchmarkTask(
            name="marketplace-supply",
            domain="product",
            prompt="Attract reliable early supply to a local services marketplace.",
        ),
        BenchmarkTask(
            name="retention-controls",
            domain="product",
            prompt="Give workspace administrators clearer data-retention controls.",
        ),
        BenchmarkTask(
            name="experiment-metric",
            domain="product",
            prompt="Evaluate a new feature-discovery experiment.",
        ),
        BenchmarkTask(
            name="enterprise-expansion",
            domain="product",
            prompt="Expand a lightweight tool into regulated enterprise accounts.",
        ),
        BenchmarkTask(
            name="climate-dashboard",
            domain="design",
            prompt="Help residents understand neighborhood heat risks through a city dashboard.",
        ),
        BenchmarkTask(
            name="permit-progress",
            domain="design",
            prompt="Show permit applicants why progress has stalled without calling staff.",
        ),
        BenchmarkTask(
            name="study-planner",
            domain="design",
            prompt="Plan short study sessions around work for adult learners.",
        ),
        BenchmarkTask(
            name="mobile-keyboard",
            domain="design",
            prompt="Support frequent language switching in mobile text entry.",
        ),
        BenchmarkTask(
            name="financial-overview",
            domain="design",
            prompt="Give freelancers a calm view of irregular income.",
        ),
        BenchmarkTask(
            name="accessible-scheduling",
            domain="design",
            prompt="Schedule clinic appointments for people using varied assistive technology.",
        ),
        BenchmarkTask(
            name="incident-handoff",
            domain="operations",
            prompt="Improve on-call handoffs during a prolonged production incident.",
        ),
        BenchmarkTask(
            name="warehouse-coordination",
            domain="operations",
            prompt="Coordinate warehouse teams amid unpredictable inbound deliveries.",
        ),
        BenchmarkTask(
            name="escalation-routing",
            domain="operations",
            prompt="Route customer escalations across support, billing, and engineering.",
        ),
        BenchmarkTask(
            name="access-review",
            domain="operations",
            prompt="Review software access regularly at a fast-growing company.",
        ),
        BenchmarkTask(
            name="quarterly-planning",
            domain="operations",
            prompt="Create a lightweight quarterly planning rhythm for distributed teams.",
        ),
        BenchmarkTask(
            name="vendor-continuity",
            domain="operations",
            prompt="Prepare for intermittent fulfillment delays from a critical vendor.",
        ),
        BenchmarkTask(
            name="literature-signals",
            domain="research",
            prompt="Find emerging signals in a fast-moving scientific literature area.",
        ),
        BenchmarkTask(
            name="interview-synthesis",
            domain="research",
            prompt="Synthesize conflicting patterns from a set of user interviews.",
        ),
        BenchmarkTask(
            name="model-evaluation",
            domain="research",
            prompt="Evaluate a language model that drafts internal knowledge articles.",
        ),
        BenchmarkTask(
            name="policy-landscape",
            domain="research",
            prompt="Track policy changes affecting a regional energy program.",
        ),
        BenchmarkTask(
            name="pricing-research",
            domain="research",
            prompt="Understand how small businesses assess a new service price.",
        ),
        BenchmarkTask(
            name="field-study",
            domain="research",
            prompt="Observe how nurses coordinate across shift changes in a field study.",
        ),
    )
)
