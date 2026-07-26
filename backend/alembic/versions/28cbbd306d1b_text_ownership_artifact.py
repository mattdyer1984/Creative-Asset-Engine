"""text ownership artifact

ADR 0001, Package A. Promotes text ownership from a runtime result to a
slide-scoped analysis artifact, so "who owned this block when this image was
produced?" stays answerable after re-analysis.

Additive only. Nothing existing is touched and nothing is back-filled:
historical slides have no recorded ownership because none was recorded, and
inventing one would assert a decision that was never made.

Revision ID: 28cbbd306d1b
Revises: 15f13187c820
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '28cbbd306d1b'
down_revision: Union[str, None] = '15f13187c820'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "text_ownership_artifacts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("analysis_run_id", sa.String(36), sa.ForeignKey("analysis_runs.id"),
                  nullable=False),
        sa.Column("schema_version", sa.String(16), nullable=False, server_default="1.0"),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("slide_id", sa.String(36), sa.ForeignKey("slides.id"), nullable=False),
        sa.Column("project_profile_id", sa.String(36), nullable=True),
        sa.Column("composition_contract_id", sa.String(36), nullable=True),
        sa.Column("ownership_model_version", sa.String(16), nullable=False, server_default="1.0"),
        sa.Column("blocks_json", sa.JSON(), nullable=True),
    )
    op.create_index("ix_text_ownership_artifacts_slide_id",
                    "text_ownership_artifacts", ["slide_id"])
    op.create_index("ix_text_ownership_artifacts_slide_current",
                    "text_ownership_artifacts", ["slide_id", "is_current"])


def downgrade() -> None:
    op.drop_index("ix_text_ownership_artifacts_slide_current",
                  table_name="text_ownership_artifacts")
    op.drop_index("ix_text_ownership_artifacts_slide_id",
                  table_name="text_ownership_artifacts")
    op.drop_table("text_ownership_artifacts")
