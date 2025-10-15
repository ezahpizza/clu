import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from app.api import deps
from app.models import InsightQuery, InsightResponse, Note, NotePublic, User
from app.services.insights import InsightService
from app.services.vector_store import VectorStoreService

router = APIRouter(prefix="/insights", tags=["insights"])


def _resolve_user(current_user: User, user_id: uuid.UUID | None) -> uuid.UUID:
    if user_id:
        if not current_user.is_superuser and user_id != current_user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions")
        return user_id
    return current_user.id


def _load_entries_by_ids(
    *,
    session: Session,
    entry_ids: list[uuid.UUID],
) -> dict[str, Note]:
    if not entry_ids:
        return {}
    statement = select(Note).where(Note.id.in_(entry_ids))
    entries = session.exec(statement).all()
    return {str(entry.id): entry for entry in entries}


def _fallback_entries(
    *,
    session: Session,
    owner_id: uuid.UUID,
    query: InsightQuery,
) -> list[NotePublic]:
    statement = select(Note).where(Note.owner_id == owner_id)
    if query.time_start:
        statement = statement.where(Note.created_at >= query.time_start)
    if query.time_end:
        statement = statement.where(Note.created_at <= query.time_end)
    statement = statement.order_by(Note.updated_at.desc()).limit(query.top_k)
    entries = session.exec(statement).all()
    return [NotePublic.model_validate(entry) for entry in entries]


@router.post("/query", response_model=InsightResponse)
def insights_query(
    *,
    session: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    insight_service: InsightService = Depends(deps.get_insight_service),
    vector_store: VectorStoreService = Depends(deps.get_vector_store_service),
    payload: InsightQuery,
) -> InsightResponse:
    target_user = _resolve_user(current_user, payload.user_id)
    context_entries: list[NotePublic] = []
    if vector_store.available:
        embedding_vector = insight_service.embed_question(question=payload.question)
        matches = vector_store.query(
            vector=embedding_vector,
            top_k=payload.top_k,
            user_id=target_user,
        )
        entry_ids = [uuid.UUID(match["entry_id"]) for match in matches if match.get("entry_id")]
        entry_map = _load_entries_by_ids(session=session, entry_ids=entry_ids)
        for match in matches:
            entry_id = match.get("entry_id")
            if entry_id is None:
                continue
            entry = entry_map.get(entry_id)
            if entry is None:
                continue
            if payload.time_start and entry.created_at < payload.time_start:
                continue
            if payload.time_end and entry.created_at > payload.time_end:
                continue
            context_entries.append(NotePublic.model_validate(entry))
    if not context_entries:
        context_entries = _fallback_entries(session=session, owner_id=target_user, query=payload)
    return insight_service.generate(query=payload, context_entries=context_entries)
