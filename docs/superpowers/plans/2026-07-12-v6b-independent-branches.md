# V6-B Independent Branch Generation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task with RED-GREEN TDD.

**Goal:** Make every live seed an independent model trajectory with an explicit creative strategy instead of returning all seeds from one batch response.

**Architecture:** Introduce typed branch strategies and a branch-generation record. The live OpenAI seeder performs one structured call per requested seed, passing only that branch strategy and the framed task, then combines metering and traces into the existing provider-neutral seed envelope. The deterministic fixture may retain its no-network implementation.

**Tech Stack:** Python 3.12, Pydantic 2, OpenAI Responses structured outputs, pytest.

## Global Constraints

- seed_count N in live mode means N independent provider invocations.
- Normal mode uses four distinct strategies; extensive mode uses six before reuse.
- Strategies change causal search direction, not cosmetic writing style.
- A failed branch does not silently reduce cardinality or duplicate another branch.
- Cost, token usage, latency, calls, and traces aggregate across branch invocations.
- Public MCP callers still choose only normal or extensive.

---

### Task 1: Branch strategy contracts

**Files:**
- Create: src/muse/branching.py
- Create: tests/test_branching.py
- Modify: src/muse/models.py

**Interfaces:**
- Produces: BranchStrategy, BranchDirective, branch_directives(seed_count), and IdeaGenome.branch_strategy.

- [ ] Write failing tests for six distinct strategy directives, deterministic ordering, reuse beyond six, and model round trips.
- [ ] Run the focused tests and verify RED.
- [ ] Implement constraint inversion, failure-first, cross-domain transfer, systems effects, minimal mechanism, and user-centered strategies with concrete instructions.
- [ ] Run focused/full tests and Ruff.
- [ ] Commit as feat: add independent branch strategies.

### Task 2: Independent live seed calls

**Files:**
- Modify: src/muse/openai_provider.py
- Modify: src/muse/openai_schemas.py
- Modify: tests/test_openai_provider.py
- Modify: tests/test_openai_live.py

**Interfaces:**
- Consumes: branch_directives and existing structured-call machinery.
- Produces: OpenAICreativeProvider.seed with one call per branch and one aggregate MeteredResponse.

- [ ] Write failing fake-client tests proving seed_count calls, distinct branch payloads, branch provenance, aggregate usage/cost/latency/call count, and all-or-nothing cardinality on a failed branch.
- [ ] Run focused tests and verify RED.
- [ ] Implement one structured seed call per directive and aggregate validated responses without changing the engine contract.
- [ ] Run focused/full tests and Ruff.
- [ ] Commit as feat: generate live seeds independently.

### Task 3: Agent-facing evidence and docs

**Files:**
- Modify: src/muse/middleware.py
- Modify: tests/test_middleware.py
- Modify: README.md
- Modify: docs/quality/benchmarking.md

**Interfaces:**
- Produces: response config field branch_generation with strategy names and independent_call_count.

- [ ] Write failing response and documentation assertions.
- [ ] Verify RED.
- [ ] Surface non-secret branch-generation metadata and explain why seed count now measures independent trajectories.
- [ ] Run focused/full tests and Ruff.
- [ ] Commit as docs: expose independent branch evidence.
