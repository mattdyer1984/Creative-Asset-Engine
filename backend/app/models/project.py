"""
Project — the aggregation root for one creative effort (Phase 10.5,
AI Creative Engine vNext, see MIGRATION_PLAN.md's "ADR: AI Creative
Engine vNext" §3 - a deliberate reversal of this model's original
design, stated plainly per that ADR's own "don't leave the code lying
about its own design" discipline rather than left stale).

Project is the container for Evidence Sources (app.models.evidence_source
- who/what an import came from) and the aggregation point this ADR
names for Generation History/Validation Results/Final Outputs (not yet
built as of Phase 10.5 - see that phase's report for what's a genuine
gap vs. deliberately deferred). Slideshow.project_id (still nullable,
for a Slideshow with no Project selected) is what a Project's assembled
view walks.

Product and its Canonical Reference Library deliberately do NOT move
into Project's ownership - a Product is durable, cross-Project-reusable
knowledge (see app.models.product's own docstring), while a Project is
a scoped unit of work that may involve many Products, and the same
Product may recur across many Projects over time. ProjectProduct (a
pure "reference, don't own" membership join, mirroring
ProductBundleMember's own shape) records which Products a Project's
work has come to involve, without claiming ownership - see
app.services.project_product for how that membership actually gets
populated.
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
