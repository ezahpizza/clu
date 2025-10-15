from datetime import datetime
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session, select

from app.api import deps
from app.models import Note, TimelineQuery, TimelineResponse, User
from app.services.timeline import TimelineService

router = APIRouter(prefix="/timeline", tags=["timeline"])


def _resolve_user(current_user: User, user_id: uuid.UUID | None) -> uuid.UUID:
    if user_id:
        if not current_user.is_superuser and user_id != current_user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions")
        return user_id
    return current_user.id


def _load_entries(
    *,
    session: Session,
    owner_id: uuid.UUID,
    start: datetime | None,
    end: datetime | None,
) -> list[Note]:
    statement = select(Note).where(Note.owner_id == owner_id)
    if start:
        statement = statement.where(Note.created_at >= start)
    if end:
        statement = statement.where(Note.created_at <= end)
    statement = statement.order_by(Note.created_at.asc())
    return session.exec(statement).all()


@router.get("/{user_id}", response_model=TimelineResponse)
def timeline_for_user(
    *,
    session: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    timeline_service: TimelineService = Depends(deps.get_timeline_service),
    user_id: uuid.UUID,
    start: datetime | None = Query(default=None),
    end: datetime | None = Query(default=None),
) -> TimelineResponse:
    target_user = _resolve_user(current_user, user_id)
    entries = _load_entries(session=session, owner_id=target_user, start=start, end=end)
    return timeline_service.build(entries)


@router.get("/trends", response_model=TimelineResponse)
def timeline_trends(
    *,
    session: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    timeline_service: TimelineService = Depends(deps.get_timeline_service),
    query: TimelineQuery = Depends(),
) -> TimelineResponse:
    target_user = _resolve_user(current_user, query.user_id)
    entries = _load_entries(session=session, owner_id=target_user, start=query.start, end=query.end)
    return timeline_service.build(entries)
