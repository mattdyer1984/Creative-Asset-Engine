"""add generation reference set id to generated images

Revision ID: 3af79717e420
Revises: dab9d7104321
Create Date: 2026-07-23 07:58:51.962941

Phase 9.1 of Product Lock v2 (see MIGRATION_PLAN.md's "ADR: Canonical
Product Reference" §1). Additive only: a new, nullable FK on
generated_images recording exactly which GenerationReferenceSet's
images were sent to the provider for that generation - more precise
provenance than "which Library state was current," since it names the
exact images.

Batch mode required (SQLite can't add a column with a new FK constraint
outside batch mode) - same as 37e53bed7ec8, d3bafd6a4965, 15210f8f4d89,
4b599e19a719.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3af79717e420'
down_revision: Union[str, None] = 'dab9d7104321'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('generated_images') as batch_op:
        batch_op.add_column(sa.Column('generation_reference_set_id', sa.String(length=36), nullable=True))
        batch_op.create_foreign_key(
            'fk_generated_images_generation_reference_set_id',
            'generation_reference_sets', ['generation_reference_set_id'], ['id'],
        )


def downgrade() -> None:
    with op.batch_alter_table('generated_images') as batch_op:
        batch_op.drop_constraint('fk_generated_images_generation_reference_set_id', type_='foreignkey')
        batch_op.drop_column('generation_reference_set_id')
