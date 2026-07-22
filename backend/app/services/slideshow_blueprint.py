"""
Assembles the single, canonical Slideshow Blueprint view (new pipeline)
- Phase 2.5 of the Slideshow/Slide migration, parallel equivalent of
app.services.creative_blueprint.assemble_creative_blueprint.

Per-slide artifacts (OCR, Creative Fingerprint) are read directly off
each Slide's current_*_id pointer. Product Lock Profile has no such
pointer by design (see Phase 2.4b) - it's resolved dynamically per slide
via that slide's current ProductAppearance -> product_id -> that
product's current ProductLockProfile, so it can never disagree with its
own is_current flag the way the old pointer-based lookup could.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.creative_fingerprint import CreativeFingerprint
from app.models.marketing_analysis import MarketingAnalysis
from app.models.ocr_result import OCRResult
from app.models.product_appearance import ProductAppearance
from app.models.product_lock_profile import ProductLockProfile
from app.models.product_reference_image import ProductReferenceImage
from app.models.recreation_prompt import RecreationPrompt
from app.models.slide import Slide
from app.models.slideshow import Slideshow
from app.schemas import (
    AssembledSlideBlueprint,
    AssembledSlideshowBlueprint,
    CreativeFingerprintRead,
    MarketingAnalysisRead,
    OCRResultRead,
    ProductLockProfileRead,
    RecreationPromptRead,
    SlideProductAppearanceRead,
    SlideProductReferenceImageRead,
)


def _assemble_slide(db: Session, slide: Slide) -> AssembledSlideBlueprint:
    ocr_result = None
    if slide.current_ocr_result_id:
        row = db.get(OCRResult, slide.current_ocr_result_id)
        if row is not None:
            ocr_result = OCRResultRead(
                id=row.id,
                schema_version=row.schema_version,
                is_current=row.is_current,
                raw_text=row.raw_text,
                structured_blocks=row.structured_blocks_json,
                created_at=row.created_at,
            )

    creative_fingerprint = None
    if slide.current_creative_fingerprint_id:
        row = db.get(CreativeFingerprint, slide.current_creative_fingerprint_id)
        if row is not None:
            creative_fingerprint = CreativeFingerprintRead(
                id=row.id,
                schema_version=row.schema_version,
                is_current=row.is_current,
                structured=row.structured_json,
                created_at=row.created_at,
            )

    current_appearances = list(
        db.scalars(
            select(ProductAppearance).where(
                ProductAppearance.slide_id == slide.id,
                ProductAppearance.is_current.is_(True),
            )
        )
    )
    appearance_reads = [
        SlideProductAppearanceRead.model_validate(a) for a in current_appearances
    ]

    product_reference_images: list[SlideProductReferenceImageRead] = []
    product_lock_profile = None
    if current_appearances:
        # Phase 2 invariant: at most one current appearance per slide -
        # the single-product assumption preserved until Phase 5.
        product_id = current_appearances[0].product_id

        ref_image_rows = db.scalars(
            select(ProductReferenceImage).where(
                ProductReferenceImage.product_id == product_id,
                ProductReferenceImage.is_current.is_(True),
            )
        )
        product_reference_images = [
            SlideProductReferenceImageRead.model_validate(row) for row in ref_image_rows
        ]

        lock_profile_row = db.scalars(
            select(ProductLockProfile).where(
                ProductLockProfile.product_id == product_id,
                ProductLockProfile.is_current.is_(True),
            )
        ).first()
        if lock_profile_row is not None:
            product_lock_profile = ProductLockProfileRead(
                id=lock_profile_row.id,
                schema_version=lock_profile_row.schema_version,
                is_current=lock_profile_row.is_current,
                structured=lock_profile_row.structured_json,
                reference_image_ids=lock_profile_row.reference_image_ids_json,
                created_at=lock_profile_row.created_at,
            )

    return AssembledSlideBlueprint(
        id=slide.id,
        slide_index=slide.slide_index,
        original_filename=slide.original_filename,
        source_type=slide.source_type,
        source_locator=slide.source_locator,
        ocr_result=ocr_result,
        creative_fingerprint=creative_fingerprint,
        product_appearances=appearance_reads,
        product_reference_images=product_reference_images,
        product_lock_profile=product_lock_profile,
    )


def assemble_slideshow_blueprint(db: Session, slideshow: Slideshow) -> AssembledSlideshowBlueprint:
    marketing_analysis = None
    if slideshow.current_marketing_analysis_id:
        row = db.get(MarketingAnalysis, slideshow.current_marketing_analysis_id)
        if row is not None:
            marketing_analysis = MarketingAnalysisRead.model_validate(row)

    recreation_prompt = None
    if slideshow.current_recreation_prompt_id:
        row = db.get(RecreationPrompt, slideshow.current_recreation_prompt_id)
        if row is not None:
            recreation_prompt = RecreationPromptRead(
                id=row.id,
                schema_version=row.schema_version,
                is_current=row.is_current,
                product_lock_profile_id=row.product_lock_profile_id,
                creative_fingerprint_id=row.creative_fingerprint_id,
                structured=row.structured_json,
                created_at=row.created_at,
            )

    slides = [_assemble_slide(db, slide) for slide in slideshow.slides]

    return AssembledSlideshowBlueprint(
        id=slideshow.id,
        status=slideshow.status,
        imported_at=slideshow.imported_at,
        project_id=slideshow.project_id,
        source_references=slideshow.source_references_json,
        slides=slides,
        marketing_analysis=marketing_analysis,
        recreation_prompt=recreation_prompt,
        failed_stage=slideshow.last_failed_stage,
        failed_stage_error=slideshow.last_failed_stage_error,
    )
