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
"""

import json

from sqlalchemy.orm import Session

from app.ai_providers.registry import default_registry
from app.models.analysis_run import ANALYSIS_TYPE_MARKETING_ANALYSIS
from app.models.creative_fingerprint import CreativeFingerprint
from app.models.marketing_analysis import MarketingAnalysis
from app.models.slideshow import Slideshow
from app.slideshow_stages.base import StageResult
from app.stages.execution import mark_failed, mark_succeeded, start_analysis_run

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

MARKETING_ANALYSIS_PROMPT_TEMPLATE = (
    "Given the following structured analysis of a marketing creative, "
    "write a clear, readable prose summary (2-4 short paragraphs) "
    "connecting these facts into a coherent narrative: what the creative "
    "is trying to achieve, who it's targeting, what emotional appeal it "
    "uses, and why it works as marketing. Write for a marketer who wants "
    "to understand the strategy at a glance, not just a list of facts.\n\n"
    "Structured analysis (JSON):\n{fingerprint_json}"
)


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
            result = text_provider.generate(
                prompt_spec={"prompt": prompt, "schema_name": "marketing_analysis"},
                response_schema=MARKETING_ANALYSIS_SCHEMA,
            )

            db.query(MarketingAnalysis).filter(
                MarketingAnalysis.slideshow_id == slideshow.id,
                MarketingAnalysis.is_current.is_(True),
            ).update({"is_current": False})

            marketing_analysis = MarketingAnalysis(
                analysis_run_id=analysis_run.id,
                slideshow_id=slideshow.id,
                narrative_text=result["narrative"],
            )
            db.add(marketing_analysis)
            db.flush()

        except Exception as exc:
            return mark_failed(db, analysis_run, exc, rollback=True)

        slideshow.current_marketing_analysis_id = marketing_analysis.id
        return mark_succeeded(db, analysis_run)
