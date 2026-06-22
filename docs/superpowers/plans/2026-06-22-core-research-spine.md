# Core Research Spine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a deterministic, runnable vertical slice of the Creativity Layer that frames a task, creates structured idea genomes, applies structural transformations, tracks cost, preserves a wildcard, selects a Pareto frontier, and writes a reproducible trace.

**Architecture:** A Python package exposes small domain modules with immutable Pydantic models and protocol-based provider boundaries. A synchronous `CreativeEngine` coordinates framing, seeding, transformation, budget accounting, population selection, and trace persistence. This milestone deliberately uses deterministic local providers so the research spine can be tested without network access or paid model calls.

**Tech Stack:** Python 3.12+, Pydantic 2.x, pytest, pytest-cov, Ruff, standard-library JSON persistence

---

## Milestone Boundaries

This is the first of four Phase 1 implementation milestones:

1. **Core research spine — this plan:** deterministic end-to-end loop, structured genomes, transformations, Pareto selection, budgets, traces, and CLI.
2. **Model/search and novelty pipeline:** live model providers, inspiration abstraction, embedding and structural novelty, prior-art search, retries, and similarity safeguards.
3. **Domain adapters and experiment harness:** eight benchmark families, baseline conditions, randomization, blind review packets, and multi-budget execution.
4. **Evaluation and research hardening:** human scoring ingestion, statistical reports, resume support, provider audits, and research-validity tests.

The first milestone does not claim to implement all Phase 1 research capabilities. It creates the smallest complete system on which later milestones can add external intelligence without replacing the core contracts.

## File Map

```text
pyproject.toml                                  Project metadata and tool configuration
README.md                                       Local setup and deterministic demo instructions
src/creativity_layer/__init__.py                Public package exports
src/creativity_layer/models.py                  Immutable domain models and validation
src/creativity_layer/providers.py               Framer, seeder, and transformer protocols
src/creativity_layer/deterministic.py           Local deterministic provider implementations
src/creativity_layer/budget.py                  Budget reservation and spend accounting
src/creativity_layer/population.py              Population state, Pareto frontier, wildcard policy
src/creativity_layer/transforms.py              Structural transformation operator definitions
src/creativity_layer/tracing.py                 Reproducible JSON trace persistence
src/creativity_layer/engine.py                  End-to-end orchestration
src/creativity_layer/cli.py                     Command-line entry point
tests/test_models.py                            Domain-model behavior
tests/test_budget.py                            Budget accounting behavior
tests/test_population.py                        Frontier and wildcard behavior
tests/test_transforms.py                        Operator behavior
tests/test_deterministic.py                     Deterministic provider behavior
tests/test_tracing.py                           Trace persistence behavior
tests/test_engine.py                            End-to-end pipeline behavior
tests/test_cli.py                               CLI behavior
```

### Task 1: Scaffold the Python Package

**Files:**
- Create: `pyproject.toml`
- Create: `README.md`
- Create: `src/creativity_layer/__init__.py`
- Create: `tests/test_package.py`

- [ ] **Step 1: Write the failing package import test**

```python
# tests/test_package.py
def test_package_exposes_version() -> None:
    import creativity_layer

    assert creativity_layer.__version__ == "0.1.0"
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```powershell
python -m pytest tests/test_package.py -v
```

Expected: FAIL because `creativity_layer` does not exist.

- [ ] **Step 3: Add project configuration**

```toml
# pyproject.toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "creativity-layer"
version = "0.1.0"
description = "Research prototype for evolutionary creative search in AI agents"
readme = "README.md"
requires-python = ">=3.12"
dependencies = [
  "pydantic>=2,<3",
]

[project.optional-dependencies]
dev = [
  "pytest>=8,<10",
  "pytest-cov>=5,<8",
  "ruff>=0.8,<1",
]

[project.scripts]
creativity-layer = "creativity_layer.cli:main"

[tool.hatch.build.targets.wheel]
packages = ["src/creativity_layer"]

[tool.pytest.ini_options]
addopts = "-ra"
testpaths = ["tests"]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM"]
```

- [ ] **Step 4: Add the package entry module**

```python
# src/creativity_layer/__init__.py
"""Creativity Layer research prototype."""

__version__ = "0.1.0"
```

- [ ] **Step 5: Add the initial README**

````markdown
# Creativity Layer

A research prototype for testing whether evolutionary creative search produces ideas
that humans judge as simultaneously more original and useful than strong prompting.

The first implementation milestone is intentionally deterministic. It validates the
core orchestration, data contracts, budget accounting, selection behavior, and trace
reproducibility before paid model and search providers are introduced.

## Development

```powershell
python -m pip install -e ".[dev]"
python -m pytest
python -m ruff check .
```
````

- [ ] **Step 6: Install the package and run the test**

Run:

```powershell
python -m pip install -e ".[dev]"
python -m pytest tests/test_package.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add pyproject.toml README.md src/creativity_layer/__init__.py tests/test_package.py
git commit -m "build: scaffold creativity layer package"
```

### Task 2: Define the Core Domain Models

**Files:**
- Create: `src/creativity_layer/models.py`
- Create: `tests/test_models.py`
- Modify: `src/creativity_layer/__init__.py`

- [ ] **Step 1: Write failing tests for task context and idea genomes**

```python
# tests/test_models.py
from uuid import UUID

import pytest
from pydantic import ValidationError

from creativity_layer.models import (
    EvaluationScores,
    IdeaGenome,
    InspirationKind,
    RunConfig,
    TaskContext,
)


def test_task_context_requires_a_non_blank_goal() -> None:
    with pytest.raises(ValidationError):
        TaskContext(goal="   ")


def test_idea_genome_records_ancestry_and_separate_scores() -> None:
    parent = IdeaGenome(
        generation=0,
        title="Borrow time",
        core_mechanism="Trade scheduling rights instead of fixed calendar slots.",
        problem_framing="Coordination is treated as ownership of time.",
        task_value="Reduces scheduling negotiation.",
        distinguishing_features=("transferable scheduling rights",),
    )

    child = IdeaGenome(
        generation=1,
        title="Time market",
        core_mechanism="Let participants exchange priority tokens.",
        problem_framing="Coordination is a constrained allocation market.",
        task_value="Makes urgency explicit.",
        distinguishing_features=("priority tokens",),
        parent_ids=(parent.id,),
        transformations=("transfer",),
        inspiration_kind=InspirationKind.SYNTHESIZED,
        scores=EvaluationScores(
            originality=0.9,
            usefulness=0.7,
            coherence=0.8,
            feasibility=0.6,
            user_fit=0.75,
        ),
    )

    assert isinstance(child.id, UUID)
    assert child.parent_ids == (parent.id,)
    assert child.scores.originality == 0.9
    assert child.scores.usefulness == 0.7


def test_run_config_rejects_impossible_reservations() -> None:
    with pytest.raises(ValidationError):
        RunConfig(
            max_cost_usd=1,
            max_calls=4,
            framing_reserve_usd=0.6,
            finalization_reserve_usd=0.5,
        )
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_models.py -v
```

Expected: FAIL because `creativity_layer.models` does not exist.

- [ ] **Step 3: Implement immutable domain models**

```python
# src/creativity_layer/models.py
from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

Score = Annotated[float, Field(ge=0.0, le=1.0)]


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class InspirationKind(StrEnum):
    INDEPENDENT = "independent"
    INSPIRED = "inspired"
    SYNTHESIZED = "synthesized"
    ADAPTED = "adapted"


class TaskContext(FrozenModel):
    goal: str = Field(min_length=1)
    audience: str | None = None
    constraints: tuple[str, ...] = ()
    preferences: tuple[str, ...] = ()
    risk_tolerance: Score = 0.5

    @model_validator(mode="after")
    def reject_blank_goal(self) -> TaskContext:
        if not self.goal.strip():
            raise ValueError("goal must not be blank")
        return self


class EvaluationScores(FrozenModel):
    originality: Score
    usefulness: Score
    coherence: Score
    feasibility: Score
    user_fit: Score


class IdeaGenome(FrozenModel):
    id: UUID = Field(default_factory=uuid4)
    generation: int = Field(ge=0)
    title: str = Field(min_length=1)
    core_mechanism: str = Field(min_length=1)
    problem_framing: str = Field(min_length=1)
    assumptions_challenged: tuple[str, ...] = ()
    task_value: str = Field(min_length=1)
    distinguishing_features: tuple[str, ...] = ()
    inspiration_principles: tuple[str, ...] = ()
    source_urls: tuple[str, ...] = ()
    first_order_effects: tuple[str, ...] = ()
    second_order_effects: tuple[str, ...] = ()
    feasibility_assumptions: tuple[str, ...] = ()
    uncertainties: tuple[str, ...] = ()
    weaknesses: tuple[str, ...] = ()
    parent_ids: tuple[UUID, ...] = ()
    transformations: tuple[str, ...] = ()
    inspiration_kind: InspirationKind = InspirationKind.INDEPENDENT
    scores: EvaluationScores | None = None
    branch_cost_usd: float = Field(default=0.0, ge=0.0)
    branch_latency_ms: int = Field(default=0, ge=0)


class RunConfig(FrozenModel):
    max_cost_usd: float = Field(default=1.0, gt=0)
    max_calls: int = Field(default=20, gt=0)
    max_generations: int = Field(default=2, ge=0)
    seed_count: int = Field(default=4, ge=2)
    finalist_count: int = Field(default=3, ge=1)
    framing_reserve_usd: float = Field(default=0.05, ge=0)
    finalization_reserve_usd: float = Field(default=0.10, ge=0)
    random_seed: int = 0

    @model_validator(mode="after")
    def reservations_fit_budget(self) -> RunConfig:
        reserved = self.framing_reserve_usd + self.finalization_reserve_usd
        if reserved > self.max_cost_usd:
            raise ValueError("reserved cost exceeds maximum cost")
        if self.finalist_count > self.seed_count:
            raise ValueError("finalist_count cannot exceed seed_count")
        return self


class FramedTask(FrozenModel):
    context: TaskContext
    assumptions: tuple[str, ...]
    obvious_solution: str
    evaluation_dimensions: tuple[str, ...] = (
        "originality",
        "usefulness",
        "coherence",
        "feasibility",
        "user_fit",
    )


class SpendRecord(FrozenModel):
    stage: str
    provider: str
    cost_usd: float = Field(ge=0)
    latency_ms: int = Field(ge=0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class RunResult(FrozenModel):
    run_id: UUID = Field(default_factory=uuid4)
    framed_task: FramedTask
    finalists: tuple[IdeaGenome, ...]
    all_candidates: tuple[IdeaGenome, ...]
    spend_records: tuple[SpendRecord, ...]
    stopped_reason: str
```

- [ ] **Step 4: Export the public models**

```python
# src/creativity_layer/__init__.py
"""Creativity Layer research prototype."""

from creativity_layer.models import (
    EvaluationScores,
    FramedTask,
    IdeaGenome,
    InspirationKind,
    RunConfig,
    RunResult,
    TaskContext,
)

__version__ = "0.1.0"

__all__ = [
    "EvaluationScores",
    "FramedTask",
    "IdeaGenome",
    "InspirationKind",
    "RunConfig",
    "RunResult",
    "TaskContext",
]
```

- [ ] **Step 5: Run the model tests**

Run:

```powershell
python -m pytest tests/test_models.py -v
```

Expected: 3 tests PASS.

- [ ] **Step 6: Run all tests and lint**

Run:

```powershell
python -m pytest
python -m ruff check .
```

Expected: all tests PASS and Ruff exits 0.

- [ ] **Step 7: Commit**

```powershell
git add src/creativity_layer/models.py src/creativity_layer/__init__.py tests/test_models.py
git commit -m "feat: define creativity domain models"
```

### Task 3: Implement Strict Budget Accounting

**Files:**
- Create: `src/creativity_layer/budget.py`
- Create: `tests/test_budget.py`

- [ ] **Step 1: Write failing budget tests**

```python
# tests/test_budget.py
import pytest

from creativity_layer.budget import BudgetController, BudgetExceeded
from creativity_layer.models import RunConfig


def test_budget_reserves_finalization_capacity() -> None:
    budget = BudgetController(
        RunConfig(
            max_cost_usd=1.0,
            max_calls=5,
            framing_reserve_usd=0.1,
            finalization_reserve_usd=0.2,
        )
    )

    budget.charge("framing", "local", 0.1, 10)
    budget.charge("seeding", "local", 0.69, 20)

    assert budget.available_for_exploration_usd == pytest.approx(0.01)
    assert budget.can_afford(0.02, preserve_finalization=True) is False
    assert budget.can_afford(0.2, preserve_finalization=False) is True


def test_budget_rejects_cost_or_call_overruns() -> None:
    budget = BudgetController(
        RunConfig(
            max_cost_usd=0.5,
            max_calls=1,
            framing_reserve_usd=0,
            finalization_reserve_usd=0,
        )
    )

    budget.charge("seed", "local", 0.4, 1)

    with pytest.raises(BudgetExceeded, match="call limit"):
        budget.charge("transform", "local", 0.01, 1)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_budget.py -v
```

Expected: FAIL because `creativity_layer.budget` does not exist.

- [ ] **Step 3: Implement the budget controller**

```python
# src/creativity_layer/budget.py
from __future__ import annotations

from creativity_layer.models import RunConfig, SpendRecord


class BudgetExceeded(RuntimeError):
    """Raised when a run would exceed its configured budget."""


class BudgetController:
    def __init__(self, config: RunConfig) -> None:
        self._config = config
        self._records: list[SpendRecord] = []

    @property
    def records(self) -> tuple[SpendRecord, ...]:
        return tuple(self._records)

    @property
    def spent_usd(self) -> float:
        return sum(record.cost_usd for record in self._records)

    @property
    def calls_used(self) -> int:
        return len(self._records)

    @property
    def remaining_usd(self) -> float:
        return max(0.0, self._config.max_cost_usd - self.spent_usd)

    @property
    def available_for_exploration_usd(self) -> float:
        return max(0.0, self.remaining_usd - self._config.finalization_reserve_usd)

    def can_afford(self, cost_usd: float, *, preserve_finalization: bool) -> bool:
        available = (
            self.available_for_exploration_usd
            if preserve_finalization
            else self.remaining_usd
        )
        return self.calls_used < self._config.max_calls and cost_usd <= available + 1e-9

    def charge(
        self,
        stage: str,
        provider: str,
        cost_usd: float,
        latency_ms: int,
    ) -> SpendRecord:
        if self.calls_used >= self._config.max_calls:
            raise BudgetExceeded("call limit exceeded")
        if cost_usd > self.remaining_usd + 1e-9:
            raise BudgetExceeded("cost limit exceeded")

        record = SpendRecord(
            stage=stage,
            provider=provider,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
        )
        self._records.append(record)
        return record
```

- [ ] **Step 4: Run the budget tests**

Run:

```powershell
python -m pytest tests/test_budget.py -v
```

Expected: 2 tests PASS.

- [ ] **Step 5: Run all tests and lint**

Run:

```powershell
python -m pytest
python -m ruff check .
```

Expected: all tests PASS and Ruff exits 0.

- [ ] **Step 6: Commit**

```powershell
git add src/creativity_layer/budget.py tests/test_budget.py
git commit -m "feat: add strict run budget accounting"
```

### Task 4: Implement Pareto Selection and Wildcard Retention

**Files:**
- Create: `src/creativity_layer/population.py`
- Create: `tests/test_population.py`

- [ ] **Step 1: Write failing population tests**

```python
# tests/test_population.py
from creativity_layer.models import EvaluationScores, IdeaGenome
from creativity_layer.population import PopulationManager


def candidate(
    title: str,
    *,
    originality: float,
    usefulness: float,
    coherence: float = 0.8,
) -> IdeaGenome:
    return IdeaGenome(
        generation=0,
        title=title,
        core_mechanism=f"{title} mechanism",
        problem_framing=f"{title} framing",
        task_value=f"{title} value",
        distinguishing_features=(title,),
        scores=EvaluationScores(
            originality=originality,
            usefulness=usefulness,
            coherence=coherence,
            feasibility=0.7,
            user_fit=0.7,
        ),
    )


def test_frontier_keeps_non_dominated_candidates() -> None:
    original = candidate("original", originality=0.95, usefulness=0.55)
    useful = candidate("useful", originality=0.60, usefulness=0.95)
    dominated = candidate("dominated", originality=0.50, usefulness=0.50)

    selected = PopulationManager().select(
        (original, useful, dominated),
        finalist_count=2,
    )

    assert {item.title for item in selected} == {"original", "useful"}


def test_wildcard_preserves_most_original_coherent_candidate() -> None:
    balanced = candidate("balanced", originality=0.75, usefulness=0.8)
    wildcard = candidate("wildcard", originality=0.99, usefulness=0.2, coherence=0.65)
    random_noise = candidate("noise", originality=1.0, usefulness=0.1, coherence=0.1)

    selected = PopulationManager(minimum_wildcard_coherence=0.6).select(
        (balanced, wildcard, random_noise),
        finalist_count=2,
    )

    assert [item.title for item in selected] == ["balanced", "wildcard"]


def test_selection_fills_capacity_after_the_frontier() -> None:
    best = candidate("best", originality=0.9, usefulness=0.9)
    second = candidate("second", originality=0.8, usefulness=0.8)
    third = candidate("third", originality=0.7, usefulness=0.7)

    selected = PopulationManager().select(
        (best, second, third),
        finalist_count=3,
    )

    assert [item.title for item in selected] == ["best", "second", "third"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_population.py -v
```

Expected: FAIL because `creativity_layer.population` does not exist.

- [ ] **Step 3: Implement population selection**

```python
# src/creativity_layer/population.py
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
```

- [ ] **Step 4: Run the population tests**

Run:

```powershell
python -m pytest tests/test_population.py -v
```

Expected: 3 tests PASS.

- [ ] **Step 5: Run all tests and lint**

Run:

```powershell
python -m pytest
python -m ruff check .
```

Expected: all tests PASS and Ruff exits 0.

- [ ] **Step 6: Commit**

```powershell
git add src/creativity_layer/population.py tests/test_population.py
git commit -m "feat: select creative Pareto frontier"
```

### Task 5: Define Structural Transformation Operators

**Files:**
- Create: `src/creativity_layer/transforms.py`
- Create: `tests/test_transforms.py`

- [ ] **Step 1: Write failing transformation tests**

```python
# tests/test_transforms.py
from creativity_layer.models import IdeaGenome
from creativity_layer.transforms import OperatorName, TransformationRequest


def test_transformation_request_records_structural_intent() -> None:
    parent = IdeaGenome(
        generation=0,
        title="Queue",
        core_mechanism="People wait in arrival order.",
        problem_framing="Demand exceeds immediate capacity.",
        assumptions_challenged=(),
        task_value="Creates predictable access.",
        distinguishing_features=("arrival order",),
    )

    request = TransformationRequest.for_operator(
        operator=OperatorName.INVERT,
        parents=(parent,),
        task_goal="Make waiting fairer without a visible queue.",
    )

    assert request.operator is OperatorName.INVERT
    assert request.parent_ids == (parent.id,)
    assert "Reverse a foundational assumption" in request.instruction
    assert "Do not merely rename" in request.instruction


def test_combine_requires_two_parents() -> None:
    parent = IdeaGenome(
        generation=0,
        title="Queue",
        core_mechanism="People wait in arrival order.",
        problem_framing="Demand exceeds immediate capacity.",
        task_value="Creates predictable access.",
    )

    try:
        TransformationRequest.for_operator(
            operator=OperatorName.COMBINE,
            parents=(parent,),
            task_goal="Improve access.",
        )
    except ValueError as error:
        assert str(error) == "combine requires exactly two parents"
    else:
        raise AssertionError("combine accepted one parent")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_transforms.py -v
```

Expected: FAIL because `creativity_layer.transforms` does not exist.

- [ ] **Step 3: Implement operator definitions**

```python
# src/creativity_layer/transforms.py
from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from pydantic import Field

from creativity_layer.models import FrozenModel, IdeaGenome


class OperatorName(StrEnum):
    INVERT = "invert"
    TRANSFER = "transfer"
    COMBINE = "combine"
    EXAGGERATE = "exaggerate"
    SUBTRACT = "subtract"
    REFRAME = "reframe"
    CONTRADICT = "contradict"
    PERSONALIZE = "personalize"
    DISTILL = "distill"


OPERATOR_INSTRUCTIONS: dict[OperatorName, str] = {
    OperatorName.INVERT: "Reverse a foundational assumption and trace the consequences.",
    OperatorName.TRANSFER: "Import an abstract mechanism from a distant domain.",
    OperatorName.COMBINE: "Merge compatible mechanisms, not surface descriptions.",
    OperatorName.EXAGGERATE: "Push one meaningful property to an extreme.",
    OperatorName.SUBTRACT: "Remove a supposedly essential component.",
    OperatorName.REFRAME: "Redefine the underlying problem before proposing an answer.",
    OperatorName.CONTRADICT: "Satisfy two goals that initially appear incompatible.",
    OperatorName.PERSONALIZE: "Reshape the mechanism around the current user and task.",
    OperatorName.DISTILL: "Remove borrowed surface traits while retaining useful principles.",
}


class TransformationRequest(FrozenModel):
    operator: OperatorName
    parent_ids: tuple[UUID, ...] = Field(min_length=1, max_length=2)
    task_goal: str = Field(min_length=1)
    instruction: str = Field(min_length=1)

    @classmethod
    def for_operator(
        cls,
        *,
        operator: OperatorName,
        parents: tuple[IdeaGenome, ...],
        task_goal: str,
    ) -> TransformationRequest:
        if operator is OperatorName.COMBINE and len(parents) != 2:
            raise ValueError("combine requires exactly two parents")
        if operator is not OperatorName.COMBINE and len(parents) != 1:
            raise ValueError(f"{operator.value} requires exactly one parent")

        instruction = (
            f"{OPERATOR_INSTRUCTIONS[operator]} "
            "Change the idea's causal or structural mechanism. "
            "Do not merely rename, restyle, or reword the parent."
        )
        return cls(
            operator=operator,
            parent_ids=tuple(parent.id for parent in parents),
            task_goal=task_goal,
            instruction=instruction,
        )
```

- [ ] **Step 4: Run the transformation tests**

Run:

```powershell
python -m pytest tests/test_transforms.py -v
```

Expected: 2 tests PASS.

- [ ] **Step 5: Run all tests and lint**

Run:

```powershell
python -m pytest
python -m ruff check .
```

Expected: all tests PASS and Ruff exits 0.

- [ ] **Step 6: Commit**

```powershell
git add src/creativity_layer/transforms.py tests/test_transforms.py
git commit -m "feat: define structural transformation operators"
```

### Task 6: Define Provider Contracts and Deterministic Providers

**Files:**
- Create: `src/creativity_layer/providers.py`
- Create: `src/creativity_layer/deterministic.py`
- Create: `tests/test_deterministic.py`

- [ ] **Step 1: Write failing deterministic-provider tests**

```python
# tests/test_deterministic.py
from creativity_layer.deterministic import DeterministicCreativeProvider
from creativity_layer.models import RunConfig, TaskContext
from creativity_layer.transforms import OperatorName, TransformationRequest


def test_provider_frames_and_seeds_reproducibly() -> None:
    provider = DeterministicCreativeProvider()
    task = TaskContext(
        goal="Invent a calmer way for distributed teams to make decisions.",
        constraints=("No meetings",),
    )

    framed = provider.frame(task)
    first = provider.seed(framed, RunConfig(seed_count=3, finalist_count=2))
    second = provider.seed(framed, RunConfig(seed_count=3, finalist_count=2))

    assert framed.obvious_solution == "Use an asynchronous voting tool."
    assert len(first.value) == 3
    assert [item.title for item in first.value] == [item.title for item in second.value]
    assert first.cost_usd == 0.01


def test_provider_transforms_the_mechanism_and_records_ancestry() -> None:
    provider = DeterministicCreativeProvider()
    task = TaskContext(goal="Invent a calmer decision process.")
    framed = provider.frame(task)
    parent = provider.seed(
        framed,
        RunConfig(seed_count=2, finalist_count=1),
    ).value[0]
    request = TransformationRequest.for_operator(
        operator=OperatorName.INVERT,
        parents=(parent,),
        task_goal=task.goal,
    )

    child = provider.transform(request, (parent,)).value

    assert child.parent_ids == (parent.id,)
    assert child.generation == 1
    assert child.transformations == ("invert",)
    assert child.core_mechanism != parent.core_mechanism
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_deterministic.py -v
```

Expected: FAIL because the provider modules do not exist.

- [ ] **Step 3: Define provider protocols and metered responses**

```python
# src/creativity_layer/providers.py
from __future__ import annotations

from typing import Generic, Protocol, TypeVar

from pydantic import Field

from creativity_layer.models import (
    EvaluationScores,
    FramedTask,
    FrozenModel,
    IdeaGenome,
    RunConfig,
    TaskContext,
)
from creativity_layer.transforms import TransformationRequest

T = TypeVar("T")


class MeteredResponse(FrozenModel, Generic[T]):
    value: T
    provider: str = Field(min_length=1)
    cost_usd: float = Field(ge=0)
    latency_ms: int = Field(ge=0)


class TaskFramer(Protocol):
    def frame(self, task: TaskContext) -> FramedTask: ...


class IdeaSeeder(Protocol):
    def seed(
        self,
        framed_task: FramedTask,
        config: RunConfig,
    ) -> MeteredResponse[tuple[IdeaGenome, ...]]: ...


class IdeaTransformer(Protocol):
    def transform(
        self,
        request: TransformationRequest,
        parents: tuple[IdeaGenome, ...],
    ) -> MeteredResponse[IdeaGenome]: ...


class IdeaEvaluator(Protocol):
    def evaluate(
        self,
        candidate: IdeaGenome,
        framed_task: FramedTask,
    ) -> MeteredResponse[EvaluationScores]: ...
```

- [ ] **Step 4: Implement deterministic local providers**

```python
# src/creativity_layer/deterministic.py
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
```

- [ ] **Step 5: Run deterministic-provider tests**

Run:

```powershell
python -m pytest tests/test_deterministic.py -v
```

Expected: 2 tests PASS.

- [ ] **Step 6: Run all tests and lint**

Run:

```powershell
python -m pytest
python -m ruff check .
```

Expected: all tests PASS and Ruff exits 0.

- [ ] **Step 7: Commit**

```powershell
git add src/creativity_layer/providers.py src/creativity_layer/deterministic.py tests/test_deterministic.py
git commit -m "feat: add deterministic creativity providers"
```

### Task 7: Persist Reproducible JSON Traces

**Files:**
- Create: `src/creativity_layer/tracing.py`
- Create: `tests/test_tracing.py`

- [ ] **Step 1: Write failing trace-store tests**

```python
# tests/test_tracing.py
import json
from uuid import uuid4

from creativity_layer.models import (
    FramedTask,
    IdeaGenome,
    RunResult,
    SpendRecord,
    TaskContext,
)
from creativity_layer.tracing import JsonTraceStore


def test_trace_store_writes_stable_structured_json(tmp_path) -> None:
    candidate = IdeaGenome(
        generation=0,
        title="Idea",
        core_mechanism="Mechanism",
        problem_framing="Framing",
        task_value="Value",
    )
    result = RunResult(
        run_id=uuid4(),
        framed_task=FramedTask(
            context=TaskContext(goal="Test creativity"),
            assumptions=("Obvious assumption",),
            obvious_solution="Obvious answer",
        ),
        finalists=(candidate,),
        all_candidates=(candidate,),
        spend_records=(
            SpendRecord(stage="seed", provider="local", cost_usd=0.01, latency_ms=1),
        ),
        stopped_reason="generation_limit",
    )

    path = JsonTraceStore(tmp_path).save(result)
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert path.name == f"{result.run_id}.json"
    assert payload["run_id"] == str(result.run_id)
    assert payload["framed_task"]["context"]["goal"] == "Test creativity"
    assert payload["finalists"][0]["title"] == "Idea"
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```powershell
python -m pytest tests/test_tracing.py -v
```

Expected: FAIL because `creativity_layer.tracing` does not exist.

- [ ] **Step 3: Implement the JSON trace store**

```python
# src/creativity_layer/tracing.py
from __future__ import annotations

from pathlib import Path

from creativity_layer.models import RunResult


class JsonTraceStore:
    def __init__(self, root: Path) -> None:
        self._root = root

    def save(self, result: RunResult) -> Path:
        self._root.mkdir(parents=True, exist_ok=True)
        path = self._root / f"{result.run_id}.json"
        path.write_text(
            result.model_dump_json(indent=2),
            encoding="utf-8",
        )
        return path
```

- [ ] **Step 4: Run the trace-store test**

Run:

```powershell
python -m pytest tests/test_tracing.py -v
```

Expected: PASS.

- [ ] **Step 5: Run all tests and lint**

Run:

```powershell
python -m pytest
python -m ruff check .
```

Expected: all tests PASS and Ruff exits 0.

- [ ] **Step 6: Commit**

```powershell
git add src/creativity_layer/tracing.py tests/test_tracing.py
git commit -m "feat: persist reproducible run traces"
```

### Task 8: Build the End-to-End Creative Engine

**Files:**
- Create: `src/creativity_layer/engine.py`
- Create: `tests/test_engine.py`
- Modify: `src/creativity_layer/__init__.py`

- [ ] **Step 1: Write failing end-to-end tests**

```python
# tests/test_engine.py
from creativity_layer.deterministic import DeterministicCreativeProvider
from creativity_layer.engine import CreativeEngine
from creativity_layer.models import RunConfig, TaskContext


def test_engine_runs_seed_transform_evaluate_select_loop() -> None:
    provider = DeterministicCreativeProvider()
    engine = CreativeEngine(
        framer=provider,
        seeder=provider,
        transformer=provider,
        evaluator=provider,
    )

    result = engine.run(
        TaskContext(
            goal="Invent a calmer way for distributed teams to make decisions.",
            constraints=("No meetings",),
        ),
        RunConfig(
            max_cost_usd=1,
            max_calls=20,
            max_generations=1,
            seed_count=3,
            finalist_count=2,
            framing_reserve_usd=0,
            finalization_reserve_usd=0.05,
        ),
    )

    assert len(result.finalists) == 2
    assert len(result.all_candidates) == 6
    assert any(candidate.generation == 1 for candidate in result.all_candidates)
    assert all(candidate.scores is not None for candidate in result.all_candidates)
    assert result.stopped_reason == "generation_limit"
    assert sum(record.cost_usd for record in result.spend_records) <= 1


def test_engine_returns_current_frontier_when_budget_cannot_transform() -> None:
    provider = DeterministicCreativeProvider()
    engine = CreativeEngine(
        framer=provider,
        seeder=provider,
        transformer=provider,
        evaluator=provider,
    )

    result = engine.run(
        TaskContext(goal="Invent a new decision process."),
        RunConfig(
            max_cost_usd=0.04,
            max_calls=10,
            max_generations=2,
            seed_count=2,
            finalist_count=1,
            framing_reserve_usd=0,
            finalization_reserve_usd=0,
        ),
    )

    assert len(result.finalists) == 1
    assert result.stopped_reason == "budget_exhausted"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_engine.py -v
```

Expected: FAIL because `creativity_layer.engine` does not exist.

- [ ] **Step 3: Implement the orchestration loop**

```python
# src/creativity_layer/engine.py
from __future__ import annotations

from itertools import cycle

from creativity_layer.budget import BudgetController
from creativity_layer.models import (
    FramedTask,
    IdeaGenome,
    RunConfig,
    RunResult,
    TaskContext,
)
from creativity_layer.population import PopulationManager
from creativity_layer.providers import IdeaEvaluator, IdeaSeeder, IdeaTransformer, TaskFramer
from creativity_layer.transforms import OperatorName, TransformationRequest


class CreativeEngine:
    def __init__(
        self,
        *,
        framer: TaskFramer,
        seeder: IdeaSeeder,
        transformer: IdeaTransformer,
        evaluator: IdeaEvaluator,
        population: PopulationManager | None = None,
    ) -> None:
        self._framer = framer
        self._seeder = seeder
        self._transformer = transformer
        self._evaluator = evaluator
        self._population = population or PopulationManager()

    def run(self, task: TaskContext, config: RunConfig) -> RunResult:
        budget = BudgetController(config)
        framed = self._framer.frame(task)

        seeded = self._seeder.seed(framed, config)
        budget.charge("seeding", seeded.provider, seeded.cost_usd, seeded.latency_ms)
        candidates = list(self._evaluate_all(seeded.value, framed, budget))

        stopped_reason = "generation_limit"
        operators = cycle(
            (
                OperatorName.INVERT,
                OperatorName.REFRAME,
                OperatorName.SUBTRACT,
                OperatorName.CONTRADICT,
            )
        )

        for _generation in range(config.max_generations):
            parents = self._population.select(
                tuple(candidates),
                finalist_count=min(config.seed_count, len(candidates)),
            )
            descendants: list[IdeaGenome] = []

            for parent in parents:
                estimated_transform_cost = 0.01
                estimated_evaluation_cost = 0.005
                if not budget.can_afford(
                    estimated_transform_cost + estimated_evaluation_cost,
                    preserve_finalization=True,
                ):
                    stopped_reason = "budget_exhausted"
                    break

                operator = next(operators)
                request = TransformationRequest.for_operator(
                    operator=operator,
                    parents=(parent,),
                    task_goal=task.goal,
                )
                transformed = self._transformer.transform(request, (parent,))
                budget.charge(
                    "transformation",
                    transformed.provider,
                    transformed.cost_usd,
                    transformed.latency_ms,
                )
                descendants.extend(
                    self._evaluate_all((transformed.value,), framed, budget)
                )

            candidates.extend(descendants)
            if stopped_reason == "budget_exhausted":
                break

        finalists = self._population.select(
            tuple(candidates),
            finalist_count=min(config.finalist_count, len(candidates)),
        )
        return RunResult(
            framed_task=framed,
            finalists=finalists,
            all_candidates=tuple(candidates),
            spend_records=budget.records,
            stopped_reason=stopped_reason,
        )

    def _evaluate_all(
        self,
        candidates: tuple[IdeaGenome, ...],
        framed_task: FramedTask,
        budget: BudgetController,
    ) -> tuple[IdeaGenome, ...]:
        evaluated: list[IdeaGenome] = []
        for candidate in candidates:
            response = self._evaluator.evaluate(candidate, framed_task)
            budget.charge(
                "evaluation",
                response.provider,
                response.cost_usd,
                response.latency_ms,
            )
            evaluated.append(candidate.model_copy(update={"scores": response.value}))
        return tuple(evaluated)
```

- [ ] **Step 4: Export the engine**

```python
# src/creativity_layer/__init__.py
"""Creativity Layer research prototype."""

from creativity_layer.engine import CreativeEngine
from creativity_layer.models import (
    EvaluationScores,
    FramedTask,
    IdeaGenome,
    InspirationKind,
    RunConfig,
    RunResult,
    TaskContext,
)

__version__ = "0.1.0"

__all__ = [
    "CreativeEngine",
    "EvaluationScores",
    "FramedTask",
    "IdeaGenome",
    "InspirationKind",
    "RunConfig",
    "RunResult",
    "TaskContext",
]
```

- [ ] **Step 5: Run the engine tests**

Run:

```powershell
python -m pytest tests/test_engine.py -v
```

Expected: 2 tests PASS.

- [ ] **Step 6: Run all tests and lint**

Run:

```powershell
python -m pytest
python -m ruff check .
```

Expected: all tests PASS and Ruff exits 0.

- [ ] **Step 7: Commit**

```powershell
git add src/creativity_layer/engine.py src/creativity_layer/__init__.py tests/test_engine.py
git commit -m "feat: orchestrate deterministic creative search"
```

### Task 9: Add a Runnable CLI and Trace Output

**Files:**
- Create: `src/creativity_layer/cli.py`
- Create: `tests/test_cli.py`
- Modify: `README.md`

- [ ] **Step 1: Write the failing CLI test**

```python
# tests/test_cli.py
import json

from creativity_layer.cli import run_cli


def test_cli_runs_research_spine_and_writes_trace(tmp_path, capsys) -> None:
    exit_code = run_cli(
        [
            "Invent a calmer decision process.",
            "--trace-dir",
            str(tmp_path),
            "--seed-count",
            "2",
            "--finalist-count",
            "1",
            "--generations",
            "1",
        ]
    )

    captured = capsys.readouterr()
    summary = json.loads(captured.out)
    traces = list(tmp_path.glob("*.json"))

    assert exit_code == 0
    assert summary["finalist_count"] == 1
    assert summary["stopped_reason"] == "generation_limit"
    assert len(traces) == 1
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```powershell
python -m pytest tests/test_cli.py -v
```

Expected: FAIL because `creativity_layer.cli` does not exist.

- [ ] **Step 3: Implement the CLI**

```python
# src/creativity_layer/cli.py
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from creativity_layer.deterministic import DeterministicCreativeProvider
from creativity_layer.engine import CreativeEngine
from creativity_layer.models import RunConfig, TaskContext
from creativity_layer.tracing import JsonTraceStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="creativity-layer",
        description="Run the deterministic Creativity Layer research spine.",
    )
    parser.add_argument("goal")
    parser.add_argument("--trace-dir", type=Path, default=Path(".traces"))
    parser.add_argument("--seed-count", type=int, default=4)
    parser.add_argument("--finalist-count", type=int, default=3)
    parser.add_argument("--generations", type=int, default=1)
    parser.add_argument("--max-cost-usd", type=float, default=1.0)
    parser.add_argument("--max-calls", type=int, default=30)
    return parser


def run_cli(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    provider = DeterministicCreativeProvider()
    engine = CreativeEngine(
        framer=provider,
        seeder=provider,
        transformer=provider,
        evaluator=provider,
    )
    result = engine.run(
        TaskContext(goal=args.goal),
        RunConfig(
            max_cost_usd=args.max_cost_usd,
            max_calls=args.max_calls,
            max_generations=args.generations,
            seed_count=args.seed_count,
            finalist_count=args.finalist_count,
            framing_reserve_usd=0,
            finalization_reserve_usd=0.05,
        ),
    )
    trace_path = JsonTraceStore(args.trace_dir).save(result)
    print(
        json.dumps(
            {
                "run_id": str(result.run_id),
                "finalist_count": len(result.finalists),
                "stopped_reason": result.stopped_reason,
                "trace_path": str(trace_path),
                "finalists": [
                    {
                        "title": candidate.title,
                        "originality": candidate.scores.originality
                        if candidate.scores is not None
                        else None,
                        "usefulness": candidate.scores.usefulness
                        if candidate.scores is not None
                        else None,
                    }
                    for candidate in result.finalists
                ],
            },
            indent=2,
        )
    )
    return 0


def main() -> None:
    raise SystemExit(run_cli())


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Update the README with the demo**

Append:

````markdown
## Deterministic research-spine demo

```powershell
creativity-layer "Invent a calmer way for distributed teams to make decisions" `
  --seed-count 4 `
  --finalist-count 3 `
  --generations 1 `
  --trace-dir .traces
```

The command prints a JSON summary and writes the complete structured run trace to
`.traces/<run-id>.json`. This milestone uses deterministic local providers; it makes
no external model or search calls.
````

- [ ] **Step 5: Run the CLI test**

Run:

```powershell
python -m pytest tests/test_cli.py -v
```

Expected: PASS.

- [ ] **Step 6: Run the CLI manually**

Run:

```powershell
creativity-layer "Invent a calmer way for distributed teams to make decisions" --seed-count 3 --finalist-count 2 --generations 1 --trace-dir .traces
```

Expected: JSON output with `finalist_count` equal to `2`, `stopped_reason` equal to `generation_limit`, and a valid trace path.

- [ ] **Step 7: Run the full verification suite**

Run:

```powershell
python -m pytest --cov=creativity_layer --cov-report=term-missing
python -m ruff check .
```

Expected: all tests PASS, coverage is reported, and Ruff exits 0.

- [ ] **Step 8: Commit**

```powershell
git add src/creativity_layer/cli.py tests/test_cli.py README.md
git commit -m "feat: add deterministic research CLI"
```

### Task 10: Final Milestone Verification

**Files:**
- Modify only if verification exposes a defect.

- [ ] **Step 1: Verify repository state**

Run:

```powershell
git status --short
git log --oneline --decorate -10
```

Expected: clean working tree and one focused commit for each completed task.

- [ ] **Step 2: Run the complete test suite**

Run:

```powershell
python -m pytest -v --cov=creativity_layer --cov-report=term-missing
```

Expected: all tests PASS with no warnings or errors.

- [ ] **Step 3: Run static checks**

Run:

```powershell
python -m ruff check .
```

Expected: Ruff exits 0.

- [ ] **Step 4: Run the end-to-end command**

Run:

```powershell
creativity-layer "Invent a novel system for sharing scarce neighborhood tools" --seed-count 4 --finalist-count 3 --generations 1 --trace-dir .traces
```

Expected:

- Exit code 0
- Three finalists in printed JSON
- A trace file containing framed task, all candidates, scores, ancestry, transformations, spend records, and stopping reason
- Total recorded spend does not exceed the configured maximum

- [ ] **Step 5: Inspect the generated trace**

Run:

```powershell
$trace = Get-ChildItem .traces\*.json | Sort-Object LastWriteTime -Descending | Select-Object -First 1
Get-Content -Raw $trace.FullName | ConvertFrom-Json | Select-Object run_id,stopped_reason,@{Name='candidate_count';Expression={$_.all_candidates.Count}},@{Name='finalist_count';Expression={$_.finalists.Count}}
```

Expected: populated run ID, `generation_limit`, at least eight candidates, and three finalists.

- [ ] **Step 6: Request final code review**

Use `superpowers:requesting-code-review` with:

- Base SHA: the design-and-plan branch point
- Head SHA: current milestone head
- Requirements: this plan and `docs/superpowers/specs/2026-06-22-creativity-layer-design.md`
- Review focus: budget correctness, immutable model boundaries, ancestry/provenance integrity, wildcard retention, deterministic reproducibility, and whether any provider-specific logic leaked into the engine

- [ ] **Step 7: Fix every Critical or Important review issue using TDD**

For each issue:

1. Add a failing regression test.
2. Run it and confirm the expected failure.
3. Add the minimal fix.
4. Run the focused test.
5. Run the full suite and Ruff.
6. Commit the fix with a focused message.

- [ ] **Step 8: Re-run final verification**

Run:

```powershell
python -m pytest -v --cov=creativity_layer --cov-report=term-missing
python -m ruff check .
git status --short
```

Expected: all tests PASS, Ruff exits 0, and the working tree is clean.
