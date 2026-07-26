"""composition contract

ADR 0001 §9, Package B. Slide-scoped, versioned. Additive only, no backfill -
a contract for a historical slide would be a guess about a layout nobody
analysed.

Revision ID: 5e3f7c70091f
Revises: 28cbbd306d1b
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '5e3f7c70091f'
down_revision: Union[str, None] = '28cbbd306d1b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "composition_contracts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("analysis_run_id", sa.String(36), sa.ForeignKey("analysis_runs.id"),
                  nullable=False),
        sa.Column("schema_version", sa.String(16), nullable=False, server_default="1.0"),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("slide_id", sa.String(36), sa.ForeignKey("slides.id"), nullable=False),
        sa.Column("device", sa.String(48), nullable=True),
        sa.Column("device_confidence", sa.Float(), nullable=True),
        sa.Column("contract_json", sa.JSON(), nullable=True),
    )
    op.create_index("ix_composition_contracts_slide_id", "composition_contracts", ["slide_id"])
    op.create_index("ix_composition_contracts_slide_current",
                    "composition_contracts", ["slide_id", "is_current"])


def downgrade() -> None:
    op.drop_index("ix_composition_contracts_slide_current", table_name="composition_contracts")
    op.drop_index("ix_composition_contracts_slide_id", table_name="composition_contracts")
    op.drop_table("composition_contracts")
