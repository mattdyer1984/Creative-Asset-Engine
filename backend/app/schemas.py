"""
API request/response schemas (Pydantic), kept separate from ORM models
so the two can evolve independently — the API's shape is a contract with
the frontend, the ORM's shape is a contract with the database.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.services.product_profile import ProductProfile


class ProjectCreate(BaseModel):
    name: str
    notes: str | None = None


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    notes: str | None
    created_at: datetime


class ProductCreate(BaseModel):
    display_name: str
    project_id: str | None = None


class ProductRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str | None
    display_name: str
    created_at: datetime


# CreativeBlueprintRead, CreativeRead, and AssignProductRequest (old
# /api/creatives/* schemas) were removed in Phase 2.7 of the
# Slideshow/Slide migration - superseded by SlideshowRead/SlideRead and
# AssignSlideProductRequest further down this file.


class ProductReferenceImageRead(BaseModel):
    """
    Used by GET /api/products/{id}/reference-images - a permanent,
    Product-scoped endpoint unrelated to the Slideshow/Slide migration.
    source_creative_id became nullable in Phase 2.3 (the new pipeline's
    Product Isolation stage populates source_slide_id instead - see
    SlideProductReferenceImageRead), so this must accept null too:
    without this, this endpoint 500s (ResponseValidationError) the
    moment any reference image created by the new pipeline exists for a
    product - reproduced and confirmed before this fix.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    source_creative_id: str | None
    isolation_method: str
    is_current: bool
    created_at: datetime


class ProductLockProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    schema_version: str
    is_current: bool
    structured: dict
    reference_image_ids: list[str]
    created_at: datetime
    # Phase 7.4 (dependency-aware staleness, see MIGRATION_PLAN.md) -
    # computed, not an ORM column; always explicitly supplied by whichever
    # service assembles this response, never left to model_validate.
    is_stale: bool = False
    stale_because: list[str] = []


class ProductSourceImportRequest(BaseModel):
    """Phase 5.6 of Product Intelligence, see MIGRATION_PLAN.md - the only input POST /source-import needs."""

    url: str


class ProductSourceImportRead(BaseModel):
    """
    Phase 5.6. Returns the ProductSourceImport row itself (not the
    assembled profile - that's the separate GET .../profile endpoint) so
    the caller can see success/failure and the error message directly,
    matching create_product/create_project's "return what you just
    created" convention.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    source_type: str
    source_url: str
    fetch_status: str
    error: str | None
    is_current: bool
    created_at: datetime


class ListingRead(BaseModel):
    """Phase 5.11 of the catalogue layer, see MIGRATION_PLAN.md's frozen catalogue ADR."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    source_type: str
    source_url: str
    resolved_product_id: str | None
    resolved_bundle_id: str | None
    price_amount: float | None
    price_currency: str | None
    seller_name: str | None
    rating: float | None
    units_sold: int | None
    shipping_info: str | None
    created_at: datetime


class PendingBundleMemberHintRead(BaseModel):
    """
    A raw pass-through of one adapter-suggested bundle member (see
    app.product_sources.base.BundleMemberHint) for a human to review -
    never itself a resolved Product, per the catalogue ADR's identity
    section (resolution is never automatic).
    """

    label: str
    attributes: dict


class ListingDetailRead(ListingRead):
    """GET /api/listings/{id} - ListingRead plus unresolved member hints, if any."""

    pending_bundle_hints: list[PendingBundleMemberHintRead] = []
    # A suggested default for "name this bundle" - never authoritative,
    # purely a hint the human can override, same as the member hints
    # themselves. None when there's no bundle evidence, or none was found.
    pending_bundle_title: str | None = None


class ListingSourceImportRequest(BaseModel):
    url: str


class ListingResolveExistingProductRequest(BaseModel):
    product_id: str


class ListingResolveNewProductRequest(BaseModel):
    display_name: str


class ListingResolveExistingBundleRequest(BaseModel):
    bundle_id: str


class BundleMemberResolutionRequest(BaseModel):
    """Exactly one of the two product fields must be set - mirrors app.services.listing_import.BundleMemberResolution."""

    existing_product_id: str | None = None
    new_product_display_name: str | None = None
    quantity: int = 1


class ListingResolveNewBundleRequest(BaseModel):
    display_name: str
    members: list[BundleMemberResolutionRequest]


class ProductBundleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str | None
    display_name: str
    created_at: datetime


class BundleMemberProfileRead(BaseModel):
    """
    One member's real, unmodified atomic ProductProfile - the catalogue
    ADR's Bundle View definition: a bundle's "profile" is a list of its
    members' real profiles, never a new merge/vocabulary of its own.
    """

    product_id: str
    quantity: int
    profile: ProductProfile


class BundleViewRead(BaseModel):
    id: str
    display_name: str
    members: list[BundleMemberProfileRead]


class CreativeFingerprintRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    schema_version: str
    is_current: bool
    structured: dict
    created_at: datetime
    is_stale: bool = False
    stale_because: list[str] = []


class MarketingAnalysisRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    is_current: bool
    narrative_text: str
    # Phase 7.3 (Narrative pass, see MIGRATION_PLAN.md) - None for rows
    # created before this field existed; "staleness unknown," not "fresh".
    creative_fingerprint_id: str | None = None
    created_at: datetime
    is_stale: bool = False
    stale_because: list[str] = []


class RecreationPromptRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    schema_version: str
    is_current: bool
    product_lock_profile_id: str
    creative_fingerprint_id: str
    structured: dict
    created_at: datetime
    is_stale: bool = False
    stale_because: list[str] = []


class NarrativeStructureRead(BaseModel):
    """Phase 7.2 of the Narrative pass, see MIGRATION_PLAN.md - structured is {slides, arc_summary}."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    schema_version: str
    is_current: bool
    structured: dict
    created_at: datetime
    is_stale: bool = False
    stale_because: list[str] = []


class OCRResultRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    schema_version: str
    is_current: bool
    raw_text: str
    structured_blocks: list[dict]
    created_at: datetime


class AnalysisRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    analysis_type: str
    provider: str
    model_name: str
    status: str
    error: str | None
    created_at: datetime


# AssembledCreativeBlueprint (old /api/creatives/*'s single-response
# view) was removed in Phase 2.7 of the Slideshow/Slide migration -
# superseded by AssembledSlideshowBlueprint below. ProductLockProfileRead,
# CreativeFingerprintRead, MarketingAnalysisRead, RecreationPromptRead,
# and OCRResultRead were kept (not old-pipeline-exclusive): they're
# still used directly by app/routers/products.py and
# app/services/slideshow_blueprint.py.


# ---------------------------------------------------------------------------
# Slideshow/Slide (new pipeline). The single, canonical, user-facing
# view - AssembledSlideshowBlueprint below - is now the only assembled
# Blueprint view; the old /api/creatives/* surface it paralleled during
# the migration (Phases 2.5-2.6) was removed in Phase 2.7.
# ---------------------------------------------------------------------------


class SlideProductAppearanceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    product_id: str
    product: ProductRead | None
    prominence: str
    confidence: float
    is_current: bool
    created_at: datetime


class SlideRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    slideshow_id: str
    slide_index: int
    original_filename: str
    source_type: str
    source_locator: str
    # Convenience denormalization (via Slide.current_product_appearance)
    # for UI parity with the old CreativeRead.product.
    current_product_appearance: SlideProductAppearanceRead | None = None
    # Phase 6.5 (multi per-slide product detection, see MIGRATION_PLAN.md):
    # exposes Slide.current_product_appearances (plural, added in 6.1) so
    # the frontend can build a real add/remove multi-product picker
    # without fetching the full assembled blueprint - added alongside the
    # unchanged singular field above, same non-breaking pattern.
    current_product_appearances: list[SlideProductAppearanceRead] = []


class SlideshowRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str | None
    imported_at: datetime
    status: str
    slides: list[SlideRead]


class AssignSlideProductRequest(BaseModel):
    product_id: str | None  # null unassigns


class AddSlideProductRequest(BaseModel):
    """
    Phase 6.1 of multi per-slide product detection, see
    MIGRATION_PLAN.md - the additive counterpart to AssignSlideProduct-
    Request above. No null case (unlike assign, "add" always adds a
    product) - removing one is DELETE .../products/{appearance_id}.
    """

    product_id: str


class SlideProductReferenceImageRead(BaseModel):
    """
    Distinct from the older ProductReferenceImageRead above: after Phase
    2.3, ProductReferenceImage.source_creative_id is nullable and new
    rows (from the new pipeline) populate source_slide_id instead - a
    row created by the new pipeline wouldn't validate against the old
    schema's non-nullable source_creative_id field.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    source_slide_id: str
    isolation_method: str
    is_current: bool
    created_at: datetime


class AssembledSlideProductBlueprint(BaseModel):
    """
    One product's full artifact set on a single slide - Phase 6.4 of
    multi per-slide product detection, see MIGRATION_PLAN.md. Replaces
    the old flat product_reference_images/product_lock_profile fields on
    AssembledSlideBlueprint, which silently only ever populated data for
    current_appearances[0] - a slide with 2+ current products now gets
    one of these per product, not just the first one.
    """

    appearance: SlideProductAppearanceRead
    product_reference_images: list[SlideProductReferenceImageRead] = []
    product_lock_profile: ProductLockProfileRead | None = None


class AssembledSlideBlueprint(BaseModel):
    id: str
    slide_index: int
    original_filename: str
    source_type: str
    source_locator: str

    ocr_result: OCRResultRead | None = None
    creative_fingerprint: CreativeFingerprintRead | None = None
    products: list[AssembledSlideProductBlueprint] = []


class AssembledSlideshowBlueprint(BaseModel):
    """
    The single, canonical view of a Slideshow (new-pipeline equivalent
    of AssembledCreativeBlueprint above): every slide-scoped artifact
    per slide, plus the slideshow-scoped artifacts (Marketing Analysis,
    Recreation Prompt), assembled into one response.
    """

    id: str
    status: str
    imported_at: datetime
    project_id: str | None
    source_references: dict

    slides: list[AssembledSlideBlueprint]

    marketing_analysis: MarketingAnalysisRead | None = None
    narrative_structure: NarrativeStructureRead | None = None
    recreation_prompt: RecreationPromptRead | None = None

    failed_stage: str | None = None
    failed_stage_error: str | None = None
