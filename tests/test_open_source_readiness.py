from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

from muse.pricing import PricingTable

ROOT = Path(__file__).resolve().parents[1]


REQUIRED_PUBLIC_FILES = (
    "LICENSE",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "CODE_OF_CONDUCT.md",
    ".env.example",
    "openai-pricing.example.json",
    ".github/ISSUE_TEMPLATE/bug_report.yml",
    ".github/ISSUE_TEMPLATE/feature_request.yml",
    ".github/ISSUE_TEMPLATE/config.yml",
    ".github/PULL_REQUEST_TEMPLATE.md",
)


def _read_text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_required_public_release_files_exist() -> None:
    missing = [path for path in REQUIRED_PUBLIC_FILES if not (ROOT / path).is_file()]

    assert missing == []


def test_pyproject_has_open_source_metadata() -> None:
    pyproject = tomllib.loads(_read_text("pyproject.toml"))
    project = pyproject["project"]

    assert project["license"] == "MIT"
    assert "Development Status :: 3 - Alpha" in project["classifiers"]
    assert "License :: OSI Approved :: MIT License" in project["classifiers"]
    assert "Programming Language :: Python :: 3.12" in project["classifiers"]
    assert project["urls"]["Repository"] == "https://github.com/rishi-golla/muse"
    assert project["urls"]["Issues"] == (
        "https://github.com/rishi-golla/muse/issues"
    )


def test_env_example_documents_safe_public_configuration() -> None:
    text = _read_text(".env.example")

    for variable in (
        "OPENAI_API_KEY",
        "OPENAI_ECONOMY_MODEL",
        "OPENAI_STRONG_MODEL",
        "OPENAI_EMBEDDING_MODEL",
        "OPENAI_PRICING_FILE",
        "MUSE_PROVIDER_MODE",
        "MUSE_EFFORT",
        "MUSE_SEARCH_MODE",
        "MUSE_SEARCH_PROVIDER",
        "MUSE_LIVE_SEARCH_APPROVED",
        "EXA_API_KEY",
        "BRAVE_SEARCH_API_KEY",
    ):
        assert f"{variable}=" in text

    assert "sk-" not in text
    assert "gho_" not in text
    assert "<" not in text
    assert "OPENAI_API_KEY=replace_me" in text


def test_local_env_files_are_ignored_but_example_is_tracked() -> None:
    text = _read_text(".gitignore")

    assert ".env" in text
    assert ".env.*" in text
    assert "!.env.example" in text


def test_openai_pricing_example_uses_current_schema() -> None:
    payload = _read_text("openai-pricing.example.json")
    pricing = PricingTable.model_validate_json(payload)
    parsed = json.loads(payload)

    assert parsed["version"] == "example-v1"
    assert pricing.text_price("gpt-5.4-mini").input_per_million > 0
    assert pricing.embedding_price("text-embedding-3-small").input_per_million > 0


def test_public_docs_include_copy_pasteable_first_run_path() -> None:
    readme = _read_text("README.md").casefold()
    host_guide = _read_text("docs/integrations/mcp-agent-hosts.md").casefold()
    combined = "\n".join((readme, host_guide))

    for phrase in (
        "open-source quickstart",
        'python -m pip install -e ".[dev]"',
        "muse-mcp-smoke",
        "muse-dogfood-quality",
        "--provider-mode deterministic",
        ".env.example",
        "openai-pricing.example.json",
        "muse_plan",
        "mcp",
    ):
        assert phrase in combined


def test_github_templates_request_quality_and_verification_evidence() -> None:
    bug = _read_text(".github/ISSUE_TEMPLATE/bug_report.yml").casefold()
    feature = _read_text(".github/ISSUE_TEMPLATE/feature_request.yml").casefold()
    pr = _read_text(".github/PULL_REQUEST_TEMPLATE.md").casefold()
    combined = "\n".join((bug, feature, pr))

    assert "muse-dogfood-quality" in combined
    assert "pytest" in combined
    assert "ruff" in combined
    assert "mcp" in combined
    assert re.search(r"quality.+gate|gate.+quality", combined)


def test_public_release_files_do_not_contain_obvious_secrets() -> None:
    combined = "\n".join(
        _read_text(path)
        for path in REQUIRED_PUBLIC_FILES
        if (ROOT / path).is_file()
    )

    assert "sk-" not in combined
    assert "gho_" not in combined
    assert "your-api-key" not in combined.casefold()
