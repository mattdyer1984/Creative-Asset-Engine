"""create product_source_imports table and extend product_reference_images

Revision ID: 37e53bed7ec8
Revises: 612553c9bfdc
Create Date: 2026-07-22 16:21:42.041453

Phase 5.1 of Product Intelligence (see MIGRATION_PLAN.md). Additive only:

- New product_source_imports table (ProductSourceImport) - records one
  fetch of a Product Source (a URL) for a Product. Not built on
  AnalysisArtifactMixin's analysis_run_id pattern - a URL fetch isn't an
  AI analysis run.
- product_reference_images gains a third, nullable provenance column,
  source_product_source_import_id, for images sourced from a Product
  Source rather than cropped from a creative/slide.
- product_reference_images.analysis_run_id relaxes from NOT NULL to
  nullable - a URL-sourced reference image has no AnalysisRun to point
  at, same reasoning as ProductSourceImport itself. Safe: it only
  permits null: every row the existing Product Isolation Stage writes
  continues to always supply a value.

Batch mode required for the product_reference_images ALTER (SQLite can't
change a column's nullability or add a column with a new FK constraint
outside batch mode) - same as every prior migration that touched this
table's nullability (see 612553c9bfdc).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '37e53bed7ec8'
down_revision: Union[str, None] = '612553c9bfdc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'product_source_imports',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('product_id', sa.String(length=36), nullable=False),
        sa.Column('is_current', sa.Boolean(), nullable=False),
        sa.Column('source_type', sa.String(length=64), nullable=False),
        sa.Column('source_url', sa.String(length=2048), nullable=False),
        sa.Column('fetch_status', sa.String(length=16), nullable=False),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('raw_response_json', sa.JSON(), nullable=True),
        sa.Column('normalized_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['product_id'], ['products.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    with op.batch_alter_table('product_reference_images') as batch_op:
        batch_op.alter_column('analysis_run_id', existing_type=sa.String(length=36), nullable=True)
        batch_op.add_column(sa.Column('source_product_source_import_id', sa.String(length=36), nullable=True))
        batch_op.create_foreign_key(
            'fk_product_reference_images_source_product_source_import_id',
            'product_source_imports',
            ['source_product_source_import_id'],
            ['id'],
        )


def downgrade() -> None:
    with op.batch_alter_table('product_reference_images') as batch_op:
        batch_op.drop_constraint(
            'fk_product_reference_images_source_product_source_import_id', type_='foreignkey'
        )
        batch_op.drop_column('source_product_source_import_id')
        batch_op.alter_column('analysis_run_id', existing_type=sa.String(length=36), nullable=False)

    op.drop_table('product_source_imports')
