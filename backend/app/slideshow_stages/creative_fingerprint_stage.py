"""
Creative Fingerprint Stage (new pipeline) — Phase 2.4c of the
Slideshow/Slide migration.

Parallel equivalent of app.stages.creative_fingerprint_stage.
CreativeFingerprintStage: reads the slide's current OCR result as
enrichment context if one exists, but does not hard-fail without it -
same reasoning as the old stage. Owns Slide.current_creative_fingerprint_id.

CREATIVE_FINGERPRINT_SCHEMA/PROMPT are duplicated from the old stage
rather than imported from it, same reasoning as the other new stages:
keeps this package fully self-contained so Phase 2.7 can delete the old
stage files cleanly.
"""

from pathlib import Path

from sqlalchemy.orm import Session

from app.ai_providers.registry import default_registry
from app.models.analysis_run import ANALYSIS_TYPE_CREATIVE_FINGERPRINT
from app.models.creative_fingerprint import CreativeFingerprint
from app.models.ocr_result import OCRResult
from app.models.slideshow import Slideshow
from app.slideshow_stages.base import StageResult
from app.stages.execution import mark_failed, mark_succeeded, start_analysis_run

CREATIVE_FINGERPRINT_SCHEMA = {
    "type": "object",
    "properties": {
        "visual_style": {"type": "string"},
        "marketing_objective": {"type": "string"},
        "emotional_appeal": {"type": "array", "items": {"type": "string"}},
        "target_audience": {"type": "string"},
        "color_palette": {"type": "array", "items": {"type": "string"}},
        "typography_style": {"type": "string"},
        "layout_and_composition": {"type": "string"},
        "background_environment": {"type": "string"},
        "lighting_style": {"type": "string"},
        "graphic_style": {"type": "string"},
        "product_prominence": {"type": "string"},
        "marketing_angle": {"type": "string"},
        "visual_hierarchy": {"type": "string"},
        "trust_elements": {
            "type": "array",
            "items": {"type": "string"},
            "description": "e.g. certifications, guarantees, testimonials.",
        },
        "promotional_devices": {
            "type": "array",
            "items": {"type": "string"},
            "description": "e.g. discounts, urgency, social proof.",
        },
        "extensions": {
            "type": "string",
            "description": "Any additional notes that don't fit the fields above.",
        },
    },
    "required": [
        "visual_style",
        "marketing_objective",
        "emotional_appeal",
        "target_audience",
        "color_palette",
        "typography_style",
        "layout_and_composition",
        "background_environment",
        "lighting_style",
        "graphic_style",
        "product_prominence",
        "marketing_angle",
        "visual_hierarchy",
        "trust_elements",
        "promotional_devices",
        "extensions",
    ],
    "additionalProperties": False,
}

CREATIVE_FINGERPRINT_PROMPT = (
    "Analyze this marketing creative and produce a structured description "
    "of its overall visual style, marketing objective, emotional appeal, "
    "target audience, color palette, typography style, layout and "
    "composition, background environment, lighting style, graphic style, "
    "product prominence, marketing angle, visual hierarchy, trust elements "
    "(e.g. certifications, guarantees, testimonials), and promotional "
    "devices (e.g. discounts, urgency, social proof)."
)


class SlideCreativeFingerprintStage:
    name = "creative_fingerprint"

    def run(self, db: Session, slideshow: Slideshow) -> StageResult:
        slide = slideshow.primary_slide
        vision_provider = default_registry.vision()

        analysis_run = start_analysis_run(
            db,
            slide_id=slide.id,
            analysis_type=ANALYSIS_TYPE_CREATIVE_FINGERPRINT,
            provider=vision_provider.provider,
            model_name=vision_provider.model,
            durable=True,
        )

        prompt = CREATIVE_FINGERPRINT_PROMPT
        if slide.current_ocr_result_id is not None:
            ocr_result = db.get(OCRResult, slide.current_ocr_result_id)
            if ocr_result is not None and ocr_result.raw_text:
                prompt += f"\n\nText detected in the image via OCR: {ocr_result.raw_text}"

        try:
            image_bytes = Path(slide.stored_file_path).read_bytes()
            result = vision_provider.analyze_creative(
                image_bytes=image_bytes,
                prompt_spec={"prompt": prompt, "schema_name": "creative_fingerprint"},
                response_schema=CREATIVE_FINGERPRINT_SCHEMA,
            )

            db.query(CreativeFingerprint).filter(
                CreativeFingerprint.slide_id == slide.id,
                CreativeFingerprint.is_current.is_(True),
            ).update({"is_current": False})

            fingerprint = CreativeFingerprint(
                analysis_run_id=analysis_run.id,
                slide_id=slide.id,
                structured_json=result,
            )
            db.add(fingerprint)
            db.flush()

        except Exception as exc:
            return mark_failed(db, analysis_run, exc, rollback=True)

        slide.current_creative_fingerprint_id = fingerprint.id
        return mark_succeeded(db, analysis_run)
