"""creative project profile

ADR 0001 §14, WP-1.1. The one durable, slideshow-scoped source of truth for
how a creative project should be recreated, introduced minimal and extended
in place by later work packages - deliberately not a temporary table that a
later migration retires.

Additive only. No existing table is touched, nothing is back-filled, and the
slide-level pipeline is unchanged: until WP-1.5A wires the profile into
generation, this table is written and read by nothing in the hot path. That
is what makes the downgrade safe.

Analysis and human decisions occupy separate columns on purpose. Re-analysis
overwrites `analysed_*` and must never touch `user_*`; a single JSON document
holding both would make that unenforceable.

Revision ID: 15f13187c820
Revises: 73360967e88f
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '15f13187c820'
down_revision: Union[str, None] = '73360967e88f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "creative_project_profiles",
        # AnalysisArtifactMixin - same four columns as every other artifact.
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("analysis_run_id", sa.String(36), sa.ForeignKey("analysis_runs.id"),
                  nullable=False),
        sa.Column("schema_version", sa.String(16), nullable=False, server_default="1.0"),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),

        sa.Column("slideshow_id", sa.String(36), sa.ForeignKey("slideshows.id"), nullable=False),

        # What the analyser inferred. Nullable: an honest "not determined"
        # beats a default that reads as a finding.
        sa.Column("analysed_primary_text_mode", sa.String(32), nullable=True),
        sa.Column("analysed_text_mode_confidence", sa.Float(), nullable=True),
        sa.Column("analysed_typography_system_json", sa.JSON(), nullable=True),
        sa.Column("classification_evidence_json", sa.JSON(), nullable=True),

        # What a human decided. Never written by the analyser; null means no
        # opinion has been expressed, not agreement.
        sa.Column("user_primary_text_mode", sa.String(32), nullable=True),
        sa.Column("user_copy_policy", sa.String(32), nullable=True),
        sa.Column("user_overlay_policy", sa.String(32), nullable=True),
        sa.Column("user_production_value_strategy", sa.String(32), nullable=True),
        sa.Column("user_typography_overrides_json", sa.JSON(), nullable=True),
    )
    op.create_index(
        "ix_creative_project_profiles_slideshow_id",
        "creative_project_profiles", ["slideshow_id"],
    )
    # The hot query is "the current profile for this slideshow".
    op.create_index(
        "ix_creative_project_profiles_slideshow_current",
        "creative_project_profiles", ["slideshow_id", "is_current"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_creative_project_profiles_slideshow_current",
        table_name="creative_project_profiles",
    )
    op.drop_index(
        "ix_creative_project_profiles_slideshow_id",
        table_name="creative_project_profiles",
    )
    op.drop_table("creative_project_profiles")
