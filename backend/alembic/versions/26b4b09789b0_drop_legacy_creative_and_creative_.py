"""drop legacy creative and creative_blueprint schema

Revision ID: 26b4b09789b0
Revises: cfaad8c3422b
Create Date: 2026-07-23 21:36:20.806147

Phase 2.8 of the Slideshow/Slide migration - the final, explicitly-gated
step. The old pipeline's code was removed in Phase 2.7; this drops the
data it left behind: the `creatives`/`creative_blueprints` tables
themselves, and the now-dead legacy `creative_id`/`source_creative_id`
columns Phase 2.3 added (nullable, alongside their real `slide_id`/
`slideshow_id`/`source_slide_id` equivalents) to six artifact tables as
a transitional dual-FK. Confirmed via a real grep sweep before writing
this migration: no live application code (routers, services, stages)
reads or writes any of these columns any more - only the columns
themselves and now-obsolete docstrings referenced them. See Phase 2.8's
report in MIGRATION_PLAN.md for the full investigation.

Column-drops run before the two table-drops so no artifact table is
left with a dangling FK to a `creatives` row that's about to disappear.
SQLite batch mode is required throughout: SQLite can't drop a column
(or its FK) via a plain ALTER TABLE.

**Downgrade recreates the schema, not the deleted rows** - stated
plainly rather than implied: reversing this migration restores empty
`creatives`/`creative_blueprints` tables and empty legacy FK columns
with the exact shape they had immediately before this migration ran,
but the actual historical Creative/CreativeBlueprint row data this
migration deletes is not recoverable from within the migration itself
(this project's real backup discipline - a full `.db` file copy taken
before running this migration - is the actual recovery path, not
downgrade()).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '26b4b09789b0'
down_revision: Union[str, None] = 'cfaad8c3422b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (table, legacy FK column name) pairs - every artifact table Phase 2.3
# gave a transitional creative_id/source_creative_id column to.
_LEGACY_FK_COLUMNS = [
    ("analysis_runs", "creative_id"),
    ("ocr_results", "creative_id"),
    ("creative_fingerprints", "creative_id"),
    ("creative_specifications", "creative_id"),
    ("marketing_analyses", "creative_id"),
    ("product_reference_images", "source_creative_id"),
]


def upgrade() -> None:
    for table, column in _LEGACY_FK_COLUMNS:
        with op.batch_alter_table(table) as batch_op:
            batch_op.drop_column(column)

    op.drop_table("creative_blueprints")
    op.drop_table("creatives")


def downgrade() -> None:
    op.create_table(
        "creatives",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.Column("product_id", sa.String(length=36), nullable=True),
        sa.Column("stored_file_path", sa.String(length=1024), nullable=False),
        sa.Column("original_filename", sa.String(length=512), nullable=False),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("source_locator", sa.String(length=2048), nullable=False),
        sa.Column("raw_metadata_json", sa.JSON(), nullable=False),
        sa.Column("imported_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "creative_blueprints",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("creative_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("current_ocr_result_id", sa.String(length=36), nullable=True),
        sa.Column("current_product_lock_profile_id", sa.String(length=36), nullable=True),
        sa.Column("current_creative_fingerprint_id", sa.String(length=36), nullable=True),
        sa.Column("current_marketing_analysis_id", sa.String(length=36), nullable=True),
        sa.Column("current_recreation_prompt_id", sa.String(length=36), nullable=True),
        sa.Column("source_references_json", sa.JSON(), nullable=False),
        sa.Column("future_generated_assets_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("last_failed_stage", sa.String(length=64), nullable=True),
        sa.Column("last_failed_stage_error", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["creative_id"], ["creatives.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("creative_id"),
    )

    for table, column in reversed(_LEGACY_FK_COLUMNS):
        with op.batch_alter_table(table) as batch_op:
            batch_op.add_column(sa.Column(column, sa.String(length=36), nullable=True))
            batch_op.create_foreign_key(f"fk_{table}_{column}_creatives", "creatives", [column], ["id"])
