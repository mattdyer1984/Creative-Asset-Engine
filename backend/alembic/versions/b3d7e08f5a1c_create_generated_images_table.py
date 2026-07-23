"""create generated_images table

Revision ID: b3d7e08f5a1c
Revises: a1c3e9f2b8d4
Create Date: 2026-07-23 05:10:00.000000

Phase 8.3 of the Generation -> Validation proof of loop (see
MIGRATION_PLAN.md's architecture direction). Additive only: new
generated_images table (GeneratedImage) - the Slide-scoped Analysis
Artifact the new Image Generation Stage writes. Deliberately
slide_id-scoped, not slideshow-scoped like MarketingAnalysis/
CreativeSpecification - see the model's own docstring for why (one
slide first, per the Phase 8 architecture direction). No pointer column
added to slides/slideshows - unlike the other artifacts, GeneratedImage
is queried directly by slide_id + is_current (same pattern
ProductLockProfile/ProductReferenceImage already use), since there's no
existing "current pointer" convention to extend for a brand-new,
deliberately-not-auto-pipelined artifact type.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b3d7e08f5a1c'
down_revision: Union[str, None] = 'a1c3e9f2b8d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'generated_images',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('analysis_run_id', sa.String(length=36), nullable=False),
        sa.Column('schema_version', sa.String(length=16), nullable=False),
        sa.Column('is_current', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('slideshow_id', sa.String(length=36), nullable=False),
        sa.Column('slide_id', sa.String(length=36), nullable=False),
        sa.Column('creative_specification_id', sa.String(length=36), nullable=False),
        sa.Column('provider', sa.String(length=64), nullable=False),
        sa.Column('model_name', sa.String(length=128), nullable=False),
        sa.Column('prompt_used', sa.Text(), nullable=False),
        sa.Column('seed', sa.String(length=128), nullable=True),
        sa.Column('generation_time_seconds', sa.Float(), nullable=False),
        sa.Column('file_path', sa.String(length=1024), nullable=False),
        sa.ForeignKeyConstraint(['analysis_run_id'], ['analysis_runs.id']),
        sa.ForeignKeyConstraint(['slideshow_id'], ['slideshows.id']),
        sa.ForeignKeyConstraint(['slide_id'], ['slides.id']),
        sa.ForeignKeyConstraint(['creative_specification_id'], ['creative_specifications.id']),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('generated_images')
