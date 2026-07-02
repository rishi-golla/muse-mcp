from __future__ import annotations

import json
import tomllib
from pathlib import Path

from muse.mcp_doctor import main


def test_mcp_doctor_json_reports_missing_live_configuration(
    capsys,
    monkeypatch,
) -> None:
    for name in (
        "OPENAI_API_KEY",
        "OPENAI_ECONOMY_MODEL",
        "OPENAI_STRONG_MODEL",
        "OPENAI_EMBEDDING_MODEL",
        "OPENAI_PRICING_FILE",
    ):
        monkeypatch.delenv(name, raising=False)

    exit_code = main(["--json"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert payload["status"] == "error"
    assert payload["pricing_source"] == "packaged:openai-pricing.example.json"
    assert payload["redacted_environment"]["OPENAI_API_KEY"] == "missing"
    assert "OPENAI_API_KEY" in "\n".join(payload["action_items"])


def test_mcp_doctor_json_accepts_minimal_live_configuration(
    capsys,
    monkeypatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-value")
    monkeypatch.setenv("OPENAI_ECONOMY_MODEL", "gpt-5.4-mini")
    monkeypatch.setenv("OPENAI_STRONG_MODEL", "gpt-5.4")
    monkeypatch.delenv("OPENAI_PRICING_FILE", raising=False)

    exit_code = main(["--json"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["status"] == "ok"
    assert payload["pricing_source"] == "packaged:openai-pricing.example.json"
    assert payload["redacted_environment"]["OPENAI_API_KEY"] == "set"
    assert "sk-test-value" not in json.dumps(payload)


def test_package_exposes_mcp_doctor_console_script() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    assert pyproject["project"]["scripts"]["muse-mcp-doctor"] == (
        "muse.mcp_doctor:main"
    )
