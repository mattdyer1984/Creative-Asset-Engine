"""source dimensions on slides

Persist source image pixel dimensions on the slide, measured once at ingestion so
the evidence survives after the source file is removed. Read back through
AnalysisSource.source_dims() with persisted-first precedence.

Nullable and additive. Existing rows get NULL width/height AND a NULL
`dimension_measurement_source` — which reads as "never attempted" (distinct from a
row whose measurement was attempted and failed, which records the attempt). The
backfill (app.services.backfill_source_dimensions) populates existing rows
idempotently and records file-missing / unreadable states explicitly.

Revision ID: 5f3a9c1e2b47
Revises: b392e2c34de2
Create Date: 2026-07-27 21:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5f3a9c1e2b47'
down_revision: Union[str, None] = 'b392e2c34de2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Batch mode: SQLite cannot ALTER a table to add columns in place otherwise.
    with op.batch_alter_table("slides") as batch:
        batch.add_column(sa.Column("source_width", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("source_height", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("dimension_measurement_source", sa.String(64), nullable=True))
        batch.add_column(sa.Column("dimension_measured_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("slides") as batch:
        batch.drop_column("dimension_measured_at")
        batch.drop_column("dimension_measurement_source")
        batch.drop_column("source_height")
        batch.drop_column("source_width")
