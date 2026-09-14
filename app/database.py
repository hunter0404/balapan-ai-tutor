"""Модели данных и сессия SQLAlchemy/SQLModel для хранения прогресса учеников."""
import os
from collections.abc import Generator
from datetime import datetime, timezone
from enum import Enum
from typing import List

from sqlmodel import Field, Relationship, Session, SQLModel, create_engine

from app.config import get_settings

settings = get_settings()

# Гарантируем существование директории для файла SQLite (если используется локальный путь).
if settings.database_url.startswith("sqlite:///./"):
    db_path = settings.database_url.replace("sqlite:///./", "")
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)

_connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, echo=False, connect_args=_connect_args)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DifficultyLevel(str, Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class Student(SQLModel, table=True):
    """Профиль ученика первого класса."""

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    age: int = Field(default=7, ge=6, le=8)
    class_name: str = Field(default="1")
    preferred_topic: str | None = Field(default=None)
    created_at: datetime = Field(default_factory=utcnow)

    word_progress: List["WordProgress"] = Relationship(back_populates="student")
    sessions: List["SessionLog"] = Relationship(back_populates="student")


class WordProgress(SQLModel, table=True):
    """Освоение конкретного казахского слова конкретным учеником."""

    id: int | None = Field(default=None, primary_key=True)
    student_id: int = Field(foreign_key="student.id", index=True)
    word_kazakh: str = Field(index=True)
    translation_ru: str = Field(default="")
    topic: str = Field(default="general", index=True)
    times_correct: int = Field(default=0)
    times_incorrect: int = Field(default=0)
    mastery_level: int = Field(default=0, ge=0, le=100)
    last_practiced: datetime = Field(default_factory=utcnow)

    student: Student | None = Relationship(back_populates="word_progress")


class SessionLog(SQLModel, table=True):
    """Журнал учебных сессий (для аналитики и продолжения диалога)."""

    id: int | None = Field(default=None, primary_key=True)
    student_id: int = Field(foreign_key="student.id", index=True)
    topic: str = Field(default="general")
    started_at: datetime = Field(default_factory=utcnow)
    ended_at: datetime | None = Field(default=None)
    summary: str | None = Field(default=None)
    turns_count: int = Field(default=0)

    student: Student | None = Relationship(back_populates="sessions")


def init_db() -> None:
    """Создаёт таблицы, если их ещё нет."""
    SQLModel.metadata.create_all(engine)


def get_session() -> Generator[Session, None, None]:
    """FastAPI-зависимость: сессия БД на один запрос."""
    with Session(engine) as session:
        yield session
