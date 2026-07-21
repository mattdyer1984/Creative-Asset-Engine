"""
Shared pytest fixtures.

Each test gets its own throwaway SQLite DB (file-based, in a temp dir,
not in-memory - the app's engine uses check_same_thread=False, and a
real temp file avoids any surprises from sharing a single in-memory DB
across the multiple connections FastAPI's dependency system can open).
"""

import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models.creative import Creative
from app.models.creative_blueprint import CreativeBlueprint
from app.models.product import Product


@pytest.fixture(autouse=True)
def isolated_storage_dir(monkeypatch, tmp_path):
    """
    Redirects app.config.settings.data_dir (and therefore storage_dir) to
    a per-test temp directory. Without this, any test that goes through
    the real import path (app.services.creative_import ->
    app.storage.save_creative_original) would write files into the real
    backend/data/storage/ directory on disk - autouse so this applies to
    every test, not just ones that obviously need it.
    """
    from app.config import settings

    monkeypatch.setattr(settings, "data_dir", tmp_path / "test-data")
    settings.ensure_directories()


@pytest.fixture()
def db_session():
    tmp_dir = tempfile.mkdtemp()
    db_path = Path(tmp_dir) / "test.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)

    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def creative_with_blueprint(db_session, tmp_path):
    """A persisted Creative + CreativeBlueprint, with a real (tiny) file on disk."""
    image_path = tmp_path / "test-image.jpg"
    # The OCR stage only reads raw bytes and hands them to the provider
    # (mocked in these tests) - it never decodes the image itself, so
    # this doesn't need to be a real, valid JPEG.
    image_path.write_bytes(b"\xff\xd8\xff\xe0fake-jpeg-bytes")

    creative = Creative(
        original_filename="test-image.jpg",
        source_type="local_file",
        source_locator="test-image.jpg",
        stored_file_path=str(image_path),
        imported_at=datetime.now(timezone.utc),
    )
    db_session.add(creative)
    db_session.flush()

    blueprint = CreativeBlueprint(creative_id=creative.id)
    db_session.add(blueprint)
    db_session.commit()
    db_session.refresh(creative)

    return creative


@pytest.fixture()
def creative_with_product(db_session, tmp_path):
    """
    Like creative_with_blueprint, but with a Product already assigned -
    the prerequisite Product Isolation and Product Lock Profile Stages
    require (plan §8A).

    Unlike creative_with_blueprint's fake byte string, this writes a real,
    decodable JPEG - the Product Isolation Stage actually opens and crops
    the image via Pillow, so it needs real image bytes, not just any
    bytes a provider double can ignore.
    """
    from PIL import Image

    product = Product(display_name="Sunrise Orange Juice")
    db_session.add(product)
    db_session.flush()

    image_path = tmp_path / "test-image.jpg"
    Image.new("RGB", (400, 400), color=(210, 160, 120)).save(image_path)

    creative = Creative(
        product_id=product.id,
        original_filename="test-image.jpg",
        source_type="local_file",
        source_locator="test-image.jpg",
        stored_file_path=str(image_path),
        imported_at=datetime.now(timezone.utc),
    )
    db_session.add(creative)
    db_session.flush()

    blueprint = CreativeBlueprint(creative_id=creative.id)
    db_session.add(blueprint)
    db_session.commit()
    db_session.refresh(creative)

    return creative
