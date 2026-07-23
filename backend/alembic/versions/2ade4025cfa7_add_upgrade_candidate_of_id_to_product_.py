"""add upgrade candidate of id to product reference images

Revision ID: 2ade4025cfa7
Revises: de63f9128ab2
Create Date: 2026-07-23 09:52:54.688718

Phase 9.6 of Product Lock v2 (see MIGRATION_PLAN.md's "ADR: Canonical
Product Reference" §4/§9). Additive only: a new, nullable, self-
referential FK on product_reference_images recording that a candidate
was detected as a higher-quality near-duplicate of an already-included
image - the "non-blocking prompt offering to upgrade" the ADR requires
never auto-applies, so this is a signal, not a state change on the
older image.

Batch mode required (SQLite can't add a column with a new FK constraint
outside batch mode) - same as 37e53bed7ec8, d3bafd6a4965, 15210f8f4d89,
4b599e19a719, 3af79717e420.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2ade4025cfa7'
down_revision: Union[str, None] = 'de63f9128ab2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('product_reference_images') as batch_op:
        batch_op.add_column(sa.Column('upgrade_candidate_of_id', sa.String(length=36), nullable=True))
        batch_op.create_foreign_key(
            'fk_product_reference_images_upgrade_candidate_of_id',
            'product_reference_images', ['upgrade_candidate_of_id'], ['id'],
        )


def downgrade() -> None:
    with op.batch_alter_table('product_reference_images') as batch_op:
        batch_op.drop_constraint('fk_product_reference_images_upgrade_candidate_of_id', type_='foreignkey')
        batch_op.drop_column('upgrade_candidate_of_id')
