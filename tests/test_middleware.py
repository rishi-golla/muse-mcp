from __future__ import annotations

import json
from pathlib import Path

from muse import middleware as middleware_module
from muse.deterministic import DeterministicCreativeProvider
from muse.middleware import (
    AgentMode,
    CreativeMiddlewareRunner,
    CreativePlanRequest,
    EffortPreset,
    ProviderMode,
    run_muse_plan,
)
from muse.models import OperationTrace
from muse.providers import MeteredProviderFailure, OperationQuote
from muse.search import DeterministicSearchProvider
from muse.search_context import SearchContextResolver, SearchProviderPolicy


class NonLiveFixtureProvider:
    name = "fixture"
    version = "fixture-v1"

    def __init__(
        self,
        *,
        fail_frame: bool = False,
        fail_seed_quote: bool = False,
        seed_quote: OperationQuote | None = None,
    ) -> None:
        self._delegate = DeterministicCreativeProvider()
        self._fail_frame = fail_frame
        self._fail_seed_quote = fail_seed_quote
        self._seed_quote = seed_quote

    def frame(self, task):
        if self._fail_frame:
            raise RuntimeError("fixture framing failed")
        return self._delegate.frame(task).model_copy(update={"provider": self.name})

    def quote_frame(self, task):
        return self._delegate.quote_frame(task)

    def seed(self, framed_task, config):
        return self._delegate.seed(framed_task, config).model_copy(
            update={"provider": self.name}
        )

    def quote_seed(self, framed_task, config):
        if self._fail_seed_quote:
            raise RuntimeError("fixture seed quote failed")
        return self._seed_quote or self._delegate.quote_seed(framed_task, config)

    def transform(self, request, parents, framed_task):
        return self._delegate.transform(request, parents, framed_task).model_copy(
            update={"provider": self.name}
        )

    def quote_transform(self, request, parents):
        return self._delegate.quote_transform(request, parents)

    def evaluate(self, candidate, framed_task):
        return self._delegate.evaluate(candidate, framed_task).model_copy(
            update={"provider": self.name}
        )

    def quote_evaluation(self, framed_task):
        return self._delegate.quote_evaluation(framed_task)


class DefaultLiveCeilingProvider(NonLiveFixtureProvider):
    def __init__(self) -> None:
        super().__init__()
        self.seed_calls = 0

    def quote_frame(self, task):
        del task
        return OperationQuote(max_cost_usd=0.0, calls=6)

    def quote_seed(self, framed_task, config):
        del framed_task
        return OperationQuote(max_cost_usd=0.01, calls=6 * config.seed_count)

    def quote_transform(self, request, parents):
        del request, parents
        return OperationQuote(max_cost_usd=0.01, calls=6)

    def quote_evaluation(self, framed_task):
        del framed_task
        return OperationQuote(max_cost_usd=0.005, calls=6)

    def seed(self, framed_task, config):
        self.seed_calls += 1
        return super().seed(framed_task, config)


class PartiallyEvidencedBranchProvider(NonLiveFixtureProvider):
    def __init__(
        self,
        *,
        requested_branches: list[dict[str, object]] | None = None,
        completed_branches: list[dict[str, object]] | None = None,
    ) -> None:
        super().__init__()
        self._requested_branches = requested_branches or [
            _branch_trace_entry(0, "constraint_inversion", "request")
        ]
        self._completed_branches = completed_branches or [
            _branch_trace_entry(0, "constraint_inversion", "response")
        ]

    def seed(self, framed_task, config):
        response = super().seed(framed_task, config)
        partial = response.model_copy(
            update={
                "value": response.value[:1],
                "calls": 1,
                "operation_trace": OperationTrace.from_payload(
                    request={
                        "operation": "seed",
                        "branches": self._requested_branches,
                    },
                    response={
                        "branches": self._completed_branches,
                        "request_ids": [
                            branch.get("request_id")
                            for branch in self._completed_branches
                        ],
                        "calls": 1,
                        "usage": {
                            "input": 0,
                            "cached_input": 0,
                            "output": 0,
                            "reasoning": 0,
                        },
                    },
                ),
            }
        )
        raise MeteredProviderFailure("fixture branch failed", partial_response=partial)

    def quote_seed(self, framed_task, config):
        del framed_task, config
        return OperationQuote(max_cost_usd=0.01, calls=3)


def _branch_trace_entry(
    branch_index: int,
    strategy: str,
    trace_kind: str,
    *,
    nested_branch_index: int | None = None,
    nested_strategy: str | None = None,
    calls: int = 1,
    input_tokens: int = 0,
) -> dict[str, object]:
    nested_index = branch_index if nested_branch_index is None else nested_branch_index
    nested_branch_strategy = strategy if nested_strategy is None else nested_strategy
    entry: dict[str, object] = {
        "branch_index": branch_index,
        "strategy": strategy,
    }
    if trace_kind == "request":
        entry["trace"] = {
            "operation": "seed",
            "domain": {
                "branch_directive": {
                    "branch_index": nested_index,
                    "strategy": nested_branch_strategy,
                    "instruction": "Exercise the fixture branch independently.",
                }
            },
        }
        return entry
    usage = {
        "input": input_tokens,
        "cached_input": 0,
        "output": 0,
        "reasoning": 0,
    }
    request_id = f"req_fixture_{branch_index}"
    entry.update(
        {
            "request_id": request_id,
            "succeeded": True,
            "trace": {
                "attempts": [
                    {
                        "attempt": 1,
                        "request_id": request_id,
                        "usage": usage,
                    }
                ],
                "request_id": request_id,
                "parsed": {"title": f"Fixture branch {branch_index}"},
                "refusal": None,
                "calls": calls,
                "error": None,
                "usage": usage,
            },
        }
    )
    return entry


def test_runner_returns_json_safe_operational_plan_from_repo_signals() -> None:
    request = CreativePlanRequest(
        goal="Design a debugging workflow for a TypeScript monorepo with flaky CI",
        repo_signals={
            "file_paths": ("pnpm-workspace.yaml", "apps/web/package.json"),
            "changed_files": ("packages/ui/src/Button.tsx",),
            "test_commands": ("pnpm test --filter apps/web -- --shard=2/4",),
            "ci_logs": ("Vitest shard 2 failed after Playwright smoke tests",),
            "dependency_hints": ("apps/web depends on packages/ui",),
            "detected_languages": ("TypeScript",),
            "detected_frameworks": ("Vitest", "Playwright"),
        },
        seed_count=4,
        finalist_count=2,
        max_generations=1,
        budget_usd=0.35,
    )

    result = CreativeMiddlewareRunner.deterministic().run(request)

    assert result["stopped_reason"] == "generation_limit"
    assert result["generated_count"] >= 4
    assert result["finalist_count"] == 2
    assert result["context_tags"] == ["typescript", "vitest", "playwright"]
    assert "test shards" in result["finalists"][0]["agent_workflow"][1]
    assert result["finalists"][0]["verification_strategy"]
    assert json.loads(json.dumps(result)) == result


def test_extensive_public_defaults_reach_live_seeding_at_default_call_ceilings() -> None:
    provider = DefaultLiveCeilingProvider()
    request = CreativePlanRequest.model_validate(
        {
            "goal": "Design a planning hook for arbitrary repos",
            "provider_mode": "live_openai",
            "mode": "extensive",
        }
    )

    result = CreativeMiddlewareRunner.live_openai(provider=provider).run(request)

    assert request.max_calls == 222
    assert provider.seed_calls == 1
    assert result["errors"] == []
    assert result["stopped_reason"] == "generation_limit"


def test_runner_exposes_live_branch_metadata_without_claiming_fixture_calls() -> None:
    result = CreativeMiddlewareRunner.live_openai(
        provider=DeterministicCreativeProvider(),
    ).run(
        CreativePlanRequest(
            goal="Design a planning hook for arbitrary repos",
            provider_mode="live_openai",
            seed_count=4,
            finalist_count=1,
            max_generations=0,
            budget_usd=0.20,
        )
    )

    assert result["config"]["branch_generation"] == {
        "strategies": [
            "constraint_inversion",
            "failure_first",
            "cross_domain_transfer",
            "systems_effects",
        ],
        "independent_call_count": 0,
    }


def test_runner_reports_zero_branch_calls_when_seeding_never_starts() -> None:
    providers = (
        NonLiveFixtureProvider(fail_frame=True),
        NonLiveFixtureProvider(fail_seed_quote=True),
        NonLiveFixtureProvider(
            seed_quote=OperationQuote(max_cost_usd=1.0, calls=1),
        ),
    )

    for provider in providers:
        result = CreativeMiddlewareRunner.live_openai(provider=provider).run(
            CreativePlanRequest(
                goal="Design a planning hook for arbitrary repos",
                provider_mode="live_openai",
                seed_count=2,
                finalist_count=1,
                max_generations=0,
                budget_usd=0.20,
            )
        )

        assert result["config"]["branch_generation"]["independent_call_count"] == 0


def test_runner_reports_only_evidenced_completed_branches_after_seed_failure() -> None:
    result = CreativeMiddlewareRunner.live_openai(
        provider=PartiallyEvidencedBranchProvider(),
    ).run(
        CreativePlanRequest(
            goal="Design a planning hook for arbitrary repos",
            provider_mode="live_openai",
            seed_count=3,
            finalist_count=1,
            max_generations=0,
            budget_usd=0.20,
        )
    )

    assert result["stopped_reason"] == "provider_error"
    assert result["config"]["branch_generation"]["independent_call_count"] == 1


def test_runner_rejects_forged_unknown_duplicate_and_overscheduled_branch_evidence() -> None:
    cases = (
        (
            [_branch_trace_entry(0, "failure_first", "request")],
            [_branch_trace_entry(0, "failure_first", "response")],
            3,
        ),
        (
            [_branch_trace_entry(99, "constraint_inversion", "request")],
            [_branch_trace_entry(99, "constraint_inversion", "response")],
            3,
        ),
        (
            [_branch_trace_entry(0, "constraint_inversion", "request")],
            [
                _branch_trace_entry(0, "constraint_inversion", "response"),
                _branch_trace_entry(0, "constraint_inversion", "response"),
            ],
            3,
        ),
        (
            [
                _branch_trace_entry(0, "constraint_inversion", "request"),
                _branch_trace_entry(1, "failure_first", "request"),
                _branch_trace_entry(2, "cross_domain_transfer", "request"),
            ],
            [
                _branch_trace_entry(0, "constraint_inversion", "response"),
                _branch_trace_entry(1, "failure_first", "response"),
                _branch_trace_entry(2, "cross_domain_transfer", "response"),
            ],
            2,
        ),
    )

    for requested_branches, completed_branches, seed_count in cases:
        result = CreativeMiddlewareRunner.live_openai(
            provider=PartiallyEvidencedBranchProvider(
                requested_branches=requested_branches,
                completed_branches=completed_branches,
            ),
        ).run(
            CreativePlanRequest(
                goal="Design a planning hook for arbitrary repos",
                provider_mode="live_openai",
                seed_count=seed_count,
                finalist_count=1,
                max_generations=0,
                budget_usd=0.20,
            )
        )

        assert result["config"]["branch_generation"]["independent_call_count"] == 0


def test_runner_rejects_placeholder_reordered_and_nonprefix_branch_evidence() -> None:
    placeholder_request = _branch_trace_entry(0, "constraint_inversion", "request")
    placeholder_response = _branch_trace_entry(0, "constraint_inversion", "response")
    placeholder_request["trace"] = {}
    placeholder_response["trace"] = {}
    boolean_request = _branch_trace_entry(0, "constraint_inversion", "request")
    boolean_response = _branch_trace_entry(0, "constraint_inversion", "response")
    boolean_request["branch_index"] = False
    boolean_request["trace"]["domain"]["branch_directive"]["branch_index"] = False
    boolean_response["branch_index"] = False
    empty_parsed_request = _branch_trace_entry(0, "constraint_inversion", "request")
    empty_parsed_response = _branch_trace_entry(0, "constraint_inversion", "response")
    empty_parsed_response["trace"]["parsed"] = {}
    cases = (
        ([placeholder_request], [placeholder_response]),
        ([boolean_request], [boolean_response]),
        ([empty_parsed_request], [empty_parsed_response]),
        (
            [
                _branch_trace_entry(1, "failure_first", "request"),
                _branch_trace_entry(0, "constraint_inversion", "request"),
            ],
            [
                _branch_trace_entry(1, "failure_first", "response"),
                _branch_trace_entry(0, "constraint_inversion", "response"),
            ],
        ),
        (
            [_branch_trace_entry(1, "failure_first", "request")],
            [_branch_trace_entry(1, "failure_first", "response")],
        ),
    )

    for requested_branches, completed_branches in cases:
        result = CreativeMiddlewareRunner.live_openai(
            provider=PartiallyEvidencedBranchProvider(
                requested_branches=requested_branches,
                completed_branches=completed_branches,
            ),
        ).run(
            CreativePlanRequest(
                goal="Design a planning hook for arbitrary repos",
                provider_mode="live_openai",
                seed_count=3,
                finalist_count=1,
                max_generations=0,
                budget_usd=0.20,
            )
        )

        assert result["config"]["branch_generation"]["independent_call_count"] == 0


def test_runner_rejects_forged_nested_branch_directive() -> None:
    result = CreativeMiddlewareRunner.live_openai(
        provider=PartiallyEvidencedBranchProvider(
            requested_branches=[
                _branch_trace_entry(
                    0,
                    "constraint_inversion",
                    "request",
                    nested_strategy="failure_first",
                )
            ],
        ),
    ).run(
        CreativePlanRequest(
            goal="Design a planning hook for arbitrary repos",
            provider_mode="live_openai",
            seed_count=3,
            finalist_count=1,
            max_generations=0,
            budget_usd=0.20,
        )
    )

    assert result["config"]["branch_generation"]["independent_call_count"] == 0


def test_runner_rejects_branch_trace_accounting_inconsistent_with_spend() -> None:
    result = CreativeMiddlewareRunner.live_openai(
        provider=PartiallyEvidencedBranchProvider(
            completed_branches=[
                _branch_trace_entry(
                    0,
                    "constraint_inversion",
                    "response",
                    calls=2,
                    input_tokens=10,
                )
            ],
        ),
    ).run(
        CreativePlanRequest(
            goal="Design a planning hook for arbitrary repos",
            provider_mode="live_openai",
            seed_count=3,
            finalist_count=1,
            max_generations=0,
            budget_usd=0.20,
        )
    )

    assert result["config"]["branch_generation"]["independent_call_count"] == 0


def test_runner_does_not_classify_custom_non_live_fixtures_as_branch_evidence() -> None:
    result = CreativeMiddlewareRunner.live_openai(
        provider=NonLiveFixtureProvider(),
    ).run(
        CreativePlanRequest(
            goal="Design a planning hook for arbitrary repos",
            provider_mode="live_openai",
            seed_count=2,
            finalist_count=1,
            max_generations=0,
            budget_usd=0.20,
        )
    )

    assert result["config"]["branch_generation"]["independent_call_count"] == 0


def test_branch_generation_docs_distinguish_live_trajectories_from_fixtures() -> None:
    readme = " ".join(Path("README.md").read_text(encoding="utf-8").split())
    benchmarking = " ".join(
        Path("docs/quality/benchmarking.md").read_text(encoding="utf-8").split()
    )

    assert (
        "`seed_count` requests an ordered schedule of independent live model trajectories"
        in readme
    )
    assert "does not prove a provider call" in readme
    assert "requested strategy directives" in readme
    assert "evidenced completed branches" in readme
    assert "ordered prefix" in readme
    assert "nested request and response traces" in readme
    assert "calls and token usage exactly reconcile" in readme
    assert "independently completed seed branches" in readme
    assert "`seed_count` requests" in readme
    assert (
        "`seed_count` requests an ordered schedule of independent live model trajectories"
        in benchmarking
    )
    assert "do not report provider calls or spend" in benchmarking
    assert "requested strategy directives" in benchmarking
    assert "evidenced completed branches" in benchmarking
    assert "ordered prefix" in benchmarking
    assert "nested request and response traces" in benchmarking
    assert "calls and token usage exactly reconcile" in benchmarking
    assert "independently completed seed branches" in benchmarking
    assert "`seed_count` requests" in benchmarking


def test_runner_returns_quality_warnings_for_generic_finalists() -> None:
    result = CreativeMiddlewareRunner.deterministic().run(
        CreativePlanRequest(
            goal="Design a better retry strategy for AI coding agents after failed tests",
            repo_signals={
                "ci_logs": ("pytest failed after retry loop change",),
                "detected_languages": ("Python",),
                "detected_frameworks": ("pytest",),
            },
            seed_count=2,
            finalist_count=1,
            max_generations=0,
            budget_usd=0.20,
        )
    )

    finalist = result["finalists"][0]

    assert "quality_warnings" in result
    assert "quality_summary" in result
    assert "quality_warnings" in finalist
    assert "generic_title" in result["quality_warnings"]
    assert "generic_title" in finalist["quality_warnings"]
    assert result["quality_summary"]["finalist_warning_count"] == 1
    assert result["quality_summary"]["warnings"]["generic_title"] == 1


def test_runner_returns_quality_action_policy_for_warning_results() -> None:
    result = CreativeMiddlewareRunner.deterministic().run(
        CreativePlanRequest(
            goal="Design a better retry strategy for AI coding agents after failed tests",
            repo_signals={
                "ci_logs": ("pytest failed after retry loop change",),
                "detected_languages": ("Python",),
                "detected_frameworks": ("pytest",),
            },
            seed_count=2,
            finalist_count=1,
            max_generations=0,
            budget_usd=0.20,
        )
    )

    policy = result["quality_action_policy"]

    assert policy["status"] == "needs_retry"
    assert policy["escalate_effort_to"] == "deep"
    assert "supply more repo signals" in policy["recommended_actions"]
    assert policy == result["agent_guidance"]["quality_action_policy"]


def test_runner_returns_suggested_next_call_for_warning_results() -> None:
    result = CreativeMiddlewareRunner.deterministic().run(
        CreativePlanRequest(
            goal="Design a better retry strategy for AI coding agents after failed tests",
            repo_signals={
                "ci_logs": ("pytest failed after retry loop change",),
                "detected_languages": ("Python",),
                "detected_frameworks": ("pytest",),
            },
            seed_count=2,
            finalist_count=1,
            max_generations=0,
            budget_usd=0.20,
        )
    )

    suggestion = result["suggested_next_call"]

    assert suggestion["tool"] == "muse_plan"
    assert suggestion["automatic"] is False
    assert suggestion["request"]["goal"] == (
        "Design a better retry strategy for AI coding agents after failed tests"
    )
    assert suggestion["request"]["mode"] == "extensive"
    assert "effort" not in suggestion["request"]
    assert "repo_signals" not in suggestion["request"]
    assert "test commands" in suggestion["repo_signal_requests"][0]
    assert suggestion == result["agent_guidance"]["suggested_next_call"]


def test_runner_returns_agent_handoff_for_warning_results() -> None:
    result = CreativeMiddlewareRunner.deterministic().run(
        CreativePlanRequest(
            goal="Design a better retry strategy for AI coding agents after failed tests",
            repo_signals={
                "ci_logs": ("pytest failed after retry loop change",),
                "detected_languages": ("Python",),
                "detected_frameworks": ("pytest",),
            },
            seed_count=2,
            finalist_count=1,
            max_generations=0,
            budget_usd=0.20,
        )
    )

    handoff = result["agent_handoff"]

    assert handoff["status"] == "retry_recommended"
    assert handoff["recommended_action"] == "retry_muse_plan"
    assert handoff["use_current_finalist"] is False
    assert handoff["selected_finalist_id"] == result["finalists"][0]["id"]
    assert handoff["suggested_next_call_available"] is True
    assert handoff["verification_required"] is True
    assert handoff == result["agent_guidance"]["agent_handoff"]


def test_runner_returns_review_agent_handoff_for_generic_review_results() -> None:
    result = CreativeMiddlewareRunner.deterministic().run(
        CreativePlanRequest(
            goal="Design a planning hook for arbitrary repos",
            seed_count=2,
            finalist_count=1,
            max_generations=0,
            budget_usd=0.20,
        )
    )

    handoff = result["agent_handoff"]

    assert result["quality_action_policy"]["status"] == "review"
    assert handoff["status"] == "review"
    assert handoff["recommended_action"] == "review_current_finalist"
    assert handoff["use_current_finalist"] is True
    assert handoff["selected_finalist_id"] == result["finalists"][0]["id"]
    assert handoff["suggested_next_call_available"] is True


def test_runner_uses_cheap_agent_defaults() -> None:
    request = CreativePlanRequest(goal="Design a planning hook for arbitrary repos")

    result = CreativeMiddlewareRunner.deterministic().run(request)

    assert request.provider_mode is ProviderMode.DETERMINISTIC
    assert request.mode is AgentMode.NORMAL
    assert request.effort is EffortPreset.STANDARD
    assert result["provider_mode"] == "deterministic"
    assert result["config"]["mode"] == "normal"
    assert result["config"]["effort"] == "standard"
    assert result["config"]["budget_usd"] == 0.35
    assert result["config"]["seed_count"] == 4
    assert result["config"]["finalist_count"] == 2
    assert result["config"]["max_generations"] == 1
    assert result["config"]["search_mode"] == "off"
    assert result["config"]["search_provider"] == "auto"
    assert result["config"]["search_strict"] is False
    assert result["search_context"]["mode"] == "off"
    assert result["search_context"]["provider_policy"] == "deterministic"
    assert result["search_context"]["used"] is False
    assert result["finalist_count"] == 2


def test_runner_extensive_mode_resolves_deeper_internal_run_shape() -> None:
    request = CreativePlanRequest(
        goal="Design an architecture strategy for a risky migration",
        mode="extensive",
    )

    result = CreativeMiddlewareRunner.deterministic().run(request)

    assert request.mode is AgentMode.EXTENSIVE
    assert request.effort is EffortPreset.DEEP
    assert result["config"]["mode"] == "extensive"
    assert result["config"]["effort"] == "deep"
    assert result["config"]["budget_usd"] == 0.75
    assert result["config"]["seed_count"] == 6
    assert result["config"]["finalist_count"] == 3
    assert result["config"]["max_generations"] == 2
    assert result["agent_guidance"]["mode"] == "extensive"


def test_runner_resolves_standard_and_deep_effort_presets() -> None:
    standard = CreativePlanRequest(
        goal="Design a planning hook for arbitrary repos",
        effort="standard",
    )
    deep = CreativePlanRequest(
        goal="Design a planning hook for arbitrary repos",
        effort="deep",
    )

    assert standard.budget_usd == 0.35
    assert standard.seed_count == 4
    assert standard.finalist_count == 2
    assert standard.max_generations == 1
    assert deep.budget_usd == 0.75
    assert deep.seed_count == 6
    assert deep.finalist_count == 3
    assert deep.max_generations == 2


def test_runner_inferrs_agent_mode_from_internal_effort_override() -> None:
    standard = CreativePlanRequest(
        goal="Design a planning hook for arbitrary repos",
        effort="standard",
    )
    deep = CreativePlanRequest(
        goal="Design a planning hook for arbitrary repos",
        effort="deep",
    )

    assert standard.mode is AgentMode.NORMAL
    assert deep.mode is AgentMode.EXTENSIVE


def test_runner_explicit_values_override_effort_presets() -> None:
    request = CreativePlanRequest(
        goal="Design a planning hook for arbitrary repos",
        effort="deep",
        budget_usd=0.21,
        seed_count=2,
        finalist_count=1,
        max_generations=0,
    )

    result = CreativeMiddlewareRunner.deterministic().run(request)

    assert result["config"]["effort"] == "deep"
    assert result["config"]["budget_usd"] == 0.21
    assert result["config"]["seed_count"] == 2
    assert result["config"]["finalist_count"] == 1
    assert result["config"]["max_generations"] == 0


def test_runner_returns_agent_guidance_contract() -> None:
    result = CreativeMiddlewareRunner.deterministic().run(
        CreativePlanRequest(goal="Design a planning hook for arbitrary repos")
    )

    guidance = result["agent_guidance"]

    assert guidance["intended_use"] == "planning_middleware"
    assert guidance["verification_required"] is True
    assert "observe_repo_state" in guidance["recommended_agent_loop"]
    assert "verification keeps failing" in guidance["escalation_policy"]


def test_runner_reports_search_approval_skip() -> None:
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

    assert result["config"]["search_mode"] == "light"
    assert result["search_context"]["mode"] == "light"
    assert result["search_context"]["used"] is False
    assert result["search_context"]["skipped_reason"] == "approval_required"


def test_runner_merges_injected_search_context() -> None:
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
    assert result["search_context"]["source_count"] == 1
    assert "search/deterministic-search/src-1" in result["context_sources"]


def test_runner_strict_search_returns_configuration_error_when_unavailable() -> None:
    runner = CreativeMiddlewareRunner.deterministic(
        search_context_resolver=SearchContextResolver(
            provider=None,
            provider_policy=SearchProviderPolicy.DETERMINISTIC,
            approval_required=False,
        )
    )

    result = runner.run(
        CreativePlanRequest(
            goal="reversible team decisions",
            search_mode="light",
            search_provider="deterministic",
            search_strict=True,
            seed_count=2,
            finalist_count=1,
            max_generations=0,
            budget_usd=0.20,
        )
    )

    assert result["stopped_reason"] == "configuration_error"
    assert result["generated_count"] == 0
    assert result["finalist_count"] == 0
    assert result["config"]["search_mode"] == "light"
    assert result["config"]["search_provider"] == "deterministic"
    assert result["config"]["search_strict"] is True
    assert result["search_context"]["skipped_reason"] == "configuration_error"
    assert result["search_context"]["strict"] is True
    assert "search provider" in result["errors"][0]["message"]


def test_direct_runner_respects_explicit_search_provider_policy(monkeypatch) -> None:
    monkeypatch.setenv("MUSE_LIVE_SEARCH_APPROVED", "1")

    result = CreativeMiddlewareRunner.deterministic().run(
        CreativePlanRequest(
            goal="reversible team decisions",
            search_mode="light",
            search_provider="exa",
            search_strict=True,
            seed_count=2,
            finalist_count=1,
            max_generations=0,
            budget_usd=0.20,
        )
    )

    assert result["stopped_reason"] == "configuration_error"
    assert result["config"]["search_provider"] == "exa"
    assert result["search_context"]["provider_policy"] == "exa"
    assert result["search_context"]["strict"] is True


def test_live_openai_mode_returns_structured_configuration_error(
    monkeypatch,
) -> None:
    for name in (
        "OPENAI_API_KEY",
        "OPENAI_ECONOMY_MODEL",
        "OPENAI_STRONG_MODEL",
        "OPENAI_PRICING_FILE",
    ):
        monkeypatch.delenv(name, raising=False)

    result = run_muse_plan(
        {
            "goal": "Design a retry strategy for AI coding agents",
            "provider_mode": "live_openai",
            "effort": "deep",
        }
    )

    assert result["provider_mode"] == "live_openai"
    assert result["stopped_reason"] == "configuration_error"
    assert result["finalist_count"] == 0
    assert result["finalists"] == []
    assert result["errors"][0]["category"] == "configuration_error"
    assert "OPENAI_API_KEY" in result["errors"][0]["message"]
    assert result["agent_guidance"]["effort"] == "deep"
    assert result["config"]["search_mode"] == "off"
    assert result["search_context"]["mode"] == "off"
    assert result["search_context"]["used"] is False
    assert result["quality_warnings"] == []
    assert result["quality_summary"] == {
        "warning_count": 0,
        "finalist_warning_count": 0,
        "warnings": {},
    }


def test_middleware_uses_packaged_pricing_when_pricing_env_is_absent(
    monkeypatch,
) -> None:
    monkeypatch.delenv("OPENAI_PRICING_FILE", raising=False)

    pricing = middleware_module._load_pricing_table_from_environment()

    assert pricing.version == "example-v1"
    assert pricing.text_price("gpt-5.4-mini").input_per_million > 0


def test_configuration_error_includes_empty_quality_warning_fields() -> None:
    result = run_muse_plan(
        {
            "goal": "Design a retry strategy for AI coding agents",
            "provider_mode": "bogus",
        }
    )

    assert result["stopped_reason"] == "configuration_error"
    assert result["quality_warnings"] == []
    assert result["quality_summary"] == {
        "warning_count": 0,
        "finalist_warning_count": 0,
        "warnings": {},
    }


def test_configuration_error_includes_clear_quality_action_policy() -> None:
    result = run_muse_plan(
        {
            "goal": "Design a retry strategy for AI coding agents",
            "provider_mode": "bogus",
        }
    )

    assert result["stopped_reason"] == "configuration_error"
    assert result["quality_action_policy"] == {
        "status": "clear",
        "escalate_effort_to": None,
        "recommended_actions": [],
        "warning_actions": {},
    }
    assert result["quality_action_policy"] == (
        result["agent_guidance"]["quality_action_policy"]
    )
    assert result["suggested_next_call"] is None
    assert result["agent_guidance"]["suggested_next_call"] is None


def test_configuration_error_includes_blocked_agent_handoff() -> None:
    result = run_muse_plan(
        {
            "goal": "Design a retry strategy for AI coding agents",
            "provider_mode": "bogus",
        }
    )

    assert result["agent_handoff"] == {
        "status": "blocked",
        "recommended_action": "fix_configuration",
        "use_current_finalist": False,
        "selected_finalist_id": None,
        "suggested_next_call_available": False,
        "verification_required": True,
    }
    assert result["agent_handoff"] == result["agent_guidance"]["agent_handoff"]


def test_invalid_search_mode_error_preserves_response_shape() -> None:
    result = run_muse_plan(
        {
            "goal": "Design a retry strategy for AI coding agents",
            "provider_mode": "deterministic",
            "search_mode": "wide-open",
        }
    )

    assert result["stopped_reason"] == "configuration_error"
    assert result["config"]["search_mode"] == "wide-open"
    assert result["search_context"]["mode"] == "wide-open"
    assert result["search_context"]["used"] is False


def test_live_openai_runner_uses_injected_provider() -> None:
    provider = DeterministicCreativeProvider()
    runner = CreativeMiddlewareRunner.live_openai(
        provider=provider,
    )

    result = runner.run(
        CreativePlanRequest(
            goal="Design a planning hook for arbitrary repos",
            provider_mode="live_openai",
            seed_count=2,
            finalist_count=1,
            max_generations=0,
            budget_usd=0.20,
        )
    )

    assert result["provider_mode"] == "live_openai"
    assert result["finalist_count"] == 1
