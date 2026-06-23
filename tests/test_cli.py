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


def make_candidate(*, scored: bool = True) -> IdeaGenome:
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
        title="Usable idea",
        core_mechanism="A concrete mechanism.",
        problem_framing="A concrete framing.",
        task_value="A concrete benefit.",
        scores=scores,
    )


def make_result(
    *,
    stopped_reason: str,
    finalists: tuple[IdeaGenome, ...],
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
        all_candidates=finalists,
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
