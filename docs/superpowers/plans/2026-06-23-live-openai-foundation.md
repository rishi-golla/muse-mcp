# Live OpenAI Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run the existing creativity engine safely against live OpenAI Responses API models with structured outputs, token-based cost accounting, retries, privacy-aware traces, and an environment-gated `live` CLI command.

**Architecture:** Extend the provider contracts so framing and every other live operation are quoted, metered, validated, and traced. An `OpenAICreativeProvider` implements the existing framing, seeding, transformation, and evaluation roles through `OpenAI.responses.parse`, while a separate `OpenAIEmbeddingProvider` exposes embeddings for Slice 2B. A reusable live-operation executor owns retries, timeouts, circuit breaking, usage normalization, pricing, and secret-safe failures; core engine modules continue to receive only internal Pydantic models.

**Tech Stack:** Python 3.12+, OpenAI Python SDK 2.x, Pydantic 2.x, httpx, pytest, Ruff

---

## Scope Boundaries

This plan implements Slice 2A only:

- OpenAI Responses API model adapter
- OpenAI embedding adapter
- Explicit economy and strong model routing
- Framing, seeding, transformation, and evaluation through structured outputs
- Actual token-usage and estimated-cost accounting
- Retry, timeout, rate-limit, structured-output repair, and circuit-breaker primitives
- Research/private trace controls
- `creativity-layer live`
- Environment-gated OpenAI smoke test

This plan does not implement:

- Exa, Brave, or OpenAI web search
- Inspired branches
- Prior-art checks
- Originality formula changes
- `compare` or `calibrate`
- Human evaluation

The live command remains fully search-isolated. Embeddings are implemented and contract
tested but are integrated into candidate novelty and deduplication in Slice 2B.

## Model Configuration

Do not hard-code a “latest” model alias. The CLI and SDK require explicit text model
identifiers through configuration:

- `OPENAI_ECONOMY_MODEL`
- `OPENAI_STRONG_MODEL`
- `OPENAI_EMBEDDING_MODEL`, defaulting to `text-embedding-3-small`

The same model may be assigned to economy and strong roles during early testing.

## File Map

```text
pyproject.toml                                  Add OpenAI SDK and httpx dependencies
README.md                                       Document live setup, pricing, and smoke tests
src/creativity_layer/models.py                  Live usage, pricing, privacy, and trace models
src/creativity_layer/providers.py               Metered framing and embedding contracts
src/creativity_layer/operation.py               Validate extended live envelopes
src/creativity_layer/budget.py                  Record token/search metadata on spend records
src/creativity_layer/engine.py                  Meter framing and preserve live usage/errors
src/creativity_layer/live_config.py             Environment/programmatic live configuration
src/creativity_layer/pricing.py                 Versioned token-pricing calculations
src/creativity_layer/reliability.py             Retry, timeout, and circuit-breaker executor
src/creativity_layer/openai_schemas.py           OpenAI structured-output schemas and converters
src/creativity_layer/openai_provider.py          Responses API creative provider
src/creativity_layer/openai_embeddings.py        OpenAI embedding adapter
src/creativity_layer/privacy.py                 Research/private trace redaction
src/creativity_layer/cli.py                     Add deterministic and live subcommands
tests/test_live_config.py                        Configuration and secret handling
tests/test_pricing.py                            Token-cost calculations
tests/test_reliability.py                        Retry and circuit-breaker behavior
tests/test_openai_schemas.py                     Structured conversion behavior
tests/test_openai_provider.py                    Mocked Responses API adapter tests
tests/test_openai_embeddings.py                  Mocked embeddings tests
tests/test_live_engine.py                        Metered framing and live engine integration
tests/test_privacy.py                            Research/private trace behavior
tests/test_live_cli.py                           Live CLI behavior
tests/test_openai_live.py                        Opt-in paid smoke test
```

## Task 1: Add Live Configuration and Dependencies

**Files:**
- Modify: `pyproject.toml`
- Create: `src/creativity_layer/live_config.py`
- Create: `tests/test_live_config.py`

- [ ] **Step 1: Write failing configuration tests**

```python
# tests/test_live_config.py
import pytest
from pydantic import SecretStr, ValidationError

from creativity_layer.live_config import LiveModelConfig, OpenAICredentials, PrivacyMode


def test_live_model_config_requires_explicit_text_models() -> None:
    with pytest.raises(ValidationError):
        LiveModelConfig(economy_model="", strong_model="")


def test_live_model_config_defaults_embedding_model_and_budget() -> None:
    config = LiveModelConfig(
        economy_model="economy-test-model",
        strong_model="strong-test-model",
    )

    assert config.embedding_model == "text-embedding-3-small"
    assert config.default_budget_usd == 0.10
    assert config.privacy_mode is PrivacyMode.RESEARCH


def test_credentials_never_serialize_secret_value() -> None:
    credentials = OpenAICredentials(api_key=SecretStr("sk-secret-value"))

    dumped = credentials.model_dump_json()

    assert "sk-secret-value" not in dumped
    assert credentials.api_key.get_secret_value() == "sk-secret-value"
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
python -m pytest tests/test_live_config.py -v
```

Expected: FAIL because `creativity_layer.live_config` does not exist.

- [ ] **Step 3: Add dependencies**

Add to `[project].dependencies`:

```toml
"httpx>=0.27,<1",
"openai>=2.11,<3",
```

- [ ] **Step 4: Implement immutable live configuration**

```python
# src/creativity_layer/live_config.py
from __future__ import annotations

import os
from enum import StrEnum

from pydantic import Field, SecretStr

from creativity_layer.models import FrozenModel, RequiredText


class PrivacyMode(StrEnum):
    RESEARCH = "research"
    PRIVATE = "private"


class OpenAICredentials(FrozenModel):
    api_key: SecretStr

    @classmethod
    def from_environment(cls) -> OpenAICredentials:
        value = os.getenv("OPENAI_API_KEY")
        if not value:
            raise ValueError("OPENAI_API_KEY is required for live OpenAI runs")
        return cls(api_key=SecretStr(value))


class LiveModelConfig(FrozenModel):
    economy_model: RequiredText
    strong_model: RequiredText
    embedding_model: RequiredText = "text-embedding-3-small"
    default_budget_usd: float = Field(default=0.10, strict=True, gt=0)
    timeout_seconds: float = Field(default=30.0, strict=True, gt=0)
    max_retries: int = Field(default=2, strict=True, ge=0, le=5)
    repair_attempts: int = Field(default=1, strict=True, ge=0, le=2)
    circuit_failure_threshold: int = Field(default=3, strict=True, ge=1)
    privacy_mode: PrivacyMode = PrivacyMode.RESEARCH

    @classmethod
    def from_environment(cls) -> LiveModelConfig:
        economy = os.getenv("OPENAI_ECONOMY_MODEL")
        strong = os.getenv("OPENAI_STRONG_MODEL")
        if not economy or not strong:
            raise ValueError(
                "OPENAI_ECONOMY_MODEL and OPENAI_STRONG_MODEL are required"
            )
        return cls(
            economy_model=economy,
            strong_model=strong,
            embedding_model=os.getenv(
                "OPENAI_EMBEDDING_MODEL",
                "text-embedding-3-small",
            ),
        )
```

- [ ] **Step 5: Install and run focused tests**

Run:

```powershell
python -m pip install -e ".[dev]"
python -m pytest tests/test_live_config.py -v
python -m ruff check src/creativity_layer/live_config.py tests/test_live_config.py
```

Expected: 3 tests PASS and Ruff exits 0.

- [ ] **Step 6: Commit**

```powershell
git add pyproject.toml src/creativity_layer/live_config.py tests/test_live_config.py
git commit -m "feat: add live OpenAI configuration"
```

## Task 2: Extend Usage, Pricing, and Spend Models

**Files:**
- Modify: `src/creativity_layer/models.py`
- Modify: `src/creativity_layer/providers.py`
- Modify: `src/creativity_layer/budget.py`
- Create: `src/creativity_layer/pricing.py`
- Create: `tests/test_pricing.py`
- Modify: `tests/test_budget.py`
- Modify: `tests/test_models.py`

- [ ] **Step 1: Write failing usage and pricing tests**

```python
# tests/test_pricing.py
from creativity_layer.models import TokenUsage
from creativity_layer.pricing import ModelPrice, PricingTable


def test_pricing_table_calculates_cached_and_uncached_tokens() -> None:
    table = PricingTable(
        version="test-2026-06-23",
        models={
            "economy-test-model": ModelPrice(
                input_per_million=1.00,
                cached_input_per_million=0.10,
                output_per_million=4.00,
            )
        },
    )
    usage = TokenUsage(
        input_tokens=1_000,
        cached_input_tokens=400,
        output_tokens=500,
        reasoning_tokens=100,
    )

    estimate = table.estimate("economy-test-model", usage)

    assert estimate.pricing_version == "test-2026-06-23"
    assert estimate.estimated_cost_usd == 0.00304
    assert estimate.is_estimated is True


def test_unknown_model_cannot_be_quoted() -> None:
    table = PricingTable(version="test", models={})

    try:
        table.estimate("missing", TokenUsage())
    except KeyError as error:
        assert str(error) == "'no pricing configured for model: missing'"
    else:
        raise AssertionError("unknown model was priced")
```

Add model tests:

```python
def test_spend_record_preserves_model_and_token_usage() -> None:
    record = SpendRecord(
        stage="seeding",
        provider="openai",
        model="economy-test-model",
        cost_usd=0.001,
        latency_ms=25,
        usage=TokenUsage(input_tokens=10, output_tokens=20),
        pricing_version="test",
        cost_is_estimated=True,
    )

    assert record.usage.output_tokens == 20
    assert record.model == "economy-test-model"
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
python -m pytest tests/test_pricing.py tests/test_models.py -v
```

Expected: FAIL because usage and pricing models do not exist.

- [ ] **Step 3: Add live usage models**

Add to `models.py`:

```python
class TokenUsage(FrozenModel):
    input_tokens: int = Field(default=0, strict=True, ge=0)
    cached_input_tokens: int = Field(default=0, strict=True, ge=0)
    output_tokens: int = Field(default=0, strict=True, ge=0)
    reasoning_tokens: int = Field(default=0, strict=True, ge=0)


class CostEstimate(FrozenModel):
    estimated_cost_usd: float = Field(strict=True, ge=0)
    pricing_version: RequiredText
    is_estimated: bool = True


class OperationTrace(FrozenModel):
    request: dict[str, object] = Field(default_factory=dict)
    response: dict[str, object] = Field(default_factory=dict)
```

Extend `SpendRecord` with:

```python
model: str | None = None
usage: TokenUsage = Field(default_factory=TokenUsage)
pricing_version: str | None = None
cost_is_estimated: bool = False
request_id: str | None = None
operation_trace: OperationTrace | None = None
```

Extend `MeteredResponse[T]` with the same optional model, usage, pricing version,
estimated flag, request ID, and operation trace fields.

- [ ] **Step 4: Implement versioned pricing**

```python
# src/creativity_layer/pricing.py
from __future__ import annotations

from decimal import Decimal

from pydantic import Field

from creativity_layer.models import CostEstimate, FrozenModel, RequiredText, TokenUsage


class ModelPrice(FrozenModel):
    input_per_million: float = Field(strict=True, ge=0)
    cached_input_per_million: float = Field(strict=True, ge=0)
    output_per_million: float = Field(strict=True, ge=0)


class EmbeddingPrice(FrozenModel):
    input_per_million: float = Field(strict=True, ge=0)


class PricingTable(FrozenModel):
    version: RequiredText
    models: dict[str, ModelPrice]
    embeddings: dict[str, EmbeddingPrice] = Field(default_factory=dict)

    def estimate(self, model: str, usage: TokenUsage) -> CostEstimate:
        if model not in self.models:
            raise KeyError(f"no pricing configured for model: {model}")
        price = self.models[model]
        cached = Decimal(usage.cached_input_tokens)
        uncached = Decimal(usage.input_tokens - usage.cached_input_tokens)
        output = Decimal(usage.output_tokens + usage.reasoning_tokens)
        million = Decimal(1_000_000)
        cost = (
            uncached * Decimal(str(price.input_per_million))
            + cached * Decimal(str(price.cached_input_per_million))
            + output * Decimal(str(price.output_per_million))
        ) / million
        return CostEstimate(
            estimated_cost_usd=float(cost),
            pricing_version=self.version,
        )

    def estimate_embeddings(
        self,
        model: str,
        input_tokens: int,
    ) -> CostEstimate:
        if model not in self.embeddings:
            raise KeyError(f"no embedding pricing configured for model: {model}")
        price = self.embeddings[model]
        cost = (
            Decimal(input_tokens)
            * Decimal(str(price.input_per_million))
            / Decimal(1_000_000)
        )
        return CostEstimate(
            estimated_cost_usd=float(cost),
            pricing_version=self.version,
        )
```

- [ ] **Step 5: Preserve metadata in budget charges**

Extend `BudgetController.charge`, `BudgetReservation.charge`, and
`record_audited_overage` with keyword-only metadata:

```python
model: str | None = None,
usage: TokenUsage | None = None,
pricing_version: str | None = None,
cost_is_estimated: bool = False,
request_id: str | None = None,
operation_trace: OperationTrace | None = None,
```

Pass those values into `SpendRecord`. Update `CreativeEngine._charge_response` so every
field from `MeteredResponse`, including the operation trace, reaches the spend record.

- [ ] **Step 6: Run focused and full tests**

Run:

```powershell
python -m pytest tests/test_pricing.py tests/test_budget.py tests/test_models.py -v
python -m pytest
python -m ruff check .
```

Expected: all tests PASS.

- [ ] **Step 7: Commit**

```powershell
git add src/creativity_layer/models.py src/creativity_layer/providers.py src/creativity_layer/budget.py src/creativity_layer/engine.py src/creativity_layer/pricing.py tests/test_pricing.py tests/test_budget.py tests/test_models.py
git commit -m "feat: account for live model usage"
```

## Task 3: Meter Framing as a First-Class Operation

**Files:**
- Modify: `src/creativity_layer/providers.py`
- Modify: `src/creativity_layer/operation.py`
- Modify: `src/creativity_layer/engine.py`
- Modify: `src/creativity_layer/deterministic.py`
- Create: `tests/test_metered_framing.py`
- Modify: `tests/test_deterministic.py`
- Modify: `tests/test_engine.py`

- [ ] **Step 1: Write failing metered-framing tests**

```python
# tests/test_metered_framing.py
from creativity_layer.deterministic import DeterministicCreativeProvider
from creativity_layer.engine import CreativeEngine
from creativity_layer.models import RunConfig, TaskContext


def test_framing_is_quoted_charged_and_traced() -> None:
    provider = DeterministicCreativeProvider()
    engine = CreativeEngine(
        framer=provider,
        seeder=provider,
        transformer=provider,
        evaluator=provider,
    )

    result = engine.run(
        TaskContext(goal="Invent a quieter coordination mechanism."),
        RunConfig(
            max_cost_usd=1.0,
            max_calls=20,
            max_generations=0,
            seed_count=2,
            finalist_count=1,
            framing_reserve_usd=0.01,
            finalization_reserve_usd=0,
        ),
    )

    assert result.spend_records[0].stage == "framing"
    assert result.spend_records[0].cost_usd == 0.0


def test_unaffordable_framing_stops_before_provider_call() -> None:
    class ExpensiveFramer(DeterministicCreativeProvider):
        frame_called = False

        def quote_frame(self, task):
            return OperationQuote(max_cost_usd=0.2)

        def frame(self, task):
            self.frame_called = True
            return super().frame(task)

    provider = ExpensiveFramer()
    result = CreativeEngine(
        framer=provider,
        seeder=provider,
        transformer=provider,
        evaluator=provider,
    ).run(
        TaskContext(goal="Test"),
        RunConfig(
            max_cost_usd=0.1,
            max_calls=10,
            seed_count=2,
            finalist_count=1,
            framing_reserve_usd=0,
            finalization_reserve_usd=0,
        ),
    )

    assert provider.frame_called is False
    assert result.stopped_reason == "budget_exhausted"
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
python -m pytest tests/test_metered_framing.py -v
```

Expected: FAIL because framing is not quoted or metered.

- [ ] **Step 3: Extend framing contract**

Replace `TaskFramer` methods with:

```python
class TaskFramer(Protocol):
    name: str
    version: str

    def quote_frame(self, task: TaskContext) -> OperationQuote:
        raise NotImplementedError

    def frame(self, task: TaskContext) -> MeteredResponse[FramedTask]:
        raise NotImplementedError
```

Add `validate_framing_payload` to `operation.py` using
`MeteredResponse[FramedTask].model_validate`.

- [ ] **Step 4: Meter framing in the engine**

Before seeding:

1. Validate `quote_frame`.
2. Reserve its cost and one call without preserving the framing reserve.
3. Invoke and validate the framed response.
4. Charge actual usage through `_charge_response`.
5. Release the configured framing reserve after successful framing.

Add `BudgetController.release_framing_reserve()` with idempotent behavior. Exploration
capacity initially subtracts framing and finalization reserves; after successful
framing it subtracts finalization only.

On framing quote/provider/validation failure, return the existing fallback frame and a
structured `provider_error`.

- [ ] **Step 5: Update deterministic framing**

```python
def quote_frame(self, task: TaskContext) -> OperationQuote:
    return OperationQuote(max_cost_usd=0.0)

def frame(self, task: TaskContext) -> MeteredResponse[FramedTask]:
    return MeteredResponse(
        value=FramedTask(
            context=task,
            assumptions=(
                "A decision requires a synchronous discussion.",
                "Every participant must respond to every proposal.",
            ),
            obvious_solution="Use an asynchronous voting tool.",
        ),
        provider=self.name,
        cost_usd=0.0,
        latency_ms=0,
    )
```

- [ ] **Step 6: Run tests**

Run:

```powershell
python -m pytest tests/test_metered_framing.py tests/test_engine.py tests/test_deterministic.py -v
python -m pytest
python -m ruff check .
```

Expected: all tests PASS.

- [ ] **Step 7: Commit**

```powershell
git add src/creativity_layer/providers.py src/creativity_layer/operation.py src/creativity_layer/engine.py src/creativity_layer/budget.py src/creativity_layer/deterministic.py tests/test_metered_framing.py tests/test_engine.py tests/test_deterministic.py
git commit -m "feat: meter task framing"
```

## Task 4: Add Reliability Executor and Circuit Breaker

**Files:**
- Create: `src/creativity_layer/reliability.py`
- Create: `tests/test_reliability.py`

- [ ] **Step 1: Write failing reliability tests**

```python
# tests/test_reliability.py
from openai import APIConnectionError, RateLimitError

from creativity_layer.reliability import (
    CircuitBreaker,
    CircuitOpenError,
    RetryPolicy,
    execute_with_retries,
)


def test_retry_executor_retries_rate_limits_with_injected_sleep() -> None:
    attempts = 0
    delays: list[float] = []

    def operation() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise RateLimitError(
                "rate limited",
                response=FakeResponse(status_code=429),
                body=None,
            )
        return "ok"

    result = execute_with_retries(
        operation,
        policy=RetryPolicy(max_retries=2, base_delay_seconds=0.1),
        sleep=delays.append,
        random_value=lambda: 0.0,
    )

    assert result == "ok"
    assert attempts == 3
    assert delays == [0.1, 0.2]


def test_circuit_opens_after_repeated_failures() -> None:
    breaker = CircuitBreaker(failure_threshold=2)
    breaker.record_failure()
    breaker.record_failure()

    try:
        breaker.before_call()
    except CircuitOpenError:
        pass
    else:
        raise AssertionError("open circuit allowed a call")
```

Use a small local `FakeResponse` in the test with `status_code`, `headers`, and
`request` fields required by the SDK exception.

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
python -m pytest tests/test_reliability.py -v
```

Expected: FAIL because reliability primitives do not exist.

- [ ] **Step 3: Implement retry policy and circuit breaker**

```python
# src/creativity_layer/reliability.py
from __future__ import annotations

import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar

from openai import APIConnectionError, APITimeoutError, RateLimitError

T = TypeVar("T")
RETRYABLE = (RateLimitError, APITimeoutError, APIConnectionError)


class CircuitOpenError(RuntimeError):
    pass


@dataclass(frozen=True)
class RetryPolicy:
    max_retries: int = 2
    base_delay_seconds: float = 0.25
    maximum_delay_seconds: float = 2.0


class CircuitBreaker:
    def __init__(self, failure_threshold: int) -> None:
        self._threshold = failure_threshold
        self._failures = 0
        self._open = False

    @property
    def is_open(self) -> bool:
        return self._open

    def before_call(self) -> None:
        if self._open:
            raise CircuitOpenError("provider circuit is open")

    def record_success(self) -> None:
        self._failures = 0

    def record_failure(self) -> None:
        self._failures += 1
        if self._failures >= self._threshold:
            self._open = True


def execute_with_retries(
    operation: Callable[[], T],
    *,
    policy: RetryPolicy,
    breaker: CircuitBreaker | None = None,
    sleep: Callable[[float], None] = time.sleep,
    random_value: Callable[[], float] = random.random,
) -> T:
    if breaker:
        breaker.before_call()
    for attempt in range(policy.max_retries + 1):
        try:
            result = operation()
        except RETRYABLE:
            if breaker:
                breaker.record_failure()
            if attempt >= policy.max_retries:
                raise
            base = min(
                policy.maximum_delay_seconds,
                policy.base_delay_seconds * (2**attempt),
            )
            sleep(base + base * 0.25 * random_value())
        else:
            if breaker:
                breaker.record_success()
            return result
    raise RuntimeError("unreachable")
```

- [ ] **Step 4: Add non-retryable and exhaustion tests**

Add tests proving:

- Authentication errors are never retried.
- Retry exhaustion re-raises the final SDK exception.
- A successful call resets consecutive failure count.
- An open circuit performs no provider call.

- [ ] **Step 5: Run tests and commit**

Run:

```powershell
python -m pytest tests/test_reliability.py -v
python -m ruff check src/creativity_layer/reliability.py tests/test_reliability.py
```

Expected: all tests PASS.

```powershell
git add src/creativity_layer/reliability.py tests/test_reliability.py
git commit -m "feat: add live provider reliability controls"
```

## Task 5: Define OpenAI Structured Schemas and Converters

**Files:**
- Create: `src/creativity_layer/openai_schemas.py`
- Create: `tests/test_openai_schemas.py`

- [ ] **Step 1: Write failing schema-conversion tests**

```python
# tests/test_openai_schemas.py
from creativity_layer.models import TaskContext
from creativity_layer.openai_schemas import (
    OpenAIEvaluation,
    OpenAIFrame,
    OpenAIIdea,
)


def test_openai_frame_converts_to_internal_frame() -> None:
    schema = OpenAIFrame(
        assumptions=["Meetings are required"],
        obvious_solution="Use a voting form",
    )

    framed = schema.to_domain(TaskContext(goal="Improve decisions"))

    assert framed.context.goal == "Improve decisions"
    assert framed.assumptions == ("Meetings are required",)


def test_openai_idea_converts_without_provider_controlled_identity() -> None:
    schema = OpenAIIdea(
        title="Confidence garden",
        core_mechanism="Claims gain reversible confidence through evidence.",
        problem_framing="Decision-making is evidence accumulation.",
        assumptions_challenged=["Votes must be final"],
        task_value="Reduces premature consensus.",
        distinguishing_features=["reversible confidence"],
        first_order_effects=[],
        second_order_effects=[],
        feasibility_assumptions=[],
        uncertainties=[],
        weaknesses=[],
    )

    candidate = schema.to_seed(generation=0)

    assert candidate.generation == 0
    assert candidate.parent_ids == ()
    assert candidate.transformations == ()


def test_openai_evaluation_converts_to_scores() -> None:
    scores = OpenAIEvaluation(
        originality=0.8,
        usefulness=0.7,
        coherence=0.9,
        feasibility=0.6,
        user_fit=0.75,
    ).to_domain()

    assert scores.originality == 0.8
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
python -m pytest tests/test_openai_schemas.py -v
```

Expected: FAIL because OpenAI schemas do not exist.

- [ ] **Step 3: Implement schemas**

Create strict Pydantic output schemas:

```python
from __future__ import annotations

from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from creativity_layer.models import (
    EvaluationScores,
    FramedTask,
    IdeaGenome,
    InspirationKind,
    TaskContext,
)
from creativity_layer.transforms import (
    TransformationRequest,
    expected_transformation_history,
)


class OpenAIOutputModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class OpenAIFrame(OpenAIOutputModel):
    assumptions: list[str]
    obvious_solution: str

    def to_domain(self, task: TaskContext) -> FramedTask:
        return FramedTask(
            context=task,
            assumptions=tuple(self.assumptions),
            obvious_solution=self.obvious_solution,
        )


class OpenAIIdea(OpenAIOutputModel):
    title: str
    core_mechanism: str
    problem_framing: str
    assumptions_challenged: list[str]
    task_value: str
    distinguishing_features: list[str]
    first_order_effects: list[str]
    second_order_effects: list[str]
    feasibility_assumptions: list[str]
    uncertainties: list[str]
    weaknesses: list[str]

    def to_seed(self, *, generation: int) -> IdeaGenome:
        return IdeaGenome(
            id=uuid4(),
            generation=generation,
            title=self.title,
            core_mechanism=self.core_mechanism,
            problem_framing=self.problem_framing,
            assumptions_challenged=tuple(self.assumptions_challenged),
            task_value=self.task_value,
            distinguishing_features=tuple(self.distinguishing_features),
            first_order_effects=tuple(self.first_order_effects),
            second_order_effects=tuple(self.second_order_effects),
            feasibility_assumptions=tuple(self.feasibility_assumptions),
            uncertainties=tuple(self.uncertainties),
            weaknesses=tuple(self.weaknesses),
            inspiration_kind=InspirationKind.INDEPENDENT,
        )

    def to_transform(
        self,
        *,
        request: TransformationRequest,
        parents: tuple[IdeaGenome, ...],
    ) -> IdeaGenome:
        return IdeaGenome(
            id=uuid4(),
            generation=max(parent.generation for parent in parents) + 1,
            title=self.title,
            core_mechanism=self.core_mechanism,
            problem_framing=self.problem_framing,
            assumptions_challenged=tuple(self.assumptions_challenged),
            task_value=self.task_value,
            distinguishing_features=tuple(self.distinguishing_features),
            first_order_effects=tuple(self.first_order_effects),
            second_order_effects=tuple(self.second_order_effects),
            feasibility_assumptions=tuple(self.feasibility_assumptions),
            uncertainties=tuple(self.uncertainties),
            weaknesses=tuple(self.weaknesses),
            parent_ids=request.parent_ids,
            transformations=expected_transformation_history(
                request.operator,
                parents,
            ),
            inspiration_kind=InspirationKind.SYNTHESIZED,
        )


class OpenAISeedBatch(OpenAIOutputModel):
    ideas: list[OpenAIIdea]


class OpenAIEvaluation(OpenAIOutputModel):
    originality: float = Field(ge=0, le=1)
    usefulness: float = Field(ge=0, le=1)
    coherence: float = Field(ge=0, le=1)
    feasibility: float = Field(ge=0, le=1)
    user_fit: float = Field(ge=0, le=1)

    def to_domain(self) -> EvaluationScores:
        return EvaluationScores.model_validate(self.model_dump())
```

Domain IDs, ancestry, generation, inspiration kind, and transformation history are
assigned locally. The model never controls those trust-boundary fields.

- [ ] **Step 4: Add adversarial conversion tests**

Test:

- Blank required text is rejected.
- Score values outside 0–1 are rejected.
- Transform conversion always uses request parent IDs and expected history.
- Seed batch cardinality mismatch is rejected by provider code, not silently truncated.

- [ ] **Step 5: Run and commit**

```powershell
python -m pytest tests/test_openai_schemas.py -v
python -m ruff check .
git add src/creativity_layer/openai_schemas.py tests/test_openai_schemas.py
git commit -m "feat: define OpenAI structured output schemas"
```

## Task 6: Implement the OpenAI Creative Provider

**Files:**
- Create: `src/creativity_layer/openai_provider.py`
- Create: `tests/test_openai_provider.py`
- Modify: `src/creativity_layer/__init__.py`

- [ ] **Step 1: Write failing mocked-provider tests**

Use a fake client that implements `responses.parse` and records keyword arguments:

```python
def test_openai_provider_frames_with_economy_model_and_structured_schema() -> None:
    client = FakeOpenAIClient(
        parsed=OpenAIFrame(
            assumptions=["Meetings are necessary"],
            obvious_solution="Use asynchronous voting",
        ),
        usage=FakeUsage(input_tokens=100, output_tokens=40),
    )
    provider = build_provider(client)

    response = provider.frame(TaskContext(goal="Improve team decisions"))

    assert client.last_request["model"] == "economy-test-model"
    assert client.last_request["text_format"] is OpenAIFrame
    assert response.value.obvious_solution == "Use asynchronous voting"
    assert response.usage.input_tokens == 100


def test_openai_provider_uses_strong_model_for_transformations() -> None:
    parent = sample_parent()
    request = TransformationRequest.for_operator(
        operator=OperatorName.INVERT,
        parents=(parent,),
        task_goal="Improve team decisions",
    )
    client = FakeOpenAIClient(
        parsed=sample_openai_idea(title="Inverted process"),
        usage=FakeUsage(input_tokens=120, output_tokens=60),
    )
    provider = build_provider(client)

    response = provider.transform(request, (parent,))

    assert client.last_request["model"] == "strong-test-model"
    assert response.value.parent_ids == (parent.id,)


def test_openai_provider_retries_one_unparseable_response() -> None:
    client = FakeOpenAIClient(
        parsed_sequence=[
            None,
            OpenAIFrame(
                assumptions=["Meetings are necessary"],
                obvious_solution="Use asynchronous voting",
            ),
        ],
        usage=FakeUsage(input_tokens=100, output_tokens=40),
    )
    provider = build_provider(client, repair_attempts=1)

    response = provider.frame(TaskContext(goal="Improve team decisions"))

    assert response.value.obvious_solution == "Use asynchronous voting"
    assert client.call_count == 2
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
python -m pytest tests/test_openai_provider.py -v
```

Expected: FAIL because the provider does not exist.

- [ ] **Step 3: Implement response extraction helpers**

In `openai_provider.py`, add:

```python
def _parsed_output(response: object, expected_type: type[T]) -> T:
    for output in response.output:
        if getattr(output, "type", None) != "message":
            continue
        for content in output.content:
            parsed = getattr(content, "parsed", None)
            if isinstance(parsed, expected_type):
                return parsed
    raise ValueError("OpenAI response did not contain parsed structured output")


def _usage(response: object) -> TokenUsage:
    usage = response.usage
    details = getattr(usage, "input_tokens_details", None)
    output_details = getattr(usage, "output_tokens_details", None)
    return TokenUsage(
        input_tokens=usage.input_tokens,
        cached_input_tokens=getattr(details, "cached_tokens", 0) or 0,
        output_tokens=usage.output_tokens,
        reasoning_tokens=getattr(output_details, "reasoning_tokens", 0) or 0,
    )
```

- [ ] **Step 4: Implement provider construction and prompts**

```python
class OpenAICreativeProvider:
    name = "openai"
    version = "responses-v1"

    def __init__(
        self,
        *,
        client: OpenAI,
        config: LiveModelConfig,
        pricing: PricingTable,
        retry_policy: RetryPolicy,
        breaker: CircuitBreaker,
    ) -> None:
        self._client = client
        self._config = config
        self._pricing = pricing
        self._retry_policy = retry_policy
        self._breaker = breaker
```

Implement:

- `quote_frame`
- `frame`
- `quote_seed`
- `seed`
- `quote_transform`
- `transform`
- `quote_evaluation`
- `evaluate`

Every live method:

1. Builds a deterministic system/developer instruction and JSON-safe input.
2. Calls `client.responses.parse(model=model_name, input=request_input, text_format=schema)`.
3. Runs through `execute_with_retries`.
4. Extracts parsed output.
5. Converts to domain models.
6. Normalizes token usage.
7. Calculates estimated cost through `PricingTable`.
8. Returns `MeteredResponse` with model, usage, pricing version, estimate flag, request
   ID, measured latency, and an `OperationTrace`.

The operation trace stores JSON-safe request and response payloads:

- Request: model role, model ID, structured prompt messages/input, schema name, and
  operation-specific domain payload.
- Response: parsed structured output and refusal metadata when present.

It never stores the API key, headers, SDK client objects, or raw exceptions.

Quotes use configurable conservative token ceilings per operation, not guessed actual
usage. Add these ceilings to `LiveModelConfig`:

```python
frame_max_input_tokens: int = 2_000
frame_max_output_tokens: int = 800
seed_max_input_tokens: int = 3_000
seed_max_output_tokens: int = 2_500
transform_max_input_tokens: int = 3_000
transform_max_output_tokens: int = 1_500
evaluation_max_input_tokens: int = 3_000
evaluation_max_output_tokens: int = 800
```

Use the pricing table to turn ceilings into `OperationQuote.max_cost_usd`.

- [ ] **Step 5: Add prompt-safety and repair tests**

Test:

- Task text is passed as user data, not concatenated into system instructions.
- The model cannot set provider identity, UUIDs, ancestry, transformations, or cost.
- Refusals and absent parsed output trigger bounded repair.
- Authentication errors are not retried.
- Rate limits and timeouts use retry policy.
- Error messages do not include API keys or full prompts.
- Actual usage over quote is handled by the existing audited-overage path.

- [ ] **Step 6: Run and commit**

```powershell
python -m pytest tests/test_openai_provider.py -v
python -m pytest
python -m ruff check .
git add src/creativity_layer/openai_provider.py src/creativity_layer/live_config.py src/creativity_layer/__init__.py tests/test_openai_provider.py
git commit -m "feat: add OpenAI creative provider"
```

## Task 7: Implement the OpenAI Embedding Adapter

**Files:**
- Create: `src/creativity_layer/embeddings.py`
- Create: `src/creativity_layer/openai_embeddings.py`
- Create: `tests/test_openai_embeddings.py`

- [ ] **Step 1: Write failing embedding tests**

```python
# tests/test_openai_embeddings.py
from creativity_layer.openai_embeddings import OpenAIEmbeddingProvider


def test_embedding_provider_preserves_input_order_and_usage() -> None:
    client = FakeEmbeddingClient(
        vectors=[[0.1, 0.2], [0.3, 0.4]],
        prompt_tokens=12,
    )
    provider = build_embedding_provider(client)

    response = provider.embed(("first", "second"))

    assert response.value.vectors == ((0.1, 0.2), (0.3, 0.4))
    assert response.value.dimensions == 2
    assert response.usage.input_tokens == 12
    assert client.last_request["model"] == "embedding-test-model"


def test_embedding_provider_rejects_wrong_vector_count() -> None:
    client = FakeEmbeddingClient(
        vectors=[[0.1, 0.2]],
        prompt_tokens=12,
    )
    provider = build_embedding_provider(client)

    try:
        provider.embed(("first", "second"))
    except ValueError as error:
        assert str(error) == "embedding count does not match input count"
    else:
        raise AssertionError("wrong vector count was accepted")
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
python -m pytest tests/test_openai_embeddings.py -v
```

Expected: FAIL because embedding contracts do not exist.

- [ ] **Step 3: Define embedding contracts**

```python
# src/creativity_layer/embeddings.py
from typing import Protocol

from pydantic import Field

from creativity_layer.models import FrozenModel
from creativity_layer.providers import MeteredResponse, OperationQuote


class EmbeddingBatch(FrozenModel):
    vectors: tuple[tuple[float, ...], ...]
    dimensions: int = Field(strict=True, gt=0)


class EmbeddingProvider(Protocol):
    name: str
    version: str

    def quote_embeddings(self, texts: tuple[str, ...]) -> OperationQuote:
        raise NotImplementedError

    def embed(self, texts: tuple[str, ...]) -> MeteredResponse[EmbeddingBatch]:
        raise NotImplementedError
```

- [ ] **Step 4: Implement OpenAI embeddings**

Call:

```python
client.embeddings.create(
    model=config.embedding_model,
    input=list(texts),
)
```

Validate:

- Nonempty input strings
- Response vector count equals input count
- All vectors have equal nonzero dimensions
- Response indices reconstruct input order
- Usage enters `TokenUsage.input_tokens`
- Pricing uses embedding-specific per-million input pricing
- Operation trace stores input count and model, not full embedding vectors
- Retry and circuit-breaker behavior matches text operations

- [ ] **Step 5: Run and commit**

```powershell
python -m pytest tests/test_openai_embeddings.py -v
python -m ruff check .
git add src/creativity_layer/embeddings.py src/creativity_layer/openai_embeddings.py tests/test_openai_embeddings.py
git commit -m "feat: add OpenAI embedding adapter"
```

## Task 8: Add Research and Private Trace Views

**Files:**
- Create: `src/creativity_layer/privacy.py`
- Modify: `src/creativity_layer/tracing.py`
- Create: `tests/test_privacy.py`
- Modify: `tests/test_tracing.py`

- [ ] **Step 1: Write failing privacy tests**

```python
# tests/test_privacy.py
from creativity_layer.live_config import PrivacyMode
from creativity_layer.privacy import TraceView


def test_research_trace_keeps_prompts_but_never_secrets() -> None:
    view = TraceView(
        mode=PrivacyMode.RESEARCH,
        secret_values=("sk-secret",),
    )

    payload = view.sanitize(
        {
            "prompt": "Create an idea using sk-secret",
            "authorization": "Bearer sk-secret",
        }
    )

    assert payload["prompt"] == "Create an idea using [REDACTED]"
    assert payload["authorization"] == "[REDACTED]"


def test_private_trace_hashes_prompt_content() -> None:
    view = TraceView(mode=PrivacyMode.PRIVATE, secret_values=())

    payload = view.sanitize({"prompt": "private task", "output": "private idea"})

    assert payload["prompt"] != "private task"
    assert payload["prompt"]["sha256"]
    assert payload["output"]["sha256"]
```

- [ ] **Step 2: Run tests and verify RED**

```powershell
python -m pytest tests/test_privacy.py -v
```

Expected: FAIL because privacy views do not exist.

- [ ] **Step 3: Implement deterministic sanitization**

`TraceView.sanitize` recursively:

- Replaces configured secret values with `[REDACTED]`
- Redacts keys matching `api_key`, `authorization`, `token`, `secret`, and `password`
- In research mode, retains sanitized prompt/output text
- In private mode, replaces prompt/output text with `{sha256, length}`
- Leaves structured scores, usage, model IDs, costs, errors, and fingerprints intact
- Never mutates the original object

- [ ] **Step 4: Add trace-store view support**

Change:

```python
JsonTraceStore(
    root,
    trace_view=TraceView(
        mode=PrivacyMode.PRIVATE,
        secret_values=(credentials.api_key.get_secret_value(),),
    ),
)
```

Before atomic JSON writing:

```python
payload = result.model_dump(mode="json")
sanitized = self._trace_view.sanitize(payload)
json.dumps(sanitized, indent=2)
```

The default trace view remains research mode with no configured secrets so deterministic
tests stay backward compatible.

- [ ] **Step 5: Test nested redaction and fingerprint behavior**

Add tests proving:

- Secrets are removed from nested errors and provider metadata.
- Private-mode files do not contain original task goals.
- Sanitization does not modify the in-memory `RunResult`.
- The run fingerprint continues to describe the internal canonical run, not the redacted
  serialized view.

- [ ] **Step 6: Run and commit**

```powershell
python -m pytest tests/test_privacy.py tests/test_tracing.py -v
python -m pytest
python -m ruff check .
git add src/creativity_layer/privacy.py src/creativity_layer/tracing.py tests/test_privacy.py tests/test_tracing.py
git commit -m "feat: add privacy-aware research traces"
```

## Task 9: Add the Live CLI Command

**Files:**
- Modify: `src/creativity_layer/cli.py`
- Create: `tests/test_live_cli.py`
- Modify: `README.md`

- [ ] **Step 1: Write failing CLI parsing tests**

```python
# tests/test_live_cli.py
from creativity_layer.cli import run_cli


def test_live_command_requires_openai_configuration(monkeypatch, capsys) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_ECONOMY_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_STRONG_MODEL", raising=False)

    exit_code = run_cli(["live", "Invent a new coordination mechanism"])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "OPENAI_API_KEY" in captured.err
    assert captured.out == ""


def test_existing_command_defaults_to_deterministic_mode(tmp_path, capsys) -> None:
    exit_code = run_cli(
        [
            "Invent a calmer process",
            "--trace-dir",
            str(tmp_path),
            "--seed-count",
            "2",
            "--finalist-count",
            "1",
        ]
    )

    assert exit_code == 0
```

- [ ] **Step 2: Run tests and verify RED**

```powershell
python -m pytest tests/test_live_cli.py -v
```

Expected: FAIL because the CLI has no `live` command.

- [ ] **Step 3: Refactor parser without breaking deterministic usage**

Support:

```powershell
creativity-layer "offline task"
creativity-layer deterministic "offline task"
creativity-layer live "live task" --budget-usd 0.10
```

To preserve compatibility, if the first argument is not a recognized subcommand, insert
`deterministic` before parsing.

Live arguments:

- `goal`
- `--budget-usd`, default `0.10`
- `--seed-count`, default `4`
- `--finalist-count`, default `2`
- `--generations`, default `1`
- `--trace-dir`, default `.traces`
- `--privacy`, `research|private`
- `--economy-model`
- `--strong-model`
- `--embedding-model`
- `--timeout-seconds`
- `--max-retries`

CLI flags override environment model configuration.

- [ ] **Step 4: Build live dependencies through a factory**

Add a small private helper:

```python
def _build_openai_provider(
    *,
    credentials: OpenAICredentials,
    config: LiveModelConfig,
    pricing: PricingTable,
) -> OpenAICreativeProvider:
    client = OpenAI(
        api_key=credentials.api_key.get_secret_value(),
        timeout=config.timeout_seconds,
        max_retries=0,
    )
    return OpenAICreativeProvider(
        client=client,
        config=config,
        pricing=pricing,
        retry_policy=RetryPolicy(max_retries=config.max_retries),
        breaker=CircuitBreaker(
            failure_threshold=config.circuit_failure_threshold
        ),
    )
```

SDK retries remain disabled because `reliability.py` owns bounded retry behavior.

The pricing table is loaded from a required JSON configuration path supplied by
`--pricing-file` or `OPENAI_PRICING_FILE`. This prevents stale hard-coded pricing.

- [ ] **Step 5: Add mocked live-run CLI tests**

Monkeypatch the provider factory and test:

- `live` uses a $0.10 default hard ceiling.
- Economy and strong model IDs enter trace providers/operation metadata.
- `--privacy private` writes no raw goal text.
- Provider errors return 1 and write a trace.
- Missing or malformed pricing config returns 2 without traceback.
- API keys never appear in stdout, stderr, or traces.

- [ ] **Step 6: Document live setup**

Add to README:

```markdown
## Live OpenAI mode

Set:

```powershell
$env:OPENAI_API_KEY = "<your-api-key>"
$env:OPENAI_ECONOMY_MODEL = "<explicit model id>"
$env:OPENAI_STRONG_MODEL = "<explicit model id>"
$env:OPENAI_EMBEDDING_MODEL = "text-embedding-3-small"
$env:OPENAI_PRICING_FILE = "path\to\pricing.json"
```

Run:

```powershell
creativity-layer live "Invent a low-cost coordination mechanism" `
  --budget-usd 0.10 `
  --privacy private
```

Live mode performs no web search in Slice 2A.
```

- [ ] **Step 7: Run and commit**

```powershell
python -m pytest tests/test_live_cli.py tests/test_cli.py -v
python -m pytest
python -m ruff check .
git add src/creativity_layer/cli.py tests/test_live_cli.py README.md
git commit -m "feat: add live OpenAI CLI mode"
```

## Task 10: Add Environment-Gated Live Smoke Test

**Files:**
- Create: `tests/test_openai_live.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Register the live marker**

Add:

```toml
[tool.pytest.ini_options]
addopts = "-ra"
testpaths = ["tests"]
markers = [
  "live_openai: incurs a bounded real OpenAI API request",
]
```

- [ ] **Step 2: Add the gated test**

```python
# tests/test_openai_live.py
import os

import pytest

from creativity_layer.cli import run_cli


pytestmark = pytest.mark.live_openai


def test_live_openai_smoke(tmp_path) -> None:
    required = (
        "OPENAI_API_KEY",
        "OPENAI_ECONOMY_MODEL",
        "OPENAI_STRONG_MODEL",
        "OPENAI_PRICING_FILE",
    )
    if any(not os.getenv(name) for name in required):
        pytest.skip("live OpenAI environment is not configured")

    exit_code = run_cli(
        [
            "live",
            "Invent one reversible way to coordinate a two-person decision.",
            "--budget-usd",
            "0.03",
            "--seed-count",
            "2",
            "--finalist-count",
            "1",
            "--generations",
            "0",
            "--trace-dir",
            str(tmp_path),
            "--privacy",
            "private",
        ]
    )

    assert exit_code == 0
    assert len(list(tmp_path.glob("*.json"))) == 1
```

- [ ] **Step 3: Verify normal tests incur no API cost**

Run:

```powershell
python -m pytest -m "not live_openai"
```

Expected: all normal tests PASS; live test is deselected or skipped and no network call
occurs.

- [ ] **Step 4: Run mocked full verification**

```powershell
python -m pytest -m "not live_openai" --cov=creativity_layer --cov-report=term-missing
python -m ruff check .
git status --short
```

Expected: tests and Ruff PASS; working tree contains only intended test changes.

- [ ] **Step 5: Optionally run paid smoke test**

Only when the user explicitly provides/approves configured credentials:

```powershell
python -m pytest tests/test_openai_live.py -m live_openai -v
```

Expected: one live test PASS within its `$0.03` ceiling.

- [ ] **Step 6: Commit**

```powershell
git add pyproject.toml tests/test_openai_live.py
git commit -m "test: add gated OpenAI live smoke test"
```

## Task 11: Final Slice 2A Verification and Review

**Files:**
- Modify only if verification exposes a defect.

- [ ] **Step 1: Run all offline tests**

```powershell
python -m pytest -m "not live_openai" -v --cov=creativity_layer --cov-report=term-missing
```

Expected: all offline tests PASS with no project-owned warnings.

- [ ] **Step 2: Run static checks**

```powershell
python -m ruff check .
python -m compileall -q src tests
```

Expected: both commands exit 0.

- [ ] **Step 3: Run deterministic regression smoke**

```powershell
creativity-layer deterministic "Invent a reversible neighborhood tool-sharing rule" `
  --seed-count 2 `
  --finalist-count 1 `
  --generations 1 `
  --trace-dir $env:TEMP\creativity-layer-2a-deterministic
```

Expected: exit 0, one finalist, and a valid trace.

- [ ] **Step 4: Run mocked live CLI contract**

```powershell
python -m pytest tests/test_live_cli.py tests/test_openai_provider.py tests/test_openai_embeddings.py -v
```

Expected: all tests PASS without network access.

- [ ] **Step 5: Inspect the branch**

```powershell
git status --short
git log --oneline --decorate -15
git diff --check main...HEAD
```

Expected: clean working tree, focused commits, and no whitespace errors.

- [ ] **Step 6: Request final code review**

Use `superpowers:requesting-code-review` with:

- Base SHA: Slice 2A branch point from `main`
- Head SHA: current Slice 2A head
- Requirements: this plan and Slice 2A in
  `docs/superpowers/specs/2026-06-23-live-model-search-novelty-design.md`
- Focus: no secret leakage, truthful usage/cost accounting, provider-neutral core,
  structured-output trust boundaries, retry ownership, hard budget behavior, private
  trace behavior, and zero network calls in normal tests

- [ ] **Step 7: Fix every Critical or Important issue with TDD**

For each issue:

1. Write a failing regression test.
2. Confirm RED for the expected reason.
3. Implement the minimal fix.
4. Run focused tests.
5. Run the complete offline suite and Ruff.
6. Commit with a focused message.
7. Request re-review.

- [ ] **Step 8: Final verification**

```powershell
python -m pytest -m "not live_openai" -q -p no:asyncio --cov=creativity_layer --cov-report=term-missing
python -m ruff check .
git status -sb
```

Expected: all tests PASS, Ruff exits 0, and the worktree is clean.
