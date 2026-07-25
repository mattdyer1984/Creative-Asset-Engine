"""
Marketing Analysis Stage (new pipeline) — Phase 2.4d of the
Slideshow/Slide migration.

Parallel equivalent of app.stages.marketing_analysis_stage.
MarketingAnalysisStage. The first slideshow-scoped (not slide-scoped)
new stage: reads the Creative Fingerprint via the slide (fingerprints
are slide-scoped), but owns Slideshow.current_marketing_analysis_id and
writes MarketingAnalysis.slideshow_id, since marketing analysis is a
property of the slideshow's overall strategy, not any one slide - see
Slideshow's module docstring.

MARKETING_ANALYSIS_SCHEMA/PROMPT_TEMPLATE duplicated from the old stage,
same self-containment reasoning as the other new stages.

Phase 7.3 (Narrative pass, see MIGRATION_PLAN.md) added
MarketingAnalysis.creative_fingerprint_id, recording which Creative
Fingerprint version this was actually generated from - a real gap fix
(the artifact was generated from the fingerprint but never recorded
which one), and the prerequisite Phase 7.4's dependency-aware staleness
check needs.
"""

import json
import time

from sqlalchemy.orm import Session

from app.ai_providers.registry import default_registry
from app.models.analysis_run import ANALYSIS_TYPE_MARKETING_ANALYSIS
from app.models.creative_fingerprint import CreativeFingerprint
from app.models.marketing_analysis import MarketingAnalysis
from app.models.slideshow import Slideshow
from app.slideshow_stages.base import StageResult
from app.stages.execution import mark_failed, mark_succeeded, start_analysis_run
from app.prompts import analysis as _analysis_prompts

MARKETING_ANALYSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "narrative": {
            "type": "string",
            "description": (
                "A readable prose summary (2-4 short paragraphs) explaining "
                "the creative's marketing strategy and why it works."
            ),
        },
    },
    "required": ["narrative"],
    "additionalProperties": False,
}

# Prompt text moved to app/prompts/ (WP-3) so it has an id, a version and a
# content hash. Re-exported under its original name: call sites and tests
# are deliberately untouched by the move.
MARKETING_ANALYSIS_PROMPT_TEMPLATE = _analysis_prompts.MARKETING_ANALYSIS.template


class SlideshowMarketingAnalysisStage:
    name = "marketing_analysis"

    def run(self, db: Session, slideshow: Slideshow) -> StageResult:
        slide = slideshow.primary_slide

        if slide.current_creative_fingerprint_id is None:
            return StageResult(
                succeeded=False,
                error="No Creative Fingerprint available yet - run Creative Fingerprint Stage first.",
            )

        fingerprint = db.get(CreativeFingerprint, slide.current_creative_fingerprint_id)
        if fingerprint is None:
            return StageResult(
                succeeded=False,
                error="Creative Fingerprint referenced by the Slide no longer exists.",
            )

        text_provider = default_registry.text_generation()

        analysis_run = start_analysis_run(
            db,
            slideshow_id=slideshow.id,
            analysis_type=ANALYSIS_TYPE_MARKETING_ANALYSIS,
            provider=text_provider.provider,
            model_name=text_provider.model,
            durable=True,
        )

        try:
            # fingerprint.structured_json is a native dict (JSON column) -
            # re-serialize explicitly so the prompt text is well-formed
            # JSON, not Python's dict repr().
            prompt = MARKETING_ANALYSIS_PROMPT_TEMPLATE.format(
                fingerprint_json=json.dumps(fingerprint.structured_json)
            )
            usage: dict = {}
            call_start = time.perf_counter()
            result = text_provider.generate(
                prompt_spec={"prompt": prompt, "schema_name": "marketing_analysis"},
                response_schema=MARKETING_ANALYSIS_SCHEMA,
                usage_sink=usage,
            )
            provider_call_ms = (time.perf_counter() - call_start) * 1000

            db.query(MarketingAnalysis).filter(
                MarketingAnalysis.slideshow_id == slideshow.id,
                MarketingAnalysis.is_current.is_(True),
            ).update({"is_current": False})

            marketing_analysis = MarketingAnalysis(
                analysis_run_id=analysis_run.id,
                slideshow_id=slideshow.id,
                creative_fingerprint_id=fingerprint.id,
                narrative_text=result["narrative"],
            )
            db.add(marketing_analysis)
            db.flush()

        except Exception as exc:
            return mark_failed(db, analysis_run, exc, rollback=True)

        slideshow.current_marketing_analysis_id = marketing_analysis.id
        return mark_succeeded(db, analysis_run, provider_call_ms=provider_call_ms, usage=usage)
