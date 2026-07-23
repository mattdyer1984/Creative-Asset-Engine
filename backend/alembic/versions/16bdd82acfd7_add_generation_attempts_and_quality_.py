"""add generation attempts and quality assessments

Revision ID: 16bdd82acfd7
Revises: 2ade4025cfa7
Create Date: 2026-07-23 10:18:27.939448

Phase 10.2 of AI Creative Engine vNext (see MIGRATION_PLAN.md's "ADR:
AI Creative Engine vNext" §12/§13). Additive only: two new tables
(GenerationAttempt, QualityAssessment) plus two new nullable columns on
generated_images (generation_attempt_id, candidate_index).

No batch mode needed for the two new tables - brand-new tables with FK
constraints don't require it (same precedent as dab9d7104321). The
generated_images column additions DO need batch mode, since
generation_attempt_id is a new FK constraint on an existing table -
same rule as every other such migration this project has made
(37e53bed7ec8, d3bafd6a4965, 15210f8f4d89, 4b599e19a719, 3af79717e420,
2ade4025cfa7).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '16bdd82acfd7'
down_revision: Union[str, None] = '2ade4025cfa7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'generation_attempts',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('slide_id', sa.String(length=36), nullable=False),
        sa.Column('creative_specification_id', sa.String(length=36), nullable=False),
        sa.Column('generation_reference_set_id', sa.String(length=36), nullable=True),
        sa.Column('quality_mode', sa.String(length=32), nullable=False),
        sa.Column('decision_json', sa.JSON(), nullable=False),
        sa.Column('retry_of_generation_attempt_id', sa.String(length=36), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['slide_id'], ['slides.id']),
        sa.ForeignKeyConstraint(['creative_specification_id'], ['creative_specifications.id']),
        sa.ForeignKeyConstraint(['generation_reference_set_id'], ['generation_reference_sets.id']),
        sa.ForeignKeyConstraint(['retry_of_generation_attempt_id'], ['generation_attempts.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'quality_assessments',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('generated_image_id', sa.String(length=36), nullable=False),
        sa.Column('image_validation_result_id', sa.String(length=36), nullable=False),
        sa.Column('creative_fidelity_json', sa.JSON(), nullable=True),
        sa.Column('photorealism_json', sa.JSON(), nullable=True),
        sa.Column('text_quality_json', sa.JSON(), nullable=True),
        sa.Column('overall_confidence_score', sa.Float(), nullable=False),
        sa.Column('accepted', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['generated_image_id'], ['generated_images.id']),
        sa.ForeignKeyConstraint(['image_validation_result_id'], ['image_validation_results.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('generated_images') as batch_op:
        batch_op.add_column(sa.Column('generation_attempt_id', sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column('candidate_index', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_generated_images_generation_attempt_id',
            'generation_attempts', ['generation_attempt_id'], ['id'],
        )


def downgrade() -> None:
    with op.batch_alter_table('generated_images') as batch_op:
        batch_op.drop_constraint('fk_generated_images_generation_attempt_id', type_='foreignkey')
        batch_op.drop_column('candidate_index')
        batch_op.drop_column('generation_attempt_id')
    op.drop_table('quality_assessments')
    op.drop_table('generation_attempts')
