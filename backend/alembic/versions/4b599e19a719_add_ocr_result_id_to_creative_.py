"""add ocr_result_id to creative_fingerprints

Revision ID: 4b599e19a719
Revises: 15210f8f4d89
Create Date: 2026-07-22 21:04:47.237200

Phase 7.4 of the Narrative pass (see MIGRATION_PLAN.md's architecture
direction for this phase). Additive only, same category as 15210f8f4d89:
a new, nullable FK recording which OCRResult a CreativeFingerprint
actually incorporated as enrichment context - found while building this
sub-phase's staleness service. Nullable both because existing rows can't
be truthfully backfilled and because OCR is genuinely optional
enrichment here (some fingerprints legitimately have no OCR to record).

Batch mode required (SQLite can't add a column with a new FK constraint
outside batch mode) - same as 37e53bed7ec8, d3bafd6a4965, 15210f8f4d89.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4b599e19a719'
down_revision: Union[str, None] = '15210f8f4d89'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('creative_fingerprints') as batch_op:
        batch_op.add_column(sa.Column('ocr_result_id', sa.String(length=36), nullable=True))
        batch_op.create_foreign_key(
            'fk_creative_fingerprints_ocr_result_id', 'ocr_results', ['ocr_result_id'], ['id']
        )


def downgrade() -> None:
    with op.batch_alter_table('creative_fingerprints') as batch_op:
        batch_op.drop_constraint('fk_creative_fingerprints_ocr_result_id', type_='foreignkey')
        batch_op.drop_column('ocr_result_id')
