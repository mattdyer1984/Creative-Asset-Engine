"""Small shared helpers used as SQLAlchemy column defaults across models."""

import uuid
from datetime import datetime, timezone


def new_uuid() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
