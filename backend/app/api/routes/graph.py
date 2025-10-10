import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.api import deps
from app.models import GraphContext, KnowledgeEntry, User
from app.services.graph import GraphService

router = APIRouter(prefix="/graph", tags=["graph"])


@router.post("/sync_entry/{entry_id}")
def sync_entry(
    *,
    session: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    graph_service: GraphService = Depends(deps.get_graph_service),
    entry_id: uuid.UUID,
) -> None:
    entry = session.get(KnowledgeEntry, entry_id)
    if not entry:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry not found")
    if not current_user.is_superuser and entry.owner_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions")
    owner = session.get(User, entry.owner_id)
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Owner not found")
    graph_service.sync_entry(entry=entry, owner=owner)


@router.get("/connections/{concept}", response_model=GraphContext)
def concept_connections(
    *,
    current_user: User = Depends(deps.get_current_user),
    graph_service: GraphService = Depends(deps.get_graph_service),
    concept: str,
) -> GraphContext:
    if not current_user.is_superuser:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only admins can explore global concepts")
    if not concept:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Concept is required")
    return graph_service.get_connections(concept=concept)


@router.get("/context/{entry_id}", response_model=GraphContext)
def entry_context(
    *,
    session: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    graph_service: GraphService = Depends(deps.get_graph_service),
    entry_id: uuid.UUID,
) -> GraphContext:
    entry = session.get(KnowledgeEntry, entry_id)
    if not entry:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry not found")
    if not current_user.is_superuser and entry.owner_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions")
    return graph_service.get_entry_context(entry_id=entry_id)
