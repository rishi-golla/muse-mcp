from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass

from creativity_layer.live_config import PrivacyMode

REDACTED = "[REDACTED]"
SECRET_VALUE_PATTERN = re.compile(
    r"(?:\bBearer\s+[A-Za-z0-9._~+/=-]+|\bsk-[A-Za-z0-9_-]{10,})",
    re.IGNORECASE,
)
SECRET_KEY_TERMS = frozenset(
    {
        "apikey",
        "authorization",
        "auth",
        "bearer",
        "cookie",
        "credential",
        "password",
        "privatekey",
        "secret",
        "token",
    }
)
TOKEN_METRIC_KEYS = frozenset(
    {
        "cachedinputtokens",
        "cachedtokens",
        "completiontokens",
        "inputtokensdetails",
        "inputtokens",
        "outputtokensdetails",
        "outputtokens",
        "prompttokens",
        "reasoningtokens",
        "tokencount",
        "totaltokens",
    }
)
PRIVATE_TEXT_KEYS = frozenset(
    {
        "assumptions",
        "assumptionschallenged",
        "audience",
        "constraints",
        "coremechanism",
        "distinguishingfeatures",
        "feasibilityassumptions",
        "firstordereffects",
        "goal",
        "obvioussolution",
        "output",
        "preferences",
        "problemframing",
        "prompt",
        "secondordereffects",
        "taskvalue",
        "title",
        "uncertainties",
        "weaknesses",
    }
)


@dataclass(frozen=True)
class TraceView:
    mode: PrivacyMode = PrivacyMode.RESEARCH
    secret_values: tuple[str, ...] = ()

    def sanitize(self, value: object) -> object:
        return self._sanitize(value, parent_key=None, path=())

    def _sanitize(
        self,
        value: object,
        *,
        parent_key: str | None,
        path: tuple[str, ...],
    ) -> object:
        if isinstance(value, dict):
            return {
                key: REDACTED
                if _is_secret_key(str(key))
                else self._sanitize(
                    item,
                    parent_key=str(key),
                    path=(*path, _normalized_key(str(key))),
                )
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [
                self._sanitize(item, parent_key=parent_key, path=path)
                for item in value
            ]
        if isinstance(value, tuple):
            return [
                self._sanitize(item, parent_key=parent_key, path=path)
                for item in value
            ]
        if isinstance(value, str):
            sanitized = self._redact_secret_values(value)
            if self.mode == PrivacyMode.PRIVATE and (
                _is_private_text_key(parent_key)
                or _is_private_operation_trace_text(path)
            ):
                return {
                    "sha256": hashlib.sha256(sanitized.encode("utf-8")).hexdigest(),
                    "length": len(sanitized),
                }
            return sanitized
        return value

    def _redact_secret_values(self, value: str) -> str:
        sanitized = SECRET_VALUE_PATTERN.sub(REDACTED, value)
        for secret in sorted(
            (secret for secret in self.secret_values if secret),
            key=len,
            reverse=True,
        ):
            sanitized = sanitized.replace(secret, REDACTED)
        return sanitized


def _is_secret_key(key: str) -> bool:
    normalized = _normalized_key(key)
    return normalized not in TOKEN_METRIC_KEYS and any(
        term in normalized for term in SECRET_KEY_TERMS
    )


def _is_private_text_key(key: str | None) -> bool:
    return key is not None and _normalized_key(key) in PRIVATE_TEXT_KEYS


def _is_private_operation_trace_text(path: tuple[str, ...]) -> bool:
    if "operationtrace" not in path:
        return False
    if "request" in path and path[-1:] == ("content",):
        return True
    if "response" in path and path[-1:] == ("refusal",):
        return True
    return "response" in path and "parsed" in path


def _normalized_key(key: str) -> str:
    normalized = unicodedata.normalize("NFKC", key).casefold()
    return re.sub(r"[^a-z0-9]+", "", normalized)
