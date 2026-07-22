"""add creative_fingerprint_id to marketing_analyses

Revision ID: 15210f8f4d89
Revises: 19b5c9909b3e
Create Date: 2026-07-22 20:59:34.912731

Phase 7.3 of the Narrative pass (see MIGRATION_PLAN.md's architecture
direction for this phase). Additive only: a new, nullable FK recording
which CreativeFingerprint a MarketingAnalysis was actually generated
from - a real gap fix (the artifact already depends on the fingerprint,
it just never recorded which version), and the prerequisite Phase 7.4's
dependency-aware staleness check needs. Nullable since existing rows
have no way to be truthfully backfilled - a None here means "staleness
unknown," not "fresh" or "stale."

Batch mode required (SQLite can't add a column with a new FK constraint
outside batch mode) - same as 37e53bed7ec8 and d3bafd6a4965.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '15210f8f4d89'
down_revision: Union[str, None] = '19b5c9909b3e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('marketing_analyses') as batch_op:
        batch_op.add_column(sa.Column('creative_fingerprint_id', sa.String(length=36), nullable=True))
        batch_op.create_foreign_key(
            'fk_marketing_analyses_creative_fingerprint_id', 'creative_fingerprints', ['creative_fingerprint_id'], ['id']
        )


def downgrade() -> None:
    with op.batch_alter_table('marketing_analyses') as batch_op:
        batch_op.drop_constraint('fk_marketing_analyses_creative_fingerprint_id', type_='foreignkey')
        batch_op.drop_column('creative_fingerprint_id')
