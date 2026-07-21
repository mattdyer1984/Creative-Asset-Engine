"""
Creatives API.

M1 added import/list/get/file-serving. M2 adds triggering the Analysis
Orchestrator and reading back its results (plan §6, §11).
"""

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.analysis_run import AnalysisRun
from app.models.creative import Creative
from app.models.creative_fingerprint import CreativeFingerprint
from app.models.marketing_analysis import MarketingAnalysis
from app.models.ocr_result import OCRResult
from app.models.product import Product
from app.models.project import Project
from app.models.recreation_prompt import RecreationPrompt
from app.orchestrator import default_orchestrator
from app.schemas import (
    AnalysisRunRead,
    AssembledCreativeBlueprint,
    AssignProductRequest,
    CreativeFingerprintRead,
    CreativeRead,
    MarketingAnalysisRead,
    OCRResultRead,
    RecreationPromptRead,
)
from app.services.creative_blueprint import assemble_creative_blueprint
from app.services.creative_import import import_creatives
from app.stages.pipeline import STAGE_PIPELINE

router = APIRouter(prefix="/api/creatives", tags=["creatives"])


@router.post("/import", response_model=list[CreativeRead], status_code=201)
async def import_local_files(
    files: list[UploadFile] = File(...),
    project_id: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> list[Creative]:
    if project_id is not None and db.get(Project, project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")

    file_payload = [{"filename": f.filename, "content": await f.read()} for f in files]

    creatives = import_creatives(
        db,
        source_type="local_file",
        source_config={"files": file_payload},
        project_id=project_id,
    )
    return creatives


@router.get("", response_model=list[CreativeRead])
def list_creatives(
    project_id: str | None = None, db: Session = Depends(get_db)
) -> list[Creative]:
    stmt = select(Creative).order_by(Creative.imported_at.desc())
    if project_id is not None:
        stmt = stmt.where(Creative.project_id == project_id)
    return list(db.scalars(stmt))


@router.get("/{creative_id}", response_model=CreativeRead)
def get_creative(creative_id: str, db: Session = Depends(get_db)) -> Creative:
    creative = db.get(Creative, creative_id)
    if creative is None:
        raise HTTPException(status_code=404, detail="Creative not found")
    return creative


@router.get("/{creative_id}/file")
def get_creative_file(creative_id: str, db: Session = Depends(get_db)) -> FileResponse:
    """Serves the original imported image - used by the frontend for thumbnails."""
    creative = db.get(Creative, creative_id)
    if creative is None:
        raise HTTPException(status_code=404, detail="Creative not found")
    return FileResponse(creative.stored_file_path)


@router.post("/{creative_id}/analyze", response_model=AssembledCreativeBlueprint)
def analyze_creative(creative_id: str, db: Session = Depends(get_db)) -> AssembledCreativeBlueprint:
    """
    Runs the full Stage pipeline (plan §6, §11) synchronously. V1 has no
    background worker, so this request blocks until every stage has
    succeeded or one has failed - acceptable for a single-user local app
    given the pipeline's current size; worth revisiting once it grows
    enough that this becomes a slow request.

    Returns the assembled Blueprint (plan §1 principle 7) directly,
    rather than the bare Creative - the whole point of M7 is that
    triggering analysis and viewing its result are the same "one call,
    one cohesive answer" shape as the rerun endpoint below.
    """
    creative = db.get(Creative, creative_id)
    if creative is None:
        raise HTTPException(status_code=404, detail="Creative not found")

    default_orchestrator.run_full_pipeline(db, creative)
    db.refresh(creative)
    return assemble_creative_blueprint(db, creative)


@router.get("/{creative_id}/ocr-result", response_model=OCRResultRead)
def get_ocr_result(creative_id: str, db: Session = Depends(get_db)) -> OCRResultRead:
    creative = db.get(Creative, creative_id)
    if creative is None:
        raise HTTPException(status_code=404, detail="Creative not found")

    ocr_result_id = creative.blueprint.current_ocr_result_id
    if ocr_result_id is None:
        raise HTTPException(status_code=404, detail="No OCR result yet for this creative")

    ocr_result = db.get(OCRResult, ocr_result_id)
    return OCRResultRead(
        id=ocr_result.id,
        schema_version=ocr_result.schema_version,
        is_current=ocr_result.is_current,
        raw_text=ocr_result.raw_text,
        structured_blocks=ocr_result.structured_blocks_json,
        created_at=ocr_result.created_at,
    )


@router.get("/{creative_id}/creative-fingerprint", response_model=CreativeFingerprintRead)
def get_creative_fingerprint(creative_id: str, db: Session = Depends(get_db)) -> CreativeFingerprintRead:
    creative = db.get(Creative, creative_id)
    if creative is None:
        raise HTTPException(status_code=404, detail="Creative not found")

    fingerprint_id = creative.blueprint.current_creative_fingerprint_id
    if fingerprint_id is None:
        raise HTTPException(status_code=404, detail="No Creative Fingerprint yet for this creative")

    fingerprint = db.get(CreativeFingerprint, fingerprint_id)
    return CreativeFingerprintRead(
        id=fingerprint.id,
        schema_version=fingerprint.schema_version,
        is_current=fingerprint.is_current,
        structured=fingerprint.structured_json,
        created_at=fingerprint.created_at,
    )


@router.get("/{creative_id}/marketing-analysis", response_model=MarketingAnalysisRead)
def get_marketing_analysis(creative_id: str, db: Session = Depends(get_db)) -> MarketingAnalysis:
    creative = db.get(Creative, creative_id)
    if creative is None:
        raise HTTPException(status_code=404, detail="Creative not found")

    marketing_analysis_id = creative.blueprint.current_marketing_analysis_id
    if marketing_analysis_id is None:
        raise HTTPException(status_code=404, detail="No Marketing Analysis yet for this creative")

    marketing_analysis = db.get(MarketingAnalysis, marketing_analysis_id)
    return marketing_analysis


@router.get("/{creative_id}/recreation-prompt", response_model=RecreationPromptRead)
def get_recreation_prompt(creative_id: str, db: Session = Depends(get_db)) -> RecreationPromptRead:
    creative = db.get(Creative, creative_id)
    if creative is None:
        raise HTTPException(status_code=404, detail="Creative not found")

    prompt_id = creative.blueprint.current_recreation_prompt_id
    if prompt_id is None:
        raise HTTPException(status_code=404, detail="No Recreation Prompt yet for this creative")

    prompt = db.get(RecreationPrompt, prompt_id)
    return RecreationPromptRead(
        id=prompt.id,
        schema_version=prompt.schema_version,
        is_current=prompt.is_current,
        product_lock_profile_id=prompt.product_lock_profile_id,
        creative_fingerprint_id=prompt.creative_fingerprint_id,
        structured=prompt.structured_json,
        created_at=prompt.created_at,
    )


@router.get("/{creative_id}/blueprint", response_model=AssembledCreativeBlueprint)
def get_creative_blueprint(creative_id: str, db: Session = Depends(get_db)) -> AssembledCreativeBlueprint:
    """
    The single, canonical view of a Creative (plan §1 principle 7): every
    Analysis Artifact it currently has, assembled into one response. This
    is what the frontend's Creative Blueprint screen renders from - it
    never needs to know these came from six independent Stages.
    """
    creative = db.get(Creative, creative_id)
    if creative is None:
        raise HTTPException(status_code=404, detail="Creative not found")
    return assemble_creative_blueprint(db, creative)


_STAGE_NAMES = {stage.name for stage in STAGE_PIPELINE}


@router.post("/{creative_id}/stages/{stage_name}/rerun", response_model=AssembledCreativeBlueprint)
def rerun_stage(
    creative_id: str, stage_name: str, db: Session = Depends(get_db)
) -> AssembledCreativeBlueprint:
    """
    Reruns exactly one stage (plan §6.2's run_single_stage) - never the
    whole pipeline, and never cascades into downstream stages. Returns
    the freshly-assembled Blueprint either way, so the frontend can show
    the result (including a failure) without a second request.
    """
    creative = db.get(Creative, creative_id)
    if creative is None:
        raise HTTPException(status_code=404, detail="Creative not found")

    if stage_name not in _STAGE_NAMES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown stage '{stage_name}'. Known stages: {sorted(_STAGE_NAMES)}",
        )

    default_orchestrator.run_single_stage(db, creative, stage_name)
    db.refresh(creative)
    return assemble_creative_blueprint(db, creative)


@router.get("/{creative_id}/analysis-runs", response_model=list[AnalysisRunRead])
def list_analysis_runs(creative_id: str, db: Session = Depends(get_db)) -> list[AnalysisRun]:
    """Full traceability view (plan §1, principle 3) - every attempt, not just the current one."""
    creative = db.get(Creative, creative_id)
    if creative is None:
        raise HTTPException(status_code=404, detail="Creative not found")

    stmt = (
        select(AnalysisRun)
        .where(AnalysisRun.creative_id == creative_id)
        .order_by(AnalysisRun.created_at.desc())
    )
    return list(db.scalars(stmt))


@router.post("/{creative_id}/assign-product", response_model=CreativeRead)
def assign_product(
    creative_id: str, payload: AssignProductRequest, db: Session = Depends(get_db)
) -> Creative:
    """
    Links (or unlinks, if product_id is null) a Creative to a Product
    (plan §11, step 1's "new product or existing?" prompt). Creating a
    new Product is a separate POST /api/products call from the frontend,
    followed by this endpoint to link it - kept as two steps rather than
    one combined endpoint, since Product creation is a standalone,
    reusable operation independent of any particular Creative.
    """
    creative = db.get(Creative, creative_id)
    if creative is None:
        raise HTTPException(status_code=404, detail="Creative not found")

    if payload.product_id is not None and db.get(Product, payload.product_id) is None:
        raise HTTPException(status_code=404, detail="Product not found")

    creative.product_id = payload.product_id
    db.commit()
    db.refresh(creative)
    return creative
