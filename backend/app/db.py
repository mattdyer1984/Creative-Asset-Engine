"""
Database engine/session setup.

SQLite via SQLAlchemy, matching the architecture plan (§2, §6). Schema
changes go through Alembic migrations (see backend/alembic/) rather than
create_all() in normal operation, so history is reviewable as the data
model grows through later milestones.

Real-world-diagnosed fix (Generate All speed work follow-up, see
MIGRATION_PLAN.md): once Generate All started firing several concurrent
`generate-creative` requests (each a genuinely separate, write-heavy
request-scoped session), a real run hit `sqlite3.OperationalError:
database is locked` and lost an entire slide's generation outright (no
GenerationLog, no partial artifact - the request 500'd before writing
anything). SQLite's Python driver defaults to a 5-second busy timeout
and the older rollback-journal mode, both of which are too easily
exceeded/contended once more than one write-heavy transaction can be in
flight at once - a real gap this app's own concurrent-by-design
features (Generate All, the per-slide analysis stages) now actually
exercise, not a hypothetical one.
"""

from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""


engine = create_engine(
    settings.database_url,
    # 30s, not the sqlite3 driver's 5s default - a genuinely slow but
    # legitimate concurrent write (several generate-creative calls at
    # once) should wait it out, not fail outright.
    connect_args={"check_same_thread": False, "timeout": 30},
)


@event.listens_for(engine, "connect")
def _set_sqlite_pragmas(dbapi_connection, _connection_record):
    """
    WAL (Write-Ahead Logging) journal mode - unlike the default
    rollback-journal mode, readers never block writers and vice versa,
    substantially reducing real contention between concurrent requests.
    `busy_timeout` (milliseconds) is SQLite's own internal retry window
    on top of the driver-level `timeout` connect_arg above - belt and
    suspenders, since the two are configured through different layers
    (PRAGMA vs. the Python driver) and either alone has been observed
    to not fully cover every SQLAlchemy code path that opens a
    connection. Must run per-connection (not once globally) - SQLite
    PRAGMAs are connection-scoped, and SQLAlchemy opens a fresh DBAPI
    connection per checkout.
    """
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=30000")
    cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a request-scoped DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
