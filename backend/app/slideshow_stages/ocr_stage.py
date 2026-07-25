"""
OCR Stage — Phase 2.4a of the Slideshow/Slide migration. Originally a
parallel equivalent of app.stages.ocr_stage.OCRStage, deleted in the
Phase 2 engineering review; this is now the only OCR stage, wired into
SLIDESHOW_STAGE_PIPELINE and run by every /analyze call. Owns
Slide.current_ocr_result_id.

Phase 7.1 (Narrative pass, see MIGRATION_PLAN.md) widened this from
`slideshow.primary_slide` only to every slide in `slideshow.slides` - a
real prerequisite gap found while scoping Phase 7: every per-slide Stage
had only ever operated on the first slide, even after Phase 4 made
multi-slide slideshows real, and Narrative Structure (Phase 7.2) needs
per-slide OCR text across the whole sequence to do anything useful. Pure
orchestration-logic change - `Slide.current_ocr_result_id` has been a
per-slide column since Phase 2.1, no migration needed. At the time, this
was deliberately NOT extended to Product Isolation/Lock Profile/Creative
Fingerprint/Scene Intelligence - each of those widened to multi-slide
means N vision/AI calls per slideshow instead of one, a real cost/design
tradeoff not required until something actually needed it. Generate All
(see MIGRATION_PLAN.md) was that something - all four now follow this
exact same pattern.

One slide's OCR failure fails the whole stage (matches the existing
single-slide failure semantics, and "honest failure over silent partial
data") - slides processed before the failing one keep their already-
committed, already-current OCR results; the failing slide and any after
it are simply not attempted this run.

Real-world-diagnosed speed fix (Generate All follow-up, see
MIGRATION_PLAN.md): the actual `extract_text` provider call for every
slide now runs concurrently (app.slideshow_stages.concurrency), not one
slide at a time - real timing data from a real multi-slide /analyze run
showed this stage's own wall-clock time scaling linearly with slide
count even though every slide's OCR call is fully independent of every
other's. Every DB write still happens afterward, sequentially, in
original slide order - only the slow network call itself moved off the
sequential path. The "failure stops the run" semantics above are now
"a failure stops the DB-writing pass" specifically - every slide's call
still fires regardless (see app.slideshow_stages.concurrency's own
docstring for why that tradeoff was accepted), but a failing slide's
result still stops this stage from persisting anything for that slide
or any slide after it in the original order, exactly as before.
"""

import time
from pathlib import Path

from sqlalchemy.orm import Session

from app.ai_providers.registry import default_registry
from app.models.analysis_run import ANALYSIS_TYPE_OCR
from app.models.ocr_result import OCRResult
from app.models.slide import Slide
from app.models.slideshow import Slideshow
from app.slideshow_stages.base import StageResult
from app.slideshow_stages.concurrency import run_concurrently
from app.stages.execution import mark_failed, mark_succeeded, start_analysis_run


class SlideOCRStage:
    name = "ocr"

    def run(self, db: Session, slideshow: Slideshow) -> StageResult:
        ocr_provider = default_registry.ocr()
        result: StageResult = StageResult(succeeded=True)

        def _extract(slide: Slide):
            image_bytes = Path(slide.stored_file_path).read_bytes()
            usage: dict = {}
            start = time.perf_counter()
            extraction = ocr_provider.extract_text(image_bytes, usage_sink=usage)
            provider_call_ms = (time.perf_counter() - start) * 1000
            return extraction, provider_call_ms, usage

        extraction_results = run_concurrently(slideshow.slides, _extract)

        for index, slide in enumerate(slideshow.slides):
            analysis_run = start_analysis_run(
                db,
                slide_id=slide.id,
                analysis_type=ANALYSIS_TYPE_OCR,
                provider=ocr_provider.provider,
                model_name=ocr_provider.model,
                durable=False,
            )

            outcome = extraction_results[index]
            if isinstance(outcome, Exception):
                # Nothing has been written for this slide yet (durable=False
                # defers all DB writes until after the provider call
                # succeeds - see app.stages.execution's docstring), so
                # there's genuinely nothing to roll back here; committing
                # the already-flushed "pending" AnalysisRun as failed is
                # both correct and preserves its audit row.
                return mark_failed(db, analysis_run, outcome, rollback=False)
            extraction, provider_call_ms, usage = outcome

            try:
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
            except Exception as exc:
                # New (Tier 1.2 reliability fix): this section used to
                # have no try/except at all, so a failure here (e.g. a
                # constraint violation on flush) propagated straight out
                # of run() and out of the orchestrator, leaving the
                # Slideshow stuck rather than landing on STATUS_FAILED.
                # rollback=True (not False, unlike the branch above) is
                # required here, not just consistent with the majority
                # pattern - a failed db.flush() leaves the session's
                # transaction unusable until rolled back, and since
                # analysis_run was itself only flushed (never committed)
                # under durable=False, the rollback takes its row with it;
                # the StageResult - the thing the orchestrator actually
                # acts on - is unaffected either way.
                return mark_failed(db, analysis_run, exc, rollback=True)

            result = mark_succeeded(db, analysis_run, provider_call_ms=provider_call_ms, usage=usage)

        return result
