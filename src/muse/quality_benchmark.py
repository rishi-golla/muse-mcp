from __future__ import annotations

from enum import StrEnum

from pydantic import Field, model_validator

from muse.models import FrozenModel, RequiredText


class Preference(StrEnum):
    A = "a"
    B = "b"
    TIE = "tie"


class BenchmarkTask(FrozenModel):
    name: RequiredText
    domain: RequiredText
    prompt: RequiredText


class BenchmarkArtifact(FrozenModel):
    content: RequiredText
    cost_usd: float = Field(strict=True, ge=0.0)
    latency_ms: float = Field(strict=True, ge=0.0)


class PairwiseJudgment(FrozenModel):
    preference: Preference
    confidence: float = Field(strict=True, ge=0.0, le=1.0)
    rationale: RequiredText
    originality: Preference
    usefulness: Preference
    operational_specificity: Preference
    task_fit: Preference


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
