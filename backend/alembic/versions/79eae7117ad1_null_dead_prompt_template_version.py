"""null dead prompt_template_version

Phase 1 remediation, WP-3.

`AnalysisRun.prompt_template_version` was a dead column: NOT NULL,
defaulted to "1.0", and never written by any code path. Every row in the
database therefore reads "1.0" - not because a prompt version was
recorded, but because nothing ever recorded one. A column that looks
like provenance while holding only a default is worse than an empty one:
it invites someone months from now to trust it.

Prompt identity now lives on `provider_calls` (prompt_id,
prompt_version, prompt_content_hash), which is the correct grain - a
prompt belongs to a CALL, and one AnalysisRun can make several.

This makes the column nullable and clears the placeholder, so its
emptiness is honest. Dropping it outright is deliberately left to a
separate later migration, once the ProviderCall path has run for a
while - the same discipline applied to the deprecated AnalysisRun cost
columns.

Revision ID: 79eae7117ad1
Revises: 7a1c9d4e2b80
Create Date: 2026-07-25 21:55:00.561643

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '79eae7117ad1'
down_revision: Union[str, None] = '7a1c9d4e2b80'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # batch_alter_table: SQLite cannot ALTER a column in place, so Alembic
    # rebuilds the table. Required here, not stylistic.
    with op.batch_alter_table("analysis_runs") as batch_op:
        batch_op.alter_column(
            "prompt_template_version",
            existing_type=sa.String(16),
            nullable=True,
            server_default=None,
        )

    # Only the placeholder is cleared. A non-"1.0" value would be
    # somebody's deliberate data, and this migration has no business
    # discarding it - even though no code path can currently produce one.
    op.execute(
        sa.text(
            "UPDATE analysis_runs SET prompt_template_version = NULL "
            "WHERE prompt_template_version = '1.0'"
        )
    )


def downgrade() -> None:
    # Restore the placeholder BEFORE reinstating NOT NULL, or the
    # constraint fails on every row this migration nulled.
    op.execute(
        sa.text(
            "UPDATE analysis_runs SET prompt_template_version = '1.0' "
            "WHERE prompt_template_version IS NULL"
        )
    )
    with op.batch_alter_table("analysis_runs") as batch_op:
        batch_op.alter_column(
            "prompt_template_version",
            existing_type=sa.String(16),
            nullable=False,
        )
