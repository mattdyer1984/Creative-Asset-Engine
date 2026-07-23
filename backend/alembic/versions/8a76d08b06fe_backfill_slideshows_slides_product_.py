"""backfill slideshows slides product_appearances

Revision ID: 8a76d08b06fe
Revises: d24ebb8f1926
Create Date: 2026-07-22 05:49:20.924991

Phase 2.2 of the Slideshow/Slide migration.

**Rewritten in Phase 2.8** (2026-07-23): originally delegated to
app.services.slideshow_backfill.backfill_slideshows, which imported the
live Creative/Slideshow/Slide/ProductAppearance ORM models. That's a
real, general correctness bug in any migration, not specific to this
one: a migration's behavior must depend on the schema as it existed *at
this point in the chain*, not on whatever the live application models
look like today. Concretely, the live Slideshow model's
current_creative_specification_id column didn't exist under that name
until Phase 8.1 renamed it - at the point this migration actually runs
in a fresh, from-empty `alembic upgrade head` replay, the physical
column is still `current_recreation_prompt_id` (see d24ebb8f1926 above).
The old code would have raised a real "no such column" error on any
fresh clone of this repository (backend/data/ is gitignored - never
committed - so every fresh checkout replays the full chain from empty).
Confirmed by direct testing during Phase 2.8's own verification (see
that phase's report in MIGRATION_PLAN.md).

Phase 2.8 also deletes app.models.creative/creative_blueprint and
app.services.slideshow_backfill entirely (the tables themselves are
dropped by a later migration in this chain), so this migration can no
longer import them regardless. Fixed by inlining frozen, lightweight
sa.table()/sa.column() Core definitions matching each table's exact
shape at this point in the chain - the standard Alembic idiom for data
migrations that must survive schema changes made by later revisions.
Behavior is otherwise identical to the original
app.services.slideshow_backfill.backfill_slideshows (still unit-tested,
now via tests/test_slideshow_backfill.py exercising this migration's
upgrade()/downgrade() directly against a throwaway schema) - idempotent
via the same "Slideshow.id reuses Creative.id verbatim, skip if already
present" check.
"""
import uuid
from datetime import datetime, timezone
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '8a76d08b06fe'
down_revision: Union[str, None] = 'd24ebb8f1926'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Frozen table shapes, exactly as they existed immediately after
# d24ebb8f1926 (this migration's own down_revision) - see this module's
# docstring for why these can't be the live ORM models.
_creatives = sa.table(
    'creatives',
    sa.column('id'),
    sa.column('project_id'),
    sa.column('product_id'),
    sa.column('stored_file_path'),
    sa.column('original_filename'),
    sa.column('source_type'),
    sa.column('source_locator'),
    sa.column('raw_metadata_json'),
    sa.column('imported_at'),
)
_creative_blueprints = sa.table(
    'creative_blueprints',
    sa.column('id'),
    sa.column('creative_id'),
    sa.column('status'),
    sa.column('current_ocr_result_id'),
    sa.column('current_product_lock_profile_id'),
    sa.column('current_creative_fingerprint_id'),
    sa.column('current_marketing_analysis_id'),
    sa.column('current_recreation_prompt_id'),
    sa.column('source_references_json'),
    sa.column('future_generated_assets_json'),
    sa.column('created_at'),
    sa.column('updated_at'),
    sa.column('last_failed_stage'),
    sa.column('last_failed_stage_error'),
)
_slideshows = sa.table(
    'slideshows',
    sa.column('id'),
    sa.column('project_id'),
    sa.column('imported_at'),
    sa.column('status'),
    sa.column('current_marketing_analysis_id'),
    sa.column('current_recreation_prompt_id'),
    sa.column('last_failed_stage'),
    sa.column('last_failed_stage_error'),
    sa.column('source_references_json'),
    sa.column('future_generated_assets_json'),
    sa.column('created_at'),
    sa.column('updated_at'),
)
_slides = sa.table(
    'slides',
    sa.column('id'),
    sa.column('slideshow_id'),
    sa.column('slide_index'),
    sa.column('stored_file_path'),
    sa.column('original_filename'),
    sa.column('source_type'),
    sa.column('source_locator'),
    sa.column('raw_metadata_json'),
    sa.column('current_ocr_result_id'),
    sa.column('current_creative_fingerprint_id'),
)
_product_appearances = sa.table(
    'product_appearances',
    sa.column('id'),
    sa.column('slide_id'),
    sa.column('product_id'),
    sa.column('prominence'),
    sa.column('confidence'),
    sa.column('is_current'),
    sa.column('created_at'),
)


def _new_uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def upgrade() -> None:
    bind = op.get_bind()

    creative_rows = bind.execute(sa.select(_creatives)).mappings().all()
    blueprint_by_creative_id = {
        row["creative_id"]: row
        for row in bind.execute(sa.select(_creative_blueprints)).mappings().all()
    }
    existing_slideshow_ids = {
        row[0] for row in bind.execute(sa.select(_slideshows.c.id))
    }

    for creative in creative_rows:
        if creative["id"] in existing_slideshow_ids:
            continue

        blueprint = blueprint_by_creative_id[creative["id"]]

        bind.execute(
            _slideshows.insert().values(
                id=creative["id"],
                project_id=creative["project_id"],
                imported_at=creative["imported_at"],
                status=blueprint["status"],
                current_marketing_analysis_id=blueprint["current_marketing_analysis_id"],
                current_recreation_prompt_id=blueprint["current_recreation_prompt_id"],
                last_failed_stage=blueprint["last_failed_stage"],
                last_failed_stage_error=blueprint["last_failed_stage_error"],
                source_references_json=blueprint["source_references_json"],
                future_generated_assets_json=blueprint["future_generated_assets_json"],
                created_at=blueprint["created_at"],
                updated_at=blueprint["updated_at"],
            )
        )

        slide_id = _new_uuid()
        bind.execute(
            _slides.insert().values(
                id=slide_id,
                slideshow_id=creative["id"],
                slide_index=0,
                stored_file_path=creative["stored_file_path"],
                original_filename=creative["original_filename"],
                source_type=creative["source_type"],
                source_locator=creative["source_locator"],
                raw_metadata_json=creative["raw_metadata_json"],
                current_ocr_result_id=blueprint["current_ocr_result_id"],
                current_creative_fingerprint_id=blueprint["current_creative_fingerprint_id"],
            )
        )

        # A ProductAppearance is only created if a product was assigned -
        # this was a user assertion, not a detection, hence prominence
        # "primary", confidence 1.0, and no bounding box (see
        # ProductAppearance's module docstring).
        if creative["product_id"] is not None:
            bind.execute(
                _product_appearances.insert().values(
                    id=_new_uuid(),
                    slide_id=slide_id,
                    product_id=creative["product_id"],
                    prominence="primary",
                    confidence=1.0,
                    is_current=True,
                    created_at=_utcnow(),
                )
            )


def downgrade() -> None:
    bind = op.get_bind()
    # FK-safe order: children before parents.
    bind.execute(sa.text("DELETE FROM product_appearances"))
    bind.execute(sa.text("DELETE FROM slides"))
    bind.execute(sa.text("DELETE FROM slideshows"))
