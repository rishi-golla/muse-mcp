from __future__ import annotations

from typing import Annotated, Protocol

from pydantic import Field, model_validator

from muse.models import FrozenModel
from muse.providers import MeteredResponse, OperationQuote

EmbeddingValue = Annotated[float, Field(strict=True)]


class EmbeddingBatch(FrozenModel):
    vectors: tuple[tuple[EmbeddingValue, ...], ...]
    dimensions: int = Field(strict=True, gt=0)

    @model_validator(mode="after")
    def dimensions_match_vectors(self) -> EmbeddingBatch:
        if not self.vectors:
            raise ValueError("embedding batch must contain at least one vector")
        if any(len(vector) != self.dimensions for vector in self.vectors):
            raise ValueError("embedding dimensions do not match vectors")
        return self


class EmbeddingProvider(Protocol):
    name: str
    version: str

    def quote_embeddings(self, texts: tuple[str, ...]) -> OperationQuote: ...

    def embed(self, texts: tuple[str, ...]) -> MeteredResponse[EmbeddingBatch]: ...
