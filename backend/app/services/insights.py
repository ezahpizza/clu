from __future__ import annotations

from typing import Iterable

from fastapi import HTTPException, status
from google import genai

from app.core.config import settings
from app.models import InsightQuery, InsightResponse, KnowledgeEntryPublic
from app.services.embedding import EmbeddingService


class InsightService:
    def __init__(
        self,
        *,
        embedding_service: EmbeddingService,
    ) -> None:
        self._embedding_service = embedding_service
        self._client: genai.Client | None = None
        if settings.gemini_enabled:
            self._client = genai.Client(api_key=settings.GEMINI_API_KEY)

    def embed_question(self, *, question: str) -> list[float]:
        embedding = self._embedding_service.generate(question)
        return list(embedding.vector)

    def generate(self, *, query: InsightQuery, context_entries: Iterable[KnowledgeEntryPublic]) -> InsightResponse:
        if not settings.gemini_enabled:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Gemini completion model is not configured",
            )
        if not self._client:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Gemini client is not configured",
            )
        references = list(context_entries)
        prompt = self._build_prompt(query=query, references=references)
        response = self._client.models.generate_content(
            model=settings.GEMINI_COMPLETION_MODEL,
            contents=prompt,
        )
        answer = getattr(response, "text", "")
        if not answer:
            answer = "No insight could be generated with the provided context."
        return InsightResponse(answer=answer.strip(), references=references)

    @staticmethod
    def _build_prompt(
        *,
        query: InsightQuery,
        references: Iterable[KnowledgeEntryPublic],
    ) -> str:
        lines = [
            "You are CLU, a temporal knowledge analyst.",
            "Summarize the user's knowledge evolution and answer the question succinctly.",
            f"Question: {query.question}",
        ]
        if query.time_start or query.time_end:
            lines.append(
                "Time Range: "
                + f"{query.time_start.isoformat() if query.time_start else 'start'}"
                + " to "
                + f"{query.time_end.isoformat() if query.time_end else 'now'}"
            )
        lines.append("Relevant entries:")
        for entry in references:
            lines.append(
                f"- {entry.created_at.isoformat()}: {entry.title} -- {entry.summary or entry.content[:200]}"
            )
        lines.append("Provide a future-focused recommendation if possible.")
        return "\n".join(lines)
