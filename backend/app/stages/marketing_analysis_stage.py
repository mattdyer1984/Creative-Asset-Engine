"""
Marketing Analysis Stage (plan §6.3, §9).

Reads the current CreativeFingerprint - a hard prerequisite, unlike
Product Lock Profile Stage's reference images. Marketing Analysis is
explicitly a second pass OVER the Fingerprint's JSON (plan §9), so
without one there's nothing to analyze.

Uses TextGenerationProvider, not vision - this stage never looks at the
image itself, only the structured Fingerprint already produced from it.
"""

from sqlalchemy.orm import Session

from app.ai_providers.registry import default_registry
from app.models.analysis_run import (
    ANALYSIS_TYPE_MARKETING_ANALYSIS,
    STATUS_FAILED,
    STATUS_SUCCEEDED,
    AnalysisRun,
)
from app.models.creative import Creative
from app.models.creative_blueprint import CreativeBlueprint
from app.models.creative_fingerprint import CreativeFingerprint
from app.models.marketing_analysis import MarketingAnalysis
from app.stages.base import StageResult

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


class MarketingAnalysisStage:
    name = "marketing_analysis"

    def run(
        self, db: Session, creative: Creative, blueprint: CreativeBlueprint
    ) -> StageResult:
        if blueprint.current_creative_fingerprint_id is None:
            return StageResult(
                succeeded=False,
                error="No Creative Fingerprint available yet - run Creative Fingerprint Stage first.",
            )

        fingerprint = db.get(CreativeFingerprint, blueprint.current_creative_fingerprint_id)
        if fingerprint is None:
            return StageResult(
                succeeded=False,
                error="Creative Fingerprint referenced by the Blueprint no longer exists.",
            )

        text_provider = default_registry.text_generation()

        analysis_run = AnalysisRun(
            creative_id=creative.id,
            analysis_type=ANALYSIS_TYPE_MARKETING_ANALYSIS,
            provider="openai",
            model_name=text_provider.model,
        )
        db.add(analysis_run)
        db.commit()
        db.refresh(analysis_run)

        try:
            prompt = MARKETING_ANALYSIS_PROMPT_TEMPLATE.format(
                fingerprint_json=fingerprint.structured_json
            )
            result = text_provider.generate(
                prompt_spec={"prompt": prompt, "schema_name": "marketing_analysis"},
                response_schema=MARKETING_ANALYSIS_SCHEMA,
            )

            db.query(MarketingAnalysis).filter(
                MarketingAnalysis.creative_id == creative.id,
                MarketingAnalysis.is_current.is_(True),
            ).update({"is_current": False})

            marketing_analysis = MarketingAnalysis(
                analysis_run_id=analysis_run.id,
                creative_id=creative.id,
                narrative_text=result["narrative"],
            )
            db.add(marketing_analysis)
            db.flush()

        except Exception as exc:
            db.rollback()
            analysis_run.status = STATUS_FAILED
            analysis_run.error = str(exc)
            db.commit()
            return StageResult(succeeded=False, error=str(exc))

        analysis_run.status = STATUS_SUCCEEDED
        blueprint.current_marketing_analysis_id = marketing_analysis.id
        db.commit()

        return StageResult(succeeded=True)
