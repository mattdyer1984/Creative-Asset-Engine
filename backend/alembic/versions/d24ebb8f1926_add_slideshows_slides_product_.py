"""add slideshows slides product_appearances tables

Revision ID: d24ebb8f1926
Revises: d7373bd34a85
Create Date: 2026-07-21 22:29:30.555027

Phase 2.1 of the Slideshow/Slide migration: purely additive - three new,
empty tables that nothing reads or writes yet. Creative/CreativeBlueprint
remain the live, authoritative tables. See Phase 2.2 for the backfill
that populates these, and the migration roadmap for the full sequence.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd24ebb8f1926'
down_revision: Union[str, None] = 'd7373bd34a85'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'slideshows',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('project_id', sa.String(length=36), nullable=True),
        sa.Column('imported_at', sa.DateTime(), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('current_marketing_analysis_id', sa.String(length=36), nullable=True),
        sa.Column('current_recreation_prompt_id', sa.String(length=36), nullable=True),
        sa.Column('last_failed_stage', sa.String(length=64), nullable=True),
        sa.Column('last_failed_stage_error', sa.Text(), nullable=True),
        sa.Column('source_references_json', sa.JSON(), nullable=False),
        sa.Column('future_generated_assets_json', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'slides',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('slideshow_id', sa.String(length=36), nullable=False),
        sa.Column('slide_index', sa.Integer(), nullable=False),
        sa.Column('stored_file_path', sa.String(length=1024), nullable=False),
        sa.Column('original_filename', sa.String(length=512), nullable=False),
        sa.Column('source_type', sa.String(length=64), nullable=False),
        sa.Column('source_locator', sa.String(length=2048), nullable=False),
        sa.Column('raw_metadata_json', sa.JSON(), nullable=False),
        sa.Column('current_ocr_result_id', sa.String(length=36), nullable=True),
        sa.Column('current_creative_fingerprint_id', sa.String(length=36), nullable=True),
        sa.ForeignKeyConstraint(['slideshow_id'], ['slideshows.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'product_appearances',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('slide_id', sa.String(length=36), nullable=False),
        sa.Column('product_id', sa.String(length=36), nullable=False),
        sa.Column('x_min', sa.Float(), nullable=True),
        sa.Column('y_min', sa.Float(), nullable=True),
        sa.Column('x_max', sa.Float(), nullable=True),
        sa.Column('y_max', sa.Float(), nullable=True),
        sa.Column('prominence', sa.String(length=32), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=False),
        sa.Column('is_current', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['slide_id'], ['slides.id']),
        sa.ForeignKeyConstraint(['product_id'], ['products.id']),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('product_appearances')
    op.drop_table('slides')
    op.drop_table('slideshows')
