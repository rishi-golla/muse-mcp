import pytest
from pydantic import SecretStr, ValidationError

from creativity_layer.live_config import LiveModelConfig, OpenAICredentials, PrivacyMode


def test_credentials_from_environment_strips_api_key(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "  sk-secret-value \n")

    credentials = OpenAICredentials.from_environment()

    assert credentials.api_key.get_secret_value() == "sk-secret-value"


def test_credentials_from_environment_rejects_missing_api_key(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(
        ValueError,
        match="OPENAI_API_KEY is required for live OpenAI runs",
    ):
        OpenAICredentials.from_environment()


def test_credentials_from_environment_rejects_whitespace_api_key(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", " \t\n ")

    with pytest.raises(
        ValueError,
        match="OPENAI_API_KEY is required for live OpenAI runs",
    ):
        OpenAICredentials.from_environment()


def test_credentials_from_environment_reads_each_call_independently(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "first-key")
    first = OpenAICredentials.from_environment()
    monkeypatch.setenv("OPENAI_API_KEY", "second-key")

    second = OpenAICredentials.from_environment()

    assert first.api_key.get_secret_value() == "first-key"
    assert second.api_key.get_secret_value() == "second-key"


def test_credentials_mask_secret_in_all_standard_representations() -> None:
    raw_secret = "sk-secret-value"
    credentials = OpenAICredentials(api_key=SecretStr(raw_secret))

    python_dump = credentials.model_dump()
    representations = (
        str(credentials),
        repr(credentials),
        credentials.model_dump_json(),
        str(python_dump),
        repr(python_dump),
        str(credentials.api_key),
        repr(credentials.api_key),
    )

    assert all(raw_secret not in representation for representation in representations)
    assert credentials.api_key.get_secret_value() == raw_secret


@pytest.mark.parametrize(
    "model_identifier",
    (
        "provider/model",
        "model.1",
        "model-1",
        "model:preview",
        "model_name",
        "Provider_2/model-1.2:preview",
    ),
)
def test_live_model_config_accepts_model_identifier_punctuation(
    model_identifier: str,
) -> None:
    config = LiveModelConfig(
        economy_model=model_identifier,
        strong_model=model_identifier,
        embedding_model=model_identifier,
    )

    assert config.economy_model == model_identifier
    assert config.strong_model == model_identifier
    assert config.embedding_model == model_identifier


@pytest.mark.parametrize("field", ("economy_model", "strong_model", "embedding_model"))
@pytest.mark.parametrize(
    "invalid_identifier",
    (
        "",
        " ",
        "\tmodel",
        "model ",
        "model name",
        "model\u00a0name",
        "model\u200bname",
        "model\u202ename",
        "model\nname",
        "model\x00name",
        "model\x7fname",
        "model\u0085name",
    ),
)
def test_live_model_config_rejects_invalid_model_identifiers(
    field: str,
    invalid_identifier: str,
) -> None:
    values = {
        "economy_model": "economy-model",
        "strong_model": "strong-model",
        "embedding_model": "embedding-model",
    }
    values[field] = invalid_identifier

    with pytest.raises(ValidationError):
        LiveModelConfig(**values)


def test_live_model_config_from_environment_reads_models(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_ECONOMY_MODEL", "provider/economy-1.2:preview")
    monkeypatch.setenv("OPENAI_STRONG_MODEL", "provider/strong-2.0:stable")
    monkeypatch.setenv("OPENAI_EMBEDDING_MODEL", "provider/embed-3.0:small")

    config = LiveModelConfig.from_environment()

    assert config.economy_model == "provider/economy-1.2:preview"
    assert config.strong_model == "provider/strong-2.0:stable"
    assert config.embedding_model == "provider/embed-3.0:small"


@pytest.mark.parametrize("missing_name", ("OPENAI_ECONOMY_MODEL", "OPENAI_STRONG_MODEL"))
def test_live_model_config_from_environment_rejects_missing_text_model(
    monkeypatch,
    missing_name: str,
) -> None:
    monkeypatch.setenv("OPENAI_ECONOMY_MODEL", "economy-model")
    monkeypatch.setenv("OPENAI_STRONG_MODEL", "strong-model")
    monkeypatch.delenv(missing_name, raising=False)

    with pytest.raises(
        ValueError,
        match="OPENAI_ECONOMY_MODEL and OPENAI_STRONG_MODEL are required",
    ):
        LiveModelConfig.from_environment()


@pytest.mark.parametrize("name", ("OPENAI_ECONOMY_MODEL", "OPENAI_STRONG_MODEL"))
def test_live_model_config_from_environment_rejects_whitespace_text_model(
    monkeypatch,
    name: str,
) -> None:
    monkeypatch.setenv("OPENAI_ECONOMY_MODEL", "economy-model")
    monkeypatch.setenv("OPENAI_STRONG_MODEL", "strong-model")
    monkeypatch.setenv(name, " \t ")

    with pytest.raises(ValueError):
        LiveModelConfig.from_environment()


def test_live_model_config_from_environment_rejects_control_characters(
    monkeypatch,
) -> None:
    monkeypatch.setenv("OPENAI_ECONOMY_MODEL", "economy\nmodel")
    monkeypatch.setenv("OPENAI_STRONG_MODEL", "strong-model")

    with pytest.raises(ValidationError):
        LiveModelConfig.from_environment()


def test_live_model_config_from_environment_defaults_embedding_model(
    monkeypatch,
) -> None:
    monkeypatch.setenv("OPENAI_ECONOMY_MODEL", "economy-model")
    monkeypatch.setenv("OPENAI_STRONG_MODEL", "strong-model")
    monkeypatch.delenv("OPENAI_EMBEDDING_MODEL", raising=False)

    config = LiveModelConfig.from_environment()

    assert config.embedding_model == "text-embedding-3-small"


def test_live_model_config_from_environment_reads_each_call_independently(
    monkeypatch,
) -> None:
    monkeypatch.setenv("OPENAI_ECONOMY_MODEL", "economy-one")
    monkeypatch.setenv("OPENAI_STRONG_MODEL", "strong-one")
    first = LiveModelConfig.from_environment()
    monkeypatch.setenv("OPENAI_ECONOMY_MODEL", "economy-two")
    monkeypatch.setenv("OPENAI_STRONG_MODEL", "strong-two")

    second = LiveModelConfig.from_environment()

    assert first.economy_model == "economy-one"
    assert first.strong_model == "strong-one"
    assert second.economy_model == "economy-two"
    assert second.strong_model == "strong-two"


def test_live_model_config_defaults_budget_and_privacy() -> None:
    config = LiveModelConfig(
        economy_model="economy-test-model",
        strong_model="strong-test-model",
    )

    assert config.default_budget_usd == 0.10
    assert config.privacy_mode is PrivacyMode.RESEARCH


def test_live_configuration_is_frozen_and_forbids_extra_fields() -> None:
    config = LiveModelConfig(
        economy_model="economy-model",
        strong_model="strong-model",
    )

    with pytest.raises(ValidationError):
        config.max_retries = 3
    with pytest.raises(ValidationError):
        LiveModelConfig(
            economy_model="economy-model",
            strong_model="strong-model",
            unknown_option=True,
        )


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    (
        ("default_budget_usd", "0.10"),
        ("timeout_seconds", "30.0"),
        ("max_retries", 1.0),
        ("repair_attempts", True),
        ("circuit_failure_threshold", "3"),
        ("default_budget_usd", 0.0),
        ("timeout_seconds", 0.0),
        ("max_retries", -1),
        ("max_retries", 6),
        ("repair_attempts", -1),
        ("repair_attempts", 3),
        ("circuit_failure_threshold", 0),
    ),
)
def test_live_model_config_rejects_invalid_numeric_settings(
    field: str,
    invalid_value: object,
) -> None:
    values = {
        "economy_model": "economy-model",
        "strong_model": "strong-model",
        field: invalid_value,
    }

    with pytest.raises(ValidationError):
        LiveModelConfig(**values)


@pytest.mark.parametrize("field", ("default_budget_usd", "timeout_seconds"))
@pytest.mark.parametrize("invalid_value", (float("nan"), float("inf"), float("-inf")))
def test_live_model_config_rejects_non_finite_numeric_settings(
    field: str,
    invalid_value: float,
) -> None:
    values = {
        "economy_model": "economy-model",
        "strong_model": "strong-model",
        field: invalid_value,
    }

    with pytest.raises(ValidationError):
        LiveModelConfig(**values)
