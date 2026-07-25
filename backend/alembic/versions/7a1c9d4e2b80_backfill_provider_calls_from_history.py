"""backfill provider_calls from historical analysis_runs and generated_images

Revision ID: 7a1c9d4e2b80
Revises: 6f43f6087bd1
Create Date: 2026-07-25

Reconstructs historical spend records so cost reporting is not blind to
everything that happened before ProviderCall existed.

Every row created here is stamped `record_source='legacy_aggregate'`,
because it is genuinely NOT known to represent exactly one provider
call. A historical AnalysisRun may have covered one call, several calls
(image_validation_stage makes two under a single run), aggregated usage,
or incomplete usage. Labelling them lets reporting exclude reconstructed
data cleanly rather than silently mixing it with genuine per-call rows.

`cost_status` is 'unknown' for every backfilled row, and that is
accurate rather than lazy: verified against the real development
database, 0 of 512 historical AnalysisRun rows carry a non-null
estimated_cost_usd, because pricing.yaml held only empty placeholders
until WP-1. There is no cost figure to preserve - only the fact that a
billable call occurred, with whatever token counts were captured.

Deliberately self-contained: uses raw SQL and a literal capability map
rather than importing application code, so it keeps working if the app's
modules move or change shape later.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "7a1c9d4e2b80"
down_revision: Union[str, None] = "6f43f6087bd1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# AnalysisRun.analysis_type is a PIPELINE-STAGE axis; capability is the
# BILLING axis. They are not the same thing - several stages share one
# capability. Anything unrecognised becomes 'unknown' rather than being
# forced into a plausible-looking bucket.
_CAPABILITY_BY_ANALYSIS_TYPE = {
    "ocr": "ocr",
    "product_isolation": "product_isolation",
    "product_lock_profile": "vision_analysis",
    "creative_fingerprint": "vision_analysis",
    "scene_intelligence": "vision_analysis",
    "image_validation": "vision_analysis",
    "marketing_analysis": "text_generation",
    "narrative_structure": "text_generation",
    "creative_specification": "prompt_generation",
    "recreation_prompt": "prompt_generation",
    "generated_image": "image_generation",
}

_RUN_REASON = (
    "legacy aggregate reconstructed from analysis_runs; this row may represent "
    "more than one provider call, and no rate was configured when it ran"
)
_IMAGE_REASON = (
    "legacy aggregate reconstructed from generated_images; no per-image rate was "
    "configured when it ran"
)


def upgrade() -> None:
    connection = op.get_bind()

    case_sql = " ".join(
        f"WHEN '{atype}' THEN '{capability}'"
        for atype, capability in _CAPABILITY_BY_ANALYSIS_TYPE.items()
    )

    # 1. Token-billed calls, from AnalysisRun rows that captured usage.
    connection.execute(
        sa.text(
            f"""
            INSERT INTO provider_calls (
                id, created_at, provider, model, capability,
                prompt_tokens, completion_tokens, provider_latency_ms,
                estimated_cost_usd, cost_status, cost_status_reason,
                record_source, analysis_run_id, slide_id, slideshow_id
            )
            SELECT
                lower(hex(randomblob(16))),
                COALESCE(finished_at, created_at),
                provider,
                model_name,
                CASE analysis_type {case_sql} ELSE 'unknown' END,
                prompt_tokens,
                completion_tokens,
                provider_call_ms,
                NULL,
                'unknown',
                :run_reason,
                'legacy_aggregate',
                id,
                slide_id,
                slideshow_id
            FROM analysis_runs
            WHERE prompt_tokens IS NOT NULL OR completion_tokens IS NOT NULL
            """
        ),
        {"run_reason": _RUN_REASON},
    )

    # 2. Image-billed calls. These are billed per image, never by token,
    #    so they are absent from the query above entirely - without this
    #    the historical record would show analysis spend and no image
    #    spend, which is the more expensive half.
    connection.execute(
        sa.text(
            """
            INSERT INTO provider_calls (
                id, created_at, provider, model, capability,
                image_count, provider_latency_ms,
                estimated_cost_usd, cost_status, cost_status_reason,
                record_source, generated_image_id, slide_id, slideshow_id
            )
            SELECT
                lower(hex(randomblob(16))),
                created_at,
                provider,
                model_name,
                'image_generation',
                1,
                CASE WHEN generation_time_seconds IS NOT NULL
                     THEN generation_time_seconds * 1000 END,
                NULL,
                'unknown',
                :image_reason,
                'legacy_aggregate',
                id,
                slide_id,
                slideshow_id
            FROM generated_images
            """
        ),
        {"image_reason": _IMAGE_REASON},
    )


def downgrade() -> None:
    # Only removes what this migration created. Genuine per_call rows
    # written by the running application are untouched.
    op.get_bind().execute(
        sa.text("DELETE FROM provider_calls WHERE record_source = 'legacy_aggregate'")
    )
