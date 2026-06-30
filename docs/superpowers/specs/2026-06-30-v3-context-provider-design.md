# V3-C Context Provider Design

## 1. Purpose

V3-C adds a provider-neutral context retrieval layer for middleware callers. V3-B
proved the engine can consume typed `ContextBundle` data. V3-C defines how an agent
backend can assemble that bundle from generic repository and task signals without
turning Creativity Layer into a CLI, a repo-specific integration, or a filesystem
crawler.

The slice tests this claim:

> A backend can pass generic repo/task facts into a `ContextProvider` and receive a
> useful, repo-agnostic `ContextBundle` for the creative engine.

## 2. Scope

### Included

- `ContextRequest` for the task plus optional repo facts.
- `RepoSignals` for generic facts: file paths, changed files, package manifests, test
  commands, CI logs, dependency graph hints, detected languages, detected frameworks,
  and arbitrary metadata.
- `ContextProvider` protocol with quote and retrieval methods.
- `DeterministicContextProvider` that converts supplied signals into a bounded
  `ContextBundle`.
- A helper that resolves context before running `CreativeEngine`.
- CLI harness support for a `--repo-signals-file`, only as an edge adapter.
- Tests proving TypeScript, Python, and arbitrary middleware tasks produce different,
  repo-agnostic context.

### Excluded

- Middleware server or SDK packaging.
- Filesystem crawling.
- Live web search expansion.
- Persistent memory.
- Provider-specific repo integrations.

## 3. Architecture

`context_provider.py` owns the new provider contract:

- `RepoSignals`: immutable Pydantic model for caller-supplied repo evidence.
- `ContextRequest`: task, repo signals, and max snippet count.
- `ContextProvider`: protocol with `quote_context(request)` and `build_context(request)`.
- `DeterministicContextProvider`: no-network implementation for tests and local harnesses.
- `build_task_context(...)`: helper that merges provider-built context into a
  `TaskContext` before the engine runs.

The engine remains unchanged. Middleware callers will do:

```text
RepoSignals + task -> ContextProvider -> ContextBundle -> TaskContext -> CreativeEngine
```

CLI support is only an adapter:

```text
--repo-signals-file -> RepoSignals -> ContextProvider -> ContextBundle
```

## 4. Provider Behavior

The deterministic provider emits snippets for evidence categories it receives:

- repository structure from file paths and changed files;
- package or dependency graph from package manifests and dependency hints;
- verification commands from test commands;
- CI failure context from CI logs;
- language/framework summary from detected languages and frameworks.

It should not hardcode a repo name or choose a stack by default. GraphQL appears only
when supplied in signals. TypeScript monorepo signals should mention package graph,
affected packages, test shards, `tsc`, Jest, Vitest, Playwright, and CI logs when the
caller provides those facts. Python signals should mention Python package/test evidence
without inventing TypeScript-specific details.

## 5. Privacy and Tracing

The provider returns normal `ContextBundle` data, so V3-B private trace hashing applies.
Provider operation traces record source categories and counts, not raw filesystem scans.
No secret-bearing environment variables or filesystem paths are read by the provider.

## 6. Testing

V3-C is complete when tests prove:

- context request and repo signal models validate bounded nonblank data;
- deterministic provider quotes zero cost and returns metered context;
- TypeScript monorepo signals produce package graph/test shard context;
- Python repo signals produce Python/pytest context without TypeScript assumptions;
- arbitrary middleware prompt does not receive GraphQL unless signals include it;
- helper merges generated context with existing task context;
- CLI `--repo-signals-file` feeds the same typed path.

## 7. Success Criteria

- Core engine stays provider-neutral and does not read files.
- Context retrieval is callable from middleware without CLI.
- CLI remains a harness.
- All normal tests remain no-network.
- Output context is useful across multiple repo shapes and does not specialize to one
  repository or task.
