"""
API request/response schemas (Pydantic), kept separate from ORM models
so the two can evolve independently — the API's shape is a contract with
the frontend, the ORM's shape is a contract with the database.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


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


class CreativeFingerprintRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    schema_version: str
    is_current: bool
    structured: dict
    created_at: datetime


class MarketingAnalysisRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    is_current: bool
    narrative_text: str
    created_at: datetime


class RecreationPromptRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    schema_version: str
    is_current: bool
    product_lock_profile_id: str
    creative_fingerprint_id: str
    structured: dict
    created_at: datetime


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


class SlideshowRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str | None
    imported_at: datetime
    status: str
    slides: list[SlideRead]


class AssignSlideProductRequest(BaseModel):
    product_id: str | None  # null unassigns


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


class AssembledSlideBlueprint(BaseModel):
    id: str
    slide_index: int
    original_filename: str
    source_type: str
    source_locator: str

    ocr_result: OCRResultRead | None = None
    creative_fingerprint: CreativeFingerprintRead | None = None
    product_appearances: list[SlideProductAppearanceRead] = []
    product_reference_images: list[SlideProductReferenceImageRead] = []
    product_lock_profile: ProductLockProfileRead | None = None


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
    recreation_prompt: RecreationPromptRead | None = None

    failed_stage: str | None = None
    failed_stage_error: str | None = None
