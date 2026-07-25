"""
Creative Fingerprint Stage — Phase 2.4c of the Slideshow/Slide
migration. Originally a parallel equivalent of
app.stages.creative_fingerprint_stage.CreativeFingerprintStage, deleted
in the Phase 2 engineering review; this is now the only Creative
Fingerprint stage. Reads the slide's current OCR result as enrichment
context if one exists, but does not hard-fail without it. Owns
Slide.current_creative_fingerprint_id.

Phase 7.4 (Narrative pass, see MIGRATION_PLAN.md) added
CreativeFingerprint.ocr_result_id, recording which OCR result was
actually incorporated into the prompt (None if OCR wasn't available or
had no text) - a real gap found while building that sub-phase's
staleness service, same category as MarketingAnalysis.
creative_fingerprint_id (7.3).
"""

import time
from pathlib import Path

from sqlalchemy.orm import Session

from app.ai_providers.registry import default_registry
from app.models.analysis_run import ANALYSIS_TYPE_CREATIVE_FINGERPRINT
from app.models.creative_fingerprint import CreativeFingerprint
from app.models.ocr_result import OCRResult
from app.models.slide import Slide
from app.models.slideshow import Slideshow
from app.slideshow_stages.base import StageResult
from app.slideshow_stages.concurrency import run_concurrently
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
        # Phase 10.4 of AI Creative Engine vNext (see MIGRATION_PLAN.md's
        # ADR §8) - the two real gaps that ADR identified in this
        # Stage's existing coverage, added as additive fields rather
        # than a fourth artifact table (per the ADR's own explicit
        # instruction).
        "object_placement": {
            "type": "string",
            "description": "How the product and key objects are physically arranged/positioned in the frame.",
        },
        "emotional_trigger": {
            "type": "string",
            "description": "The specific emotional lever this creative pulls (more granular than emotional_appeal's tag list).",
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
        "object_placement",
        "emotional_trigger",
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
    "(e.g. certifications, guarantees, testimonials), promotional "
    "devices (e.g. discounts, urgency, social proof), object placement "
    "(how the product and key objects are physically arranged/positioned "
    "in the frame), and the specific emotional trigger this creative "
    "pulls (more granular than a general emotional-appeal tag - name the "
    "precise psychological lever, e.g. 'fear of missing a limited window' "
    "rather than just 'urgency')."
)


class SlideCreativeFingerprintStage:
    name = "creative_fingerprint"

    def run(self, db: Session, slideshow: Slideshow) -> StageResult:
        """
        Real-world-diagnosed fix (Generate All, see MIGRATION_PLAN.md):
        widened from `slideshow.primary_slide` only to every slide in
        `slideshow.slides`, mirroring `SlideOCRStage`'s own Phase 7.1
        precedent - unlike Product Isolation/Lock Profile, this stage
        never depended on a product appearance at all, so every slide
        is processed unconditionally, exactly like OCR already does.

        Real-world-diagnosed speed fix (see MIGRATION_PLAN.md): the
        actual `analyze_creative` provider call for every slide now runs
        concurrently (app.slideshow_stages.concurrency). Each slide's
        own OCR-enrichment prompt is built up front, sequentially - a
        real DB read (`db.get(OCRResult, ...)`) that must stay on this
        thread, and building it early doesn't change its content, since
        nothing else in this stage writes OCRResult rows.
        """
        result: StageResult = StageResult(succeeded=True)

        # Real-world-driven cost/quality change (see MIGRATION_PLAN.md) -
        # explicit provider_name="gemini" override: this is one of only
        # two vision_analysis tasks moved to Gemini (Product Lock
        # Profile is the other), a narrower scope the user chose over
        # moving every vision_analysis task at once.
        vision_provider = default_registry.vision(provider_name="gemini")

        entries: list[tuple[Slide, str, str | None]] = []
        for slide in slideshow.slides:
            prompt = CREATIVE_FINGERPRINT_PROMPT
            used_ocr_result_id = None
            if slide.current_ocr_result_id is not None:
                ocr_result = db.get(OCRResult, slide.current_ocr_result_id)
                if ocr_result is not None and ocr_result.raw_text:
                    prompt += f"\n\nText detected in the image via OCR: {ocr_result.raw_text}"
                    used_ocr_result_id = ocr_result.id
            entries.append((slide, prompt, used_ocr_result_id))

        def _analyze(entry: tuple[Slide, str, str | None]):
            slide, prompt, _used_ocr_result_id = entry
            image_bytes = Path(slide.stored_file_path).read_bytes()
            usage: dict = {}
            start = time.perf_counter()
            analysis_result = vision_provider.analyze_creative(
                image_bytes=image_bytes,
                prompt_spec={"prompt": prompt, "schema_name": "creative_fingerprint"},
                response_schema=CREATIVE_FINGERPRINT_SCHEMA,
                usage_sink=usage,
            )
            provider_call_ms = (time.perf_counter() - start) * 1000
            return analysis_result, provider_call_ms, usage

        analysis_results = run_concurrently(entries, _analyze)

        for index, (slide, _prompt, used_ocr_result_id) in enumerate(entries):
            analysis_run = start_analysis_run(
                db,
                slide_id=slide.id,
                analysis_type=ANALYSIS_TYPE_CREATIVE_FINGERPRINT,
                provider=vision_provider.provider,
                model_name=vision_provider.model,
                durable=True,
            )

            try:
                outcome = analysis_results[index]
                if isinstance(outcome, Exception):
                    raise outcome
                analysis_result, provider_call_ms, usage = outcome

                db.query(CreativeFingerprint).filter(
                    CreativeFingerprint.slide_id == slide.id,
                    CreativeFingerprint.is_current.is_(True),
                ).update({"is_current": False})

                fingerprint = CreativeFingerprint(
                    analysis_run_id=analysis_run.id,
                    slide_id=slide.id,
                    ocr_result_id=used_ocr_result_id,
                    structured_json=analysis_result,
                )
                db.add(fingerprint)
                db.flush()

            except Exception as exc:
                return mark_failed(db, analysis_run, exc, rollback=True)

            slide.current_creative_fingerprint_id = fingerprint.id
            result = mark_succeeded(db, analysis_run, provider_call_ms=provider_call_ms, usage=usage)

        return result
