from __future__ import annotations

import pytest
from pydantic import ValidationError

from creativity_layer.context_provider import (
    ContextRequest,
    DeterministicContextProvider,
    RepoSignals,
)
from creativity_layer.models import ContextBundle, ContextSnippet, TaskContext


def test_repo_signals_validate_bounded_nonblank_evidence() -> None:
    signals = RepoSignals(
        file_paths=("apps/web/package.json", "packages/ui/package.json"),
        changed_files=("apps/web/src/App.tsx",),
        package_manifests=("apps/web/package.json",),
        test_commands=("pnpm test --filter apps/web",),
        ci_logs=("Shard 2 failed in apps/web",),
        dependency_hints=("apps/web depends on packages/ui",),
        detected_languages=("TypeScript",),
        detected_frameworks=("Vitest",),
        metadata={"workspace": "pnpm"},
    )

    assert signals.file_paths == ("apps/web/package.json", "packages/ui/package.json")
    assert signals.metadata["workspace"] == "pnpm"

    with pytest.raises(ValidationError):
        RepoSignals(file_paths=("   ",))


def test_context_request_rejects_zero_snippets() -> None:
    with pytest.raises(ValidationError):
        ContextRequest(
            task=TaskContext(goal="Improve flaky CI"),
            repo_signals=RepoSignals(),
            max_snippets=0,
        )


def test_deterministic_context_provider_quotes_and_returns_context() -> None:
    provider = DeterministicContextProvider()
    request = ContextRequest(
        task=TaskContext(goal="Improve flaky CI"),
        repo_signals=RepoSignals(
            file_paths=("apps/web/package.json",),
            test_commands=("pnpm test --filter apps/web",),
            detected_languages=("TypeScript",),
        ),
        max_snippets=4,
    )

    quote = provider.quote_context(request)
    response = provider.build_context(request)

    assert quote.max_cost_usd == 0.0
    assert response.provider == provider.name
    assert response.cost_usd == 0.0
    assert isinstance(response.value, ContextBundle)
    assert response.value.snippets
    assert all(isinstance(snippet, ContextSnippet) for snippet in response.value.snippets)
