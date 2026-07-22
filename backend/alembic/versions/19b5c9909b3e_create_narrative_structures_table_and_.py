"""create narrative_structures table and add current_narrative_structure_id to slideshows

Revision ID: 19b5c9909b3e
Revises: d3bafd6a4965
Create Date: 2026-07-22 20:45:42.738550

Phase 7.2 of the Narrative pass (see MIGRATION_PLAN.md's architecture
direction for this phase). Additive only:

- New narrative_structures table (NarrativeStructure) - the slideshow-
  scoped Analysis Artifact the new Narrative Structure Stage writes.
  ocr_result_ids_json records which OCR result versions (one per slide)
  it was built from, for Phase 7.4's staleness check.
- slideshows gains a new, nullable current_narrative_structure_id
  pointer column, same plain-String pattern as the existing
  current_marketing_analysis_id/current_recreation_prompt_id (not a real
  FK constraint, matching those two).

No batch mode needed - a plain nullable column add with no new FK
constraint, unlike the migrations that needed it (37e53bed7ec8,
d3bafd6a4965).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '19b5c9909b3e'
down_revision: Union[str, None] = 'd3bafd6a4965'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'narrative_structures',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('analysis_run_id', sa.String(length=36), nullable=False),
        sa.Column('schema_version', sa.String(length=16), nullable=False),
        sa.Column('is_current', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('slideshow_id', sa.String(length=36), nullable=False),
        sa.Column('structured_json', sa.JSON(), nullable=False),
        sa.Column('ocr_result_ids_json', sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(['analysis_run_id'], ['analysis_runs.id']),
        sa.ForeignKeyConstraint(['slideshow_id'], ['slideshows.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.add_column('slideshows', sa.Column('current_narrative_structure_id', sa.String(length=36), nullable=True))


def downgrade() -> None:
    op.drop_column('slideshows', 'current_narrative_structure_id')
    op.drop_table('narrative_structures')
