"""
EvidenceSource — Phase 10.5 of AI Creative Engine vNext (see
MIGRATION_PLAN.md's "ADR: AI Creative Engine vNext" §4b). A Project-
scoped event-log row recording one evidence-intake event - who/what
platform it came from, what they said about it, and what the platform
itself already claims about products in it.

Deliberately NOT a duplicate store: the heavy artifacts an import
actually produces (Slideshow, its Slides, their stored images) stay
owned by Slideshow exactly as before this phase. This table only holds
the package-level facts an EvidencePackage carries that had nowhere to
live prior to this phase - Slideshow.evidence_source_id is a plain
many-to-one pointer back to the row that produced it (many Slideshows
share one EvidenceSource for a group_as_one=False multi-file import,
matching EvidencePackage's own one-package-many-media_assets shape).

evidence_type/source_locator/status are the ADR's own literal field
list; source_platform/creator_json/caption/hashtags_json/
product_references_json/platform_metadata_json/raw_json/imported_at are
the "package-level facts" the same section separately calls out as
belonging on this row. evidence_type is set by the caller (e.g.
app.services.slideshow_import passes "slideshow_upload"), not derived
from source_platform here - the same platform can back more than one
evidence_type in principle (a TikTok URL could be a slideshow import
today, a product-URL import in a later phase), so which routing purpose
this event serves is the caller's call, not this row's to infer.

Only "slideshow_upload" is wired through this table as of Phase 10.5 -
Phase 9.6's reference-image upload path predates this table and is a
documented, not-yet-retrofitted gap (see that phase's own report), not
something this phase silently claims to have unified.

project_id is nullable, mirroring Slideshow.project_id's own
nullability - an import with no Project selected still gets a real
EvidenceSource row, just unscoped, consistent with "Project groups,
never owns" holding for evidence exactly as it does for Slideshow.

status defaults to "succeeded": record_evidence_source is only ever
called once an ImportProvider has already returned successfully (a
raised exception never reaches this table) - matching
ProductSourceImport.fetch_status's vocabulary for a future partial/
failed evidence-intake path (e.g. a multi-file import where some files
failed) without needing that path to exist yet to have somewhere to
write to.
"""

from datetime import datetime

from sqlalchemy import JSON, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._shared import new_uuid, utcnow

EVIDENCE_TYPE_SLIDESHOW_UPLOAD = "slideshow_upload"
EVIDENCE_TYPE_TIKTOK_SLIDESHOW_URL = "tiktok_slideshow_url"
EVIDENCE_TYPE_PRODUCT_URL = "product_url"
EVIDENCE_TYPE_REFERENCE_IMAGE_UPLOAD = "reference_image_upload"
EVIDENCE_TYPE_BRAND_ASSET = "brand_asset"
EVIDENCE_TYPE_MANUAL_CORRECTION = "manual_correction"

STATUS_SUCCEEDED = "succeeded"
STATUS_PARTIAL = "partial"
STATUS_FAILED = "failed"


class EvidenceSource(Base):
    __tablename__ = "evidence_sources"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"), nullable=True)

    evidence_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_locator: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default=STATUS_SUCCEEDED)

    source_platform: Mapped[str] = mapped_column(String(64), nullable=False)
    creator_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    caption: Mapped[str | None] = mapped_column(Text, nullable=True)
    hashtags_json: Mapped[list] = mapped_column(JSON, default=list)
    product_references_json: Mapped[list] = mapped_column(JSON, default=list)
    platform_metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    raw_json: Mapped[dict] = mapped_column(JSON, default=dict)

    imported_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
