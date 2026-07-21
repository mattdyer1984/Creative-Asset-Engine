"""
Assembles the single, canonical Creative Blueprint view (plan §1
principle 7, §11 M7) from the six independent Analysis Artifacts.

This is the one place that knows how to gather everything - the router
calls this and nothing else, so the "what does a fully-understood
Creative look like" logic lives in one testable function rather than
being reconstructed in the route handler.
"""

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.creative import Creative
from app.models.creative_fingerprint import CreativeFingerprint
from app.models.marketing_analysis import MarketingAnalysis
from app.models.ocr_result import OCRResult
from app.models.product_lock_profile import ProductLockProfile
from app.models.product_reference_image import ProductReferenceImage
from app.models.recreation_prompt import RecreationPrompt
from app.schemas import (
    AssembledCreativeBlueprint,
    CreativeFingerprintRead,
    MarketingAnalysisRead,
    OCRResultRead,
    ProductLockProfileRead,
    ProductReferenceImageRead,
    RecreationPromptRead,
)


def assemble_creative_blueprint(db: Session, creative: Creative) -> AssembledCreativeBlueprint:
    blueprint = creative.blueprint

    ocr_result = None
    if blueprint.current_ocr_result_id:
        row = db.get(OCRResult, blueprint.current_ocr_result_id)
        if row is not None:
            ocr_result = OCRResultRead(
                id=row.id,
                schema_version=row.schema_version,
                is_current=row.is_current,
                raw_text=row.raw_text,
                structured_blocks=json.loads(row.structured_blocks_json),
                created_at=row.created_at,
            )

    product_reference_images: list[ProductReferenceImageRead] = []
    if creative.product_id:
        stmt = select(ProductReferenceImage).where(
            ProductReferenceImage.product_id == creative.product_id,
            ProductReferenceImage.is_current.is_(True),
        )
        product_reference_images = [
            ProductReferenceImageRead.model_validate(row) for row in db.scalars(stmt)
        ]

    product_lock_profile = None
    if blueprint.current_product_lock_profile_id:
        row = db.get(ProductLockProfile, blueprint.current_product_lock_profile_id)
        if row is not None:
            product_lock_profile = ProductLockProfileRead(
                id=row.id,
                schema_version=row.schema_version,
                is_current=row.is_current,
                structured=json.loads(row.structured_json),
                reference_image_ids=json.loads(row.reference_image_ids_json),
                created_at=row.created_at,
            )

    creative_fingerprint = None
    if blueprint.current_creative_fingerprint_id:
        row = db.get(CreativeFingerprint, blueprint.current_creative_fingerprint_id)
        if row is not None:
            creative_fingerprint = CreativeFingerprintRead(
                id=row.id,
                schema_version=row.schema_version,
                is_current=row.is_current,
                structured=json.loads(row.structured_json),
                created_at=row.created_at,
            )

    marketing_analysis = None
    if blueprint.current_marketing_analysis_id:
        row = db.get(MarketingAnalysis, blueprint.current_marketing_analysis_id)
        if row is not None:
            marketing_analysis = MarketingAnalysisRead.model_validate(row)

    recreation_prompt = None
    if blueprint.current_recreation_prompt_id:
        row = db.get(RecreationPrompt, blueprint.current_recreation_prompt_id)
        if row is not None:
            recreation_prompt = RecreationPromptRead(
                id=row.id,
                schema_version=row.schema_version,
                is_current=row.is_current,
                product_lock_profile_id=row.product_lock_profile_id,
                creative_fingerprint_id=row.creative_fingerprint_id,
                structured=json.loads(row.structured_json),
                created_at=row.created_at,
            )

    return AssembledCreativeBlueprint(
        id=creative.id,
        status=blueprint.status,
        original_filename=creative.original_filename,
        source_type=creative.source_type,
        source_locator=creative.source_locator,
        imported_at=creative.imported_at,
        project_id=creative.project_id,
        product_id=creative.product_id,
        product=creative.product,
        source_references=json.loads(blueprint.source_references_json),
        ocr_result=ocr_result,
        product_reference_images=product_reference_images,
        product_lock_profile=product_lock_profile,
        creative_fingerprint=creative_fingerprint,
        marketing_analysis=marketing_analysis,
        recreation_prompt=recreation_prompt,
        failed_stage=blueprint.last_failed_stage,
        failed_stage_error=blueprint.last_failed_stage_error,
    )
