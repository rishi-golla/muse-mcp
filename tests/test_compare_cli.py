from __future__ import annotations

import json
from pathlib import Path

import pytest

from creativity_layer.cli import run_cli


def test_compare_cli_writes_baseline_and_search_aware_traces(
    tmp_path,
    capsys,
) -> None:
    exit_code = run_cli(
        [
            "compare",
            "Reversible team decisions",
            "--trace-dir",
            str(tmp_path),
            "--seed-count",
            "4",
            "--finalist-count",
            "2",
            "--generations",
            "0",
            "--budget-usd",
            "0.10",
        ]
    )

    captured = capsys.readouterr()
    summary = json.loads(captured.out)
    trace_paths = {
        Path(summary["baseline"]["trace_path"]),
        Path(summary["search_aware"]["trace_path"]),
    }

    assert exit_code == 0
    assert summary == {
        "baseline": {
            "trace_path": summary["baseline"]["trace_path"],
            "finalist_count": 2,
            "stopped_reason": "generation_limit",
        },
        "search_aware": {
            "trace_path": summary["search_aware"]["trace_path"],
            "finalist_count": 2,
            "stopped_reason": "generation_limit",
            "novelty_mode": "provisional_no_network",
        },
    }
    assert all(path.is_absolute() for path in trace_paths)
    assert all(path.parent == tmp_path.resolve() for path in trace_paths)
    assert all(path.exists() for path in trace_paths)
    assert len(trace_paths) == 2
    assert len(list(tmp_path.glob("*.json"))) == 2
    assert captured.err == ""


def test_compare_cli_context_file_feeds_both_runs(tmp_path, capsys) -> None:
    context_path = tmp_path / "context.json"
    context_path.write_text(
        json.dumps(
            {
                "snippets": [
                    {
                        "source": "repo/package-graph",
                        "content": "package graph with affected packages and test shards",
                    }
                ],
                "tags": ["typescript", "monorepo"],
            }
        ),
        encoding="utf-8",
    )

    exit_code = run_cli(
        [
            "compare",
            "Design a TypeScript monorepo CI workflow",
            "--context-file",
            str(context_path),
            "--trace-dir",
            str(tmp_path / "traces"),
            "--seed-count",
            "4",
            "--finalist-count",
            "2",
        ]
    )

    captured = capsys.readouterr()
    summary = json.loads(captured.out)
    baseline = json.loads(
        Path(summary["baseline"]["trace_path"]).read_text(encoding="utf-8")
    )
    search_aware = json.loads(
        Path(summary["search_aware"]["trace_path"]).read_text(encoding="utf-8")
    )

    assert exit_code == 0
    assert baseline["framed_task"]["context"]["context_bundle"]["snippets"][0][
        "source"
    ] == "repo/package-graph"
    assert search_aware["framed_task"]["context"]["context_bundle"]["tags"] == [
        "typescript",
        "monorepo",
    ]
    assert captured.err == ""


def test_compare_is_recognized_as_command_instead_of_goal(
    tmp_path,
    capsys,
) -> None:
    exit_code = run_cli(
        [
            "compare",
            "Reversible team decisions",
            "--trace-dir",
            str(tmp_path),
        ]
    )

    captured = capsys.readouterr()
    summary = json.loads(captured.out)

    assert exit_code == 0
    assert set(summary) == {"baseline", "search_aware"}
    assert captured.err == ""


def test_compare_cli_reports_invalid_model_input_as_argparse_error(
    tmp_path,
    capsys,
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        run_cli(
            [
                "compare",
                "Goal",
                "--trace-dir",
                str(tmp_path),
                "--seed-count",
                "2",
                "--finalist-count",
                "3",
            ]
        )

    captured = capsys.readouterr()

    assert exc_info.value.code == 2
    assert captured.out == ""
    assert "usage: creativity-layer" in captured.err
    assert "error: finalist_count cannot exceed seed_count" in captured.err
    assert "Traceback" not in captured.err
