"""
Tests for the Phase 2.2 Slideshow/Slide/ProductAppearance backfill,
now a frozen data migration (alembic/versions/8a76d08b06fe) rather than
a live-model-importing service function - see that migration's own
docstring for why it was rewritten in Phase 2.8.

Builds a real, throwaway SQLite schema matching the exact frozen table
shapes the migration expects (mirroring the historical migrations that
actually created them - 70f7977ef7c5, 4f150be6a5d4, ed82f697e346,
d24ebb8f1926), inserts real rows via Core, then exercises the
migration's own upgrade()/downgrade() functions directly through a real
Alembic Operations context bound to that schema - not the live app
models, which no longer exist for Creative/CreativeBlueprint.
"""

import importlib.util
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext


def _load_migration_module(filename: str):
    """
    Alembic version files live in a plain (non-package) directory and
    have filenames starting with a hex revision id, so they can't be
    imported via a normal dotted `import` - load by file path instead.
    """
    path = Path(__file__).resolve().parent.parent / "alembic" / "versions" / filename
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


migration = _load_migration_module("8a76d08b06fe_backfill_slideshows_slides_product_.py")

metadata = sa.MetaData()

creatives = sa.Table(
    "creatives",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("project_id", sa.String(36), nullable=True),
    sa.Column("product_id", sa.String(36), nullable=True),
    sa.Column("stored_file_path", sa.String(1024), nullable=False),
    sa.Column("original_filename", sa.String(512), nullable=False),
    sa.Column("source_type", sa.String(64), nullable=False),
    sa.Column("source_locator", sa.String(2048), nullable=False),
    sa.Column("raw_metadata_json", sa.JSON(), nullable=False),
    sa.Column("imported_at", sa.DateTime(), nullable=False),
)
creative_blueprints = sa.Table(
    "creative_blueprints",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("creative_id", sa.String(36), nullable=False, unique=True),
    sa.Column("status", sa.String(32), nullable=False),
    sa.Column("current_ocr_result_id", sa.String(36), nullable=True),
    sa.Column("current_product_lock_profile_id", sa.String(36), nullable=True),
    sa.Column("current_creative_fingerprint_id", sa.String(36), nullable=True),
    sa.Column("current_marketing_analysis_id", sa.String(36), nullable=True),
    sa.Column("current_recreation_prompt_id", sa.String(36), nullable=True),
    sa.Column("source_references_json", sa.JSON(), nullable=False),
    sa.Column("future_generated_assets_json", sa.JSON(), nullable=False),
    sa.Column("created_at", sa.DateTime(), nullable=False),
    sa.Column("updated_at", sa.DateTime(), nullable=False),
    sa.Column("last_failed_stage", sa.String(64), nullable=True),
    sa.Column("last_failed_stage_error", sa.Text(), nullable=True),
)
slideshows = sa.Table(
    "slideshows",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("project_id", sa.String(36), nullable=True),
    sa.Column("imported_at", sa.DateTime(), nullable=False),
    sa.Column("status", sa.String(32), nullable=False),
    sa.Column("current_marketing_analysis_id", sa.String(36), nullable=True),
    sa.Column("current_recreation_prompt_id", sa.String(36), nullable=True),
    sa.Column("last_failed_stage", sa.String(64), nullable=True),
    sa.Column("last_failed_stage_error", sa.Text(), nullable=True),
    sa.Column("source_references_json", sa.JSON(), nullable=False),
    sa.Column("future_generated_assets_json", sa.JSON(), nullable=False),
    sa.Column("created_at", sa.DateTime(), nullable=False),
    sa.Column("updated_at", sa.DateTime(), nullable=False),
)
slides = sa.Table(
    "slides",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("slideshow_id", sa.String(36), nullable=False),
    sa.Column("slide_index", sa.Integer(), nullable=False),
    sa.Column("stored_file_path", sa.String(1024), nullable=False),
    sa.Column("original_filename", sa.String(512), nullable=False),
    sa.Column("source_type", sa.String(64), nullable=False),
    sa.Column("source_locator", sa.String(2048), nullable=False),
    sa.Column("raw_metadata_json", sa.JSON(), nullable=False),
    sa.Column("current_ocr_result_id", sa.String(36), nullable=True),
    sa.Column("current_creative_fingerprint_id", sa.String(36), nullable=True),
)
product_appearances = sa.Table(
    "product_appearances",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("slide_id", sa.String(36), nullable=False),
    sa.Column("product_id", sa.String(36), nullable=False),
    sa.Column("prominence", sa.String(32), nullable=False),
    sa.Column("confidence", sa.Float(), nullable=False),
    sa.Column("is_current", sa.Boolean(), nullable=False),
    sa.Column("created_at", sa.DateTime(), nullable=False),
)


@pytest.fixture()
def conn():
    engine = sa.create_engine("sqlite://")
    metadata.create_all(engine)
    with engine.connect() as connection:
        yield connection


@contextmanager
def _op(connection):
    ctx = MigrationContext.configure(connection)
    with Operations.context(ctx):
        yield


def _insert_creative_with_blueprint(connection, *, product_id: str | None = None) -> str:
    creative_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    connection.execute(
        creatives.insert().values(
            id=creative_id,
            project_id=None,
            product_id=product_id,
            stored_file_path="/tmp/x.jpg",
            original_filename="x.jpg",
            source_type="local_file",
            source_locator="/tmp/x.jpg",
            raw_metadata_json={},
            imported_at=now,
        )
    )
    connection.execute(
        creative_blueprints.insert().values(
            id=str(uuid.uuid4()),
            creative_id=creative_id,
            status="imported",
            current_ocr_result_id=None,
            current_product_lock_profile_id=None,
            current_creative_fingerprint_id=None,
            current_marketing_analysis_id=None,
            current_recreation_prompt_id=None,
            source_references_json={"source_type": "local_file"},
            future_generated_assets_json=[],
            created_at=now,
            updated_at=now,
            last_failed_stage=None,
            last_failed_stage_error=None,
        )
    )
    connection.commit()
    return creative_id


def test_backfills_slideshow_and_slide_from_creative(conn):
    creative_id = _insert_creative_with_blueprint(conn)

    with _op(conn):
        migration.upgrade()
    conn.commit()

    slideshow = conn.execute(sa.select(slideshows).where(slideshows.c.id == creative_id)).mappings().one()
    assert slideshow["status"] == "imported"
    assert slideshow["source_references_json"] == {"source_type": "local_file"}

    slide = conn.execute(sa.select(slides).where(slides.c.slideshow_id == creative_id)).mappings().one()
    assert slide["slide_index"] == 0
    assert slide["stored_file_path"] == "/tmp/x.jpg"

    assert conn.execute(sa.select(sa.func.count()).select_from(product_appearances)).scalar() == 0


def test_backfills_product_appearance_when_product_assigned(conn):
    creative_id = _insert_creative_with_blueprint(conn, product_id="prod-1")

    with _op(conn):
        migration.upgrade()
    conn.commit()

    slide = conn.execute(sa.select(slides).where(slides.c.slideshow_id == creative_id)).mappings().one()
    appearance = conn.execute(
        sa.select(product_appearances).where(product_appearances.c.slide_id == slide["id"])
    ).mappings().one()
    assert appearance["product_id"] == "prod-1"
    assert appearance["prominence"] == "primary"
    assert appearance["confidence"] == 1.0
    assert appearance["is_current"] == 1


def test_idempotent_second_run_skips_already_backfilled(conn):
    _insert_creative_with_blueprint(conn)

    with _op(conn):
        migration.upgrade()
    conn.commit()
    with _op(conn):
        migration.upgrade()
    conn.commit()

    assert conn.execute(sa.select(sa.func.count()).select_from(slideshows)).scalar() == 1
    assert conn.execute(sa.select(sa.func.count()).select_from(slides)).scalar() == 1


def test_slideshow_id_reuses_creative_id(conn):
    creative_id = _insert_creative_with_blueprint(conn)

    with _op(conn):
        migration.upgrade()
    conn.commit()

    assert conn.execute(sa.select(sa.func.count()).select_from(slideshows).where(slideshows.c.id == creative_id)).scalar() == 1


def test_downgrade_clears_backfilled_rows(conn):
    _insert_creative_with_blueprint(conn, product_id="prod-1")

    with _op(conn):
        migration.upgrade()
    conn.commit()

    with _op(conn):
        migration.downgrade()
    conn.commit()

    assert conn.execute(sa.select(sa.func.count()).select_from(slideshows)).scalar() == 0
    assert conn.execute(sa.select(sa.func.count()).select_from(slides)).scalar() == 0
    assert conn.execute(sa.select(sa.func.count()).select_from(product_appearances)).scalar() == 0
