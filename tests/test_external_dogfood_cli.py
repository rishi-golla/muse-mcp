from __future__ import annotations

import json
import tomllib
from pathlib import Path

from muse.external_dogfood_cli import main


def test_external_dogfood_cli_prints_json_report(tmp_path: Path, capsys) -> None:
    exit_code = main(["--workspace", str(tmp_path / "external"), "--json"])

    output = capsys.readouterr()
    payload = json.loads(output.out)

    assert exit_code == 0
    assert payload["workspace"].endswith("external")
    assert payload["host"] == "generic-json"
    assert payload["mcp_smoke_status"] == "skipped"
    assert output.err == ""


def test_external_dogfood_cli_strict_live_fails_when_preflight_is_not_ready(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    for name in (
        "OPENAI_API_KEY",
        "OPENAI_ECONOMY_MODEL",
        "OPENAI_STRONG_MODEL",
        "OPENAI_EMBEDDING_MODEL",
        "OPENAI_PRICING_FILE",
    ):
        monkeypatch.delenv(name, raising=False)

    exit_code = main(["--workspace", str(tmp_path / "external"), "--strict-live"])

    output = capsys.readouterr()

    assert exit_code == 1
    assert "ready_for_manual_agent_test: false" in output.out
    assert output.err == ""


def test_package_exposes_external_dogfood_console_script() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    assert pyproject["project"]["scripts"]["muse-external-dogfood"] == (
        "muse.external_dogfood_cli:main"
    )
