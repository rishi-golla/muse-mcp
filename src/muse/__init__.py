"""Muse research prototype."""

from muse.calibration_packets import (
    ReviewPacket,
    ReviewPacketStore,
    build_review_packet,
)
from muse.engine import CreativeEngine
from muse.models import (
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
from muse.openai_provider import OpenAICreativeProvider
from muse.quality_benchmark import (
    ArtifactGenerator,
    BenchmarkArtifact,
    BenchmarkCorpus,
    BenchmarkRecord,
    BenchmarkReport,
    BenchmarkTask,
    GenerationAttempt,
    GenerationFailure,
    JudgeArtifact,
    PairwiseJudge,
    PairwiseJudgment,
    Preference,
    run_quality_benchmark,
)

__version__ = "0.1.0"

__all__ = [
    "CreativeEngine",
    "ArtifactGenerator",
    "BenchmarkArtifact",
    "BenchmarkCorpus",
    "BenchmarkRecord",
    "BenchmarkReport",
    "BenchmarkTask",
    "EvaluationScores",
    "FramedTask",
    "IdeaGenome",
    "InspirationKind",
    "GenerationAttempt",
    "GenerationFailure",
    "JudgeArtifact",
    "OpenAICreativeProvider",
    "PairwiseJudge",
    "PairwiseJudgment",
    "Preference",
    "ProviderIdentity",
    "ReviewPacket",
    "ReviewPacketStore",
    "RunConfig",
    "RunError",
    "RunProviders",
    "RunResult",
    "TaskContext",
    "build_review_packet",
    "run_quality_benchmark",
]
