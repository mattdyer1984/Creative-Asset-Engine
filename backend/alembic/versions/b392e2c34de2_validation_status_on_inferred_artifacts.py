"""validation status on inferred artifacts

Phase F. Every major inferred artifact now exposes BOTH confidence and
validation status, which are different concepts: confidence is how sure the
producer was, validation is whether anything checked.

Nullable and additive. Every existing row predates the validators and
genuinely was never checked - NULL says exactly that, where back-filling
`validated` would claim a verification that never happened.

Revision ID: b392e2c34de2
Revises: 1f46f688fc71
Create Date: 2026-07-26 13:35:25.029289

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b392e2c34de2'
down_revision: Union[str, None] = '1f46f688fc71'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = (
    "composition_contracts",
    "text_ownership_artifacts",
    "creative_project_profiles",
)


def upgrade() -> None:
    # Batch mode: SQLite cannot ALTER a column in place.
    for table in _TABLES:
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column("validation_status", sa.String(24), nullable=True))
            batch.add_column(sa.Column("validation_json", sa.JSON(), nullable=True))


def downgrade() -> None:
    for table in _TABLES:
        with op.batch_alter_table(table) as batch:
            batch.drop_column("validation_json")
            batch.drop_column("validation_status")
