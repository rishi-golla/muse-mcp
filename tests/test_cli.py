import json
from pathlib import Path

import pytest

import creativity_layer.cli as cli_module
from creativity_layer.cli import main, run_cli
from creativity_layer.models import (
    EvaluationScores,
    FramedTask,
    IdeaGenome,
    ProviderIdentity,
    RunConfig,
    RunProviders,
    RunResult,
    TaskContext,
)


def make_candidate(*, title: str = "Usable idea", scored: bool = True) -> IdeaGenome:
    scores = (
        EvaluationScores(
            originality=0.8,
            usefulness=0.7,
            coherence=0.9,
            feasibility=0.6,
            user_fit=0.75,
        )
        if scored
        else None
    )
    return IdeaGenome(
        generation=0,
        title=title,
        core_mechanism="A concrete mechanism.",
        problem_framing="A concrete framing.",
        task_value="A concrete benefit.",
        scores=scores,
    )


def make_result(
    *,
    stopped_reason: str,
    finalists: tuple[IdeaGenome, ...],
    all_candidates: tuple[IdeaGenome, ...] | None = None,
) -> RunResult:
    return RunResult(
        config=RunConfig(seed_count=2, finalist_count=1),
        providers=RunProviders(
            framer=ProviderIdentity(name="local", version="1"),
            seeder=ProviderIdentity(name="local", version="1"),
            transformer=ProviderIdentity(name="local", version="1"),
            evaluator=ProviderIdentity(name="local", version="1"),
        ),
        operator_schedule=("invert",),
        framed_task=FramedTask(
            context=TaskContext(goal="Test goal"),
            assumptions=(),
            obvious_solution="An obvious solution.",
        ),
        finalists=finalists,
        all_candidates=all_candidates if all_candidates is not None else finalists,
        spend_records=(),
        stopped_reason=stopped_reason,
    )


def use_engine_result(monkeypatch, result: RunResult) -> None:
    class StaticEngine:
        def __init__(self, **_kwargs) -> None:
            pass

        def run(self, _task, _config) -> RunResult:
            return result

    monkeypatch.setattr(cli_module, "CreativeEngine", StaticEngine)


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
    assert Path(summary["trace_path"]) == traces[0].resolve()
    assert Path(summary["trace_path"]).is_absolute()
    assert len(traces) == 1
    assert captured.err == ""


def test_deterministic_cli_context_file_feeds_typed_context(
    tmp_path,
    capsys,
) -> None:
    context_path = tmp_path / "context.json"
    context_path.write_text(
        json.dumps(
            {
                "snippets": [
                    {
                        "source": "repo/ci-snapshot",
                        "title": "CI signals",
                        "content": (
                            "package graph, affected packages, test shards, "
                            "tsc, Jest, Vitest, Playwright, CI logs"
                        ),
                    }
                ],
                "tags": ["typescript", "monorepo"],
            }
        ),
        encoding="utf-8",
    )

    exit_code = run_cli(
        [
            "deterministic",
            "Design a debugging workflow for flaky CI",
            "--context-file",
            str(context_path),
            "--trace-dir",
            str(tmp_path / "traces"),
            "--seed-count",
            "2",
            "--finalist-count",
            "1",
            "--generations",
            "0",
        ]
    )

    captured = capsys.readouterr()
    summary = json.loads(captured.out)
    trace = json.loads(Path(summary["trace_path"]).read_text(encoding="utf-8"))
    candidate_text = json.dumps(trace["all_candidates"][0]).casefold()

    assert exit_code == 0
    assert trace["framed_task"]["context"]["context_bundle"]["snippets"][0][
        "source"
    ] == "repo/ci-snapshot"
    assert "package graph" in candidate_text
    assert "test shards" in candidate_text
    assert captured.err == ""


def test_deterministic_cli_repo_signals_file_builds_context(
    tmp_path,
    capsys,
) -> None:
    signals_path = tmp_path / "repo-signals.json"
    signals_path.write_text(
        json.dumps(
            {
                "file_paths": ["pnpm-workspace.yaml", "apps/web/package.json"],
                "changed_files": ["packages/ui/src/Button.tsx"],
                "package_manifests": ["apps/web/package.json"],
                "test_commands": ["pnpm test --filter apps/web -- --shard=2/4"],
                "ci_logs": ["Vitest shard 2 failed after Playwright smoke tests"],
                "dependency_hints": ["apps/web depends on packages/ui"],
                "detected_languages": ["TypeScript"],
                "detected_frameworks": ["Vitest", "Playwright"],
            }
        ),
        encoding="utf-8",
    )

    exit_code = run_cli(
        [
            "deterministic",
            "Design a debugging workflow for flaky CI",
            "--repo-signals-file",
            str(signals_path),
            "--trace-dir",
            str(tmp_path / "traces"),
            "--seed-count",
            "2",
            "--finalist-count",
            "1",
            "--generations",
            "0",
        ]
    )

    captured = capsys.readouterr()
    summary = json.loads(captured.out)
    trace = json.loads(Path(summary["trace_path"]).read_text(encoding="utf-8"))
    candidate_text = json.dumps(trace["all_candidates"][0]).casefold()

    assert exit_code == 0
    assert trace["framed_task"]["context"]["context_bundle"]["snippets"]
    assert "affected packages" in candidate_text
    assert "test shards" in candidate_text
    assert captured.err == ""


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        (["   "], "goal must not be blank"),
        (
            ["Goal", "--seed-count", "2", "--finalist-count", "3"],
            "finalist_count cannot exceed seed_count",
        ),
        (["Goal", "--seed-count", "1"], "greater than or equal to 2"),
        (["Goal", "--max-calls", "0"], "greater than 0"),
        (["Goal", "--max-cost-usd", "0"], "greater than 0"),
    ],
)
def test_cli_reports_invalid_model_input_as_argparse_error(
    arguments: list[str],
    message: str,
    capsys,
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        run_cli(arguments)

    captured = capsys.readouterr()

    assert exc_info.value.code == 2
    assert captured.out == ""
    assert "usage: creativity-layer" in captured.err
    assert f"error: {message}" in captured.err
    assert "Traceback" not in captured.err


def test_cli_reports_invalid_numeric_input_as_argparse_error(capsys) -> None:
    with pytest.raises(SystemExit) as exc_info:
        run_cli(["Goal", "--max-cost-usd", "not-a-number"])

    captured = capsys.readouterr()

    assert exc_info.value.code == 2
    assert captured.out == ""
    assert "invalid float value" in captured.err
    assert "Traceback" not in captured.err


def test_cli_reports_invalid_context_file_without_traceback(tmp_path, capsys) -> None:
    context_path = tmp_path / "context.json"
    context_path.write_text("{not valid json", encoding="utf-8")

    with pytest.raises(SystemExit) as exc_info:
        run_cli(["Goal", "--context-file", str(context_path)])

    captured = capsys.readouterr()

    assert exc_info.value.code == 2
    assert captured.out == ""
    assert "could not read context file" in captured.err
    assert "Traceback" not in captured.err


def test_cli_returns_one_for_provider_error_but_writes_summary_and_trace(
    tmp_path,
    capsys,
    monkeypatch,
) -> None:
    use_engine_result(
        monkeypatch,
        make_result(
            stopped_reason="provider_error",
            finalists=(make_candidate(),),
        ),
    )

    exit_code = run_cli(["Goal", "--trace-dir", str(tmp_path)])

    captured = capsys.readouterr()
    summary = json.loads(captured.out)

    assert exit_code == 1
    assert summary["stopped_reason"] == "provider_error"
    assert summary["finalist_count"] == 1
    trace_payload = json.loads(
        Path(summary["trace_path"]).read_text(encoding="utf-8")
    )
    assert trace_payload["stopped_reason"] == "provider_error"
    assert captured.err == ""


def test_cli_summarizes_unevaluated_generated_candidates(
    tmp_path,
    capsys,
    monkeypatch,
) -> None:
    scored = make_candidate(title="Scored", scored=True)
    unevaluated = make_candidate(title="Unevaluated", scored=False)
    use_engine_result(
        monkeypatch,
        make_result(
            stopped_reason="provider_error",
            finalists=(scored,),
            all_candidates=(scored, unevaluated),
        ),
    )

    exit_code = run_cli(["Goal", "--trace-dir", str(tmp_path)])

    summary = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert summary["generated_count"] == 2
    assert summary["unevaluated_count"] == 1
    assert summary["unevaluated_candidates"] == [{"title": "Unevaluated"}]


@pytest.mark.parametrize(
    "finalists",
    [
        (),
        (make_candidate(scored=False),),
    ],
    ids=["zero-finalists", "unscored-finalist"],
)
def test_cli_returns_one_without_a_usable_finalist(
    finalists: tuple[IdeaGenome, ...],
    tmp_path,
    capsys,
    monkeypatch,
) -> None:
    use_engine_result(
        monkeypatch,
        make_result(stopped_reason="generation_limit", finalists=finalists),
    )

    exit_code = run_cli(["Goal", "--trace-dir", str(tmp_path)])

    captured = capsys.readouterr()
    summary = json.loads(captured.out)

    assert exit_code == 1
    assert summary["finalist_count"] == len(finalists)
    assert Path(summary["trace_path"]).exists()
    assert captured.err == ""


def test_cli_treats_budget_exhaustion_with_valid_frontier_as_success(
    tmp_path,
    capsys,
    monkeypatch,
) -> None:
    use_engine_result(
        monkeypatch,
        make_result(
            stopped_reason="budget_exhausted",
            finalists=(make_candidate(),),
        ),
    )

    exit_code = run_cli(["Goal", "--trace-dir", str(tmp_path)])

    captured = capsys.readouterr()
    summary = json.loads(captured.out)

    assert exit_code == 0
    assert summary["stopped_reason"] == "budget_exhausted"
    assert summary["finalist_count"] == 1
    assert captured.err == ""


def test_cli_resolves_relative_trace_path(
    tmp_path,
    capsys,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    exit_code = run_cli(
        [
            "Goal",
            "--trace-dir",
            "relative-traces",
            "--seed-count",
            "2",
            "--finalist-count",
            "1",
            "--generations",
            "0",
        ]
    )

    captured = capsys.readouterr()
    trace_path = Path(json.loads(captured.out)["trace_path"])

    assert exit_code == 0
    assert trace_path.is_absolute()
    assert trace_path.parent == (tmp_path / "relative-traces").resolve()
    assert captured.err == ""


def test_cli_returns_one_with_stderr_only_when_trace_save_fails(
    tmp_path,
    capsys,
    monkeypatch,
) -> None:
    def fail_save(_store, _result) -> Path:
        raise OSError("disk full")

    monkeypatch.setattr(cli_module.JsonTraceStore, "save", fail_save)

    exit_code = run_cli(["Goal", "--trace-dir", str(tmp_path)])

    captured = capsys.readouterr()

    assert exit_code == 1
    assert captured.out == ""
    assert "could not write trace" in captured.err.lower()
    assert str(tmp_path.resolve()) in captured.err
    assert "disk full" in captured.err
    assert "Traceback" not in captured.err


def test_main_returns_run_cli_status(tmp_path, capsys) -> None:
    exit_code = main(
        [
            "Goal",
            "--trace-dir",
            str(tmp_path),
            "--seed-count",
            "2",
            "--finalist-count",
            "1",
            "--generations",
            "0",
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 0
    assert json.loads(captured.out)["finalist_count"] == 1
    assert captured.err == ""
