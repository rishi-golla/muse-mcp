import json
from pathlib import Path

from creativity_layer.cli import run_cli
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


def make_result(*, goal: str = "Review packet goal", title: str = "Packet idea") -> RunResult:
    finalist = IdeaGenome(
        generation=0,
        title=title,
        core_mechanism="Use a reversible trial before committing.",
        problem_framing="The team treats early uncertainty as a final decision.",
        task_value="The team can compare the option without exposing internals.",
        scores=EvaluationScores(
            originality=0.8,
            usefulness=0.7,
            coherence=0.9,
            feasibility=0.6,
            user_fit=0.75,
        ),
    )
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
            context=TaskContext(goal=goal),
            assumptions=(),
            obvious_solution="Use a standard review.",
        ),
        finalists=(finalist,),
        all_candidates=(finalist,),
        spend_records=(),
        stopped_reason="generation_limit",
    )


def write_trace(path: Path, result: RunResult) -> None:
    path.write_text(
        json.dumps(result.model_dump(mode="json")),
        encoding="utf-8",
    )


def test_review_packet_cli_writes_packet_file_and_summary(tmp_path, capsys) -> None:
    trace_path = tmp_path / "trace.json"
    output_dir = tmp_path / "packets"
    write_trace(trace_path, make_result())

    exit_code = run_cli(
        [
            "review-packet",
            "--trace",
            str(trace_path),
            "--output-dir",
            str(output_dir),
            "--shuffle-seed",
            "17",
        ]
    )

    captured = capsys.readouterr()
    summary = json.loads(captured.out)
    packet_path = Path(summary["packets"][0]["path"])

    assert exit_code == 0
    assert summary["packet_count"] == 1
    assert summary["packets"][0]["packet_id"]
    assert summary["packets"][0]["candidate_count"] == 1
    assert packet_path.is_absolute()
    assert packet_path.exists()
    assert packet_path.parent == output_dir.resolve()
    assert captured.err == ""


def test_review_packet_cli_repeated_trace_writes_one_packet_per_trace(
    tmp_path,
    capsys,
) -> None:
    first_trace = tmp_path / "first-trace.json"
    second_trace = tmp_path / "second-trace.json"
    output_dir = tmp_path / "packets"
    write_trace(first_trace, make_result(title="First packet idea"))
    write_trace(second_trace, make_result(title="Second packet idea"))

    exit_code = run_cli(
        [
            "review-packet",
            "--trace",
            str(first_trace),
            "--trace",
            str(second_trace),
            "--output-dir",
            str(output_dir),
        ]
    )

    captured = capsys.readouterr()
    summary = json.loads(captured.out)
    packet_paths = [Path(packet["path"]) for packet in summary["packets"]]

    assert exit_code == 0
    assert summary["packet_count"] == 2
    assert len(packet_paths) == 2
    assert all(path.exists() for path in packet_paths)
    assert len(set(packet_paths)) == 2
    assert captured.err == ""


def test_review_packet_cli_invalid_trace_returns_two_without_traceback_or_packets(
    tmp_path,
    capsys,
) -> None:
    trace_path = tmp_path / "invalid-trace.json"
    output_dir = tmp_path / "packets"
    trace_path.write_text("{not json", encoding="utf-8")

    exit_code = run_cli(
        [
            "review-packet",
            "--trace",
            str(trace_path),
            "--output-dir",
            str(output_dir),
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 2
    assert captured.out == ""
    assert "invalid trace" in captured.err.lower()
    assert "Traceback" not in captured.err
    assert list(output_dir.glob("*.review-packet.json")) == []


def test_review_packet_command_is_recognized_instead_of_treated_as_goal(
    tmp_path,
    capsys,
) -> None:
    missing_trace = tmp_path / "missing-trace.json"

    exit_code = run_cli(["review-packet", "--trace", str(missing_trace)])

    captured = capsys.readouterr()

    assert exit_code == 2
    assert captured.out == ""
    assert "could not read trace" in captured.err.lower()
    assert "unrecognized arguments" not in captured.err
    assert "Traceback" not in captured.err
