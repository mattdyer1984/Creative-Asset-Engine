"""
OCR Stage (new pipeline) — Phase 2.4a of the Slideshow/Slide migration.

Parallel equivalent of app.stages.ocr_stage.OCRStage: identical
behavior, operating on Slideshow/Slide instead of Creative/
CreativeBlueprint. Owns Slide.current_ocr_result_id (the slide-scoped
equivalent of the old stage owning CreativeBlueprint.current_ocr_result_id).

Not wired into any route yet - see the migration roadmap.
"""

from pathlib import Path

from sqlalchemy.orm import Session

from app.ai_providers.registry import default_registry
from app.models.analysis_run import ANALYSIS_TYPE_OCR
from app.models.ocr_result import OCRResult
from app.models.slideshow import Slideshow
from app.slideshow_stages.base import StageResult
from app.slideshow_stages.execution import start_analysis_run
from app.stages.execution import mark_failed, mark_succeeded


class SlideOCRStage:
    name = "ocr"

    def run(self, db: Session, slideshow: Slideshow) -> StageResult:
        slide = slideshow.slide
        ocr_provider = default_registry.ocr()

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
        return mark_succeeded(db, analysis_run)
