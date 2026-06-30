import json
from pathlib import Path

import pytest
from pydantic import SecretStr

import creativity_layer.cli as cli_module
from creativity_layer.cli import run_cli
from creativity_layer.models import (
    EvaluationScores,
    FramedTask,
    IdeaGenome,
    OperationTrace,
    TaskContext,
    TokenUsage,
)
from creativity_layer.pricing import ModelPrice
from creativity_layer.providers import MeteredResponse, OperationQuote
from creativity_layer.transforms import (
    TransformationRequest,
    expected_transformation_history,
)


def test_live_command_requires_openai_configuration(monkeypatch, capsys) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_ECONOMY_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_STRONG_MODEL", raising=False)

    exit_code = run_cli(["live", "Invent a new coordination mechanism"])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "OPENAI_API_KEY" in captured.err
    assert captured.out == ""


def test_existing_command_defaults_to_deterministic_mode(tmp_path, capsys) -> None:
    exit_code = run_cli(
        [
            "Invent a calmer process",
            "--trace-dir",
            str(tmp_path),
            "--seed-count",
            "2",
            "--finalist-count",
            "1",
        ]
    )
    assert exit_code == 0


class FakeLiveProvider:
    name = "openai"
    version = "fake-live"

    def __init__(
        self,
        *,
        config,
        leaked_secret: str | None = None,
        fail_frame: bool = False,
    ) -> None:
        self._config = config
        self._leaked_secret = leaked_secret
        self._fail_frame = fail_frame

    def quote_frame(self, _task: TaskContext) -> OperationQuote:
        return OperationQuote(max_cost_usd=0.001)

    def frame(self, task: TaskContext) -> MeteredResponse[FramedTask]:
        if self._fail_frame:
            raise RuntimeError("boom")
        return self._metered(
            operation="frame",
            role="economy",
            model=self._config.economy_model,
            value=FramedTask(
                context=task,
                assumptions=(f"Assumption for {task.goal}",),
                obvious_solution=f"Obvious answer for {task.goal}",
            ),
        )

    def quote_seed(self, _framed_task: FramedTask, _config) -> OperationQuote:
        return OperationQuote(max_cost_usd=0.001)

    def seed(self, framed_task: FramedTask, config) -> MeteredResponse[tuple[IdeaGenome, ...]]:
        candidates = tuple(
            IdeaGenome(
                generation=0,
                title=self._leaked_secret or f"Seed {index} for {framed_task.context.goal}",
                core_mechanism=f"Mechanism for {framed_task.context.goal}",
                problem_framing=f"Framing for {framed_task.context.goal}",
                task_value=f"Value for {framed_task.context.goal}",
            )
            for index in range(config.seed_count)
        )
        return self._metered(
            operation="seed",
            role="economy",
            model=self._config.economy_model,
            value=candidates,
        )

    def quote_transform(
        self,
        _request: TransformationRequest,
        _parents: tuple[IdeaGenome, ...],
    ) -> OperationQuote:
        return OperationQuote(max_cost_usd=0.001)

    def transform(
        self,
        request: TransformationRequest,
        parents: tuple[IdeaGenome, ...],
    ) -> MeteredResponse[IdeaGenome]:
        parent = parents[0]
        transformed = IdeaGenome(
            generation=parent.generation + 1,
            title=f"Transformed {request.operator.value}",
            core_mechanism="Strong model mechanism",
            problem_framing="Strong model framing",
            task_value="Strong model value",
            parent_ids=request.parent_ids,
            transformations=expected_transformation_history(request.operator, parents),
        )
        return self._metered(
            operation="transform",
            role="strong",
            model=self._config.strong_model,
            value=transformed,
        )

    def quote_evaluation(self, _framed_task: FramedTask) -> OperationQuote:
        return OperationQuote(max_cost_usd=0.001)

    def evaluate(
        self,
        _candidate: IdeaGenome,
        _framed_task: FramedTask,
    ) -> MeteredResponse[EvaluationScores]:
        return self._metered(
            operation="evaluate",
            role="economy",
            model=self._config.economy_model,
            value=EvaluationScores(
                originality=0.8,
                usefulness=0.7,
                coherence=0.9,
                feasibility=0.6,
                user_fit=0.75,
            ),
        )

    def _metered(self, *, operation: str, role: str, model: str, value):
        return MeteredResponse(
            value=value,
            provider=self.name,
            model=model,
            cost_usd=0.0,
            latency_ms=1,
            usage=TokenUsage(input_tokens=1, output_tokens=1),
            pricing_version="test-pricing",
            operation_trace=OperationTrace.from_payload(
                request={
                    "operation": operation,
                    "model_role": role,
                    "model": model,
                    "content": f"{operation} request",
                },
                response={
                    "parsed": {
                        "operation": operation,
                        "model": model,
                    }
                },
            ),
        )


def write_pricing_file(tmp_path: Path) -> Path:
    path = tmp_path / "pricing.json"
    path.write_text(
        json.dumps(
            {
                "version": "test-pricing",
                "models": {
                    "env-economy": {
                        "input_per_million": 1.0,
                        "cached_input_per_million": 0.1,
                        "output_per_million": 2.0,
                    },
                    "env-strong": {
                        "input_per_million": 3.0,
                        "cached_input_per_million": 0.3,
                        "output_per_million": 4.0,
                    },
                    "cli-economy": {
                        "input_per_million": 1.0,
                        "cached_input_per_million": 0.1,
                        "output_per_million": 2.0,
                    },
                    "cli-strong": {
                        "input_per_million": 3.0,
                        "cached_input_per_million": 0.3,
                        "output_per_million": 4.0,
                    },
                },
                "embeddings": {
                    "text-embedding-3-small": {
                        "input_per_million": 0.02,
                    },
                    "cli-embedding": {
                        "input_per_million": 0.03,
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    return path


def configure_live(
    monkeypatch,
    tmp_path: Path,
    *,
    api_key: str = "sk-test-live-cli-1234567890",
    leaked_secret: str | None = None,
    fail_frame: bool = False,
) -> dict[str, object]:
    captured: dict[str, object] = {}
    monkeypatch.setenv("OPENAI_API_KEY", api_key)
    monkeypatch.setenv("OPENAI_ECONOMY_MODEL", "env-economy")
    monkeypatch.setenv("OPENAI_STRONG_MODEL", "env-strong")
    monkeypatch.setenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
    monkeypatch.setenv("OPENAI_PRICING_FILE", str(write_pricing_file(tmp_path)))

    def build_provider(*, credentials, config, pricing):
        captured["credentials"] = credentials
        captured["config"] = config
        captured["pricing"] = pricing
        return FakeLiveProvider(
            config=config,
            leaked_secret=leaked_secret,
            fail_frame=fail_frame,
        )

    monkeypatch.setattr(cli_module, "_build_openai_provider", build_provider, raising=False)
    return captured


def trace_payload_from_summary(stdout: str) -> dict[str, object]:
    summary = json.loads(stdout)
    return json.loads(Path(summary["trace_path"]).read_text(encoding="utf-8"))


def test_live_uses_default_ten_cent_hard_ceiling(monkeypatch, tmp_path, capsys) -> None:
    configure_live(monkeypatch, tmp_path)

    exit_code = run_cli(
        [
            "live",
            "Invent a low-cost coordination mechanism",
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
    trace = trace_payload_from_summary(captured.out)

    assert exit_code == 0
    assert trace["config"]["max_cost_usd"] == 0.10
    assert captured.err == ""


def test_live_cli_model_flags_enter_trace_operation_metadata(
    monkeypatch,
    tmp_path,
    capsys,
) -> None:
    captured_config = configure_live(monkeypatch, tmp_path)

    exit_code = run_cli(
        [
            "live",
            "Invent a model-routed mechanism",
            "--trace-dir",
            str(tmp_path / "traces"),
            "--seed-count",
            "2",
            "--finalist-count",
            "1",
            "--generations",
            "1",
            "--economy-model",
            "cli-economy",
            "--strong-model",
            "cli-strong",
            "--embedding-model",
            "cli-embedding",
        ]
    )

    output = capsys.readouterr()
    trace = trace_payload_from_summary(output.out)
    spend_models = {record["model"] for record in trace["spend_records"]}
    request_models = {
        record["operation_trace"]["request"]["model"]
        for record in trace["spend_records"]
        if record["operation_trace"] is not None
    }

    assert exit_code == 0
    assert captured_config["config"].economy_model == "cli-economy"
    assert captured_config["config"].strong_model == "cli-strong"
    assert captured_config["config"].embedding_model == "cli-embedding"
    assert {"cli-economy", "cli-strong"} <= spend_models
    assert {"cli-economy", "cli-strong"} <= request_models
    assert output.err == ""


def test_live_cli_context_file_enters_trace(
    monkeypatch,
    tmp_path,
    capsys,
) -> None:
    configure_live(monkeypatch, tmp_path)
    context_path = tmp_path / "context.json"
    context_path.write_text(
        json.dumps(
            {
                "snippets": [
                    {
                        "source": "repo/ci-snapshot",
                        "content": "affected packages, tsc, Jest, and CI logs",
                    }
                ],
                "tags": ["typescript", "monorepo"],
            }
        ),
        encoding="utf-8",
    )

    exit_code = run_cli(
        [
            "live",
            "Invent a context-grounded workflow",
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

    output = capsys.readouterr()
    trace = trace_payload_from_summary(output.out)

    assert exit_code == 0
    assert trace["framed_task"]["context"]["context_bundle"]["snippets"][0][
        "source"
    ] == "repo/ci-snapshot"
    assert trace["framed_task"]["context"]["context_bundle"]["tags"] == [
        "typescript",
        "monorepo",
    ]
    assert output.err == ""


def test_live_privacy_private_writes_no_raw_goal_text(
    monkeypatch,
    tmp_path,
    capsys,
) -> None:
    configure_live(monkeypatch, tmp_path)
    goal = "Invent a private high-context coordination mechanism"

    exit_code = run_cli(
        [
            "live",
            goal,
            "--trace-dir",
            str(tmp_path / "traces"),
            "--seed-count",
            "2",
            "--finalist-count",
            "1",
            "--generations",
            "0",
            "--privacy",
            "private",
        ]
    )

    output = capsys.readouterr()
    summary = json.loads(output.out)
    raw_trace = Path(summary["trace_path"]).read_text(encoding="utf-8")
    trace = json.loads(raw_trace)

    assert exit_code == 0
    assert goal not in raw_trace
    assert trace["framed_task"]["context"]["goal"]["sha256"]
    assert output.err == ""


def test_live_provider_errors_return_one_and_write_trace(
    monkeypatch,
    tmp_path,
    capsys,
) -> None:
    configure_live(monkeypatch, tmp_path, fail_frame=True)

    exit_code = run_cli(
        [
            "live",
            "Invent a resilient mechanism",
            "--trace-dir",
            str(tmp_path / "traces"),
            "--seed-count",
            "2",
            "--finalist-count",
            "1",
        ]
    )

    output = capsys.readouterr()
    summary = json.loads(output.out)
    trace_path = Path(summary["trace_path"])
    trace = json.loads(trace_path.read_text(encoding="utf-8"))

    assert exit_code == 1
    assert summary["stopped_reason"] == "provider_error"
    assert trace_path.exists()
    assert trace["stopped_reason"] == "provider_error"
    assert output.err == ""


@pytest.mark.parametrize(
    ("pricing_value", "expected_message"),
    [
        (None, "OPENAI_PRICING_FILE"),
        ("not-json", "pricing"),
    ],
)
def test_live_pricing_config_errors_return_two_without_traceback(
    monkeypatch,
    tmp_path,
    capsys,
    pricing_value,
    expected_message,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-live-cli-1234567890")
    monkeypatch.setenv("OPENAI_ECONOMY_MODEL", "env-economy")
    monkeypatch.setenv("OPENAI_STRONG_MODEL", "env-strong")
    monkeypatch.delenv("OPENAI_PRICING_FILE", raising=False)
    if pricing_value is not None:
        path = tmp_path / "pricing.json"
        path.write_text(pricing_value, encoding="utf-8")
        monkeypatch.setenv("OPENAI_PRICING_FILE", str(path))

    exit_code = run_cli(["live", "Invent a priced mechanism"])

    output = capsys.readouterr()

    assert exit_code == 2
    assert output.out == ""
    assert expected_message in output.err
    assert "Traceback" not in output.err


def test_live_missing_selected_model_pricing_returns_two_without_trace(
    monkeypatch,
    tmp_path,
    capsys,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-live-cli-1234567890")
    monkeypatch.setenv("OPENAI_ECONOMY_MODEL", "missing-economy")
    monkeypatch.setenv("OPENAI_STRONG_MODEL", "env-strong")
    monkeypatch.setenv("OPENAI_PRICING_FILE", str(write_pricing_file(tmp_path)))

    exit_code = run_cli(
        [
            "live",
            "Invent a priced mechanism",
            "--trace-dir",
            str(tmp_path / "traces"),
        ]
    )

    output = capsys.readouterr()

    assert exit_code == 2
    assert output.out == ""
    assert "no pricing configured for model: missing-economy" in output.err
    assert not (tmp_path / "traces").exists()
    assert "Traceback" not in output.err


def test_openai_provider_factory_disables_sdk_retries_and_wires_local_reliability(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeOpenAI:
        def __init__(self, **kwargs: object) -> None:
            captured["openai_kwargs"] = kwargs

    class FakeProvider:
        def __init__(self, **kwargs: object) -> None:
            captured["provider_kwargs"] = kwargs

    monkeypatch.setattr(cli_module, "OpenAI", FakeOpenAI)
    monkeypatch.setattr(cli_module, "OpenAICreativeProvider", FakeProvider)
    credentials = cli_module.OpenAICredentials(
        api_key=SecretStr("sk-test-live-cli-1234567890")
    )
    config = cli_module.LiveModelConfig(
        economy_model="env-economy",
        strong_model="env-strong",
        timeout_seconds=12.5,
        max_retries=3,
        circuit_failure_threshold=4,
    )
    pricing = cli_module.PricingTable(
        version="test-pricing",
        models={
            "env-economy": ModelPrice(
                input_per_million=1.0,
                cached_input_per_million=0.1,
                output_per_million=2.0,
            ),
            "env-strong": ModelPrice(
                input_per_million=3.0,
                cached_input_per_million=0.3,
                output_per_million=4.0,
            ),
        },
    )

    provider = cli_module._build_openai_provider(
        credentials=credentials,
        config=config,
        pricing=pricing,
    )

    openai_kwargs = captured["openai_kwargs"]
    provider_kwargs = captured["provider_kwargs"]
    assert provider is not None
    assert openai_kwargs["api_key"] == "sk-test-live-cli-1234567890"
    assert openai_kwargs["timeout"] == 12.5
    assert openai_kwargs["max_retries"] == 0
    assert provider_kwargs["pricing"] is pricing
    assert provider_kwargs["retry_policy"].max_retries == 3
    assert provider_kwargs["breaker"]._failure_threshold == 4


def test_live_api_key_never_appears_in_output_or_traces(
    monkeypatch,
    tmp_path,
    capsys,
) -> None:
    api_key = "sk-live-cli-secret-1234567890"
    configure_live(
        monkeypatch,
        tmp_path,
        api_key=api_key,
        leaked_secret=api_key,
    )

    exit_code = run_cli(
        [
            "live",
            "Invent a secret-safe mechanism",
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

    output = capsys.readouterr()
    summary = json.loads(output.out)
    raw_trace = Path(summary["trace_path"]).read_text(encoding="utf-8")

    assert exit_code == 0
    assert api_key not in output.out
    assert api_key not in output.err
    assert api_key not in raw_trace
