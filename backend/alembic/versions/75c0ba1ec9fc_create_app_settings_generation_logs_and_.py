"""create app_settings generation_logs and generation_reviews tables

Revision ID: 75c0ba1ec9fc
Revises: 26b4b09789b0
Create Date: 2026-07-24 09:01:17.491979

Phase 12 (Human Feedback & Learning System, see MIGRATION_PLAN.md):

- Three brand-new tables (app_settings, generation_logs,
  generation_reviews - no batch mode needed, CREATE TABLE not ALTER).
- generation_attempts gains a new nullable FK, generation_log_id, set
  by the router after generate_with_retry returns (this migration only
  adds the column - generate_with_retry.py/generation_engine.py are
  unmodified).

Batch mode required for the generation_attempts ALTER (SQLite can't add
a column with a new FK constraint outside batch mode) - same as every
prior migration that added an FK column in this codebase (e.g.
f3ab7b7888f5's own bundle_composition_id addition).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '75c0ba1ec9fc'
down_revision: Union[str, None] = '26b4b09789b0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'app_settings',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('learning_mode_enabled', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'generation_logs',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('slideshow_id', sa.String(length=36), nullable=False),
        sa.Column('slide_id', sa.String(length=36), nullable=False),
        sa.Column('project_id', sa.String(length=36), nullable=True),
        sa.Column('product_id', sa.String(length=36), nullable=True),
        sa.Column('bundle_product_ids_json', sa.JSON(), nullable=True),
        sa.Column('winning_generated_image_id', sa.String(length=36), nullable=True),
        sa.Column('final_output_id', sa.String(length=36), nullable=True),
        sa.Column('quality_mode', sa.String(length=32), nullable=False),
        sa.Column('creativity_level', sa.String(length=32), nullable=False),
        sa.Column('text_strategy', sa.String(length=32), nullable=True),
        sa.Column('ai_provider', sa.String(length=64), nullable=True),
        sa.Column('ai_model', sa.String(length=128), nullable=True),
        sa.Column('prompt_used', sa.Text(), nullable=True),
        sa.Column('creative_specification_id', sa.String(length=36), nullable=False),
        sa.Column('creative_specification_schema_version', sa.String(length=16), nullable=False),
        sa.Column('retry_count', sa.Integer(), nullable=False),
        sa.Column('generation_duration_seconds', sa.Float(), nullable=False),
        sa.Column('archive_path', sa.String(length=1024), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['slideshow_id'], ['slideshows.id']),
        sa.ForeignKeyConstraint(['slide_id'], ['slides.id']),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id']),
        sa.ForeignKeyConstraint(['product_id'], ['products.id']),
        sa.ForeignKeyConstraint(['winning_generated_image_id'], ['generated_images.id']),
        sa.ForeignKeyConstraint(['final_output_id'], ['final_outputs.id']),
        sa.ForeignKeyConstraint(['creative_specification_id'], ['creative_specifications.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'generation_reviews',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('generation_log_id', sa.String(length=36), nullable=False),
        sa.Column('overall_score', sa.Integer(), nullable=False),
        sa.Column('main_issue', sa.String(length=32), nullable=False),
        sa.Column('comment', sa.Text(), nullable=True),
        sa.Column('learning_mode_enabled', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['generation_log_id'], ['generation_logs.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('generation_log_id'),
    )

    with op.batch_alter_table('generation_attempts') as batch_op:
        batch_op.add_column(sa.Column('generation_log_id', sa.String(length=36), nullable=True))
        batch_op.create_foreign_key(
            'fk_generation_attempts_generation_log_id',
            'generation_logs', ['generation_log_id'], ['id'],
        )


def downgrade() -> None:
    with op.batch_alter_table('generation_attempts') as batch_op:
        batch_op.drop_constraint('fk_generation_attempts_generation_log_id', type_='foreignkey')
        batch_op.drop_column('generation_log_id')

    op.drop_table('generation_reviews')
    op.drop_table('generation_logs')
    op.drop_table('app_settings')
