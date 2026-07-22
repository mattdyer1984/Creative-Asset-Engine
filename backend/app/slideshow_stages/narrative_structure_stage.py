"""
Narrative Structure Stage (new pipeline) — Phase 7.2 of the Narrative
pass (see MIGRATION_PLAN.md's architecture direction for Phase 7).

Genuinely new work, not a migration of an old stage - no legacy
equivalent exists. Slideshow-scoped, like Marketing Analysis/Recreation
Prompt: owns Slideshow.current_narrative_structure_id, writes
NarrativeStructure.slideshow_id.

Deliberately text-only (TextGenerationProvider, the same capability
Marketing Analysis already uses) rather than vision-based - no
multi-image AI-provider capability exists today
(VisionAnalysisProvider.analyze_creative takes exactly one image), and
building one is real, undesigned AI-provider work out of scope for this
sub-phase (see MIGRATION_PLAN.md's Suggested future improvements).
Classifies each slide's narrative beat (hook/story/reveal/proof/cta/
other) from that slide's current OCR text alone, in slide_index order -
depends on Phase 7.1's OCR-across-every-slide widening.

Honesty over guessing: a slide with no current OCR result, or an empty
raw_text, contributes no signal a text-only model could classify from -
it is never sent to the AI and is force-assigned "unclassifiable" by
this stage's own code, not left to the model to self-report (which would
depend on the model reliably following an instruction rather than the
code guaranteeing it). If literally every slide lacks OCR text, the
whole stage fails with a clear prerequisite error, mirroring every other
stage's "the one thing I need doesn't exist yet" pattern - there being
nothing at all to classify is different from some slides being
unclassifiable while others aren't.
"""

import json

from sqlalchemy.orm import Session

from app.ai_providers.registry import default_registry
from app.models.analysis_run import ANALYSIS_TYPE_NARRATIVE_STRUCTURE
from app.models.narrative_structure import NarrativeStructure
from app.models.ocr_result import OCRResult
from app.models.slideshow import Slideshow
from app.slideshow_stages.base import StageResult
from app.stages.execution import mark_failed, mark_succeeded, start_analysis_run

BEAT_UNCLASSIFIABLE = "unclassifiable"
VALID_BEATS = {"hook", "story", "reveal", "proof", "cta", "other", BEAT_UNCLASSIFIABLE}

NARRATIVE_STRUCTURE_SCHEMA = {
    "type": "object",
    "properties": {
        "slides": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "slide_index": {"type": "integer"},
                    "beat": {
                        "type": "string",
                        "enum": ["hook", "story", "reveal", "proof", "cta", "other"],
                    },
                },
                "required": ["slide_index", "beat"],
                "additionalProperties": False,
            },
        },
        "arc_summary": {
            "type": "string",
            "description": "A short (1-2 sentence) summary of the overall persuasion arc across the sequence.",
        },
    },
    "required": ["slides", "arc_summary"],
    "additionalProperties": False,
}

NARRATIVE_STRUCTURE_PROMPT_TEMPLATE = (
    "The following is the on-screen text extracted from each slide of a "
    "marketing slideshow, in display order. Classify each slide's role in "
    "the overall persuasion narrative using exactly one of: hook (grabs "
    "attention), story (builds context/relatability), reveal (introduces "
    "the product/solution), proof (evidence/credibility - reviews, "
    "results, comparisons), cta (call to action), or other (doesn't fit "
    "the above). Then write a short 1-2 sentence summary of the overall "
    "arc.\n\nSlides:\n{slides_json}"
)


class SlideshowNarrativeStructureStage:
    name = "narrative_structure"

    def run(self, db: Session, slideshow: Slideshow) -> StageResult:
        slides = slideshow.slides

        ocr_by_slide: dict[str, OCRResult | None] = {}
        for slide in slides:
            ocr_by_slide[slide.id] = (
                db.get(OCRResult, slide.current_ocr_result_id)
                if slide.current_ocr_result_id
                else None
            )

        textful_slides = [
            slide for slide in slides if ocr_by_slide[slide.id] and ocr_by_slide[slide.id].raw_text.strip()
        ]
        if not textful_slides:
            return StageResult(
                succeeded=False,
                error="No OCR text available on any slide yet - run OCR first.",
            )

        text_provider = default_registry.text_generation()

        analysis_run = start_analysis_run(
            db,
            slideshow_id=slideshow.id,
            analysis_type=ANALYSIS_TYPE_NARRATIVE_STRUCTURE,
            provider=text_provider.provider,
            model_name=text_provider.model,
            durable=True,
        )

        try:
            slides_payload = [
                {"slide_index": slide.slide_index, "text": ocr_by_slide[slide.id].raw_text}
                for slide in textful_slides
            ]
            prompt = NARRATIVE_STRUCTURE_PROMPT_TEMPLATE.format(slides_json=json.dumps(slides_payload))
            result = text_provider.generate(
                prompt_spec={"prompt": prompt, "schema_name": "narrative_structure"},
                response_schema=NARRATIVE_STRUCTURE_SCHEMA,
            )

            beats_by_index = {item["slide_index"]: item["beat"] for item in result["slides"]}
            final_slides = [
                {
                    "slide_id": slide.id,
                    "slide_index": slide.slide_index,
                    "beat": beats_by_index.get(slide.slide_index, BEAT_UNCLASSIFIABLE)
                    if ocr_by_slide[slide.id] and ocr_by_slide[slide.id].raw_text.strip()
                    else BEAT_UNCLASSIFIABLE,
                }
                for slide in slides
            ]

            db.query(NarrativeStructure).filter(
                NarrativeStructure.slideshow_id == slideshow.id,
                NarrativeStructure.is_current.is_(True),
            ).update({"is_current": False})

            narrative_structure = NarrativeStructure(
                analysis_run_id=analysis_run.id,
                slideshow_id=slideshow.id,
                structured_json={"slides": final_slides, "arc_summary": result["arc_summary"]},
                ocr_result_ids_json=[
                    ocr_by_slide[slide.id].id if ocr_by_slide[slide.id] else None for slide in slides
                ],
            )
            db.add(narrative_structure)
            db.flush()

        except Exception as exc:
            return mark_failed(db, analysis_run, exc, rollback=True)

        slideshow.current_narrative_structure_id = narrative_structure.id
        return mark_succeeded(db, analysis_run)
