"""add timing and cost instrumentation to analysis runs and generated images

Revision ID: 19332028a3ac
Revises: a3f6fe387657
Create Date: 2026-07-25 14:20:34.861507

Optimisation & Stability Pass, Tier 2 (see MIGRATION_PLAN.md) - no
timing or cost instrumentation existed anywhere in the pipeline before
this. All columns nullable/additive: every pre-existing row genuinely
has none of this data (it was never measured), not a value to backfill
or guess.

analysis_runs gets the full set (finished_at/duration_ms/
provider_call_ms/prompt_tokens/completion_tokens/estimated_cost_usd) -
one place, since every Stage already writes an AnalysisRun via
mark_succeeded/mark_failed (app.stages.execution). generated_images gets
only estimated_cost_usd - image generation is billed per-image, not by
token, and already has its own generation_time_seconds column from
Phase 8.2, so no duration/token columns are needed there.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '19332028a3ac'
down_revision: Union[str, None] = 'a3f6fe387657'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('analysis_runs') as batch_op:
        batch_op.add_column(sa.Column('finished_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('duration_ms', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('provider_call_ms', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('prompt_tokens', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('completion_tokens', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('estimated_cost_usd', sa.Float(), nullable=True))

    with op.batch_alter_table('generated_images') as batch_op:
        batch_op.add_column(sa.Column('estimated_cost_usd', sa.Float(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('generated_images') as batch_op:
        batch_op.drop_column('estimated_cost_usd')

    with op.batch_alter_table('analysis_runs') as batch_op:
        batch_op.drop_column('estimated_cost_usd')
        batch_op.drop_column('completion_tokens')
        batch_op.drop_column('prompt_tokens')
        batch_op.drop_column('provider_call_ms')
        batch_op.drop_column('duration_ms')
        batch_op.drop_column('finished_at')
