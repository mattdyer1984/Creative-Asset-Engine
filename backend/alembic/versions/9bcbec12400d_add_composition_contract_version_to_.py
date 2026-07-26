"""add composition contract version to ownership artifacts

Package C. An ownership artifact already pointed at the contract that
informed it; this records the schema that contract was written under, so a
past run stays readable in its own terms after the contract is superseded.

Additive and nullable: every existing row predates composition-informed
routing and genuinely has no contract, which NULL states honestly.

Revision ID: 9bcbec12400d
Revises: 5e3f7c70091f
Create Date: 2026-07-26 10:36:05.884656

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9bcbec12400d'
down_revision: Union[str, None] = '5e3f7c70091f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Batch mode: SQLite cannot ALTER a column in place.
    with op.batch_alter_table("text_ownership_artifacts") as batch:
        batch.add_column(
            sa.Column("composition_contract_version", sa.String(16), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("text_ownership_artifacts") as batch:
        batch.drop_column("composition_contract_version")
