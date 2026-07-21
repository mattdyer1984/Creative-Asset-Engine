"""
OCR Stage — the first stage in STAGE_PIPELINE (plan §6.3).

Reads the Creative's stored image, calls the configured OCRProvider, and
writes a new AnalysisRun + OCRResult (Analysis Artifact). Owns
CreativeBlueprint.current_ocr_result_id.
"""

from pathlib import Path

from sqlalchemy.orm import Session

from app.ai_providers.registry import default_registry
from app.models.analysis_run import ANALYSIS_TYPE_OCR
from app.models.creative import Creative
from app.models.creative_blueprint import CreativeBlueprint
from app.models.ocr_result import OCRResult
from app.stages.base import StageResult
from app.stages.execution import mark_failed, mark_succeeded, start_analysis_run


class OCRStage:
    name = "ocr"

    def run(
        self, db: Session, creative: Creative, blueprint: CreativeBlueprint
    ) -> StageResult:
        ocr_provider = default_registry.ocr()

        analysis_run = start_analysis_run(
            db,
            creative_id=creative.id,
            analysis_type=ANALYSIS_TYPE_OCR,
            provider=ocr_provider.provider,
            model_name=ocr_provider.model,
            durable=False,
        )

        try:
            image_bytes = Path(creative.stored_file_path).read_bytes()
            extraction = ocr_provider.extract_text(image_bytes)
        except Exception as exc:
            return mark_failed(db, analysis_run, exc, rollback=False)

        # Flip the previous current OCRResult (if any) via the Blueprint's
        # own pointer - the Blueprint's current_ocr_result_id is the single
        # source of truth for "what's current," so we use it directly
        # rather than re-deriving the same answer with a separate
        # `WHERE is_current=True` table scan.
        if blueprint.current_ocr_result_id is not None:
            previous_result = db.get(OCRResult, blueprint.current_ocr_result_id)
            if previous_result is not None:
                previous_result.is_current = False

        ocr_result = OCRResult(
            analysis_run_id=analysis_run.id,
            creative_id=creative.id,
            raw_text=extraction.raw_text,
            structured_blocks_json=extraction.structured_blocks,
        )
        db.add(ocr_result)
        db.flush()

        blueprint.current_ocr_result_id = ocr_result.id
        return mark_succeeded(db, analysis_run)
