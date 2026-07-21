"""
Project — an optional organisational grouping around Creatives (plan §1, §6).

Project is intentionally NOT the owner of Creatives - it exists purely so
related Creatives can be grouped in the UI. A Creative's project_id is
nullable (see app.models.creative) and everything in the domain model is
built outward from Creative, not downward from Project.
"""

from datetime import datetime

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._shared import new_uuid, utcnow


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
