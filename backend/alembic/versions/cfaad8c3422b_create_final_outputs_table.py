"""create final outputs table

Revision ID: cfaad8c3422b
Revises: f3ab7b7888f5
Create Date: 2026-07-23 16:36:03.294505

Phase 10.8 of AI Creative Engine vNext (see MIGRATION_PLAN.md's "ADR:
AI Creative Engine vNext" §15). Additive only: one brand-new table
(FinalOutput) - no batch mode needed, CREATE TABLE not ALTER.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cfaad8c3422b'
down_revision: Union[str, None] = 'f3ab7b7888f5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'final_outputs',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('generation_attempt_id', sa.String(length=36), nullable=False),
        sa.Column('generated_image_id', sa.String(length=36), nullable=False),
        sa.Column('file_path', sa.String(length=1024), nullable=False),
        sa.Column('text_assets_json', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['generation_attempt_id'], ['generation_attempts.id']),
        sa.ForeignKeyConstraint(['generated_image_id'], ['generated_images.id']),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('final_outputs')
