import os

import pytest

from muse.cli import run_cli

pytestmark = pytest.mark.live_openai


def test_live_openai_smoke(tmp_path) -> None:
    required = (
        "MUSE_RUN_PAID_OPENAI_TEST",
        "OPENAI_API_KEY",
        "OPENAI_ECONOMY_MODEL",
        "OPENAI_STRONG_MODEL",
        "OPENAI_PRICING_FILE",
    )
    if any(not os.getenv(name) for name in required):
        pytest.skip("live OpenAI environment is not configured")
    if os.getenv("MUSE_RUN_PAID_OPENAI_TEST") != "1":
        pytest.skip("paid live OpenAI test is not explicitly approved")

    exit_code = run_cli(
        [
            "live",
            "Invent one reversible way to coordinate a two-person decision.",
            "--budget-usd",
            "0.04",
            "--seed-count",
            "2",
            "--finalist-count",
            "1",
            "--generations",
            "0",
            "--trace-dir",
            str(tmp_path),
            "--privacy",
            "private",
        ]
    )

    assert exit_code == 0
    assert len(list(tmp_path.glob("*.json"))) == 1
