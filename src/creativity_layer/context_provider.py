from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Protocol

from pydantic import Field, field_validator

from creativity_layer.models import (
    ContextBundle,
    ContextSnippet,
    FrozenModel,
    OperationTrace,
    RequiredText,
    TaskContext,
)
from creativity_layer.providers import MeteredResponse, OperationQuote


class RepoSignals(FrozenModel):
    file_paths: tuple[RequiredText, ...] = ()
    changed_files: tuple[RequiredText, ...] = ()
    package_manifests: tuple[RequiredText, ...] = ()
    test_commands: tuple[RequiredText, ...] = ()
    ci_logs: tuple[RequiredText, ...] = ()
    dependency_hints: tuple[RequiredText, ...] = ()
    detected_languages: tuple[RequiredText, ...] = ()
    detected_frameworks: tuple[RequiredText, ...] = ()
    metadata: Mapping[str, object] = Field(default_factory=dict)

    @field_validator(
        "file_paths",
        "changed_files",
        "package_manifests",
        "test_commands",
        "ci_logs",
        "dependency_hints",
        "detected_languages",
        "detected_frameworks",
    )
    @classmethod
    def deduplicate_values(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(dict.fromkeys(item.strip() for item in value))


class ContextRequest(FrozenModel):
    task: TaskContext
    repo_signals: RepoSignals = Field(default_factory=RepoSignals)
    max_snippets: int = Field(default=8, strict=True, ge=1, le=20)


class ContextProvider(Protocol):
    name: str
    version: str

    def quote_context(self, request: ContextRequest) -> OperationQuote: ...

    def build_context(self, request: ContextRequest) -> MeteredResponse[ContextBundle]: ...


class DeterministicContextProvider:
    name = "deterministic-context"
    version = "repo-signals-v1"

    def quote_context(self, request: ContextRequest) -> OperationQuote:
        del request
        return OperationQuote(max_cost_usd=0.0)

    def build_context(self, request: ContextRequest) -> MeteredResponse[ContextBundle]:
        snippets = _snippets_from_signals(request.repo_signals)[: request.max_snippets]
        bundle = ContextBundle(
            snippets=tuple(snippets),
            tags=_tags_from_signals(request.repo_signals),
        )
        trace = OperationTrace.from_payload(
            request={
                "operation": "build_context",
                "provider": self.name,
                "max_snippets": request.max_snippets,
                "signal_counts": _signal_counts(request.repo_signals),
            },
            response={
                "snippet_count": len(bundle.snippets),
                "tags": bundle.tags,
                "sources": [snippet.source for snippet in bundle.snippets],
            },
        )
        return MeteredResponse(
            value=bundle,
            provider=self.name,
            cost_usd=0.0,
            latency_ms=0,
            operation_trace=trace,
        )


def _snippets_from_signals(signals: RepoSignals) -> list[ContextSnippet]:
    snippets: list[ContextSnippet] = []
    affected_packages = _affected_packages(signals)
    test_shards = _test_shard_signals(signals)
    if signals.file_paths or signals.changed_files:
        snippets.append(
            ContextSnippet(
                source="repo/structure",
                title="Repository structure",
                content=_join_evidence(
                    "Files",
                    (*signals.file_paths, *signals.changed_files),
                ),
            )
        )
    if signals.package_manifests or signals.dependency_hints:
        package_evidence = (*signals.package_manifests, *signals.dependency_hints)
        if affected_packages:
            package_evidence = (
                *package_evidence,
                "affected packages: " + ", ".join(affected_packages),
            )
        snippets.append(
            ContextSnippet(
                source="repo/package-graph",
                title="Package and dependency graph",
                content=_join_evidence("Package graph", package_evidence),
            )
        )
    if signals.test_commands:
        test_evidence = signals.test_commands
        if test_shards:
            test_evidence = (
                *test_evidence,
                "test shards: " + ", ".join(test_shards),
            )
        snippets.append(
            ContextSnippet(
                source="repo/test-commands",
                title="Verification commands",
                content=_join_evidence("Test commands", test_evidence),
            )
        )
    if signals.ci_logs:
        snippets.append(
            ContextSnippet(
                source="repo/ci-logs",
                title="CI log signals",
                content=_join_evidence("CI logs", signals.ci_logs),
            )
        )
    if signals.detected_languages or signals.detected_frameworks:
        snippets.append(
            ContextSnippet(
                source="repo/stack-signals",
                title="Detected stack signals",
                content=_join_evidence(
                    "Detected stack",
                    (*signals.detected_languages, *signals.detected_frameworks),
                ),
            )
        )
    return snippets


def _affected_packages(signals: RepoSignals) -> tuple[str, ...]:
    candidates: list[str] = []
    for path in (*signals.changed_files, *signals.file_paths):
        parts = re.split(r"[\\/]+", path)
        if len(parts) >= 2 and parts[0] in {"apps", "packages", "libs", "services"}:
            candidates.append("/".join(parts[:2]))
    return tuple(dict.fromkeys(candidates))


def _test_shard_signals(signals: RepoSignals) -> tuple[str, ...]:
    candidates: list[str] = []
    for item in (*signals.test_commands, *signals.ci_logs):
        if re.search(r"\bshard(?:s|ed)?\b|--shard", item, re.IGNORECASE):
            candidates.append(item)
    return tuple(dict.fromkeys(candidates))


def _tags_from_signals(signals: RepoSignals) -> tuple[str, ...]:
    raw_tags = [
        *signals.detected_languages,
        *signals.detected_frameworks,
    ]
    return tuple(dict.fromkeys(tag.strip().casefold() for tag in raw_tags if tag.strip()))


def _join_evidence(label: str, values: tuple[str, ...]) -> str:
    return f"{label}: " + "; ".join(values)


def _signal_counts(signals: RepoSignals) -> dict[str, int]:
    return {
        "file_paths": len(signals.file_paths),
        "changed_files": len(signals.changed_files),
        "package_manifests": len(signals.package_manifests),
        "test_commands": len(signals.test_commands),
        "ci_logs": len(signals.ci_logs),
        "dependency_hints": len(signals.dependency_hints),
        "detected_languages": len(signals.detected_languages),
        "detected_frameworks": len(signals.detected_frameworks),
    }
