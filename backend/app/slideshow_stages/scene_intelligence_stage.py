"""
Scene Intelligence Stage — Phase 10.4 of AI Creative Engine vNext (see
MIGRATION_PLAN.md's "ADR: AI Creative Engine vNext" §8). Detects and
scores the regions of a slide's image - the input Creative Intelligence
(same sub-phase) needs to decide what's safe to transform.

Reuses `VisionAnalysisProvider.analyze_creative` unchanged - no new
provider capability needed, same "one shared capability, many
consumers" pattern every other vision-backed stage in this codebase
already follows. Part of `SLIDESHOW_STAGE_PIPELINE` (an analysis pass,
not a paid generation/validation action), mirroring
`SlideCreativeFingerprintStage` structurally (`Slide.
current_scene_analysis_id` pointer, is_current versioning, durable
AnalysisRun).

**Hard constraint enforced in code, never trusted from the AI
response**: any region the model classifies as `region_type="product"`
is force-set to `importance_tier="essential"` after the call returns,
regardless of what tier the model itself assigned - the one thing this
Stage must get right every time, not something to leave to the model's
own judgment call.
"""

from pathlib import Path

from sqlalchemy.orm import Session

from app.ai_providers.registry import default_registry
from app.models.analysis_run import ANALYSIS_TYPE_SCENE_INTELLIGENCE
from app.models.scene_analysis import SceneAnalysis
from app.models.slideshow import Slideshow
from app.slideshow_stages.base import StageResult
from app.stages.execution import mark_failed, mark_succeeded, start_analysis_run

REGION_TYPES = [
    "primary_subject", "secondary_subject", "product", "human_subject",
    "environment", "background", "prop", "decorative_element", "negative_space",
]
IMPORTANCE_TIERS = ["essential", "important", "context", "incidental", "replaceable"]

SCENE_REGION_SCHEMA = {
    "type": "object",
    "properties": {
        "regions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "region_type": {"type": "string", "enum": REGION_TYPES},
                    "x_min": {"type": "number"},
                    "y_min": {"type": "number"},
                    "x_max": {"type": "number"},
                    "y_max": {"type": "number"},
                    "importance_tier": {"type": "string", "enum": IMPORTANCE_TIERS},
                    "notes": {"type": "string"},
                },
                "required": [
                    "region_type", "x_min", "y_min", "x_max", "y_max",
                    "importance_tier", "notes",
                ],
                "additionalProperties": False,
            },
        },
    },
    "required": ["regions"],
    "additionalProperties": False,
}

SCENE_INTELLIGENCE_PROMPT = (
    "Segment this marketing creative into its distinct visual regions and "
    "classify each one. For every region, give a normalized bounding box "
    "(x_min/y_min/x_max/y_max, 0.0-1.0), a region_type (primary_subject, "
    "secondary_subject, product, human_subject, environment, background, "
    "prop, decorative_element, or negative_space), and an importance_tier "
    "rating how safe that region is to change if this creative were "
    "regenerated: essential (must never change - the product itself, a "
    "person's hands/pose directly interacting with it, its exact "
    "positioning), important (should closely match - overall pose, action, "
    "composition), context (the general setting/room type - can be "
    "replaced with a different instance of the same category), incidental "
    "(furniture, decor - free to change), or replaceable (wall art, "
    "background clutter - safe to remove or swap freely). Give a short "
    "note explaining each region's classification."
)


def _enforce_product_region_is_essential(regions: list[dict]) -> list[dict]:
    for region in regions:
        if region["region_type"] == "product":
            region["importance_tier"] = "essential"
    return regions


class SceneIntelligenceStage:
    name = "scene_intelligence"

    def run(self, db: Session, slideshow: Slideshow) -> StageResult:
        slide = slideshow.primary_slide
        vision_provider = default_registry.vision()

        analysis_run = start_analysis_run(
            db,
            slide_id=slide.id,
            analysis_type=ANALYSIS_TYPE_SCENE_INTELLIGENCE,
            provider=vision_provider.provider,
            model_name=vision_provider.model,
            durable=True,
        )

        try:
            image_bytes = Path(slide.stored_file_path).read_bytes()
            result = vision_provider.analyze_creative(
                image_bytes=image_bytes,
                prompt_spec={"prompt": SCENE_INTELLIGENCE_PROMPT, "schema_name": "scene_intelligence"},
                response_schema=SCENE_REGION_SCHEMA,
            )
            regions = _enforce_product_region_is_essential(result["regions"])

            db.query(SceneAnalysis).filter(
                SceneAnalysis.slide_id == slide.id,
                SceneAnalysis.is_current.is_(True),
            ).update({"is_current": False})

            scene_analysis = SceneAnalysis(
                analysis_run_id=analysis_run.id,
                slide_id=slide.id,
                regions_json=regions,
            )
            db.add(scene_analysis)
            db.flush()

        except Exception as exc:
            return mark_failed(db, analysis_run, exc, rollback=True)

        slide.current_scene_analysis_id = scene_analysis.id
        return mark_succeeded(db, analysis_run)
