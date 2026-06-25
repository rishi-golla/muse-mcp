from __future__ import annotations

import re

from pydantic import Field, model_validator

from creativity_layer.models import FrozenModel, RequiredText, Score
from creativity_layer.search import SearchResult

MAX_MECHANISM_LENGTH = 160
MAX_PRINCIPLE_LENGTH = 240
INSTRUCTION_LIKE_TEXT = re.compile(
    r"\b("
    r"ignore\s+(?:all\s+)?previous\s+instructions"
    r"|reveal\s+secrets?"
    r"|system\s+prompt"
    r")\b",
    re.IGNORECASE,
)
URL_TEXT = re.compile(r"https?://\S+", re.IGNORECASE)


class SourceAbstraction(FrozenModel):
    source_id: RequiredText
    source_url: RequiredText
    mechanism: RequiredText
    constraints: tuple[RequiredText, ...] = ()
    tensions: tuple[RequiredText, ...] = ()
    domain: RequiredText
    confidence: Score = Field(default=0.5)
    principle: RequiredText

    @model_validator(mode="after")
    def reject_unsafe_text(self) -> SourceAbstraction:
        checked_text = " ".join(
            (
                self.mechanism,
                self.domain,
                self.principle,
                *self.constraints,
                *self.tensions,
            )
        )
        if INSTRUCTION_LIKE_TEXT.search(checked_text):
            raise ValueError("source abstraction contains instruction-like text")
        if URL_TEXT.search(self.principle) or self.source_url in self.principle:
            raise ValueError("source abstraction principle must not contain URLs")
        return self


def abstract_sources(
    sources: tuple[SearchResult, ...],
    *,
    task_goal: str,
) -> tuple[SourceAbstraction, ...]:
    abstractions: list[SourceAbstraction] = []
    safe_goal = _clean_text(task_goal, max_length=72) or "the task"
    for source in sources:
        if _contains_instruction_like_source_text(source):
            continue
        mechanism = _clean_text(_source_text(source), max_length=MAX_MECHANISM_LENGTH)
        if not mechanism:
            continue
        principle = _clean_text(
            f"Transfer the mechanism of {mechanism} to {safe_goal}.",
            max_length=MAX_PRINCIPLE_LENGTH,
        )
        if not principle:
            continue
        abstractions.append(
            SourceAbstraction(
                source_id=source.source_id,
                source_url=str(source.url),
                mechanism=mechanism,
                constraints=("Use only bounded source evidence.",),
                tensions=("Source context may differ from the target task.",),
                domain="general",
                confidence=0.6,
                principle=principle,
            )
        )
    return tuple(abstractions)


def _contains_instruction_like_source_text(source: SearchResult) -> bool:
    return any(
        INSTRUCTION_LIKE_TEXT.search(text)
        for text in (source.title, source.snippet, source.bounded_excerpt)
    )


def _source_text(source: SearchResult) -> str:
    return source.bounded_excerpt or source.snippet or source.title


def _clean_text(text: str, *, max_length: int) -> str:
    without_urls = URL_TEXT.sub("", text)
    normalized = re.sub(r"\s+", " ", without_urls).strip()
    if not normalized or INSTRUCTION_LIKE_TEXT.search(normalized):
        return ""
    return normalized[:max_length].strip(" .,;:")
