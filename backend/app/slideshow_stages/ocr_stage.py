"""
OCR Stage (new pipeline) — Phase 2.4a of the Slideshow/Slide migration.

Parallel equivalent of app.stages.ocr_stage.OCRStage: identical
behavior, operating on Slideshow/Slide instead of Creative/
CreativeBlueprint. Owns Slide.current_ocr_result_id (the slide-scoped
equivalent of the old stage owning CreativeBlueprint.current_ocr_result_id).

Not wired into any route yet - see the migration roadmap.

Phase 7.1 (Narrative pass, see MIGRATION_PLAN.md) widened this from
`slideshow.primary_slide` only to every slide in `slideshow.slides` - a
real prerequisite gap found while scoping Phase 7: every per-slide Stage
had only ever operated on the first slide, even after Phase 4 made
multi-slide slideshows real, and Narrative Structure (Phase 7.2) needs
per-slide OCR text across the whole sequence to do anything useful. Pure
orchestration-logic change - `Slide.current_ocr_result_id` has been a
per-slide column since Phase 2.1, no migration needed. Deliberately NOT
extended to Product Isolation/Lock Profile/Creative Fingerprint in this
phase - each of those widened to multi-slide means N vision/AI calls per
slideshow instead of one, a real cost/design tradeoff not required here
(see MIGRATION_PLAN.md's Suggested future improvements).

One slide's OCR failure fails the whole stage (matches the existing
single-slide failure semantics, and "honest failure over silent partial
data") - slides processed before the failing one keep their already-
committed, already-current OCR results; the failing slide and any after
it are simply not attempted this run.
"""

from pathlib import Path

from sqlalchemy.orm import Session

from app.ai_providers.registry import default_registry
from app.models.analysis_run import ANALYSIS_TYPE_OCR
from app.models.ocr_result import OCRResult
from app.models.slideshow import Slideshow
from app.slideshow_stages.base import StageResult
from app.stages.execution import mark_failed, mark_succeeded, start_analysis_run


class SlideOCRStage:
    name = "ocr"

    def run(self, db: Session, slideshow: Slideshow) -> StageResult:
        ocr_provider = default_registry.ocr()

        result: StageResult = StageResult(succeeded=True)
        for slide in slideshow.slides:
            analysis_run = start_analysis_run(
                db,
                slide_id=slide.id,
                analysis_type=ANALYSIS_TYPE_OCR,
                provider=ocr_provider.provider,
                model_name=ocr_provider.model,
                durable=False,
            )

            try:
                image_bytes = Path(slide.stored_file_path).read_bytes()
                extraction = ocr_provider.extract_text(image_bytes)
            except Exception as exc:
                return mark_failed(db, analysis_run, exc, rollback=False)

            if slide.current_ocr_result_id is not None:
                previous_result = db.get(OCRResult, slide.current_ocr_result_id)
                if previous_result is not None:
                    previous_result.is_current = False

            ocr_result = OCRResult(
                analysis_run_id=analysis_run.id,
                slide_id=slide.id,
                raw_text=extraction.raw_text,
                structured_blocks_json=extraction.structured_blocks,
            )
            db.add(ocr_result)
            db.flush()

            slide.current_ocr_result_id = ocr_result.id
            result = mark_succeeded(db, analysis_run)

        return result
