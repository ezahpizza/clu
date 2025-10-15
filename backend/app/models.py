import uuid
from datetime import datetime, timezone

from pydantic import EmailStr
from sqlalchemy import Column, DateTime, JSON
from sqlmodel import Field, Relationship, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UserBase(SQLModel):
    email: EmailStr = Field(unique=True, index=True, max_length=255)
    username: str = Field(unique=True, index=True, min_length=3, max_length=50)
    is_active: bool = True
    is_superuser: bool = False
    full_name: str | None = Field(default=None, max_length=255)


class UserCreate(UserBase):
    password: str = Field(min_length=8, max_length=40)


class UserRegister(SQLModel):
    email: EmailStr = Field(max_length=255)
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=8, max_length=40)
    full_name: str | None = Field(default=None, max_length=255)


class UserUpdate(UserBase):
    email: EmailStr | None = Field(default=None, max_length=255)  # type: ignore
    username: str | None = Field(default=None, min_length=3, max_length=50)  # type: ignore
    password: str | None = Field(default=None, min_length=8, max_length=40)


class UserUpdateMe(SQLModel):
    full_name: str | None = Field(default=None, max_length=255)
    email: EmailStr | None = Field(default=None, max_length=255)
    username: str | None = Field(default=None, min_length=3, max_length=50)


class UpdatePassword(SQLModel):
    current_password: str = Field(min_length=8, max_length=40)
    new_password: str = Field(min_length=8, max_length=40)


class User(UserBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    hashed_password: str
    entries: list["Note"] = Relationship(
        back_populates="owner", cascade_delete=True
    )


class UserPublic(UserBase):
    id: uuid.UUID


class UsersPublic(SQLModel):
    data: list[UserPublic]
    count: int


class NoteBase(SQLModel):
    title: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1)
    tags: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))


class NoteCreate(NoteBase):
    pass


class NoteUpdate(SQLModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    content: str | None = Field(default=None, min_length=1)
    tags: list[str] | None = None


class Note(NoteBase, table=True):
    __tablename__ = "notes"
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    owner_id: uuid.UUID = Field(
        foreign_key="user.id", nullable=False, ondelete="CASCADE"
    )
    embedding_id: str | None = Field(default=None, index=True)
    embedding_provider: str | None = Field(default=None, max_length=50)
    created_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False, default=utcnow),
    )
    updated_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(
            DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
        ),
    )
    owner: User | None = Relationship(back_populates="entries")


class NotePublic(NoteBase):
    id: uuid.UUID
    owner_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    embedding_id: str | None = None
    embedding_provider: str | None = None


class KnowledgeEntriesPublic(SQLModel):
    data: list[NotePublic]
    count: int


class VectorSearchRequest(SQLModel):
    query_text: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=50)
    user_id: uuid.UUID | None = None


class VectorSearchResult(SQLModel):
    entry: NotePublic
    score: float


class VectorSearchResponse(SQLModel):
    results: list[VectorSearchResult]


class EmbeddingReindexRequest(SQLModel):
    entry_id: uuid.UUID


class TimelineQuery(SQLModel):
    user_id: uuid.UUID | None = None
    start: datetime | None = None
    end: datetime | None = None


class TimelinePoint(SQLModel):
    period_start: datetime
    period_end: datetime
    entries: list[NotePublic]


class TimelineResponse(SQLModel):
    data: list[TimelinePoint]


class GraphContext(SQLModel):
    nodes: list[dict[str, str | float | int]]
    edges: list[dict[str, str | float | int]]


class InsightQuery(SQLModel):
    user_id: uuid.UUID
    question: str = Field(min_length=3)
    time_start: datetime | None = None
    time_end: datetime | None = None
    top_k: int = Field(default=5, ge=1, le=20)


class InsightResponse(SQLModel):
    answer: str
    references: list[NotePublic]


class Message(SQLModel):
    message: str


class Token(SQLModel):
    access_token: str
    token_type: str = "bearer"


class TokenPayload(SQLModel):
    sub: str | None = None


class NewPassword(SQLModel):
    token: str
    new_password: str = Field(min_length=8, max_length=40)
