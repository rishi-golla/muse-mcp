import pytest
from pydantic import SecretStr, ValidationError

from creativity_layer.live_config import LiveModelConfig, OpenAICredentials, PrivacyMode


def test_live_model_config_requires_explicit_text_models() -> None:
    with pytest.raises(ValidationError):
        LiveModelConfig(economy_model="", strong_model="")


def test_live_model_config_defaults_embedding_model_and_budget() -> None:
    config = LiveModelConfig(
        economy_model="economy-test-model",
        strong_model="strong-test-model",
    )

    assert config.embedding_model == "text-embedding-3-small"
    assert config.default_budget_usd == 0.10
    assert config.privacy_mode is PrivacyMode.RESEARCH


def test_credentials_never_serialize_secret_value() -> None:
    credentials = OpenAICredentials(api_key=SecretStr("sk-secret-value"))

    dumped = credentials.model_dump_json()

    assert "sk-secret-value" not in dumped
    assert credentials.api_key.get_secret_value() == "sk-secret-value"
