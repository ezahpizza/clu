from __future__ import annotations

import uuid
from typing import Any

from fastapi import HTTPException, status

from app.core.config import settings
from app.models import Note


class VectorStoreService:
    def __init__(self) -> None:
        self._client = None
        self._index_name = settings.PINECONE_INDEX_NAME
        if settings.pinecone_enabled:
            from pinecone import Pinecone

            environment: dict[str, Any] = {}
            if settings.PINECONE_ENVIRONMENT:
                environment["environment"] = settings.PINECONE_ENVIRONMENT
            self._client = Pinecone(api_key=settings.PINECONE_API_KEY, **environment)
            self._ensure_index_exists()

    def _ensure_index_exists(self) -> None:
        """Create the Pinecone index if it doesn't exist."""
        if not self._client or not self._index_name:
            return
        
        try:
            from pinecone import ServerlessSpec
            
            # Check if index exists
            existing_indexes = [index.name for index in self._client.list_indexes()]
            
            if self._index_name not in existing_indexes:
                # Create index with dimension 768 for Gemini embedding-001 model
                self._client.create_index(
                    name=self._index_name,
                    dimension=768,  # Gemini embedding-001 dimension
                    metric="cosine",
                    spec=ServerlessSpec(
                        cloud="aws",
                        region="us-east-1"
                    )
                )
                print(f"Created Pinecone index: {self._index_name}")
        except Exception as e:
            print(f"Warning: Could not ensure Pinecone index exists: {e}")

    @property
    def available(self) -> bool:
        return bool(self._client and self._index_name)

    def _get_index(self):
        if not self.available:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Vector store is not configured",
            )
        return self._client.Index(self._index_name)

    def upsert_entry(
        self,
        *,
        entry: Note,
        vector: list[float],
        provider: str,
        model: str,
    ) -> str:
        index = self._get_index()
        vector_id = str(entry.id)
        metadata = {
            "entry_id": vector_id,
            "title": entry.title,
            "user_id": str(entry.owner_id),
            "provider": provider,
            "model": model,
            "tags": entry.tags,
        }
        index.upsert(vectors=[{"id": vector_id, "values": vector, "metadata": metadata}])
        return vector_id

    def delete_entry(self, entry_id: uuid.UUID) -> None:
        index = self._get_index()
        index.delete(ids=[str(entry_id)])

    def query(
        self,
        *,
        vector: list[float],
        top_k: int,
        user_id: uuid.UUID | None,
    ) -> list[dict[str, Any]]:
        index = self._get_index()
        params: dict[str, Any] = {"vector": vector, "top_k": top_k, "include_metadata": True}
        if user_id:
            params["filter"] = {"user_id": {"$eq": str(user_id)}}
        response = index.query(**params)
        matches = response.get("matches", [])
        results: list[dict[str, Any]] = []
        for match in matches:
            metadata = match.get("metadata") or {}
            score = match.get("score", 0.0)
            results.append({
                "entry_id": metadata.get("entry_id"),
                "score": score,
                "metadata": metadata,
            })
        return results
