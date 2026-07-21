"""convert json text columns to json type

Revision ID: d7373bd34a85
Revises: ed82f697e346
Create Date: 2026-07-21 22:02:22.759847

Every column below already stores JSON-serialized text written by
json.dumps() (see app/stages, app/services) - this migration only
changes the declared column type from Text to JSON so SQLAlchemy
handles (de)serialization automatically; it does not touch any row's
actual bytes.

SQLite has no native JSON storage class - it stores JSON exactly as it
stores Text (dynamic per-value typing, not enforced by the declared
column type), so no data conversion/cast is needed or possible here:
existing values, however they're materialized (Text or JSON column),
already are - and remain - valid json.dumps() output. Since SQLite's
ALTER TABLE cannot change a column's type directly, each table below
goes through Alembic's "batch mode" (create a shadow table with the new
schema, copy every row across via a plain SELECT, drop the old table,
rename the shadow table into place) to get there.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd7373bd34a85'
down_revision: Union[str, None] = 'ed82f697e346'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('creatives') as batch_op:
        batch_op.alter_column(
            'raw_metadata_json', existing_type=sa.Text(), type_=sa.JSON(), existing_nullable=False
        )

    with op.batch_alter_table('creative_blueprints') as batch_op:
        batch_op.alter_column(
            'source_references_json', existing_type=sa.Text(), type_=sa.JSON(), existing_nullable=False
        )
        batch_op.alter_column(
            'future_generated_assets_json', existing_type=sa.Text(), type_=sa.JSON(), existing_nullable=False
        )

    with op.batch_alter_table('ocr_results') as batch_op:
        batch_op.alter_column(
            'structured_blocks_json', existing_type=sa.Text(), type_=sa.JSON(), existing_nullable=False
        )

    with op.batch_alter_table('product_lock_profiles') as batch_op:
        batch_op.alter_column(
            'structured_json', existing_type=sa.Text(), type_=sa.JSON(), existing_nullable=False
        )
        batch_op.alter_column(
            'reference_image_ids_json', existing_type=sa.Text(), type_=sa.JSON(), existing_nullable=False
        )

    with op.batch_alter_table('creative_fingerprints') as batch_op:
        batch_op.alter_column(
            'structured_json', existing_type=sa.Text(), type_=sa.JSON(), existing_nullable=False
        )

    with op.batch_alter_table('recreation_prompts') as batch_op:
        batch_op.alter_column(
            'structured_json', existing_type=sa.Text(), type_=sa.JSON(), existing_nullable=False
        )


def downgrade() -> None:
    with op.batch_alter_table('recreation_prompts') as batch_op:
        batch_op.alter_column(
            'structured_json', existing_type=sa.JSON(), type_=sa.Text(), existing_nullable=False
        )

    with op.batch_alter_table('creative_fingerprints') as batch_op:
        batch_op.alter_column(
            'structured_json', existing_type=sa.JSON(), type_=sa.Text(), existing_nullable=False
        )

    with op.batch_alter_table('product_lock_profiles') as batch_op:
        batch_op.alter_column(
            'reference_image_ids_json', existing_type=sa.JSON(), type_=sa.Text(), existing_nullable=False
        )
        batch_op.alter_column(
            'structured_json', existing_type=sa.JSON(), type_=sa.Text(), existing_nullable=False
        )

    with op.batch_alter_table('ocr_results') as batch_op:
        batch_op.alter_column(
            'structured_blocks_json', existing_type=sa.JSON(), type_=sa.Text(), existing_nullable=False
        )

    with op.batch_alter_table('creative_blueprints') as batch_op:
        batch_op.alter_column(
            'future_generated_assets_json', existing_type=sa.JSON(), type_=sa.Text(), existing_nullable=False
        )
        batch_op.alter_column(
            'source_references_json', existing_type=sa.JSON(), type_=sa.Text(), existing_nullable=False
        )

    with op.batch_alter_table('creatives') as batch_op:
        batch_op.alter_column(
            'raw_metadata_json', existing_type=sa.JSON(), type_=sa.Text(), existing_nullable=False
        )
