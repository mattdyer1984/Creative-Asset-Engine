"""
OCR Stage — the first stage in STAGE_PIPELINE (plan §6.3).

Reads the Creative's stored image, calls the configured OCRProvider, and
writes a new AnalysisRun + OCRResult (Analysis Artifact). Owns
CreativeBlueprint.current_ocr_result_id.
"""

import json
from pathlib import Path

from sqlalchemy.orm import Session

from app.ai_providers.registry import default_registry
from app.models.analysis_run import (
    ANALYSIS_TYPE_OCR,
    STATUS_FAILED,
    STATUS_SUCCEEDED,
    AnalysisRun,
)
from app.models.creative import Creative
from app.models.creative_blueprint import CreativeBlueprint
from app.models.ocr_result import OCRResult
from app.stages.base import StageResult


class OCRStage:
    name = "ocr"

    def run(
        self, db: Session, creative: Creative, blueprint: CreativeBlueprint
    ) -> StageResult:
        provider = default_registry.ocr()

        analysis_run = AnalysisRun(
            creative_id=creative.id,
            analysis_type=ANALYSIS_TYPE_OCR,
            provider="openai",  # TODO(M4+): read from providers_config once
                                 # more than one provider is registered for
                                 # this capability, rather than hardcoding.
            model_name=provider.model,
        )
        db.add(analysis_run)
        db.flush()

        try:
            image_bytes = Path(creative.stored_file_path).read_bytes()
            extraction = provider.extract_text(image_bytes)
        except Exception as exc:
            analysis_run.status = STATUS_FAILED
            analysis_run.error = str(exc)
            db.commit()
            return StageResult(succeeded=False, error=str(exc))

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
            structured_blocks_json=json.dumps(extraction.structured_blocks),
        )
        db.add(ocr_result)
        db.flush()

        analysis_run.status = STATUS_SUCCEEDED
        blueprint.current_ocr_result_id = ocr_result.id
        db.commit()

        return StageResult(succeeded=True)
