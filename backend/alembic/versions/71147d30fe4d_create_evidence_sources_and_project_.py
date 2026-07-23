"""create evidence sources and project products tables and add evidence source id to slideshows

Revision ID: 71147d30fe4d
Revises: b71e0e3f1ca2
Create Date: 2026-07-23 12:42:11.119263

Phase 10.5 of AI Creative Engine vNext (see MIGRATION_PLAN.md's "ADR: AI
Creative Engine vNext" §3/§4b). Two new tables (EvidenceSource,
ProjectProduct - both brand-new CREATE TABLEs, no batch mode needed for
either) plus one new nullable FK column on slideshows
(evidence_source_id).

Batch mode required for the slideshows.evidence_source_id column
(SQLite can't add a column with a new FK constraint outside batch mode)
- same as 2ade4025cfa7, 37e53bed7ec8, d3bafd6a4965, 15210f8f4d89,
4b599e19a719, 3af79717e420.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '71147d30fe4d'
down_revision: Union[str, None] = 'b71e0e3f1ca2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'evidence_sources',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('project_id', sa.String(length=36), nullable=True),
        sa.Column('evidence_type', sa.String(length=32), nullable=False),
        sa.Column('source_locator', sa.String(length=2048), nullable=True),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('source_platform', sa.String(length=64), nullable=False),
        sa.Column('creator_json', sa.JSON(), nullable=True),
        sa.Column('caption', sa.Text(), nullable=True),
        sa.Column('hashtags_json', sa.JSON(), nullable=False),
        sa.Column('product_references_json', sa.JSON(), nullable=False),
        sa.Column('platform_metadata_json', sa.JSON(), nullable=False),
        sa.Column('raw_json', sa.JSON(), nullable=False),
        sa.Column('imported_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'project_products',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('project_id', sa.String(length=36), nullable=False),
        sa.Column('product_id', sa.String(length=36), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id']),
        sa.ForeignKeyConstraint(['product_id'], ['products.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('slideshows') as batch_op:
        batch_op.add_column(sa.Column('evidence_source_id', sa.String(length=36), nullable=True))
        batch_op.create_foreign_key(
            'fk_slideshows_evidence_source_id',
            'evidence_sources', ['evidence_source_id'], ['id'],
        )


def downgrade() -> None:
    with op.batch_alter_table('slideshows') as batch_op:
        batch_op.drop_constraint('fk_slideshows_evidence_source_id', type_='foreignkey')
        batch_op.drop_column('evidence_source_id')
    op.drop_table('project_products')
    op.drop_table('evidence_sources')
