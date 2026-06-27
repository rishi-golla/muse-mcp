import pytest
from pydantic import SecretStr, ValidationError

from creativity_layer.live_search_config import (
    BraveSearchCredentials,
    ExaSearchCredentials,
    LiveSearchRuntime,
    OpenAIWebSearchConfig,
    SearchProviderError,
)


def test_exa_credentials_from_environment_strip_and_hide_secret(monkeypatch) -> None:
    monkeypatch.setenv("EXA_API_KEY", " exa-secret ")

    credentials = ExaSearchCredentials.from_environment()

    assert credentials.api_key.get_secret_value() == "exa-secret"
    assert "exa-secret" not in credentials.model_dump_json()


@pytest.mark.parametrize("value", [None, "  "])
def test_exa_credentials_reject_missing_or_blank_environment(monkeypatch, value) -> None:
    if value is None:
        monkeypatch.delenv("EXA_API_KEY", raising=False)
    else:
        monkeypatch.setenv("EXA_API_KEY", value)

    with pytest.raises(ValueError, match="EXA_API_KEY"):
        ExaSearchCredentials.from_environment()


def test_brave_credentials_from_environment_strip_and_hide_secret(monkeypatch) -> None:
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", " brave-secret ")

    credentials = BraveSearchCredentials.from_environment()

    assert credentials.api_key.get_secret_value() == "brave-secret"
    assert "brave-secret" not in credentials.model_dump_json()


def test_brave_credentials_reject_missing_environment(monkeypatch) -> None:
    monkeypatch.delenv("BRAVE_SEARCH_API_KEY", raising=False)

    with pytest.raises(ValueError, match="BRAVE_SEARCH_API_KEY"):
        BraveSearchCredentials.from_environment()


def test_openai_web_search_config_requires_explicit_model() -> None:
    with pytest.raises(ValidationError):
        OpenAIWebSearchConfig(model="")


def test_openai_web_search_config_from_environment_strip_model(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_WEB_SEARCH_MODEL", " gpt-test-search ")

    config = OpenAIWebSearchConfig.from_environment()

    assert config.model == "gpt-test-search"


def test_openai_web_search_config_rejects_missing_environment(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_WEB_SEARCH_MODEL", raising=False)

    with pytest.raises(ValueError, match="OPENAI_WEB_SEARCH_MODEL"):
        OpenAIWebSearchConfig.from_environment()


def test_runtime_defaults_are_conservative() -> None:
    runtime = LiveSearchRuntime()

    assert runtime.timeout_seconds == 10.0
    assert runtime.max_results == 10
    assert runtime.snippet_chars == 500


def test_runtime_rejects_unbounded_values() -> None:
    with pytest.raises(ValidationError):
        LiveSearchRuntime(timeout_seconds=0)
    with pytest.raises(ValidationError):
        LiveSearchRuntime(max_results=11)
    with pytest.raises(ValidationError):
        LiveSearchRuntime(snippet_chars=79)


def test_search_provider_error_redacts_secret_values() -> None:
    error = SearchProviderError(
        provider="exa",
        category="network_error",
        message="request failed with exa-secret",
        secret_values=("exa-secret",),
    )

    assert "exa-secret" not in str(error)
    assert "[REDACTED]" in str(error)


def test_credentials_accept_secretstr_without_exposing_value() -> None:
    credentials = ExaSearchCredentials(api_key=SecretStr("exa-secret"))

    assert credentials.api_key.get_secret_value() == "exa-secret"
    assert "exa-secret" not in repr(credentials)
