"""create generation reference sets and library columns

Revision ID: dab9d7104321
Revises: c4e91a6d2f7b
Create Date: 2026-07-23 07:58:28.845857

Phase 9.1 of Product Lock v2 (see MIGRATION_PLAN.md's "ADR: Canonical
Product Reference" §1/§2). Additive only: two new tables
(GenerationReferenceSet, GenerationReferenceSetImage) plus four new
nullable columns on product_reference_images (quality_score,
quality_reasons_json, role, library_status) - the columns that turn
that existing table into the Canonical Reference Library
(library_status="included", queried on read, not a new snapshot table).

No batch mode needed for any of this - two brand-new tables, and four
nullable columns with no FK constraint on an existing table, same
precedent as 19b5c9909b3e. The FK-adding column additions to
generated_images and image_validation_results are separate, batch-mode
migrations (per this project's own established rule), not part of this
one.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'dab9d7104321'
down_revision: Union[str, None] = 'c4e91a6d2f7b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'generation_reference_sets',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('analysis_run_id', sa.String(length=36), nullable=True),
        sa.Column('schema_version', sa.String(length=16), nullable=False),
        sa.Column('is_current', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('generated_image_id', sa.String(length=36), nullable=True),
        sa.Column('selection_method_json', sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(['analysis_run_id'], ['analysis_runs.id']),
        sa.ForeignKeyConstraint(['generated_image_id'], ['generated_images.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'generation_reference_set_images',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('generation_reference_set_id', sa.String(length=36), nullable=False),
        sa.Column('product_reference_image_id', sa.String(length=36), nullable=False),
        sa.Column('product_id', sa.String(length=36), nullable=False),
        sa.Column('role', sa.String(length=64), nullable=True),
        sa.Column('rank', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['generation_reference_set_id'], ['generation_reference_sets.id']),
        sa.ForeignKeyConstraint(['product_reference_image_id'], ['product_reference_images.id']),
        sa.ForeignKeyConstraint(['product_id'], ['products.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.add_column('product_reference_images', sa.Column('quality_score', sa.Float(), nullable=True))
    op.add_column(
        'product_reference_images', sa.Column('quality_reasons_json', sa.JSON(), nullable=True)
    )
    op.add_column(
        'product_reference_images', sa.Column('role', sa.String(length=64), nullable=True)
    )
    op.add_column(
        'product_reference_images', sa.Column('library_status', sa.String(length=32), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('product_reference_images', 'library_status')
    op.drop_column('product_reference_images', 'role')
    op.drop_column('product_reference_images', 'quality_reasons_json')
    op.drop_column('product_reference_images', 'quality_score')
    op.drop_table('generation_reference_set_images')
    op.drop_table('generation_reference_sets')
