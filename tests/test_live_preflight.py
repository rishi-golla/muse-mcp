from __future__ import annotations

from pathlib import Path

import pytest

from muse.live_preflight import (
    LivePreflightStatus,
    check_live_openai_environment,
    resolve_openai_pricing_table,
)


def test_resolve_openai_pricing_table_uses_packaged_default_when_env_is_absent() -> None:
    pricing, source = resolve_openai_pricing_table({})

    assert source == "packaged:openai-pricing.example.json"
    assert pricing.text_price("gpt-5.4-mini").input_per_million > 0
    assert pricing.text_price("gpt-5.4").output_per_million > 0
    assert pricing.embedding_price("text-embedding-3-small").input_per_million > 0


def test_resolve_openai_pricing_table_rejects_invalid_override_file(tmp_path: Path) -> None:
    pricing_file = tmp_path / "pricing.json"
    pricing_file.write_text("not-json", encoding="utf-8")

    with pytest.raises(ValueError, match="invalid pricing config"):
        resolve_openai_pricing_table({"OPENAI_PRICING_FILE": str(pricing_file)})


def test_live_preflight_reports_missing_required_openai_environment() -> None:
    report = check_live_openai_environment({})

    assert report.ok is False
    assert report.status is LivePreflightStatus.ERROR
    assert report.pricing_source == "packaged:openai-pricing.example.json"
    assert report.checks_by_name()["openai_api_key"].status is LivePreflightStatus.ERROR
    assert report.checks_by_name()["openai_models"].status is LivePreflightStatus.ERROR
    action_text = "\n".join(report.action_items)
    assert "OPENAI_API_KEY" in action_text
    assert "OPENAI_ECONOMY_MODEL" in action_text


def test_live_preflight_accepts_minimal_live_environment_without_pricing_file() -> None:
    report = check_live_openai_environment(
        {
            "OPENAI_API_KEY": "sk-test-value",
            "OPENAI_ECONOMY_MODEL": "gpt-5.4-mini",
            "OPENAI_STRONG_MODEL": "gpt-5.4",
            "OPENAI_EMBEDDING_MODEL": "text-embedding-3-small",
        }
    )

    assert report.ok is True
    assert report.status is LivePreflightStatus.OK
    assert report.pricing_source == "packaged:openai-pricing.example.json"
    assert report.redacted_environment["OPENAI_API_KEY"] == "set"
    assert "sk-test-value" not in report.model_dump_json()


def test_live_preflight_reports_invalid_model_identifiers_without_crashing() -> None:
    report = check_live_openai_environment(
        {
            "OPENAI_API_KEY": "sk-test-value",
            "OPENAI_ECONOMY_MODEL": "bad model",
            "OPENAI_STRONG_MODEL": "gpt-5.4",
        }
    )

    assert report.ok is False
    assert report.checks_by_name()["openai_models"].status is LivePreflightStatus.ERROR
    assert "model identifier" in report.checks_by_name()["openai_models"].message
