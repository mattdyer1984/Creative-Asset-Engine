"""
Text Ownership Stage (ADR 0001 §4/§6, Package E).

The stage that makes Packages A and C reachable. Ownership was computed
inside the rendering path and discarded; Package A gave it a home and Package
C taught it to read composition, but nothing produced one during analysis. So
"who owns this block?" could not be answered before generation - which is
exactly when the generator needs to be told what NOT to draw.

Entirely deterministic. Every input already exists by the time this runs:
OCR blocks, the Composition Contract (E1) and the Creative Project Profile
(E2). No provider call, no cost, and no reason for it to fail when a provider
is down.

**It reads the profile's EFFECTIVE values, not the analysed ones.** A user who
set `overlay_policy=remove` has said what should happen to their captions, and
routing that ignored them would make the setting decorative.
"""

import logging

from sqlalchemy.orm import Session

from app.models.analysis_run import ANALYSIS_TYPE_TEXT_OWNERSHIP
from app.models.ocr_result import OCRResult
from app.models.slide import Slide
from app.models.slideshow import Slideshow
from app.services.composition_contract import contract_of, get_current_contract
from app.services.creative_project_profile import (
    effective_copy_policy,
    effective_overlay_policy,
    effective_primary_text_mode,
    effective_typography_system,
    get_current_profile,
)
from app.services.ownership_artifact import record_ownership
from app.services.text_ownership import assert_single_ownership, decide_ownership
from app.slideshow_stages.base import StageResult
from app.stages.execution import mark_failed, mark_succeeded, start_analysis_run

logger = logging.getLogger(__name__)


class SlideTextOwnershipStage:
    name = "text_ownership"

    def run(self, db: Session, slideshow: Slideshow) -> StageResult:
        profile = get_current_profile(db, slideshow.id)
        text_mode = effective_primary_text_mode(profile) if profile else None
        overlay_policy = effective_overlay_policy(profile) if profile else None
        copy_policy = effective_copy_policy(profile) if profile else None
        typography = effective_typography_system(profile) if profile else None

        result: StageResult = StageResult(succeeded=True)
        for slide in slideshow.slides:
            result = self._run_for_slide(
                db, slide,
                text_mode=text_mode,
                overlay_policy=overlay_policy,
                copy_policy=copy_policy,
                capability_level=typography.capability_level if typography else None,
                profile_id=profile.id if profile else None,
            )
            if not result.succeeded:
                return result
        return result

    def _run_for_slide(
        self, db: Session, slide: Slide, *,
        text_mode, overlay_policy, copy_policy, capability_level, profile_id,
    ) -> StageResult:
        analysis_run = start_analysis_run(
            db,
            slide_id=slide.id,
            analysis_type=ANALYSIS_TYPE_TEXT_OWNERSHIP,
            provider="local",
            model_name="deterministic",
            durable=True,
        )

        try:
            blocks = []
            if slide.current_ocr_result_id is not None:
                ocr = db.get(OCRResult, slide.current_ocr_result_id)
                if ocr is not None:
                    blocks = list(ocr.structured_blocks_json or [])

            contract_artifact = get_current_contract(db, slide.id)
            contract = contract_of(contract_artifact)

            kwargs = {"contract": contract, "capability_level": capability_level}
            if text_mode is not None:
                kwargs["project_text_mode"] = text_mode
            if overlay_policy is not None:
                kwargs["overlay_policy"] = overlay_policy

            plan = decide_ownership(blocks, **kwargs)

            # Checked before persistence, not after. An artifact recording a
            # block owned twice is a record of the defect, not a guard
            # against it.
            assert_single_ownership(plan)

            record_ownership(
                db,
                slide_id=slide.id,
                analysis_run_id=analysis_run.id,
                plan=plan,
                project_profile_id=profile_id,
                contract_artifact=contract_artifact,
                effective_copy_policy=str(copy_policy) if copy_policy else None,
                effective_overlay_policy=str(overlay_policy) if overlay_policy else None,
                expected_block_ids={f"block-{i}" for i in range(len(blocks))},
                expected_block_count=len(blocks),
            )
        except Exception as exc:
            return mark_failed(db, analysis_run, exc, rollback=True)

        # Deterministic work makes no provider call, so it gets no row in a
        # ledger that exists to account for paid ones.
        return mark_succeeded(db, analysis_run, emit_provider_call=False)
