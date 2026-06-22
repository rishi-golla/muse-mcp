import json
from uuid import uuid4

from creativity_layer.models import (
    FramedTask,
    IdeaGenome,
    RunResult,
    SpendRecord,
    TaskContext,
)
from creativity_layer.tracing import JsonTraceStore


def test_trace_store_writes_stable_structured_json(tmp_path) -> None:
    candidate = IdeaGenome(
        generation=0,
        title="Idea",
        core_mechanism="Mechanism",
        problem_framing="Framing",
        task_value="Value",
    )
    result = RunResult(
        run_id=uuid4(),
        framed_task=FramedTask(
            context=TaskContext(goal="Test creativity"),
            assumptions=("Obvious assumption",),
            obvious_solution="Obvious answer",
        ),
        finalists=(candidate,),
        all_candidates=(candidate,),
        spend_records=(
            SpendRecord(stage="seed", provider="local", cost_usd=0.01, latency_ms=1),
        ),
        stopped_reason="generation_limit",
    )

    path = JsonTraceStore(tmp_path).save(result)
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert path.name == f"{result.run_id}.json"
    assert payload["run_id"] == str(result.run_id)
    assert payload["framed_task"]["context"]["goal"] == "Test creativity"
    assert payload["finalists"][0]["title"] == "Idea"
