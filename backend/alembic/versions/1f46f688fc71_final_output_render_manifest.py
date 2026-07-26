"""final output render manifest

Package E. Outputs produced by the ownership-aware rendering path carry a
manifest: who owned every block, what was drawn, where, in what style, which
zones were enforced and what that cost.

Nullable and additive. Every existing row was produced by the legacy renderer
and genuinely has no manifest, which NULL states honestly - back-filling one
would be inventing an audit trail for work nobody audited.

Revision ID: 1f46f688fc71
Revises: 9bcbec12400d
Create Date: 2026-07-26 11:25:51.277938

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1f46f688fc71'
down_revision: Union[str, None] = '9bcbec12400d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Batch mode: SQLite cannot ALTER a column in place.
    with op.batch_alter_table("final_outputs") as batch:
        batch.add_column(sa.Column("render_manifest_json", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("final_outputs") as batch:
        batch.drop_column("render_manifest_json")
