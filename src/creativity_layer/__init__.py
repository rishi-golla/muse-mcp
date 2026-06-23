"""Creativity Layer research prototype."""

from creativity_layer.engine import CreativeEngine
from creativity_layer.models import (
    EvaluationScores,
    FramedTask,
    IdeaGenome,
    InspirationKind,
    ProviderIdentity,
    RunConfig,
    RunError,
    RunProviders,
    RunResult,
    TaskContext,
)
from creativity_layer.openai_provider import OpenAICreativeProvider

__version__ = "0.1.0"

__all__ = [
    "CreativeEngine",
    "EvaluationScores",
    "FramedTask",
    "IdeaGenome",
    "InspirationKind",
    "OpenAICreativeProvider",
    "ProviderIdentity",
    "RunConfig",
    "RunError",
    "RunProviders",
    "RunResult",
    "TaskContext",
]
