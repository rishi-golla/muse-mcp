# Muse Quality Benchmarking

This is a library-first maintainer workflow for producing evidence about Muse's
creative quality. It is deliberately separate from the public MCP workflow and
does not add a public CLI. Agents and users continue to use `muse_plan`; benchmark
adapters are assembled by maintainers when a controlled quality comparison is
needed.

## What the benchmark measures

The benchmark compares two independently generated artifacts for the same
`BenchmarkTask`:

- Muse, using the adapter under evaluation.
- A direct strong-model baseline, using the same task prompt with the strong
  model directly and without Muse's search or orchestration.

The baseline must be strong enough to be a meaningful comparator. Comparing Muse
with a weak prompt, a cheaper model, or a baseline that receives less useful task
context does not support a claim that Muse improves quality.

The corpus is `DEFAULT_BENCHMARK_CORPUS`, a domain-varied set of at least 30 tasks.
Adapters are injected into `run_quality_benchmark`, so the core runner remains
provider-neutral and ordinary tests make no network calls or provider spend.

## Library-first workflow

Maintainers provide three callables: a Muse artifact generator, a direct baseline
artifact generator, and a pairwise judge. Each generator returns a
`BenchmarkArtifact` with the generated content plus measured `cost_usd` and
`latency_ms`. The judge returns a typed `JudgeAttempt`, which contains either a
`PairwiseJudgment` or a sanitized `JudgeFailure`, plus its own cost and latency.
Returned failure attempts are sanitized by the runner just like judge exceptions.

```python
from datetime import UTC, datetime

from muse.quality_benchmark import (
    DEFAULT_BENCHMARK_CORPUS,
    BenchmarkArtifact,
    BenchmarkTask,
    JudgeArtifact,
    JudgeAttempt,
    run_quality_benchmark,
)


def muse_generator(task: BenchmarkTask) -> BenchmarkArtifact:
    result = call_muse(task.prompt)
    return BenchmarkArtifact(
        content=result.text,
        cost_usd=result.cost_usd,
        latency_ms=result.latency_ms,
    )


def baseline_generator(task: BenchmarkTask) -> BenchmarkArtifact:
    result = call_strong_model_directly(task.prompt)
    return BenchmarkArtifact(
        content=result.text,
        cost_usd=result.cost_usd,
        latency_ms=result.latency_ms,
    )


def judge(
    task: BenchmarkTask,
    candidate_a: JudgeArtifact,
    candidate_b: JudgeArtifact,
) -> JudgeAttempt:
    result = call_blinded_judge(task.prompt, candidate_a.content, candidate_b.content)
    return JudgeAttempt(
        judgment=result.judgment,
        cost_usd=result.cost_usd,
        latency_ms=result.latency_ms,
    )


configured_api_key = get_secret_from_secret_manager()


report = run_quality_benchmark(
    DEFAULT_BENCHMARK_CORPUS,
    muse_generator,
    baseline_generator,
    judge,
    repetitions=3,
    random_seed=17,
    run_timestamp=datetime(2026, 7, 12, 12, 0, tzinfo=UTC),
    prompt_version="prompt-v3",
    config_version="config-v4",
    muse_adapter="muse-live-v1",
    baseline_adapter="strong-direct-v1",
    judge_adapter="quality-judge-v1",
    blind_labels=("muse-live-v1", "strong-direct-v1"),
    system_identifiers=("system-alpha", "system-beta"),
    provider_labels=("provider-name", "model-name"),
    secret_values=(configured_api_key,),
)
```

The example's `call_muse`, `call_strong_model_directly`, and
`call_blinded_judge` are live adapters supplied by the maintainer. They are not
part of the public Muse API. Keep credentials and provider-specific behavior in
those adapters, not in the provider-neutral runner.

## Blinded pairwise judging

The runner generates both artifacts independently. It derives the A/B assignment
from `random_seed`, task name, and repetition, so a failed earlier cell cannot
shift later mappings. The judge receives only `JudgeArtifact` content;
`for_judge()` removes cost, latency, and system identity.

By default, ordinary words such as `baseline` and `judge` are not treated as
identity leaks. Before the judge call, the runner rejects and records content
containing an explicitly configured `blind_labels`, `system_identifiers`, or
`provider_labels` value, using identifier boundaries rather than substring
matching. Such a cell retains its generation telemetry but is excluded from
judging. Do not put model names, system labels, cost, or latency in judge input.
A judge that can identify the systems is not a blinded pairwise comparison.

## Repeated runs and accounting

`RunMetadata` makes each report self-describing and deterministic when the caller
supplies stable inputs. It records the seed, repetition count, corpus version,
aware run timestamp, prompt version, configuration version, adapter identifiers,
and configured blind/provider labels. The timestamp is caller-supplied rather than
generated inside the runner, so deterministic tests can use a fixed value.
`secret_values` is used only while sanitizing generation and judge exceptions; it
is never stored in metadata or report records. Use a fixed `random_seed` when a
run must be reproduced. Do not treat one favorable run as a stable result.

Repetitions are raw evidence, not independent Wilson trials. The runner first
aggregates each task's decisive repetition outcomes: a task counts as a win or
loss only when one side has a strict decisive majority; otherwise it is a tie.
Wilson lower and upper bounds use those task-level decisive outcomes. Raw
repetition judgments remain in `records` for auditability.

Every report includes:

- raw judged repetitions and task-level wins, losses, ties, and decisive comparisons;
- Wilson lower and upper bounds for the task-level decisive preference rate;
- generation attempts/failures and judge attempts/failures;
- separate generation and judge cost/latency plus combined totals;
- failure type and sanitized message for every failed generation or judge attempt.

Live adapters must report measured cost and latency for both systems and the judge,
and let the runner capture generation and judge exceptions as failures. A quality
report that omits failed attempts, spend, latency, or deterministic metadata is
incomplete and should not be used for a comparative claim.

## Quality-claim rule

Unit tests do not establish creative quality. They establish that contracts,
validation, deterministic randomization, blinding, label-leak rejection,
task-level repetition handling, failure capture, and accounting behave as
intended without making provider calls.

A claim that Muse produces better creative work requires a benchmark report based
on the domain-varied corpus, a direct strong-model baseline, blinded pairwise
judging, repeated runs, task-level uncertainty, and complete generation/judge
cost, latency, and failure accounting. Describe uncertainty and ties; do not
convert a passing test suite or a single unblinded example into a creative-quality
claim.
