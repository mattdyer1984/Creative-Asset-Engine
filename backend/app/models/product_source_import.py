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

listing_id (Phase 5.8 of the catalogue layer, see MIGRATION_PLAN.md's
frozen catalogue ADR) is a new, nullable, purely additive FK to Listing -
used only by the new unknown-URL/bundle-aware import path (Phase 5.10+).
The existing product_id-direct flow (the already-shipped
POST /api/products/{id}/source-import, Phase 5.6) is completely
unaffected by any of this: it always sets product_id immediately, exactly
as before. This is a deliberate implementation choice the ADR itself left
open (see its Non-goals section) rather than a redesign - extend, don't
replace, same pattern as every other provenance column in this codebase.

product_id relaxes from NOT NULL to nullable in the same migration that
adds listing_id, for a real reason (not a broadening for its own sake): a
Listing-scoped import (Phase 5.10) is created *before* resolution - the
whole point of Listing is that "which Product is this" isn't known yet
at fetch time, and per the catalogue ADR that resolution is never
automatic. product_id is backfilled once a human resolves the Listing to
a Product (at which point this row behaves exactly like one created
through the existing direct flow, and Phase 5.5's merge service picks it
up unchanged, with no new code needed there). Every row the existing
direct flow writes still always supplies product_id immediately, so
nothing about today's behavior changes.
"""

from datetime import datetime

from sqlalchemy import JSON, Boolean, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._shared import new_uuid, utcnow

FETCH_STATUS_SUCCEEDED = "succeeded"
FETCH_STATUS_PARTIAL = "partial"
FETCH_STATUS_FAILED = "failed"


class ProductSourceImport(Base):
    __tablename__ = "product_source_imports"
    __table_args__ = (
        # Optimisation & Stability Pass, Tier 3.1 (see MIGRATION_PLAN.md) -
        # two real, independently-confirmed query shapes: "the current
        # import for product X" (product_source_import.py, product_profile.py)
        # and "the current import for listing X" (listing_import.py) - both
        # columns are independently nullable, so neither subsumes the other.
        Index("ix_product_source_imports_product_id_is_current", "product_id", "is_current"),
        Index("ix_product_source_imports_listing_id_is_current", "listing_id", "is_current"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    product_id: Mapped[str | None] = mapped_column(ForeignKey("products.id"), nullable=True)
    listing_id: Mapped[str | None] = mapped_column(ForeignKey("listings.id"), nullable=True)
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
