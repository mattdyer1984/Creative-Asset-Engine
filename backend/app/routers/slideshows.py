"""
Slideshows API - the sole creative-import/analysis surface as of the
Slideshow/Slide migration (it replaced /api/creatives/*, removed in
Phase 2.7).
"""

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.models.analysis_run import AnalysisRun
from app.models.product import Product
from app.models.product_appearance import ProductAppearance
from app.models.project import Project
from app.models.slide import Slide
from app.models.slideshow import Slideshow
from app.schemas import (
    AnalysisRunRead,
    AssembledSlideshowBlueprint,
    AssignSlideProductRequest,
    SlideshowRead,
)
from app.services.slideshow_blueprint import assemble_slideshow_blueprint
from app.services.slideshow_import import import_slideshows
from app.slideshow_stages.orchestrator import default_slideshow_orchestrator
from app.slideshow_stages.pipeline import SLIDESHOW_STAGE_PIPELINE

router = APIRouter(prefix="/api/slideshows", tags=["slideshows"])


@router.post("/import", response_model=list[SlideshowRead], status_code=201)
async def import_local_files(
    files: list[UploadFile] = File(...),
    project_id: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> list[Slideshow]:
    if project_id is not None and db.get(Project, project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")

    file_payload = [{"filename": f.filename, "content": await f.read()} for f in files]

    slideshows = import_slideshows(
        db,
        source_type="local_file",
        source_config={"files": file_payload},
        project_id=project_id,
    )
    return slideshows


def _with_slide_relationships(stmt):
    """
    Eager-loads what SlideshowRead needs to serialize (slides, each
    slide's product_appearances for current_product_appearance, and each
    appearance's product) in a fixed small number of queries regardless
    of row count - without this, iterating N slideshows lazy-loads
    slides/appearances/products per slideshow. Measured with a fresh
    session per request (matching production - get_db opens/closes a
    new session per call, so no request benefits from another request's
    identity-map cache): 5 slideshows/1 product went from 12 queries to
    4; 10 slideshows/2 products stayed flat at 4 after this fix.
    """
    return stmt.options(
        selectinload(Slideshow.slides)
        .selectinload(Slide.product_appearances)
        .selectinload(ProductAppearance.product)
    )


@router.get("", response_model=list[SlideshowRead])
def list_slideshows(
    project_id: str | None = None, db: Session = Depends(get_db)
) -> list[Slideshow]:
    stmt = _with_slide_relationships(select(Slideshow)).order_by(Slideshow.imported_at.desc())
    if project_id is not None:
        stmt = stmt.where(Slideshow.project_id == project_id)
    return list(db.scalars(stmt))


@router.get("/{slideshow_id}", response_model=SlideshowRead)
def get_slideshow(slideshow_id: str, db: Session = Depends(get_db)) -> Slideshow:
    stmt = _with_slide_relationships(select(Slideshow)).where(Slideshow.id == slideshow_id)
    slideshow = db.scalars(stmt).first()
    if slideshow is None:
        raise HTTPException(status_code=404, detail="Slideshow not found")
    return slideshow


@router.get("/{slideshow_id}/slides/{slide_id}/file")
def get_slide_file(
    slideshow_id: str, slide_id: str, db: Session = Depends(get_db)
) -> FileResponse:
    """Serves one slide's original imported image - used by the frontend for thumbnails."""
    slide = db.get(Slide, slide_id)
    if slide is None or slide.slideshow_id != slideshow_id:
        raise HTTPException(status_code=404, detail="Slide not found")
    return FileResponse(slide.stored_file_path)


@router.post("/{slideshow_id}/analyze", response_model=AssembledSlideshowBlueprint)
def analyze_slideshow(
    slideshow_id: str, db: Session = Depends(get_db)
) -> AssembledSlideshowBlueprint:
    """
    Runs the full new Stage pipeline synchronously - same blocking
    behavior as the old /api/creatives/{id}/analyze (async execution is
    a separate, later phase, not this one).
    """
    slideshow = db.get(Slideshow, slideshow_id)
    if slideshow is None:
        raise HTTPException(status_code=404, detail="Slideshow not found")

    default_slideshow_orchestrator.run_full_pipeline(db, slideshow)
    db.refresh(slideshow)
    return assemble_slideshow_blueprint(db, slideshow)


@router.get("/{slideshow_id}/blueprint", response_model=AssembledSlideshowBlueprint)
def get_slideshow_blueprint(
    slideshow_id: str, db: Session = Depends(get_db)
) -> AssembledSlideshowBlueprint:
    slideshow = db.get(Slideshow, slideshow_id)
    if slideshow is None:
        raise HTTPException(status_code=404, detail="Slideshow not found")
    return assemble_slideshow_blueprint(db, slideshow)


_STAGE_NAMES = {stage.name for stage in SLIDESHOW_STAGE_PIPELINE}


@router.post("/{slideshow_id}/stages/{stage_name}/rerun", response_model=AssembledSlideshowBlueprint)
def rerun_stage(
    slideshow_id: str, stage_name: str, db: Session = Depends(get_db)
) -> AssembledSlideshowBlueprint:
    slideshow = db.get(Slideshow, slideshow_id)
    if slideshow is None:
        raise HTTPException(status_code=404, detail="Slideshow not found")

    if stage_name not in _STAGE_NAMES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown stage '{stage_name}'. Known stages: {sorted(_STAGE_NAMES)}",
        )

    default_slideshow_orchestrator.run_single_stage(db, slideshow, stage_name)
    db.refresh(slideshow)
    return assemble_slideshow_blueprint(db, slideshow)


@router.get("/{slideshow_id}/analysis-runs", response_model=list[AnalysisRunRead])
def list_analysis_runs(slideshow_id: str, db: Session = Depends(get_db)) -> list[AnalysisRun]:
    """Full traceability view - every attempt, not just the current one."""
    slideshow = db.get(Slideshow, slideshow_id)
    if slideshow is None:
        raise HTTPException(status_code=404, detail="Slideshow not found")

    slide_ids = [s.id for s in slideshow.slides]
    stmt = (
        select(AnalysisRun)
        .where(
            (AnalysisRun.slideshow_id == slideshow_id) | (AnalysisRun.slide_id.in_(slide_ids))
        )
        .order_by(AnalysisRun.created_at.desc())
    )
    return list(db.scalars(stmt))


@router.post("/{slideshow_id}/slides/{slide_id}/assign-product", response_model=SlideshowRead)
def assign_product(
    slideshow_id: str,
    slide_id: str,
    payload: AssignSlideProductRequest,
    db: Session = Depends(get_db),
) -> Slideshow:
    """
    Links (or unlinks, if product_id is null) a Slide to a Product by
    creating (or flipping off) a ProductAppearance - the new-pipeline
    equivalent of the old assign-product endpoint's direct
    Creative.product_id assignment.
    """
    slideshow = db.get(Slideshow, slideshow_id)
    if slideshow is None:
        raise HTTPException(status_code=404, detail="Slideshow not found")

    slide = db.get(Slide, slide_id)
    if slide is None or slide.slideshow_id != slideshow_id:
        raise HTTPException(status_code=404, detail="Slide not found")

    if payload.product_id is not None and db.get(Product, payload.product_id) is None:
        raise HTTPException(status_code=404, detail="Product not found")

    db.query(ProductAppearance).filter(
        ProductAppearance.slide_id == slide.id,
        ProductAppearance.is_current.is_(True),
    ).update({"is_current": False})

    if payload.product_id is not None:
        appearance = ProductAppearance(
            slide_id=slide.id,
            product_id=payload.product_id,
            prominence="primary",
            confidence=1.0,
            is_current=True,
        )
        db.add(appearance)

    db.commit()
    db.refresh(slideshow)
    return slideshow
