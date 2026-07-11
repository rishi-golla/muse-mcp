from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum
from math import sqrt
from random import Random

from pydantic import Field, model_validator

from muse.models import FrozenModel, RequiredText


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


PairwiseJudge = Callable[[BenchmarkTask, JudgeArtifact, JudgeArtifact], PairwiseJudgment]


class GenerationFailure(FrozenModel):
    system: BenchmarkSystem
    error_type: RequiredText
    message: RequiredText


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
    judgment: PairwiseJudgment | None = None

    @model_validator(mode="after")
    def require_blinded_judgment_for_successful_generations(self) -> BenchmarkRecord:
        completed_generations = (
            self.muse.artifact is not None and self.baseline.artifact is not None
        )
        blinded_fields = (self.candidate_a, self.candidate_b, self.muse_label, self.judgment)
        if completed_generations and any(value is None for value in blinded_fields):
            raise ValueError("successful generations require a blinded judgment")
        if not completed_generations and any(value is not None for value in blinded_fields):
            raise ValueError("failed generations must not be scored")
        if self.muse_label == Preference.TIE:
            raise ValueError("muse label must identify candidate a or b")
        return self


class BenchmarkReport(FrozenModel):
    records: tuple[BenchmarkRecord, ...]
    generation_attempts: int = Field(strict=True, ge=0)
    generation_failures: int = Field(strict=True, ge=0)
    judged_comparisons: int = Field(strict=True, ge=0)
    wins: int = Field(strict=True, ge=0)
    losses: int = Field(strict=True, ge=0)
    ties: int = Field(strict=True, ge=0)
    decisive_comparisons: int = Field(strict=True, ge=0)
    preference_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    wilson_lower: float | None = Field(default=None, ge=0.0, le=1.0)
    wilson_upper: float | None = Field(default=None, ge=0.0, le=1.0)
    total_cost_usd: float = Field(strict=True, ge=0.0)
    total_latency_ms: float = Field(strict=True, ge=0.0)


def _capture_generation(
    system: BenchmarkSystem, generator: ArtifactGenerator, task: BenchmarkTask
) -> GenerationAttempt:
    try:
        return GenerationAttempt(artifact=generator(task))
    except Exception as error:
        return GenerationAttempt(
            failure=GenerationFailure(
                system=system,
                error_type=type(error).__name__,
                message=str(error) or type(error).__name__,
            )
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
) -> BenchmarkReport:
    """Run reproducible, blinded pairwise comparisons over a benchmark corpus."""
    if isinstance(repetitions, bool) or not isinstance(repetitions, int) or repetitions < 1:
        raise ValueError("repetitions must be a positive integer")
    if isinstance(random_seed, bool) or not isinstance(random_seed, int):
        raise ValueError("random_seed must be an integer")

    random_source = Random(random_seed)
    records: list[BenchmarkRecord] = []

    for task in corpus.tasks:
        for repetition in range(1, repetitions + 1):
            muse = _capture_generation(BenchmarkSystem.MUSE, muse_generator, task)
            baseline = _capture_generation(BenchmarkSystem.BASELINE, baseline_generator, task)
            if muse.artifact is None or baseline.artifact is None:
                records.append(
                    BenchmarkRecord(task=task, repetition=repetition, muse=muse, baseline=baseline)
                )
                continue

            if random_source.getrandbits(1):
                candidate_a = muse.artifact.for_judge()
                candidate_b = baseline.artifact.for_judge()
                muse_label = Preference.A
            else:
                candidate_a = baseline.artifact.for_judge()
                candidate_b = muse.artifact.for_judge()
                muse_label = Preference.B

            judgment = judge(task, candidate_a, candidate_b)
            if not isinstance(judgment, PairwiseJudgment):
                raise TypeError("judge must return PairwiseJudgment")
            records.append(
                BenchmarkRecord(
                    task=task,
                    repetition=repetition,
                    muse=muse,
                    baseline=baseline,
                    candidate_a=candidate_a,
                    candidate_b=candidate_b,
                    muse_label=muse_label,
                    judgment=judgment,
                )
            )

    wins = sum(
        record.judgment is not None
        and record.judgment.preference != Preference.TIE
        and record.judgment.preference == record.muse_label
        for record in records
    )
    losses = sum(
        record.judgment is not None
        and record.judgment.preference != Preference.TIE
        and record.judgment.preference != record.muse_label
        for record in records
    )
    ties = sum(
        record.judgment is not None and record.judgment.preference == Preference.TIE
        for record in records
    )
    decisive_comparisons = wins + losses
    bounds = _wilson_bounds(wins, decisive_comparisons)
    attempts = tuple(attempt for record in records for attempt in (record.muse, record.baseline))

    return BenchmarkReport(
        records=tuple(records),
        generation_attempts=len(attempts),
        generation_failures=sum(attempt.failure is not None for attempt in attempts),
        judged_comparisons=wins + losses + ties,
        wins=wins,
        losses=losses,
        ties=ties,
        decisive_comparisons=decisive_comparisons,
        preference_rate=wins / decisive_comparisons if decisive_comparisons else None,
        wilson_lower=bounds[0] if bounds is not None else None,
        wilson_upper=bounds[1] if bounds is not None else None,
        total_cost_usd=sum(
            attempt.artifact.cost_usd for attempt in attempts if attempt.artifact is not None
        ),
        total_latency_ms=sum(
            attempt.artifact.latency_ms for attempt in attempts if attempt.artifact is not None
        ),
    )


class BenchmarkCorpus(FrozenModel):
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
