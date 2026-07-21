"""
Database engine/session setup.

SQLite via SQLAlchemy, matching the architecture plan (§2, §6). Schema
changes go through Alembic migrations (see backend/alembic/) rather than
create_all() in normal operation, so history is reviewable as the data
model grows through later milestones.
"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""


engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},  # needed for SQLite + FastAPI's threaded requests
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a request-scoped DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
