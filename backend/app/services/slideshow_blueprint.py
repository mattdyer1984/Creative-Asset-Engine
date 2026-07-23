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

Phase 6.4 (multi per-slide product detection, see MIGRATION_PLAN.md)
regrouped each slide's product-scoped artifacts (reference images, lock
profile) per product instead of flattening them for only
current_appearances[0] - AssembledSlideBlueprint.products is a list with
one AssembledSlideProductBlueprint per current ProductAppearance, so a
slide with 2+ current products surfaces all of their data, not just the
first one silently. This is a breaking response-shape change (the old
flat product_appearances/product_reference_images/product_lock_profile
fields are gone), landed together with its frontend consumer (Phase 6.5)
in the same slice per the plan.

Phase 7.4 (dependency-aware staleness, see MIGRATION_PLAN.md) wires
app.services.staleness's compute-on-read checks into every dependent
artifact's *Read schema here - is_stale/stale_because are never ORM
columns, always computed fresh on every assembly, same compute-on-read
philosophy as this whole module.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.creative_fingerprint import CreativeFingerprint
from app.models.creative_specification import CreativeSpecification
from app.models.marketing_analysis import MarketingAnalysis
from app.models.narrative_structure import NarrativeStructure
from app.models.ocr_result import OCRResult
from app.models.product_appearance import ProductAppearance
from app.models.product_lock_profile import ProductLockProfile
from app.models.product_reference_image import ProductReferenceImage
from app.models.scene_analysis import SceneAnalysis
from app.models.slide import Slide
from app.models.slideshow import Slideshow
from app.schemas import (
    AssembledSlideBlueprint,
    AssembledSlideProductBlueprint,
    AssembledSlideshowBlueprint,
    CreativeFingerprintRead,
    CreativeSpecificationRead,
    MarketingAnalysisRead,
    NarrativeStructureRead,
    OCRResultRead,
    ProductLockProfileRead,
    SceneAnalysisRead,
    SceneRegionRead,
    SlideProductAppearanceRead,
    SlideProductReferenceImageRead,
)
from app.services.staleness import (
    creative_fingerprint_staleness,
    creative_specification_staleness,
    marketing_analysis_staleness,
    narrative_structure_staleness,
    product_lock_profile_staleness,
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
            staleness = creative_fingerprint_staleness(db, row)
            creative_fingerprint = CreativeFingerprintRead(
                id=row.id,
                schema_version=row.schema_version,
                is_current=row.is_current,
                structured=row.structured_json,
                created_at=row.created_at,
                is_stale=staleness.is_stale,
                stale_because=staleness.stale_because,
            )

    scene_analysis = None
    if slide.current_scene_analysis_id:
        row = db.get(SceneAnalysis, slide.current_scene_analysis_id)
        if row is not None:
            scene_analysis = SceneAnalysisRead(
                id=row.id,
                schema_version=row.schema_version,
                is_current=row.is_current,
                regions=[SceneRegionRead(**region) for region in row.regions_json],
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

    products = [_assemble_slide_product(db, appearance) for appearance in current_appearances]

    return AssembledSlideBlueprint(
        id=slide.id,
        slide_index=slide.slide_index,
        original_filename=slide.original_filename,
        source_type=slide.source_type,
        source_locator=slide.source_locator,
        ocr_result=ocr_result,
        creative_fingerprint=creative_fingerprint,
        scene_analysis=scene_analysis,
        products=products,
    )


def _assemble_slide_product(
    db: Session, appearance: ProductAppearance
) -> AssembledSlideProductBlueprint:
    ref_image_rows = db.scalars(
        select(ProductReferenceImage).where(
            ProductReferenceImage.product_id == appearance.product_id,
            ProductReferenceImage.is_current.is_(True),
        )
    )
    product_reference_images = [
        SlideProductReferenceImageRead.model_validate(row) for row in ref_image_rows
    ]

    lock_profile_row = db.scalars(
        select(ProductLockProfile).where(
            ProductLockProfile.product_id == appearance.product_id,
            ProductLockProfile.is_current.is_(True),
        )
    ).first()
    product_lock_profile = None
    if lock_profile_row is not None:
        staleness = product_lock_profile_staleness(db, lock_profile_row)
        product_lock_profile = ProductLockProfileRead(
            id=lock_profile_row.id,
            schema_version=lock_profile_row.schema_version,
            is_current=lock_profile_row.is_current,
            structured=lock_profile_row.structured_json,
            reference_image_ids=lock_profile_row.reference_image_ids_json,
            created_at=lock_profile_row.created_at,
            is_stale=staleness.is_stale,
            stale_because=staleness.stale_because,
        )

    return AssembledSlideProductBlueprint(
        appearance=SlideProductAppearanceRead.model_validate(appearance),
        product_reference_images=product_reference_images,
        product_lock_profile=product_lock_profile,
    )


def assemble_slideshow_blueprint(db: Session, slideshow: Slideshow) -> AssembledSlideshowBlueprint:
    marketing_analysis = None
    if slideshow.current_marketing_analysis_id:
        row = db.get(MarketingAnalysis, slideshow.current_marketing_analysis_id)
        if row is not None:
            staleness = marketing_analysis_staleness(db, row)
            marketing_analysis = MarketingAnalysisRead(
                id=row.id,
                is_current=row.is_current,
                narrative_text=row.narrative_text,
                creative_fingerprint_id=row.creative_fingerprint_id,
                created_at=row.created_at,
                is_stale=staleness.is_stale,
                stale_because=staleness.stale_because,
            )

    narrative_structure = None
    if slideshow.current_narrative_structure_id:
        row = db.get(NarrativeStructure, slideshow.current_narrative_structure_id)
        if row is not None:
            staleness = narrative_structure_staleness(db, row)
            narrative_structure = NarrativeStructureRead(
                id=row.id,
                schema_version=row.schema_version,
                is_current=row.is_current,
                structured=row.structured_json,
                created_at=row.created_at,
                is_stale=staleness.is_stale,
                stale_because=staleness.stale_because,
            )

    creative_specification = None
    if slideshow.current_creative_specification_id:
        row = db.get(CreativeSpecification, slideshow.current_creative_specification_id)
        if row is not None:
            staleness = creative_specification_staleness(db, row)
            creative_specification = CreativeSpecificationRead(
                id=row.id,
                schema_version=row.schema_version,
                is_current=row.is_current,
                product_lock_profile_id=row.product_lock_profile_id,
                creative_fingerprint_id=row.creative_fingerprint_id,
                structured=row.structured_json,
                created_at=row.created_at,
                is_stale=staleness.is_stale,
                stale_because=staleness.stale_because,
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
        narrative_structure=narrative_structure,
        creative_specification=creative_specification,
        failed_stage=slideshow.last_failed_stage,
        failed_stage_error=slideshow.last_failed_stage_error,
    )
