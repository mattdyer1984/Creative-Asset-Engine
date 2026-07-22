"""add slide and slideshow FK columns to artifact tables

Revision ID: 612553c9bfdc
Revises: 8a76d08b06fe
Create Date: 2026-07-22 06:00:08.244388

Phase 2.3 of the Slideshow/Slide migration. Gives the five artifact
tables (plus AnalysisRun) a path to reference the new entities without
duplicating the artifact data itself: adds nullable slide_id/
slideshow_id/source_slide_id columns, and relaxes the existing
creative_id/source_creative_id columns from NOT NULL to nullable (safe -
it only permits null; every row the old, still-live pipeline writes
continues to always supply a value). Both old and new FK columns are
backfilled for existing rows using Phase 2.2's mapping (Slideshow.id ==
Creative.id, and each Slideshow has exactly one Slide in Phase 2).

Batch mode required throughout: SQLite can't ALTER a column's
nullability or add a column with a new FK constraint outside batch mode.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '612553c9bfdc'
down_revision: Union[str, None] = '8a76d08b06fe'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('ocr_results') as batch_op:
        batch_op.alter_column('creative_id', existing_type=sa.String(length=36), nullable=True)
        batch_op.add_column(sa.Column('slide_id', sa.String(length=36), nullable=True))
        batch_op.create_foreign_key('fk_ocr_results_slide_id_slides', 'slides', ['slide_id'], ['id'])

    with op.batch_alter_table('creative_fingerprints') as batch_op:
        batch_op.alter_column('creative_id', existing_type=sa.String(length=36), nullable=True)
        batch_op.add_column(sa.Column('slide_id', sa.String(length=36), nullable=True))
        batch_op.create_foreign_key(
            'fk_creative_fingerprints_slide_id_slides', 'slides', ['slide_id'], ['id']
        )

    with op.batch_alter_table('marketing_analyses') as batch_op:
        batch_op.alter_column('creative_id', existing_type=sa.String(length=36), nullable=True)
        batch_op.add_column(sa.Column('slideshow_id', sa.String(length=36), nullable=True))
        batch_op.create_foreign_key(
            'fk_marketing_analyses_slideshow_id_slideshows', 'slideshows', ['slideshow_id'], ['id']
        )

    with op.batch_alter_table('recreation_prompts') as batch_op:
        batch_op.alter_column('creative_id', existing_type=sa.String(length=36), nullable=True)
        batch_op.add_column(sa.Column('slideshow_id', sa.String(length=36), nullable=True))
        batch_op.create_foreign_key(
            'fk_recreation_prompts_slideshow_id_slideshows', 'slideshows', ['slideshow_id'], ['id']
        )

    with op.batch_alter_table('product_reference_images') as batch_op:
        batch_op.alter_column('source_creative_id', existing_type=sa.String(length=36), nullable=True)
        batch_op.add_column(sa.Column('source_slide_id', sa.String(length=36), nullable=True))
        batch_op.create_foreign_key(
            'fk_product_reference_images_source_slide_id_slides', 'slides', ['source_slide_id'], ['id']
        )

    with op.batch_alter_table('analysis_runs') as batch_op:
        batch_op.alter_column('creative_id', existing_type=sa.String(length=36), nullable=True)
        batch_op.add_column(sa.Column('slide_id', sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column('slideshow_id', sa.String(length=36), nullable=True))
        batch_op.create_foreign_key('fk_analysis_runs_slide_id_slides', 'slides', ['slide_id'], ['id'])
        batch_op.create_foreign_key(
            'fk_analysis_runs_slideshow_id_slideshows', 'slideshows', ['slideshow_id'], ['id']
        )

    bind = op.get_bind()

    # Slide-scoped artifacts: slide_id via the 1:1 Slideshow -> Slide
    # backfilled in Phase 2.2 (Slideshow.id == Creative.id).
    for table in ('ocr_results', 'creative_fingerprints'):
        bind.execute(sa.text(
            f"UPDATE {table} SET slide_id = "
            f"(SELECT slides.id FROM slides WHERE slides.slideshow_id = {table}.creative_id) "
            f"WHERE creative_id IS NOT NULL"
        ))
    bind.execute(sa.text(
        "UPDATE product_reference_images SET source_slide_id = "
        "(SELECT slides.id FROM slides WHERE slides.slideshow_id = product_reference_images.source_creative_id) "
        "WHERE source_creative_id IS NOT NULL"
    ))

    # Slideshow-scoped artifacts: slideshow_id == creative_id directly.
    for table in ('marketing_analyses', 'recreation_prompts'):
        bind.execute(sa.text(
            f"UPDATE {table} SET slideshow_id = creative_id WHERE creative_id IS NOT NULL"
        ))

    # AnalysisRun: slide_id for slide-scoped analysis_types, slideshow_id
    # for slideshow-scoped ones - mirroring each analysis_type's own split above.
    bind.execute(sa.text(
        "UPDATE analysis_runs SET slide_id = "
        "(SELECT slides.id FROM slides WHERE slides.slideshow_id = analysis_runs.creative_id) "
        "WHERE creative_id IS NOT NULL "
        "AND analysis_type IN ('ocr', 'product_isolation', 'product_lock_profile', 'creative_fingerprint')"
    ))
    bind.execute(sa.text(
        "UPDATE analysis_runs SET slideshow_id = creative_id "
        "WHERE creative_id IS NOT NULL "
        "AND analysis_type IN ('marketing_analysis', 'recreation_prompt')"
    ))


def downgrade() -> None:
    with op.batch_alter_table('analysis_runs') as batch_op:
        batch_op.drop_constraint('fk_analysis_runs_slideshow_id_slideshows', type_='foreignkey')
        batch_op.drop_constraint('fk_analysis_runs_slide_id_slides', type_='foreignkey')
        batch_op.drop_column('slideshow_id')
        batch_op.drop_column('slide_id')
        batch_op.alter_column('creative_id', existing_type=sa.String(length=36), nullable=False)

    with op.batch_alter_table('product_reference_images') as batch_op:
        batch_op.drop_constraint(
            'fk_product_reference_images_source_slide_id_slides', type_='foreignkey'
        )
        batch_op.drop_column('source_slide_id')
        batch_op.alter_column('source_creative_id', existing_type=sa.String(length=36), nullable=False)

    with op.batch_alter_table('recreation_prompts') as batch_op:
        batch_op.drop_constraint(
            'fk_recreation_prompts_slideshow_id_slideshows', type_='foreignkey'
        )
        batch_op.drop_column('slideshow_id')
        batch_op.alter_column('creative_id', existing_type=sa.String(length=36), nullable=False)

    with op.batch_alter_table('marketing_analyses') as batch_op:
        batch_op.drop_constraint(
            'fk_marketing_analyses_slideshow_id_slideshows', type_='foreignkey'
        )
        batch_op.drop_column('slideshow_id')
        batch_op.alter_column('creative_id', existing_type=sa.String(length=36), nullable=False)

    with op.batch_alter_table('creative_fingerprints') as batch_op:
        batch_op.drop_constraint('fk_creative_fingerprints_slide_id_slides', type_='foreignkey')
        batch_op.drop_column('slide_id')
        batch_op.alter_column('creative_id', existing_type=sa.String(length=36), nullable=False)

    with op.batch_alter_table('ocr_results') as batch_op:
        batch_op.drop_constraint('fk_ocr_results_slide_id_slides', type_='foreignkey')
        batch_op.drop_column('slide_id')
        batch_op.alter_column('creative_id', existing_type=sa.String(length=36), nullable=False)
