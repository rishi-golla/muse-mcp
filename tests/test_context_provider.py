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


def test_typescript_monorepo_signals_include_package_and_shard_context() -> None:
    provider = DeterministicContextProvider()
    response = provider.build_context(
        ContextRequest(
            task=TaskContext(goal="Design a debugging workflow for flaky CI"),
            repo_signals=RepoSignals(
                file_paths=("pnpm-workspace.yaml", "apps/web/package.json"),
                changed_files=("packages/ui/src/Button.tsx",),
                package_manifests=("apps/web/package.json", "packages/ui/package.json"),
                test_commands=(
                    "pnpm test --filter apps/web -- --shard=2/4",
                    "pnpm tsc --build",
                ),
                ci_logs=("Vitest shard 2 failed after Playwright smoke tests",),
                dependency_hints=("apps/web depends on packages/ui",),
                detected_languages=("TypeScript",),
                detected_frameworks=("Jest", "Vitest", "Playwright"),
            ),
        )
    )
    text = " ".join(snippet.content for snippet in response.value.snippets).casefold()

    for expected in (
        "package graph",
        "affected packages",
        "test shards",
        "tsc",
        "jest",
        "vitest",
        "playwright",
        "ci logs",
    ):
        assert expected in text


def test_python_repo_signals_do_not_invent_typescript_context() -> None:
    provider = DeterministicContextProvider()
    response = provider.build_context(
        ContextRequest(
            task=TaskContext(goal="Improve test recovery in a Python service"),
            repo_signals=RepoSignals(
                file_paths=("pyproject.toml", "src/service/app.py"),
                changed_files=("tests/test_api.py",),
                package_manifests=("pyproject.toml",),
                test_commands=("python -m pytest tests/test_api.py",),
                ci_logs=("pytest failed in tests/test_api.py",),
                detected_languages=("Python",),
                detected_frameworks=("pytest",),
            ),
        )
    )
    text = " ".join(snippet.content for snippet in response.value.snippets).casefold()

    assert "python" in text
    assert "pytest" in text
    assert "typescript" not in text
    assert "playwright" not in text
    assert "test shards" not in text


def test_arbitrary_middleware_context_does_not_default_to_graphql() -> None:
    provider = DeterministicContextProvider()
    response = provider.build_context(
        ContextRequest(
            task=TaskContext(goal="Design middleware for arbitrary agent repos"),
            repo_signals=RepoSignals(
                file_paths=("src/agent/planner.py",),
                test_commands=("python -m pytest",),
                detected_languages=("Python",),
            ),
        )
    )
    text = " ".join(snippet.content for snippet in response.value.snippets).casefold()

    assert "graphql" not in text


def test_graphql_appears_only_when_supplied_by_signals() -> None:
    provider = DeterministicContextProvider()
    response = provider.build_context(
        ContextRequest(
            task=TaskContext(goal="Design middleware for this repo"),
            repo_signals=RepoSignals(
                file_paths=("schema.graphql",),
                dependency_hints=("existing GraphQL schema is required",),
            ),
        )
    )
    text = " ".join(snippet.content for snippet in response.value.snippets).casefold()

    assert "graphql" in text
