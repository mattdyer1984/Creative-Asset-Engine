"""create image_validation_results table

Revision ID: c4e91a6d2f7b
Revises: b3d7e08f5a1c
Create Date: 2026-07-23 06:00:00.000000

Phase 8.4 of the Generation -> Validation proof of loop (see
MIGRATION_PLAN.md's architecture direction). Additive only: new
image_validation_results table (ImageValidationResult) - closes the
loop, judging a GeneratedImage against the canonical Product Profile's
immutable fields. Same "query directly by owning-id + is_current, no
pointer column" pattern as generated_images (b3d7e08f5a1c) - see that
migration's docstring for why.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4e91a6d2f7b'
down_revision: Union[str, None] = 'b3d7e08f5a1c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'image_validation_results',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('analysis_run_id', sa.String(length=36), nullable=False),
        sa.Column('schema_version', sa.String(length=16), nullable=False),
        sa.Column('is_current', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('generated_image_id', sa.String(length=36), nullable=False),
        sa.Column('product_id', sa.String(length=36), nullable=False),
        sa.Column('passed', sa.Boolean(), nullable=False),
        sa.Column('field_checks_json', sa.JSON(), nullable=False),
        sa.Column('overall_explanation', sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(['analysis_run_id'], ['analysis_runs.id']),
        sa.ForeignKeyConstraint(['generated_image_id'], ['generated_images.id']),
        sa.ForeignKeyConstraint(['product_id'], ['products.id']),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('image_validation_results')
