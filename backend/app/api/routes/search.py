import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from app.api import deps
from app.models import (
    KnowledgeEntry,
    KnowledgeEntryPublic,
    VectorSearchRequest,
    VectorSearchResponse,
    VectorSearchResult,
    User,
)
from app.services.embedding import EmbeddingService
from app.services.vector_store import VectorStoreService

router = APIRouter(prefix="/search", tags=["search"])


@router.post("/vector", response_model=VectorSearchResponse)
def vector_search(
    *,
    session: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    embedding_service: EmbeddingService = Depends(deps.get_embedding_service),
    vector_store: VectorStoreService = Depends(deps.get_vector_store_service),
    payload: VectorSearchRequest,
) -> VectorSearchResponse:
    if not vector_store.available:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Vector search is not available",
        )
    query_owner = payload.user_id or current_user.id
    if not current_user.is_superuser and query_owner != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions")
    embedding = embedding_service.generate(payload.query_text)
    matches = vector_store.query(
        vector=list(embedding.vector),
        top_k=payload.top_k,
        user_id=query_owner,
    )
    entry_ids = [uuid.UUID(match["entry_id"]) for match in matches if match.get("entry_id")]
    if not entry_ids:
        return VectorSearchResponse(results=[])
    statement = select(KnowledgeEntry).where(KnowledgeEntry.id.in_(entry_ids))
    entries = session.exec(statement).all()
    entries_map = {str(entry.id): entry for entry in entries}
    results: list[VectorSearchResult] = []
    for match in matches:
        entry_id = match.get("entry_id")
        score = float(match.get("score", 0.0))
        entry = entries_map.get(entry_id)
        if entry is None:
            continue
        results.append(VectorSearchResult(entry=KnowledgeEntryPublic.model_validate(entry), score=score))
    return VectorSearchResponse(results=results)
