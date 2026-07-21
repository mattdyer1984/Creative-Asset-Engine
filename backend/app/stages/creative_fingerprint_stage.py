"""
Creative Fingerprint Stage (plan §6.3, §9).

Generates the structured Creative Fingerprint via the general-purpose
VisionAnalysisProvider (the same adapter Product Lock Profile Stage
uses, with a different prompt/schema - plan §4's intended reuse).

Reads the current OCR result as enrichment context if one exists, but
does not hard-fail without it - OCR text sharpens fields like
promotional_devices and marketing_angle, but the vision model can still
assess overall visual style, layout, and tone from the image alone.

Same two adaptations from the plan's illustrative schema (§9) as
Product Lock Profile Stage: schema_version is system-assigned, and
"extensions" is a free-text string rather than an open object (OpenAI's
strict Structured Outputs mode requires a fully enumerated shape).
"""

from pathlib import Path

from sqlalchemy.orm import Session

from app.ai_providers.registry import default_registry
from app.models.analysis_run import ANALYSIS_TYPE_CREATIVE_FINGERPRINT
from app.models.creative import Creative
from app.models.creative_blueprint import CreativeBlueprint
from app.models.creative_fingerprint import CreativeFingerprint
from app.models.ocr_result import OCRResult
from app.stages.base import StageResult
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


class CreativeFingerprintStage:
    name = "creative_fingerprint"

    def run(
        self, db: Session, creative: Creative, blueprint: CreativeBlueprint
    ) -> StageResult:
        vision_provider = default_registry.vision()

        analysis_run = start_analysis_run(
            db,
            creative_id=creative.id,
            analysis_type=ANALYSIS_TYPE_CREATIVE_FINGERPRINT,
            provider=vision_provider.provider,
            model_name=vision_provider.model,
            durable=True,
        )

        prompt = CREATIVE_FINGERPRINT_PROMPT
        if blueprint.current_ocr_result_id is not None:
            ocr_result = db.get(OCRResult, blueprint.current_ocr_result_id)
            if ocr_result is not None and ocr_result.raw_text:
                prompt += f"\n\nText detected in the image via OCR: {ocr_result.raw_text}"

        try:
            image_bytes = Path(creative.stored_file_path).read_bytes()
            result = vision_provider.analyze_creative(
                image_bytes=image_bytes,
                prompt_spec={"prompt": prompt, "schema_name": "creative_fingerprint"},
                response_schema=CREATIVE_FINGERPRINT_SCHEMA,
            )

            db.query(CreativeFingerprint).filter(
                CreativeFingerprint.creative_id == creative.id,
                CreativeFingerprint.is_current.is_(True),
            ).update({"is_current": False})

            fingerprint = CreativeFingerprint(
                analysis_run_id=analysis_run.id,
                creative_id=creative.id,
                structured_json=result,
            )
            db.add(fingerprint)
            db.flush()

        except Exception as exc:
            return mark_failed(db, analysis_run, exc, rollback=True)

        blueprint.current_creative_fingerprint_id = fingerprint.id
        return mark_succeeded(db, analysis_run)
