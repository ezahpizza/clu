import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, func, select

from app import crud
from app.api import deps
from app.core.config import settings
from app.core.security import get_password_hash, verify_password
from app.models import (
    Note,
    Message,
    UpdatePassword,
    User,
    UserCreate,
    UserPublic,
    UserRegister,
    UsersPublic,
    UserUpdate,
    UserUpdateMe,
)
from app.services.vector_store import VectorStoreService
from app.utils import generate_new_account_email, send_email

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/", response_model=UsersPublic)
def list_users(
    *,
    session: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    skip: int = 0,
    limit: int = 100,
    email: str | None = None,
) -> UsersPublic:
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions"
        )

    if limit <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Limit must be positive"
        )

    query = select(User)
    count_query = select(func.count()).select_from(User)
    if email:
        query = query.where(User.email == email)
        count_query = count_query.where(User.email == email)

    page_size = min(limit, 200)
    query = query.order_by(User.email).offset(skip).limit(page_size)
    users = session.exec(query).all()
    count = session.exec(count_query).one()
    return UsersPublic(data=users, count=count)


@router.post("/", response_model=UserPublic)
def create_user(
    *,
    session: Session = Depends(deps.get_db),
    user_in: UserCreate,
    _: User = Depends(deps.get_current_active_superuser),
) -> User:
    existing = crud.get_user_by_email(session=session, email=user_in.email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The user with this email already exists in the system.",
        )

    user = crud.create_user(session=session, user_create=user_in)
    if settings.emails_enabled and user_in.email:
        email_data = generate_new_account_email(
            email_to=user_in.email, username=user_in.email, password=user_in.password
        )
        send_email(
            email_to=user_in.email,
            subject=email_data.subject,
            html_content=email_data.html_content,
        )
    return user


@router.patch("/me", response_model=UserPublic)
def update_user_me(
    *,
    session: Session = Depends(deps.get_db),
    user_in: UserUpdateMe,
    current_user: User = Depends(deps.get_current_user),
) -> User:
    if user_in.email:
        existing = crud.get_user_by_email(session=session, email=user_in.email)
        if existing and existing.id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="User with this email already exists",
            )
    user_data = user_in.model_dump(exclude_unset=True)
    current_user.sqlmodel_update(user_data)
    session.add(current_user)
    session.commit()
    session.refresh(current_user)
    return current_user


@router.patch("/me/password", response_model=Message)
def update_password_me(
    *,
    session: Session = Depends(deps.get_db),
    body: UpdatePassword,
    current_user: User = Depends(deps.get_current_user),
) -> Message:
    if not verify_password(body.current_password, current_user.hashed_password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Incorrect password")
    if body.current_password == body.new_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password cannot be the same as the current one",
        )
    hashed_password = get_password_hash(body.new_password)
    current_user.hashed_password = hashed_password
    session.add(current_user)
    session.commit()
    return Message(message="Password updated successfully")


@router.get("/me", response_model=UserPublic)
def read_user_me(current_user: User = Depends(deps.get_current_user)) -> User:
    return current_user


@router.delete("/me", response_model=Message)
def delete_user_me(
    *,
    session: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    vector_store: VectorStoreService = Depends(deps.get_vector_store_service),
) -> Message:
    if current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super users are not allowed to delete themselves",
        )
    _purge_user_entries(session=session, user_id=current_user.id, vector_store=vector_store)
    session.delete(current_user)
    session.commit()
    return Message(message="User deleted successfully")


@router.post("/signup", response_model=UserPublic)
def register_user(
    *,
    session: Session = Depends(deps.get_db),
    user_in: UserRegister,
) -> User:
    existing = crud.get_user_by_email(session=session, email=user_in.email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The user with this email already exists in the system",
        )
    existing_username = crud.get_user_by_username(session=session, username=user_in.username)
    if existing_username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The user with this username already exists in the system",
        )
    user_create = UserCreate.model_validate(user_in)
    return crud.create_user(session=session, user_create=user_create)


@router.get("/{user_id}", response_model=UserPublic)
def read_user_by_id(
    *,
    user_id: uuid.UUID,
    session: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> User:
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if user == current_user or current_user.is_superuser:
        return user
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions")


@router.patch("/{user_id}", response_model=UserPublic)
def update_user(
    *,
    session: Session = Depends(deps.get_db),
    _: User = Depends(deps.get_current_active_superuser),
    user_id: uuid.UUID,
    user_in: UserUpdate,
) -> User:
    db_user = session.get(User, user_id)
    if not db_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The user with this id does not exist in the system",
        )
    if user_in.email:
        existing = crud.get_user_by_email(session=session, email=user_in.email)
        if existing and existing.id != user_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="User with this email already exists",
            )

    return crud.update_user(session=session, db_user=db_user, user_in=user_in)


@router.delete("/{user_id}", response_model=Message)
def delete_user(
    *,
    session: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_superuser),
    vector_store: VectorStoreService = Depends(deps.get_vector_store_service),
    user_id: uuid.UUID,
) -> Message:
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if user == current_user:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super users are not allowed to delete themselves",
        )
    _purge_user_entries(session=session, user_id=user_id, vector_store=vector_store)
    session.delete(user)
    session.commit()
    return Message(message="User deleted successfully")


def _purge_user_entries(
    *,
    session: Session,
    user_id: uuid.UUID,
    vector_store: VectorStoreService,
) -> None:
    entries = session.exec(
        select(Note).where(Note.owner_id == user_id)
    ).all()
    if vector_store.available:
        for entry in entries:
            vector_store.delete_entry(entry.id)
