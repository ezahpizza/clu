from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from google import genai

from fastapi import HTTPException, status

from app.core.config import settings


@dataclass
class EmbeddingResult:
    vector: Sequence[float]
    provider: str
    model: str


class EmbeddingService:
    def __init__(self) -> None:
        self._provider = settings.DEFAULT_EMBEDDING_PROVIDER
        self._client: genai.Client | None = None
        if settings.gemini_enabled:
            self._client = genai.Client(api_key=settings.GEMINI_API_KEY)

    def generate(self, text: str, provider: str | None = None) -> EmbeddingResult:
        if not text:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Text is required for embeddings")
        active_provider = provider or self._provider
        if active_provider == "gemini":
            return self._generate_gemini(text)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="No supported embedding provider configured")

    def _generate_gemini(self, text: str) -> EmbeddingResult:
        if not settings.gemini_enabled:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Gemini embedding provider is not available")
        if not self._client:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Gemini client is not configured")
        embed_model = settings.GEMINI_EMBEDDING_MODEL
        response = self._client.models.embed_content(model=embed_model, contents=text)
        embeddings = getattr(response, "embeddings", None)
        if not embeddings:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Gemini embedding response missing vectors")
        vector = list(embeddings[0].values)
        return EmbeddingResult(vector=vector, provider="gemini", model=embed_model)
