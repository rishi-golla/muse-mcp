import json
import os
from uuid import uuid4

import pytest

from creativity_layer.models import (
    FramedTask,
    IdeaGenome,
    ProviderIdentity,
    RunConfig,
    RunProviders,
    RunResult,
    SpendRecord,
    TaskContext,
)
from creativity_layer.tracing import JsonTraceStore


def run_result() -> RunResult:
    candidate = IdeaGenome(
        generation=0,
        title="Idea",
        core_mechanism="Mechanism",
        problem_framing="Framing",
        task_value="Value",
    )
    return RunResult(
        run_id=uuid4(),
        config=RunConfig(seed_count=2, finalist_count=1),
        providers=RunProviders(
            framer=ProviderIdentity(name="local", version="1"),
            seeder=ProviderIdentity(name="local", version="1"),
            transformer=ProviderIdentity(name="local", version="1"),
            evaluator=ProviderIdentity(name="local", version="1"),
        ),
        operator_schedule=("invert",),
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


def test_trace_store_writes_stable_structured_json(tmp_path) -> None:
    result = run_result()

    path = JsonTraceStore(tmp_path).save(result)
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert path.name == f"{result.run_id}.json"
    assert payload["run_id"] == str(result.run_id)
    assert payload["framed_task"]["context"]["goal"] == "Test creativity"
    assert payload["finalists"][0]["title"] == "Idea"


def test_repeated_save_is_byte_stable_and_atomically_overwrites(
    tmp_path,
    monkeypatch,
) -> None:
    result = run_result()
    replaced_from = []
    fsynced = []
    real_replace = os.replace
    real_fsync = os.fsync

    def record_replace(source, destination) -> None:
        replaced_from.append(source)
        real_replace(source, destination)

    def record_fsync(file_descriptor) -> None:
        fsynced.append(file_descriptor)
        real_fsync(file_descriptor)

    monkeypatch.setattr(os, "replace", record_replace)
    monkeypatch.setattr(os, "fsync", record_fsync)

    store = JsonTraceStore(tmp_path)
    path = store.save(result)
    first_bytes = path.read_bytes()
    path.write_text("stale trace", encoding="utf-8")

    overwritten_path = store.save(result)

    assert overwritten_path == path
    assert overwritten_path.read_bytes() == first_bytes
    assert len(fsynced) == 2
    assert len(replaced_from) == 2
    assert replaced_from[0] != replaced_from[1]
    assert all(source.parent == tmp_path for source in replaced_from)
    assert list(tmp_path.iterdir()) == [path]


def test_replace_failure_preserves_destination_and_cleans_up_temp_file(
    tmp_path,
    monkeypatch,
) -> None:
    result = run_result()
    store = JsonTraceStore(tmp_path)
    path = store.save(result)
    original_bytes = path.read_bytes()
    replacement = result.model_copy(update={"stopped_reason": "replacement"})

    def fail_replace(source, destination) -> None:
        raise OSError("replace failed")

    monkeypatch.setattr(os, "replace", fail_replace)

    with pytest.raises(OSError, match="replace failed"):
        store.save(replacement)

    assert path.read_bytes() == original_bytes
    assert list(tmp_path.iterdir()) == [path]
