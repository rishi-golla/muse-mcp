import json
import os
from uuid import uuid4

import pytest

from creativity_layer.live_config import PrivacyMode
from creativity_layer.models import (
    ContextBundle,
    ContextSnippet,
    FramedTask,
    IdeaGenome,
    OperationTrace,
    ProviderIdentity,
    RunConfig,
    RunProviders,
    RunResult,
    SpendRecord,
    TaskContext,
    compute_reproducibility_fingerprint,
)
from creativity_layer.privacy import TraceView
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
            context=TaskContext(
                goal="Test creativity",
                audience="Sensitive audience",
                constraints=("Sensitive constraint",),
                preferences=("Sensitive preference",),
            ),
            assumptions=("Obvious assumption",),
            obvious_solution="Obvious answer",
        ),
        finalists=(candidate,),
        all_candidates=(candidate,),
        spend_records=(
            SpendRecord(
                stage="seed",
                provider="local",
                cost_usd=0.01,
                latency_ms=1,
                operation_trace=OperationTrace.from_payload(
                    request={
                        "model": "economy-model",
                        "input": [
                            {
                                "role": "user",
                                "content": "Trace prompt for Test creativity",
                            }
                        ],
                    },
                    response={
                        "parsed": {
                            "obvious_solution": "Trace output for Test creativity",
                        },
                        "refusal": "Refused because Test creativity is private",
                        "usage": {"input_tokens": 10},
                    },
                ),
            ),
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


def test_private_trace_store_file_does_not_contain_original_task_goal(tmp_path) -> None:
    result = run_result()
    view = TraceView(mode=PrivacyMode.PRIVATE, secret_values=())

    path = JsonTraceStore(tmp_path, trace_view=view).save(result)
    raw_trace = path.read_text(encoding="utf-8")
    payload = json.loads(raw_trace)

    assert "Test creativity" not in raw_trace
    assert "Trace prompt for Test creativity" not in raw_trace
    assert "Trace output for Test creativity" not in raw_trace
    assert "Refused because Test creativity is private" not in raw_trace
    assert "Idea" not in raw_trace
    assert "Mechanism" not in raw_trace
    assert "Framing" not in raw_trace
    assert "Value" not in raw_trace
    assert "Sensitive audience" not in raw_trace
    assert "Sensitive constraint" not in raw_trace
    assert "Sensitive preference" not in raw_trace
    assert "Obvious assumption" not in raw_trace
    assert "Obvious answer" not in raw_trace
    assert payload["framed_task"]["context"]["goal"]["sha256"]
    assert payload["framed_task"]["context"]["audience"]["sha256"]
    assert payload["framed_task"]["context"]["constraints"][0]["sha256"]
    assert payload["framed_task"]["context"]["preferences"][0]["sha256"]
    assert payload["framed_task"]["assumptions"][0]["sha256"]
    assert payload["framed_task"]["obvious_solution"]["sha256"]
    assert payload["finalists"][0]["title"]["sha256"]
    assert payload["finalists"][0]["core_mechanism"]["sha256"]
    assert payload["finalists"][0]["problem_framing"]["sha256"]
    assert payload["finalists"][0]["task_value"]["sha256"]
    trace = payload["spend_records"][0]["operation_trace"]
    assert trace["request"]["input"][0]["content"]["sha256"]
    assert trace["response"]["parsed"]["obvious_solution"]["sha256"]
    assert trace["response"]["refusal"]["sha256"]
    assert payload["framed_task"]["context"]["goal"]["length"] == len("Test creativity")


def test_private_trace_store_hashes_search_source_snippets(tmp_path) -> None:
    result = run_result()
    search_trace = OperationTrace.from_payload(
        request={"operation": "search", "provider": "deterministic-search"},
        response={
            "search_results": [
                {
                    "url": "https://example.com/source",
                    "snippet": "Trace source snippet",
                    "bounded_excerpt": "Trace bounded excerpt",
                }
            ]
        },
    )
    search_record = result.spend_records[0].model_copy(
        update={"operation_trace": search_trace}
    )
    result = result.model_copy(update={"spend_records": (search_record,)})
    view = TraceView(mode=PrivacyMode.PRIVATE, secret_values=())

    path = JsonTraceStore(tmp_path, trace_view=view).save(result)
    raw_trace = path.read_text(encoding="utf-8")
    payload = json.loads(raw_trace)

    assert "Trace source snippet" not in raw_trace
    assert "Trace bounded excerpt" not in raw_trace
    search_result = payload["spend_records"][0]["operation_trace"]["response"][
        "search_results"
    ][0]
    assert search_result["url"] == "https://example.com/source"
    assert search_result["snippet"]["sha256"]
    assert search_result["bounded_excerpt"]["sha256"]


def test_private_trace_store_hashes_context_bundle(tmp_path) -> None:
    result = run_result()
    context = result.framed_task.context.model_copy(
        update={
            "context_bundle": ContextBundle(
                snippets=(
                    ContextSnippet(
                        source="repo/private-package-graph",
                        title="Private package graph",
                        content="apps/secret depends on packages/internal",
                        metadata={"branch": "secret-feature"},
                    ),
                ),
                tags=("typescript", "monorepo"),
            )
        }
    )
    result = result.model_copy(
        update={
            "framed_task": result.framed_task.model_copy(update={"context": context})
        }
    )
    view = TraceView(mode=PrivacyMode.PRIVATE, secret_values=())

    path = JsonTraceStore(tmp_path, trace_view=view).save(result)
    raw_trace = path.read_text(encoding="utf-8")
    payload = json.loads(raw_trace)

    assert "repo/private-package-graph" not in raw_trace
    assert "apps/secret" not in raw_trace
    assert "secret-feature" not in raw_trace
    bundle = payload["framed_task"]["context"]["context_bundle"]
    assert bundle["snippets"][0]["source"]["sha256"]
    assert bundle["snippets"][0]["content"]["sha256"]
    assert bundle["snippets"][0]["metadata"]["branch"]["sha256"]
    assert bundle["tags"][0]["sha256"]


def test_private_trace_store_does_not_mutate_run_result(tmp_path) -> None:
    result = run_result()
    before = result.model_dump(mode="json")
    view = TraceView(mode=PrivacyMode.PRIVATE, secret_values=())

    JsonTraceStore(tmp_path, trace_view=view).save(result)

    assert result.model_dump(mode="json") == before
    assert result.framed_task.context.goal == "Test creativity"


def test_run_fingerprint_uses_internal_canonical_run_not_private_trace_view(
    tmp_path,
) -> None:
    result = run_result()
    view = TraceView(mode=PrivacyMode.PRIVATE, secret_values=())

    path = JsonTraceStore(tmp_path, trace_view=view).save(result)
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["reproducibility_fingerprint"] == result.reproducibility_fingerprint
    assert result.reproducibility_fingerprint == compute_reproducibility_fingerprint(
        result
    )
