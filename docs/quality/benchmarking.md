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
`latency_ms`.

```python
from muse.quality_benchmark import (
    DEFAULT_BENCHMARK_CORPUS,
    BenchmarkArtifact,
    BenchmarkTask,
    JudgeArtifact,
    PairwiseJudgment,
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
) -> PairwiseJudgment:
    return call_blinded_judge(task.prompt, candidate_a.content, candidate_b.content)


report = run_quality_benchmark(
    DEFAULT_BENCHMARK_CORPUS,
    muse_generator,
    baseline_generator,
    judge,
    repetitions=3,
    random_seed=17,
)
```

The example's `call_muse`, `call_strong_model_directly`, and
`call_blinded_judge` are live adapters supplied by the maintainer. They are not
part of the public Muse API. Keep credentials and provider-specific behavior in
those adapters, not in the provider-neutral runner.

## Blinded pairwise judging

The runner generates Muse and baseline artifacts independently, then randomly
assigns them to candidate A or candidate B using the supplied seed. The judge
receives only `JudgeArtifact` content. `for_judge()` removes cost, latency, and
system identity before judging, and the raw record retains the hidden mapping so
the result can be scored afterward.

The judge returns a `PairwiseJudgment` containing an overall preference, confidence,
rationale, and separate originality, usefulness, operational-specificity, and
task-fit preferences. Do not put model names, system labels, cost, or latency in
the judge input. A judge that can identify the systems is not a blinded pairwise
comparison.

## Repeated runs and accounting

Use `repetitions` to run every task more than once and provide a fixed
`random_seed` when a run must be reproduced. Record the corpus, adapter model
identifiers, prompt/configuration version, repetition count, seed, and run date
alongside the report. Do not treat one favorable run as a stable result.

Every report includes:

- judged comparisons, wins, losses, ties, decisive comparisons, and preference rate;
- Wilson lower and upper bounds for the decisive preference rate;
- total generation cost and latency;
- total generation attempts and failures, with failure type and message in each
  failed record.

Live adapters must report measured cost and latency for both systems and let the
runner capture generation exceptions as failures. A quality report that omits
failed attempts, spend, or latency is incomplete and should not be used for a
comparative claim.

## Quality-claim rule

Unit tests do not establish creative quality. They establish that contracts,
validation, deterministic randomization, blinding, repetition handling, failure
capture, and accounting behave as intended without making provider calls.

A claim that Muse produces better creative work requires a benchmark report based
on the domain-varied corpus, a direct strong-model baseline, blinded pairwise
judging, repeated runs, and complete cost, latency, and failure accounting.
Describe uncertainty and ties; do not convert a passing test suite or a single
unblinded example into a creative-quality claim.
