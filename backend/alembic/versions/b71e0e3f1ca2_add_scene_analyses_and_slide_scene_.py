"""add scene analyses and slide scene analysis pointer

Revision ID: b71e0e3f1ca2
Revises: 16bdd82acfd7
Create Date: 2026-07-23 11:32:36.816781

Phase 10.4 of AI Creative Engine vNext (see MIGRATION_PLAN.md's "ADR:
AI Creative Engine vNext" §8). Additive only: one new table
(SceneAnalysis, AnalysisArtifactMixin-shaped) plus one new nullable
column on slides (current_scene_analysis_id).

No batch mode needed - scene_analyses is a brand-new table (CREATE
TABLE, not ALTER), and current_scene_analysis_id has no FK constraint,
matching current_ocr_result_id/current_creative_fingerprint_id's own
plain-string-pointer convention on this same table (same precedent as
19b5c9909b3e/dab9d7104321's nullable-no-FK column additions).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b71e0e3f1ca2'
down_revision: Union[str, None] = '16bdd82acfd7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'scene_analyses',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('analysis_run_id', sa.String(length=36), nullable=False),
        sa.Column('schema_version', sa.String(length=16), nullable=False),
        sa.Column('is_current', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('slide_id', sa.String(length=36), nullable=False),
        sa.Column('regions_json', sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(['analysis_run_id'], ['analysis_runs.id']),
        sa.ForeignKeyConstraint(['slide_id'], ['slides.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.add_column('slides', sa.Column('current_scene_analysis_id', sa.String(length=36), nullable=True))


def downgrade() -> None:
    op.drop_column('slides', 'current_scene_analysis_id')
    op.drop_table('scene_analyses')
