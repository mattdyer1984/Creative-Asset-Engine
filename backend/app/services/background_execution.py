"""
Background execution wrappers (Phase 3.1 of the async execution boundary
work — see MIGRATION_PLAN.md).

A request-scoped Session (app.db.get_db) is closed as soon as the request
that owns it finishes - it cannot be reused after the HTTP response has
been sent, which is exactly when a FastAPI BackgroundTasks callback runs.
These wrappers exist solely to open their own short-lived Session, re-fetch
the Slideshow by id inside it, and delegate to the existing
SlideshowOrchestrator - no analysis logic lives here.

Wired into app.routers.slideshows since Phase 3.2/3.3 - the
analyze/rerun-stage endpoints schedule these via BackgroundTasks.

Imports app.db as a module (not `from app.db import SessionLocal`) and
looks up `app.db.SessionLocal` at call time rather than binding it at
import time - tests need to monkeypatch app.db.SessionLocal to point at
their own per-test engine (see tests/conftest.py's db_session fixture),
the same way app.dependency_overrides[get_db] redirects the request-scoped
session; a `from ... import` binding would capture the real, un-patched
SessionLocal before any test fixture had a chance to override it.
"""

import app.db
from app.models.product import Product
from app.models.slideshow import Slideshow
from app.services.reference_scoring_stage import run_reference_scoring
from app.slideshow_stages.orchestrator import default_slideshow_orchestrator


def run_pipeline_in_background(slideshow_id: str) -> None:
    db = app.db.SessionLocal()
    try:
        slideshow = db.get(Slideshow, slideshow_id)
        if slideshow is None:
            return
        default_slideshow_orchestrator.run_full_pipeline(db, slideshow)
    finally:
        db.close()


def run_stage_in_background(slideshow_id: str, stage_name: str) -> None:
    db = app.db.SessionLocal()
    try:
        slideshow = db.get(Slideshow, slideshow_id)
        if slideshow is None:
            return
        default_slideshow_orchestrator.run_single_stage(db, slideshow, stage_name)
    finally:
        db.close()


def run_reference_scoring_in_background(product_id: str) -> None:
    """Phase 9.2 of Product Lock v2 (see MIGRATION_PLAN.md's ADR §4/§8)."""
    db = app.db.SessionLocal()
    try:
        product = db.get(Product, product_id)
        if product is None:
            return
        run_reference_scoring(db, product_id)
        db.commit()
    finally:
        db.close()
