"""
Recreation Prompt Stage (plan §6.3, §10) — the final stage in the pipeline.

Pure composition: reads the current ProductLockProfile and
CreativeFingerprint (both hard prerequisites - unlike Product Lock
Profile's soft dependency on reference images) and composes them into a
provider-neutral Recreation Prompt. Never touches the Creative's image
file and never calls a vision capability - this is enforced structurally
by PromptGenerationProvider's interface (lock_profile: dict, fingerprint:
dict, no image_bytes), not just by convention.

The AI call generates only the creative-direction fields (subject,
composition, style, etc.) - it is never asked to produce
product_lock_profile_id or reference_image_ids, since those are already
known facts, not something an LLM should be asked to recall or
hallucinate. This Stage assembles the final structured_json by merging
the AI's creative direction with a product_lock_reference block built
directly from the ProductLockProfile row.
"""

import json

from sqlalchemy.orm import Session

from app.ai_providers.registry import default_registry
from app.models.analysis_run import ANALYSIS_TYPE_RECREATION_PROMPT
from app.models.creative import Creative
from app.models.creative_blueprint import CreativeBlueprint
from app.models.creative_fingerprint import CreativeFingerprint
from app.models.product_lock_profile import ProductLockProfile
from app.models.recreation_prompt import RecreationPrompt
from app.stages.base import StageResult
from app.stages.execution import mark_failed, mark_succeeded, start_analysis_run

RECREATION_PROMPT_AI_SCHEMA = {
    "type": "object",
    "properties": {
        "subject": {"type": "string"},
        "composition": {"type": "string"},
        "style_direction": {"type": "string"},
        "color_palette": {"type": "array", "items": {"type": "string"}},
        "lighting": {"type": "string"},
        "camera_and_perspective": {"type": "string"},
        "background_environment": {"type": "string"},
        "mood": {"type": "string"},
        "text_overlays": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "role": {
                        "type": "string",
                        "description": "headline, subhead, or cta",
                    },
                    "content": {"type": "string"},
                },
                "required": ["role", "content"],
                "additionalProperties": False,
            },
        },
        "things_to_avoid": {"type": "array", "items": {"type": "string"}},
        "aspect_ratio": {"type": "string"},
        "extensions": {
            "type": "string",
            "description": "Any additional notes that don't fit the fields above.",
        },
    },
    "required": [
        "subject",
        "composition",
        "style_direction",
        "color_palette",
        "lighting",
        "camera_and_perspective",
        "background_environment",
        "mood",
        "text_overlays",
        "things_to_avoid",
        "aspect_ratio",
        "extensions",
    ],
    "additionalProperties": False,
}


class RecreationPromptStage:
    name = "recreation_prompt"

    def run(
        self, db: Session, creative: Creative, blueprint: CreativeBlueprint
    ) -> StageResult:
        if blueprint.current_product_lock_profile_id is None:
            return StageResult(
                succeeded=False,
                error="No Product Lock Profile available yet - run that stage first.",
            )
        if blueprint.current_creative_fingerprint_id is None:
            return StageResult(
                succeeded=False,
                error="No Creative Fingerprint available yet - run that stage first.",
            )

        lock_profile = db.get(ProductLockProfile, blueprint.current_product_lock_profile_id)
        fingerprint = db.get(CreativeFingerprint, blueprint.current_creative_fingerprint_id)
        if lock_profile is None or fingerprint is None:
            return StageResult(
                succeeded=False,
                error="Product Lock Profile or Creative Fingerprint referenced by the Blueprint no longer exists.",
            )

        prompt_provider = default_registry.prompt_generation()

        analysis_run = start_analysis_run(
            db,
            creative_id=creative.id,
            analysis_type=ANALYSIS_TYPE_RECREATION_PROMPT,
            provider="openai",
            model_name=prompt_provider.model,
            durable=True,
        )

        try:
            lock_profile_data = json.loads(lock_profile.structured_json)
            fingerprint_data = json.loads(fingerprint.structured_json)

            ai_result = prompt_provider.generate_recreation_prompt(
                lock_profile=lock_profile_data,
                fingerprint=fingerprint_data,
                response_schema=RECREATION_PROMPT_AI_SCHEMA,
            )

            # Assembled directly from known facts, never asked of the AI.
            final_structured = dict(ai_result)
            final_structured["product_lock_reference"] = {
                "product_lock_profile_id": lock_profile.id,
                "reference_image_ids": json.loads(lock_profile.reference_image_ids_json),
                "immutable_characteristics": lock_profile_data.get(
                    "immutable_characteristics", []
                ),
            }

            db.query(RecreationPrompt).filter(
                RecreationPrompt.creative_id == creative.id,
                RecreationPrompt.is_current.is_(True),
            ).update({"is_current": False})

            recreation_prompt = RecreationPrompt(
                analysis_run_id=analysis_run.id,
                creative_id=creative.id,
                product_lock_profile_id=lock_profile.id,
                creative_fingerprint_id=fingerprint.id,
                structured_json=json.dumps(final_structured),
            )
            db.add(recreation_prompt)
            db.flush()

        except Exception as exc:
            return mark_failed(db, analysis_run, exc, rollback=True)

        blueprint.current_recreation_prompt_id = recreation_prompt.id
        return mark_succeeded(db, analysis_run)
