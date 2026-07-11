# V6-A Quality Benchmark Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Build a provider-neutral, blinded benchmark that measures Muse against a baseline across a 30-task corpus.

**Architecture:** Add immutable benchmark contracts, a deterministic corpus, and a runner that receives injected Muse, baseline, and judge callables. Keep live-provider concerns outside the core so tests are free and reproducible.

**Tech Stack:** Python 3.12, Pydantic 2, pytest, existing Muse frozen models.

## Global Constraints

- Public MCP usage remains live-first and agent-native.
- Ordinary tests make no network calls and spend no provider budget.
- Candidate identity is hidden from judges and randomized deterministically.
- Reports retain raw judgments, cost, latency, failures, and confidence bounds.
- The default corpus contains at least 30 tasks across multiple domains.

---

### Task 1: Benchmark contracts and corpus

**Files:**
- Create: src/muse/quality_benchmark.py
- Create: tests/test_quality_benchmark.py

**Interfaces:**
- Produces: BenchmarkTask, BenchmarkArtifact, PairwiseJudgment, BenchmarkCorpus, and DEFAULT_BENCHMARK_CORPUS.

- [ ] Step 1: Write tests proving invalid artifacts and preferences are rejected, names are unique, and the corpus contains at least 30 tasks across coding, product, design, operations, and research.
- [ ] Step 2: Run python -m pytest tests/test_quality_benchmark.py -q and verify failure because the module is absent.
- [ ] Step 3: Implement immutable contracts, a Preference enum, and curated domain-varied tasks without expected-answer keywords.
- [ ] Step 4: Run the focused test and verify it passes.
- [ ] Step 5: Commit as feat: add blinded benchmark contracts.

### Task 2: Blinded runner and statistics

**Files:**
- Modify: src/muse/quality_benchmark.py
- Modify: tests/test_quality_benchmark.py
- Modify: src/muse/__init__.py

**Interfaces:**
- Consumes: injected ArtifactGenerator and PairwiseJudge callables.
- Produces: run_quality_benchmark returning BenchmarkReport.

- [ ] Step 1: Write tests for reproducible order randomization, hidden labels, repetitions, failures, ties, accounting, and Wilson bounds.
- [ ] Step 2: Run the focused test and verify the runner tests fail.
- [ ] Step 3: Implement independent artifact generation, blinded mapping, raw records, summary counts, preference rate, Wilson bounds, total cost, and latency.
- [ ] Step 4: Run focused and full tests and verify they pass.
- [ ] Step 5: Commit as feat: run blinded quality comparisons.

### Task 3: Benchmark documentation

**Files:**
- Modify: README.md
- Create: docs/quality/benchmarking.md
- Modify: tests/test_open_source_readiness.py

**Interfaces:**
- Produces: maintainer guidance for live adapters without a public CLI.

- [ ] Step 1: Write documentation assertions for the direct baseline, blinding, repeated runs, accounting, and the distinction between correctness tests and quality evidence.
- [ ] Step 2: Verify the documentation test fails.
- [ ] Step 3: Document the library-first API and quality-claim rule.
- [ ] Step 4: Run focused and full tests and verify they pass.
- [ ] Step 5: Commit as docs: define Muse quality benchmarking.
