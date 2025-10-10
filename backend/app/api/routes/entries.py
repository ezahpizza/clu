import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, func, select

from app import crud
from app.api import deps
from app.models import (
    EmbeddingReindexRequest,
    KnowledgeEntriesPublic,
    KnowledgeEntry,
    KnowledgeEntryCreate,
    KnowledgeEntryPublic,
    KnowledgeEntryUpdate,
    Message,
    User,
)
from app.services.embedding import EmbeddingService
from app.services.vector_store import VectorStoreService

router = APIRouter(prefix="/entries", tags=["entries"])


def _authorize_entry_owner(entry: KnowledgeEntry, current_user: User) -> None:
    if current_user.is_superuser:
        return
    if entry.owner_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions")


@router.get("/", response_model=KnowledgeEntriesPublic)
def list_entries(
    session: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    skip: int = 0,
    limit: int = 100,
    user_id: uuid.UUID | None = None,
    tag: str | None = None,
) -> KnowledgeEntriesPublic:
    if limit <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Limit must be positive")
    page_size = min(limit, 200)
    statement = select(KnowledgeEntry)
    count_statement = select(func.count()).select_from(KnowledgeEntry)
    if current_user.is_superuser:
        if user_id:
            statement = statement.where(KnowledgeEntry.owner_id == user_id)
            count_statement = count_statement.where(KnowledgeEntry.owner_id == user_id)
    else:
        statement = statement.where(KnowledgeEntry.owner_id == current_user.id)
        count_statement = count_statement.where(KnowledgeEntry.owner_id == current_user.id)
    if tag:
        statement = statement.where(KnowledgeEntry.tags.contains([tag]))
        count_statement = count_statement.where(KnowledgeEntry.tags.contains([tag]))
    statement = statement.order_by(KnowledgeEntry.created_at.desc()).offset(skip).limit(page_size)
    entries = session.exec(statement).all()
    count = session.exec(count_statement).one()
    return KnowledgeEntriesPublic(data=entries, count=count)


@router.get("/{entry_id}", response_model=KnowledgeEntryPublic)
def get_entry(
    *,
    session: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    entry_id: uuid.UUID,
) -> KnowledgeEntry:
    entry = session.get(KnowledgeEntry, entry_id)
    if not entry:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry not found")
    _authorize_entry_owner(entry, current_user)
    return entry


@router.post("/", response_model=KnowledgeEntryPublic, status_code=status.HTTP_201_CREATED)
def create_entry(
    *,
    session: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    embedding_service: EmbeddingService = Depends(deps.get_embedding_service),
    vector_store: VectorStoreService = Depends(deps.get_vector_store_service),
    entry_in: KnowledgeEntryCreate,
) -> KnowledgeEntry:
    entry = crud.create_entry(session=session, entry_in=entry_in, owner_id=current_user.id)
    embedding = embedding_service.generate(entry.content)
    entry.embedding_provider = embedding.provider
    if vector_store.available:
        vector_id = vector_store.upsert_entry(
            entry=entry,
            vector=list(embedding.vector),
            provider=embedding.provider,
            model=embedding.model,
        )
        entry.embedding_id = vector_id
    session.add(entry)
    session.commit()
    session.refresh(entry)
    return entry


@router.patch("/{entry_id}", response_model=KnowledgeEntryPublic)
def update_entry(
    *,
    session: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    embedding_service: EmbeddingService = Depends(deps.get_embedding_service),
    vector_store: VectorStoreService = Depends(deps.get_vector_store_service),
    entry_id: uuid.UUID,
    entry_in: KnowledgeEntryUpdate,
) -> KnowledgeEntry:
    entry = session.get(KnowledgeEntry, entry_id)
    if not entry:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry not found")
    _authorize_entry_owner(entry, current_user)
    updated_entry = crud.update_entry(session=session, entry=entry, entry_in=entry_in)
    if entry_in.content is not None or entry_in.title is not None or entry_in.summary is not None:
        embedding = embedding_service.generate(updated_entry.content)
        updated_entry.embedding_provider = embedding.provider
        if vector_store.available:
            vector_id = vector_store.upsert_entry(
                entry=updated_entry,
                vector=list(embedding.vector),
                provider=embedding.provider,
                model=embedding.model,
            )
            updated_entry.embedding_id = vector_id
    session.add(updated_entry)
    session.commit()
    session.refresh(updated_entry)
    return updated_entry


@router.delete("/{entry_id}", response_model=Message)
def delete_entry(
    *,
    session: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    vector_store: VectorStoreService = Depends(deps.get_vector_store_service),
    entry_id: uuid.UUID,
) -> Message:
    entry = session.get(KnowledgeEntry, entry_id)
    if not entry:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry not found")
    _authorize_entry_owner(entry, current_user)
    if vector_store.available and entry.embedding_id:
        vector_store.delete_entry(entry_id)
    session.delete(entry)
    session.commit()
    return Message(message="Entry deleted successfully")


@router.post("/reindex", response_model=KnowledgeEntryPublic)
def reindex_entry(
    *,
    session: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    embedding_service: EmbeddingService = Depends(deps.get_embedding_service),
    vector_store: VectorStoreService = Depends(deps.get_vector_store_service),
    payload: EmbeddingReindexRequest,
) -> KnowledgeEntry:
    entry = session.get(KnowledgeEntry, payload.entry_id)
    if not entry:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry not found")
    _authorize_entry_owner(entry, current_user)
    embedding = embedding_service.generate(entry.content)
    entry.embedding_provider = embedding.provider
    if vector_store.available:
        vector_id = vector_store.upsert_entry(
            entry=entry,
            vector=list(embedding.vector),
            provider=embedding.provider,
            model=embedding.model,
        )
        entry.embedding_id = vector_id
    session.add(entry)
    session.commit()
    session.refresh(entry)
    return entry
