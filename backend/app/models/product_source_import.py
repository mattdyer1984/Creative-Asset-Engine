"""
ProductSourceImport — Phase 5.1 of Product Intelligence (see
MIGRATION_PLAN.md). Records one fetch of a Product Source (a URL - the
generic schema.org/OpenGraph fallback, or a platform-specific adapter
like TikTok Shop) for a Product.

Deliberately NOT built on AnalysisArtifactMixin/AnalysisRun - that
mixin's analysis_run_id FK points at AnalysisRun, which requires
non-nullable provider/model_name (AI-call-specific). A Product Source
fetch isn't an AI call, so it gets its own small, independent set of
columns instead. is_current is still scoped to product_id, following the
same convention as every other artifact regardless.

Stores BOTH raw_response_json (whatever the adapter's underlying fetch
literally returned, in the source's own native shape) and
normalized_json (the same evidence mapped into the shared canonical
vocabulary - see app.product_sources.base, Phase 5.2) - not just the
normalized form. This is deliberate: if the canonical vocabulary or an
adapter's own mapping logic needs fixing later, the raw evidence is
still there to reprocess without re-fetching. Both are nullable since a
failed fetch (fetch_status=FETCH_STATUS_FAILED) may have no raw response
at all (e.g. the URL was unreachable) and therefore nothing to normalize
either.
"""

from datetime import datetime

from sqlalchemy import JSON, Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._shared import new_uuid, utcnow

FETCH_STATUS_SUCCEEDED = "succeeded"
FETCH_STATUS_PARTIAL = "partial"
FETCH_STATUS_FAILED = "failed"


class ProductSourceImport(Base):
    __tablename__ = "product_source_imports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"), nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)

    # Plain string, not a hardcoded enum - a future adapter (e.g. a real
    # Shopify integration) is additive data, not a schema change. Values
    # in use as of Phase 5: "generic_url", "tiktok_shop".
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_url: Mapped[str] = mapped_column(String(2048), nullable=False)

    fetch_status: Mapped[str] = mapped_column(String(16), nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    raw_response_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    normalized_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(default=utcnow)
