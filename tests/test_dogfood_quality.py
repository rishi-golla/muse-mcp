from __future__ import annotations

import json

from muse.dogfood_quality import (
    DEFAULT_DOGFOOD_CASES,
    DEFAULT_SEARCH_VARIANTS,
    SearchVariant,
    evaluate_quality_gates,
    run_dogfood_quality_suite,
)


def test_default_dogfood_cases_cover_agent_and_frontend_tasks() -> None:
    case_names = {case.name for case in DEFAULT_DOGFOOD_CASES}

    assert "agent-retry-python" in case_names
    assert "typescript-monorepo-flaky-ci" in case_names
    assert "agent-middleware-arbitrary-repo" in case_names
    assert "interactive-portfolio-nextjs" in case_names
    assert all(case.required_terms for case in DEFAULT_DOGFOOD_CASES)


def test_default_search_variants_compare_off_light_and_deep() -> None:
    variants = {variant.name: variant for variant in DEFAULT_SEARCH_VARIANTS}

    assert variants["search-off"].search_mode == "off"
    assert variants["search-light"].search_mode == "light"
    assert variants["search-deep"].search_mode == "deep"


def test_quality_gates_flag_generic_deterministic_output() -> None:
    case = DEFAULT_DOGFOOD_CASES[0]
    variant = SearchVariant(name="search-off", search_mode="off")
    result = {
        "stopped_reason": "generation_limit",
        "finalists": [
            {
                "title": "Decision garden",
                "core_mechanism": (
                    "People allocate reversible confidence rather than casting "
                    "binary votes."
                ),
                "inputs_required": ["task goal"],
                "outputs_produced": ["next action"],
                "agent_workflow": ["collect current evidence"],
                "decision_policy": "prefer bounded actions",
                "integration_points": ["agent planning step"],
                "verification_strategy": "run the smallest relevant check",
                "failure_modes": ["ambiguous evidence"],
            }
        ],
        "search_context": {"used": False},
        "errors": [],
    }

    gates = evaluate_quality_gates(case, variant, result)

    assert "generic_title" in gates
    assert "generic_mechanism" in gates
    assert "missing_required_terms" in gates


def test_quality_gates_flag_requested_search_that_was_not_used() -> None:
    case = DEFAULT_DOGFOOD_CASES[0]
    variant = SearchVariant(name="search-light", search_mode="light")
    result = {
        "stopped_reason": "generation_limit",
        "finalists": [],
        "search_context": {"used": False, "skipped_reason": "approval_required"},
        "errors": [],
    }

    gates = evaluate_quality_gates(case, variant, result)

    assert "search_expected_but_unused" in gates
    assert "missing_finalist" in gates


def test_dogfood_suite_invokes_mcp_and_returns_json_safe_report(monkeypatch) -> None:
    monkeypatch.setenv("MUSE_ENABLE_TEST_PROVIDER", "1")
    monkeypatch.setenv("MUSE_PROVIDER_MODE", "deterministic")

    report = run_dogfood_quality_suite(
        provider_mode="deterministic",
        case_names=("agent-retry-python",),
        variant_names=("search-off",),
    )

    assert report["summary"]["case_count"] == 1
    assert report["summary"]["variant_count"] == 1
    assert report["summary"]["run_count"] == 1
    assert report["runs"][0]["case"] == "agent-retry-python"
    assert report["runs"][0]["variant"] == "search-off"
    assert report["runs"][0]["provider_mode"] == "deterministic"
    assert report["runs"][0]["finalist_count"] == 1
    assert "quality_gates" in report["runs"][0]
    assert json.loads(json.dumps(report)) == report
