"""create bundle compositions and add bundle composition id to generation attempts and relax quality assessment image validation result id

Revision ID: f3ab7b7888f5
Revises: 71147d30fe4d
Create Date: 2026-07-23 14:03:10.390597

Phase 10.7 of AI Creative Engine vNext (see MIGRATION_PLAN.md's "ADR: AI
Creative Engine vNext" §12's "Bundle Composition" addendum):

- Two brand-new tables (bundle_compositions, bundle_composition_members
  - no batch mode needed, CREATE TABLE not ALTER).
- generation_attempts gains a new nullable FK, bundle_composition_id,
  mutually exclusive with the existing generation_reference_set_id.
- quality_assessments.image_validation_result_id relaxes from NOT NULL
  to nullable (a Bundle Composition candidate has N results, not one -
  see the new image_validation_result_ids_json column), and gains that
  new nullable JSON column.

Batch mode required for both ALTERs (SQLite can't add a column with a
new FK constraint, or change a column's nullability, outside batch
mode) - same as every prior migration that touched nullability/added an
FK column in this codebase (e.g. 37e53bed7ec8, 2ade4025cfa7).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f3ab7b7888f5'
down_revision: Union[str, None] = '71147d30fe4d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'bundle_compositions',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('slide_id', sa.String(length=36), nullable=False),
        sa.Column('creative_specification_id', sa.String(length=36), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['slide_id'], ['slides.id']),
        sa.ForeignKeyConstraint(['creative_specification_id'], ['creative_specifications.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'bundle_composition_members',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('bundle_composition_id', sa.String(length=36), nullable=False),
        sa.Column('product_id', sa.String(length=36), nullable=False),
        sa.Column('generation_reference_set_id', sa.String(length=36), nullable=False),
        sa.Column('role_in_scene', sa.String(length=64), nullable=False),
        sa.Column('rank', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['bundle_composition_id'], ['bundle_compositions.id']),
        sa.ForeignKeyConstraint(['product_id'], ['products.id']),
        sa.ForeignKeyConstraint(['generation_reference_set_id'], ['generation_reference_sets.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    with op.batch_alter_table('generation_attempts') as batch_op:
        batch_op.add_column(sa.Column('bundle_composition_id', sa.String(length=36), nullable=True))
        batch_op.create_foreign_key(
            'fk_generation_attempts_bundle_composition_id',
            'bundle_compositions', ['bundle_composition_id'], ['id'],
        )

    with op.batch_alter_table('quality_assessments') as batch_op:
        batch_op.alter_column('image_validation_result_id', existing_type=sa.String(length=36), nullable=True)
        batch_op.add_column(sa.Column('image_validation_result_ids_json', sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('quality_assessments') as batch_op:
        batch_op.drop_column('image_validation_result_ids_json')
        batch_op.alter_column('image_validation_result_id', existing_type=sa.String(length=36), nullable=False)

    with op.batch_alter_table('generation_attempts') as batch_op:
        batch_op.drop_constraint('fk_generation_attempts_bundle_composition_id', type_='foreignkey')
        batch_op.drop_column('bundle_composition_id')

    op.drop_table('bundle_composition_members')
    op.drop_table('bundle_compositions')
