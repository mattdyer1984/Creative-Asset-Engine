"""make creative_specifications product_lock_profile_id nullable

Revision ID: 4fe5f7a5f887
Revises: e31d892e83a4
Create Date: 2026-07-25 16:09:59.675339

Story Slide feature (see MIGRATION_PLAN.md) - a slide with no detected
product still gets a CreativeSpecification (built from its Creative
Fingerprint alone), just with no Product Lock Profile to point at.
Batch mode required - SQLite can't ALTER a column's nullability directly.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4fe5f7a5f887'
down_revision: Union[str, None] = 'e31d892e83a4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('creative_specifications') as batch_op:
        batch_op.alter_column(
            'product_lock_profile_id',
            existing_type=sa.String(length=36),
            nullable=True,
        )


def downgrade() -> None:
    with op.batch_alter_table('creative_specifications') as batch_op:
        batch_op.alter_column(
            'product_lock_profile_id',
            existing_type=sa.String(length=36),
            nullable=False,
        )
