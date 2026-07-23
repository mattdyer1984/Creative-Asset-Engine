"""rename recreation_prompt to creative_specification

Revision ID: a1c3e9f2b8d4
Revises: 4b599e19a719
Create Date: 2026-07-22 22:10:00.000000

Phase 8.1 of the Generation -> Validation proof of loop (see
MIGRATION_PLAN.md's Phase 8 architecture direction). Once generation
exists, "prompt" is ambiguous - there's the Creative Specification
(provider-neutral intent, persisted) and the compiled provider prompt
(OpenAI-specific syntax, never the canonical record). Renames the
new-pipeline table and its Slideshow pointer column only - the legacy,
Phase-2.8-gated CreativeBlueprint.current_recreation_prompt_id column is
untouched.

Pure rename, no shape change - batch mode used for both operations per
this project's established caution around SQLite column-level ALTERs,
even though the column rename itself has no FK constraint.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1c3e9f2b8d4'
down_revision: Union[str, None] = '4b599e19a719'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.rename_table('recreation_prompts', 'creative_specifications')
    with op.batch_alter_table('slideshows') as batch_op:
        batch_op.alter_column(
            'current_recreation_prompt_id', new_column_name='current_creative_specification_id'
        )


def downgrade() -> None:
    with op.batch_alter_table('slideshows') as batch_op:
        batch_op.alter_column(
            'current_creative_specification_id', new_column_name='current_recreation_prompt_id'
        )
    op.rename_table('creative_specifications', 'recreation_prompts')
