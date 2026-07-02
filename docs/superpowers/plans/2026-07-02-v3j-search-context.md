# V3-J Search Context MCP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add opt-in search context to the MCP planning contract without making search automatic, repo-crawling, or surprise-spending.

**Architecture:** Add a focused `search_context` module that owns `search_mode`, bounded search metadata, approval checks, and conversion from `SearchResult` records to `ContextSnippet` data. Middleware resolves search context before engine execution and serializes top-level search metadata. MCP and smoke remain thin adapters that forward explicit fields and runtime defaults.

**Tech Stack:** Python 3.12, Pydantic v2, existing search/context models, FastMCP, pytest, Markdown.

---

## File Map

- Create `src/muse/search_context.py`: search mode enum, metadata model, resolver, and search-result-to-context conversion.
- Create `tests/test_search_context.py`: resolver behavior and metadata tests.
- Modify `src/muse/runtime_defaults.py`: add `search_mode` and `MUSE_SEARCH_MODE`.
- Modify `src/muse/middleware.py`: add `search_mode` to requests, inject resolver, merge context, serialize metadata.
- Modify `src/muse/mcp_server.py`: expose `search_mode`, resolve runtime default, preserve positional compatibility.
- Modify `src/muse/mcp_smoke.py`: add `--search-mode`.
- Modify `tests/test_runtime_defaults.py`, `tests/test_middleware.py`, `tests/test_mcp_server.py`, `tests/test_mcp_smoke.py`, `tests/test_mcp_config_packs.py`: contract tests.
- Modify `README.md`, `docs/integrations/mcp-agent-hosts.md`, `docs/integrations/agent-dogfood-playbook.md`: opt-in search docs.

---

## Task 1: Search Context Resolver

**Files:**
- Create: `src/muse/search_context.py`
- Create: `tests/test_search_context.py`

- [ ] **Step 1: Write failing resolver tests**

Add tests that cover `off`, approval-required skip, provider configuration skip, and deterministic provider context conversion:

```python
from __future__ import annotations

from muse.context_provider import RepoSignals
from muse.models import TaskContext
from muse.search import DeterministicSearchProvider
from muse.search_context import SearchContextMode, SearchContextResolver


def test_search_context_off_returns_empty_metadata() -> None:
    result = SearchContextResolver().resolve(
        mode=SearchContextMode.OFF,
        task=TaskContext(goal="reversible team decisions"),
        repo_signals=RepoSignals(),
        max_snippets=4,
    )

    assert result.bundle.snippets == ()
    assert result.metadata.mode == "off"
    assert result.metadata.used is False
    assert result.metadata.skipped_reason == "disabled"


def test_search_context_requires_approval_before_provider_use() -> None:
    result = SearchContextResolver(
        provider=DeterministicSearchProvider(),
        approval_required=True,
        environ={},
    ).resolve(
        mode=SearchContextMode.LIGHT,
        task=TaskContext(goal="reversible team decisions"),
        repo_signals=RepoSignals(detected_frameworks=("pytest",)),
        max_snippets=4,
    )

    assert result.bundle.snippets == ()
    assert result.metadata.used is False
    assert result.metadata.skipped_reason == "approval_required"


def test_search_context_reports_missing_provider_after_approval() -> None:
    result = SearchContextResolver(
        provider=None,
        approval_required=True,
        environ={"MUSE_LIVE_SEARCH_APPROVED": "1"},
    ).resolve(
        mode=SearchContextMode.LIGHT,
        task=TaskContext(goal="reversible team decisions"),
        repo_signals=RepoSignals(),
        max_snippets=4,
    )

    assert result.bundle.snippets == ()
    assert result.metadata.skipped_reason == "configuration_error"
    assert "search provider" in result.metadata.errors[0]


def test_search_context_converts_results_to_context_snippets() -> None:
    result = SearchContextResolver(
        provider=DeterministicSearchProvider(),
        approval_required=False,
    ).resolve(
        mode=SearchContextMode.LIGHT,
        task=TaskContext(goal="reversible team decisions"),
        repo_signals=RepoSignals(detected_languages=("Python",)),
        max_snippets=4,
    )

    assert result.metadata.used is True
    assert result.metadata.mode == "light"
    assert result.metadata.source_count == 1
    assert result.bundle.tags == ("search:light", "search:deterministic-search")
    assert result.bundle.snippets[0].source == "search/deterministic-search/src-1"
    assert "Teams use reversible claims" in result.bundle.snippets[0].content
```

- [ ] **Step 2: Run tests to verify RED**

Run: `python -m pytest tests/test_search_context.py -q`

Expected: FAIL because `muse.search_context` does not exist.

- [ ] **Step 3: Implement resolver**

Create `search_context.py` with:

```python
class SearchContextMode(StrEnum):
    OFF = "off"
    LIGHT = "light"
    DEEP = "deep"


class SearchContextMetadata(FrozenModel):
    mode: str
    used: bool = False
    skipped_reason: str | None = None
    provider: str | None = None
    source_count: int = Field(default=0, strict=True, ge=0)
    query_count: int = Field(default=0, strict=True, ge=0)
    errors: tuple[str, ...] = ()


class SearchContextResult(FrozenModel):
    bundle: ContextBundle = Field(default_factory=ContextBundle)
    metadata: SearchContextMetadata
```

`SearchContextResolver.resolve(...)` should:

- return disabled metadata for `off`;
- require `MUSE_LIVE_SEARCH_APPROVED=1` when `approval_required=True`;
- skip with `configuration_error` when approved but no provider exists;
- run one `SearchQuery` for `light` and two bounded queries for `deep`;
- convert provider results into private `ContextSnippet` records with sources like `search/<provider>/<source_id>`;
- sanitize provider exceptions into metadata errors.

- [ ] **Step 4: Run tests to verify GREEN**

Run: `python -m pytest tests/test_search_context.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src\muse\search_context.py tests\test_search_context.py
git commit -m "feat: add search context resolver"
```

---

## Task 2: Runtime Defaults and Middleware Contract

**Files:**
- Modify: `src/muse/runtime_defaults.py`
- Modify: `src/muse/middleware.py`
- Modify: `tests/test_runtime_defaults.py`
- Modify: `tests/test_middleware.py`

- [ ] **Step 1: Write failing defaults and middleware tests**

Add tests for `MUSE_SEARCH_MODE`, default `off`, explicit override, metadata serialization, approval skip, and injected search context:

```python
def test_runtime_defaults_include_search_mode() -> None:
    defaults = RuntimeDefaults.from_environment({"MUSE_SEARCH_MODE": "light"})
    assert defaults.search_mode == "light"


def test_middleware_defaults_search_context_off() -> None:
    result = CreativeMiddlewareRunner.deterministic().run(
        CreativePlanRequest(goal="Design a planning hook for arbitrary repos")
    )
    assert result["config"]["search_mode"] == "off"
    assert result["search_context"]["mode"] == "off"
    assert result["search_context"]["used"] is False


def test_middleware_reports_search_approval_skip() -> None:
    result = CreativeMiddlewareRunner.deterministic().run(
        CreativePlanRequest(
            goal="reversible team decisions",
            search_mode="light",
            seed_count=2,
            finalist_count=1,
            max_generations=0,
            budget_usd=0.20,
        )
    )
    assert result["search_context"]["skipped_reason"] == "approval_required"


def test_middleware_merges_injected_search_context() -> None:
    runner = CreativeMiddlewareRunner.deterministic(
        search_context_resolver=SearchContextResolver(
            provider=DeterministicSearchProvider(),
            approval_required=False,
        )
    )
    result = runner.run(
        CreativePlanRequest(
            goal="reversible team decisions",
            search_mode="light",
            seed_count=2,
            finalist_count=1,
            max_generations=0,
            budget_usd=0.20,
        )
    )
    assert result["search_context"]["used"] is True
    assert "search/deterministic-search/src-1" in result["context_sources"]
```

- [ ] **Step 2: Run tests to verify RED**

Run: `python -m pytest tests/test_runtime_defaults.py tests/test_middleware.py -q`

Expected: FAIL because runtime defaults and middleware do not know `search_mode`.

- [ ] **Step 3: Implement middleware support**

Add `search_mode` to `RuntimeDefaults` and `RuntimeDefaults.resolve`. Add `search_mode: SearchContextMode = SearchContextMode.OFF` to `CreativePlanRequest`. Add `search_context_resolver` to `CreativeMiddlewareRunner.__init__`, `.deterministic(...)`, and `.live_openai(...)`.

In `CreativeMiddlewareRunner.run`, resolve search context before calling `build_task_context`, merge returned search snippets into the base `TaskContext`, then run existing repo-signal context provider.

In `_serialize_result`, include:

```python
"search_context": search_context_metadata.model_dump(mode="json"),
"config": {
    ...
    "search_mode": request.search_mode.value,
}
```

- [ ] **Step 4: Run tests to verify GREEN**

Run: `python -m pytest tests/test_runtime_defaults.py tests/test_middleware.py tests/test_search_context.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src\muse\runtime_defaults.py src\muse\middleware.py tests\test_runtime_defaults.py tests\test_middleware.py
git commit -m "feat: add search mode to middleware"
```

---

## Task 3: MCP and Smoke Search Mode

**Files:**
- Modify: `src/muse/mcp_server.py`
- Modify: `src/muse/mcp_smoke.py`
- Modify: `tests/test_mcp_server.py`
- Modify: `tests/test_mcp_smoke.py`

- [ ] **Step 1: Write failing MCP tests**

Add tests that explicit `search_mode` is forwarded, env default is honored, explicit mode overrides env, and smoke accepts `--search-mode`.

- [ ] **Step 2: Run tests to verify RED**

Run: `python -m pytest tests/test_mcp_server.py tests/test_mcp_smoke.py -q`

Expected: FAIL because MCP and smoke do not accept search mode.

- [ ] **Step 3: Implement MCP/smoke forwarding**

Add `search_mode: str | None = None` after `effort` in `muse_plan` to preserve existing numeric positional ordering. Pass it into `RuntimeDefaults.resolve(...)` and the request. Add `--search-mode` choices `off`, `light`, `deep` to `mcp_smoke.py`, then forward it only when explicitly supplied.

- [ ] **Step 4: Run tests to verify GREEN**

Run: `python -m pytest tests/test_mcp_server.py tests/test_mcp_smoke.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src\muse\mcp_server.py src\muse\mcp_smoke.py tests\test_mcp_server.py tests\test_mcp_smoke.py
git commit -m "feat: expose search mode through mcp"
```

---

## Task 4: Documentation Contract

**Files:**
- Modify: `tests/test_mcp_config_packs.py`
- Modify: `README.md`
- Modify: `docs/integrations/mcp-agent-hosts.md`
- Modify: `docs/integrations/agent-dogfood-playbook.md`

- [ ] **Step 1: Write failing docs test**

Add a test asserting docs mention `search_mode`, `MUSE_SEARCH_MODE`, `MUSE_LIVE_SEARCH_APPROVED`, default `off`, and opt-in search.

- [ ] **Step 2: Run docs test to verify RED**

Run: `python -m pytest tests/test_mcp_config_packs.py -q`

Expected: FAIL because docs do not mention the V3-J search context contract.

- [ ] **Step 3: Update docs**

Document:

- default search mode is `off`;
- explicit MCP payload can set `"search_mode": "light"` or `"deep"`;
- env default can set `MUSE_SEARCH_MODE`;
- live search requires `MUSE_LIVE_SEARCH_APPROVED=1`;
- agents must still pass repo signals and must not rely on repo crawling.

- [ ] **Step 4: Run docs test to verify GREEN**

Run: `python -m pytest tests/test_mcp_config_packs.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add tests\test_mcp_config_packs.py README.md docs\integrations\mcp-agent-hosts.md docs\integrations\agent-dogfood-playbook.md
git commit -m "docs: document mcp search context"
```

---

## Final Verification

- [ ] Run focused tests:

```powershell
python -m pytest tests/test_search_context.py tests/test_runtime_defaults.py tests/test_middleware.py tests/test_mcp_server.py tests/test_mcp_smoke.py tests/test_mcp_config_packs.py -q
```

- [ ] Run full tests:

```powershell
python -m pytest -q
```

- [ ] Run Ruff:

```powershell
python -m ruff check .
```

- [ ] Request code review for `origin/main..HEAD`.

- [ ] Fix any critical or important review findings.

- [ ] Push and open a PR if requested.
