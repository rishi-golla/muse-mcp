import json

from creativity_layer.cli import run_cli


def test_cli_runs_research_spine_and_writes_trace(tmp_path, capsys) -> None:
    exit_code = run_cli(
        [
            "Invent a calmer decision process.",
            "--trace-dir",
            str(tmp_path),
            "--seed-count",
            "2",
            "--finalist-count",
            "1",
            "--generations",
            "1",
        ]
    )

    captured = capsys.readouterr()
    summary = json.loads(captured.out)
    traces = list(tmp_path.glob("*.json"))

    assert exit_code == 0
    assert summary["finalist_count"] == 1
    assert summary["stopped_reason"] == "generation_limit"
    assert len(traces) == 1
