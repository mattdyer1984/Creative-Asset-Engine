"""add identity checks to image validation results

Revision ID: de63f9128ab2
Revises: 3af79717e420
Create Date: 2026-07-23 07:58:52.391116

Phase 9.1 of Product Lock v2 (see MIGRATION_PLAN.md's "ADR: Canonical
Product Reference" §1/§7). Additive only: two new nullable columns on
image_validation_results (identity_passed, identity_checks_json) for
Stage 1 Identity Validation's output, distinct from the existing
passed/field_checks_json pair (which continue to mean the Stage 2
creative checks specifically from this phase onward - no column
renamed, no shape changed).

No batch mode needed here, unlike 3af79717e420 - neither new column
adds an FK constraint (both are a plain Boolean and a plain JSON
column), and this project's batch-mode rule is specifically about
columns that add a new FK, not additive columns in general - same
precedent as the four plain nullable columns added to
product_reference_images in dab9d7104321.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'de63f9128ab2'
down_revision: Union[str, None] = '3af79717e420'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('image_validation_results', sa.Column('identity_passed', sa.Boolean(), nullable=True))
    op.add_column(
        'image_validation_results', sa.Column('identity_checks_json', sa.JSON(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('image_validation_results', 'identity_checks_json')
    op.drop_column('image_validation_results', 'identity_passed')
