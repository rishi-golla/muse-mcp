from __future__ import annotations

from creativity_layer.quality_warnings import (
    build_suggested_next_call,
    finalist_quality_warnings,
    quality_action_policy,
    summarize_quality_warnings,
)


def test_finalist_quality_warnings_flags_generic_title_mechanism_and_empty_contract() -> None:
    finalist = {
        "title": "Decision garden",
        "core_mechanism": (
            "People allocate reversible confidence rather than binary votes."
        ),
        "inputs_required": [],
        "outputs_produced": ["next action"],
        "agent_workflow": ["collect evidence"],
        "decision_policy": "choose bounded action",
        "integration_points": ["planning step"],
        "verification_strategy": "run tests",
        "failure_modes": ["ambiguous evidence"],
    }

    warnings = finalist_quality_warnings(finalist)

    assert warnings == (
        "generic_title",
        "generic_mechanism",
        "missing_operational_field",
    )


def test_finalist_quality_warnings_flags_missing_required_terms() -> None:
    finalist = {
        "title": "Shard replay",
        "core_mechanism": "Replay the failing shard and compare verification output.",
        "inputs_required": ["test command"],
        "outputs_produced": ["report"],
        "agent_workflow": ["run failing shard"],
        "decision_policy": "stop after repeated failure",
        "integration_points": ["agent planning step"],
        "verification_strategy": "run the shard",
        "failure_modes": ["environment mismatch"],
    }

    assert finalist_quality_warnings(
        finalist,
        required_terms=("pytest", "retry"),
    ) == ("missing_required_terms",)


def test_summarize_quality_warnings_counts_unique_finalists() -> None:
    summary = summarize_quality_warnings(
        [
            ("generic_title", "generic_mechanism"),
            ("generic_title",),
            (),
        ]
    )

    assert summary == {
        "warning_count": 3,
        "finalist_warning_count": 2,
        "warnings": {"generic_mechanism": 1, "generic_title": 2},
    }


def test_quality_action_policy_is_clear_without_warnings() -> None:
    policy = quality_action_policy((), effort="quick")

    assert policy == {
        "status": "clear",
        "escalate_effort_to": None,
        "recommended_actions": [],
        "warning_actions": {},
    }


def test_quality_action_policy_recommends_retry_for_missing_operational_detail() -> None:
    policy = quality_action_policy(
        ("generic_title", "missing_required_terms"),
        effort="quick",
    )

    assert policy["status"] == "needs_retry"
    assert policy["escalate_effort_to"] == "standard"
    assert "supply more repo signals" in policy["recommended_actions"]
    assert "missing_required_terms" in policy["warning_actions"]


def test_quality_action_policy_stops_effort_escalation_at_deep() -> None:
    policy = quality_action_policy(("generic_mechanism",), effort="deep")

    assert policy["status"] == "review"
    assert policy["escalate_effort_to"] is None


def test_suggested_next_call_is_none_when_quality_policy_is_clear() -> None:
    policy = quality_action_policy((), effort="quick")

    assert (
        build_suggested_next_call(
            policy,
            goal="Design a retry strategy",
            provider_mode="live_openai",
            privacy="research",
            effort="quick",
            search_mode="off",
            search_provider="auto",
            search_strict=False,
            max_context_snippets=8,
        )
        is None
    )


def test_suggested_next_call_escalates_without_copying_repo_signals() -> None:
    policy = quality_action_policy(
        ("generic_title", "missing_required_terms"),
        effort="quick",
    )

    suggestion = build_suggested_next_call(
        policy,
        goal="Design a retry strategy for AI coding agents",
        provider_mode="live_openai",
        privacy="research",
        effort="quick",
        search_mode="light",
        search_provider="brave",
        search_strict=True,
        max_context_snippets=6,
    )

    assert suggestion == {
        "tool": "creative_plan",
        "automatic": False,
        "reason": "quality_action_policy",
        "request": {
            "goal": "Design a retry strategy for AI coding agents",
            "provider_mode": "live_openai",
            "privacy": "research",
            "effort": "standard",
            "search_mode": "light",
            "search_provider": "brave",
            "search_strict": True,
            "max_context_snippets": 6,
        },
        "repo_signal_requests": [
            "include observed stack, changed files, test commands, and failure excerpts",
            "ask for task-specific title and mechanism before editing",
        ],
    }
