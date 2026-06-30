from creativity_layer.live_config import PrivacyMode
from creativity_layer.privacy import TraceView


def test_research_trace_keeps_prompts_but_never_secrets() -> None:
    view = TraceView(
        mode=PrivacyMode.RESEARCH,
        secret_values=("sk-secret",),
    )

    payload = view.sanitize(
        {
            "prompt": "Create an idea using sk-secret",
            "authorization": "Bearer sk-secret",
        }
    )

    assert payload["prompt"] == "Create an idea using [REDACTED]"
    assert payload["authorization"] == "[REDACTED]"


def test_research_trace_redacts_secret_shaped_text_without_exact_secret_value() -> None:
    view = TraceView(mode=PrivacyMode.RESEARCH, secret_values=())

    payload = view.sanitize(
        {
            "goal": "Use sk-abcdefghijklmnopqrstuvwxyz123456 in a mock task",
            "error": "Provider returned Bearer sk-othersecret123456",
            "lowercase": "provider returned bearer sk-lowersecret123456",
        }
    )

    assert payload["goal"] == "Use [REDACTED] in a mock task"
    assert payload["error"] == "Provider returned [REDACTED]"
    assert payload["lowercase"] == "provider returned [REDACTED]"


def test_private_trace_hashes_prompt_content() -> None:
    view = TraceView(mode=PrivacyMode.PRIVATE, secret_values=())

    payload = view.sanitize({"prompt": "private task", "output": "private idea"})

    assert payload["prompt"] != "private task"
    assert payload["prompt"]["sha256"]
    assert payload["output"]["sha256"]


def test_private_trace_hashes_source_snippets_and_excerpts() -> None:
    view = TraceView(mode=PrivacyMode.PRIVATE, secret_values=())

    payload = view.sanitize(
        {
            "search_results": [
                {
                    "url": "https://example.com/source",
                    "snippet": "Private source snippet",
                    "bounded_excerpt": "Private bounded excerpt",
                    "boundedExcerpt": "Private camel excerpt",
                }
            ]
        }
    )

    result = payload["search_results"][0]
    assert result["url"] == "https://example.com/source"
    assert result["snippet"]["sha256"]
    assert result["snippet"]["length"] == len("Private source snippet")
    assert result["bounded_excerpt"]["sha256"]
    assert result["bounded_excerpt"]["length"] == len("Private bounded excerpt")
    assert result["boundedExcerpt"]["sha256"]
    assert result["boundedExcerpt"]["length"] == len("Private camel excerpt")


def test_private_trace_hashes_context_bundle_text() -> None:
    view = TraceView(mode=PrivacyMode.PRIVATE, secret_values=())

    payload = view.sanitize(
        {
            "context_bundle": {
                "snippets": [
                    {
                        "source": "repo/private-package-graph",
                        "title": "Private package graph",
                        "content": "apps/secret depends on packages/internal",
                        "metadata": {"branch": "secret-feature"},
                        "sensitivity": "private",
                    }
                ],
                "tags": ["typescript", "monorepo"],
            }
        }
    )

    snippet = payload["context_bundle"]["snippets"][0]
    assert snippet["source"]["sha256"]
    assert snippet["title"]["sha256"]
    assert snippet["content"]["sha256"]
    assert snippet["metadata"]["branch"]["sha256"]
    assert snippet["sensitivity"] == "private"
    assert payload["context_bundle"]["tags"][0]["sha256"]


def test_sanitize_removes_secrets_from_nested_errors_and_provider_metadata() -> None:
    view = TraceView(mode=PrivacyMode.RESEARCH, secret_values=("sk-secret",))

    payload = view.sanitize(
        {
            "errors": [
                {
                    "message": "Provider returned sk-secret",
                    "details": {"password": "sk-secret"},
                }
            ],
            "provider_metadata": {
                "headers": {"api_key": "sk-secret"},
                "raw": "metadata sk-secret",
            },
        }
    )

    assert payload["errors"][0]["message"] == "Provider returned [REDACTED]"
    assert payload["errors"][0]["details"]["password"] == "[REDACTED]"
    assert payload["provider_metadata"]["headers"]["api_key"] == "[REDACTED]"
    assert payload["provider_metadata"]["raw"] == "metadata [REDACTED]"


def test_sanitize_redacts_compound_secret_key_variants() -> None:
    view = TraceView(mode=PrivacyMode.RESEARCH, secret_values=())

    payload = view.sanitize(
        {
            "access_token": "access-secret",
            "refresh_token": "refresh-secret",
            "client_secret": "client-secret",
            "x-api-key": "api-secret",
            "bearer_token": "bearer-secret",
            "auth_header": "auth-secret",
            "cached_tokens": 7,
            "completion_tokens": 9,
            "token_count": 42,
            "input_tokens": 12,
            "input_tokens_details": {"cached_tokens": 7},
        }
    )

    assert payload["access_token"] == "[REDACTED]"
    assert payload["refresh_token"] == "[REDACTED]"
    assert payload["client_secret"] == "[REDACTED]"
    assert payload["x-api-key"] == "[REDACTED]"
    assert payload["bearer_token"] == "[REDACTED]"
    assert payload["auth_header"] == "[REDACTED]"
    assert payload["cached_tokens"] == 7
    assert payload["completion_tokens"] == 9
    assert payload["token_count"] == 42
    assert payload["input_tokens"] == 12
    assert payload["input_tokens_details"] == {"cached_tokens": 7}


def test_sanitize_does_not_mutate_original_payload() -> None:
    view = TraceView(mode=PrivacyMode.PRIVATE, secret_values=("sk-secret",))
    original = {
        "prompt": "private sk-secret",
        "metadata": {"authorization": "Bearer sk-secret"},
    }

    sanitized = view.sanitize(original)

    assert original == {
        "prompt": "private sk-secret",
        "metadata": {"authorization": "Bearer sk-secret"},
    }
    assert sanitized["prompt"]["sha256"]
    assert sanitized["metadata"]["authorization"] == "[REDACTED]"
