"""
Slideshows API - the sole creative-import/analysis surface as of the
Slideshow/Slide migration (it replaced /api/creatives/*, removed in
Phase 2.7).
"""

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select, update
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.models.analysis_run import AnalysisRun
from app.models.creative_specification import CreativeSpecification
from app.models.final_output import FinalOutput
from app.models.generated_image import GeneratedImage
from app.models.generation_attempt import GenerationAttempt
from app.models.generation_log import GenerationLog
from app.models.generation_reference_set import GenerationReferenceSet
from app.models.generation_reference_set_image import GenerationReferenceSetImage
from app.models.image_validation_result import ImageValidationResult
from app.models.product import Product
from app.models.product_appearance import ProductAppearance
from app.models.project import Project
from app.models.quality_assessment import QualityAssessment
from app.models.slide import Slide
from app.models.slideshow import STATUS_ANALYZING, STATUS_QUEUED, Slideshow
from app.importers.downie import (
    DownieImportError,
    DownieImportTimeoutError,
    DownieImportUnavailableError,
    DownieImportUnsupportedContentError,
)
from app.importers.playwright_tiktok import (
    TikTokImportBlockedError,
    TikTokImportError,
    TikTokImportNotFoundError,
    TikTokImportUnsupportedContentError,
)
from app.schemas import (
    AddSlideProductRequest,
    AnalysisRunRead,
    AssembledSlideshowBlueprint,
    AssignSlideProductRequest,
    FinalOutputRead,
    GenerateCreativeRequest,
    GenerateCreativeResponse,
    GeneratedImageRead,
    GenerationAttemptRead,
    GenerationCandidateRead,
    GenerationReferenceSetImageRead,
    GenerationReferenceSetRead,
    ImageValidationFieldCheckRead,
    ImageValidationResultRead,
    QualityAssessmentRead,
    SlideshowRead,
    SlideshowUrlImportRequest,
)
from app.services.background_execution import run_pipeline_in_background, run_stage_in_background
from app.services.generate_with_retry import RetryLoopResult, generate_with_retry
from app.services.generation_log_archive import create_archive
from app.services.project_product import ensure_project_product_membership
from app.services.slideshow_blueprint import assemble_slideshow_blueprint
from app.slideshow_stages.creative_specification_stage import resolve_primary_appearance
from app.services.slideshow_import import import_slideshows
from app.slideshow_stages.base import StageResult
from app.slideshow_stages.image_generation_stage import SlideImageGenerationStage
from app.slideshow_stages.image_validation_stage import SlideImageValidationStage
from app.slideshow_stages.pipeline import SLIDESHOW_STAGE_PIPELINE

router = APIRouter(prefix="/api/slideshows", tags=["slideshows"])


@router.post("/import", response_model=list[SlideshowRead], status_code=201)
async def import_local_files(
    files: list[UploadFile] = File(...),
    project_id: str | None = Form(default=None),
    group_as_one: bool = Form(default=False),
    db: Session = Depends(get_db),
) -> list[Slideshow]:
    """
    group_as_one (Phase 4 - true multi-slide import, see
    MIGRATION_PLAN.md): default False preserves the existing behavior
    (every file becomes its own independent Slideshow). Set True to
    import all files in this one request as a single Slideshow's ordered
    Slides instead - an explicit choice, never inferred from "more than
    one file was selected."
    """
    if project_id is not None and db.get(Project, project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")

    file_payload = [{"filename": f.filename, "content": await f.read()} for f in files]

    slideshows = import_slideshows(
        db,
        source_type="local_file",
        source_config={"files": file_payload},
        project_id=project_id,
        group_as_one=group_as_one,
    )
    return slideshows


@router.post("/import-url", response_model=list[SlideshowRead], status_code=201)
def import_from_url(payload: SlideshowUrlImportRequest, db: Session = Depends(get_db)) -> list[Slideshow]:
    """
    Phase 10.6 of AI Creative Engine vNext, see MIGRATION_PLAN.md - the
    URL counterpart to import_local_files, backed by
    PlaywrightTikTokImporter by default, or DownieImporter (Phase 10.6b's
    documented fallback) via an explicit `payload.provider="downie"` opt-in
    - never inferred, since Downie is a deployment-environment decision
    (a licensed local copy must be installed). Deliberately a plain `def`,
    not `async def`: FastAPI runs a sync path operation in a threadpool,
    which is what both providers need (a real browser launch, or shelling
    out to `open` and polling disk) to not block the event loop - the same
    reasoning app.routers.products' create_source_import already applies
    to its own blocking httpx fetch.

    Always group_as_one=True: a TikTok post's images are one coherent
    slideshow the platform itself already ordered, not "N unrelated
    files the user happened to select" - the reasoning that makes
    group_as_one an explicit opt-in for local_file uploads doesn't apply
    here, so this isn't user-configurable for this source type.
    """
    if payload.project_id is not None and db.get(Project, payload.project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if payload.provider not in ("tiktok", "downie"):
        raise HTTPException(
            status_code=400, detail=f"Unknown provider '{payload.provider}' - expected 'tiktok' or 'downie'"
        )

    try:
        return import_slideshows(
            db,
            source_type=payload.provider,
            source_config={"url": payload.url},
            project_id=payload.project_id,
            group_as_one=True,
        )
    except TikTokImportBlockedError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except TikTokImportUnsupportedContentError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except TikTokImportNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except TikTokImportError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except DownieImportUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except DownieImportTimeoutError as exc:
        raise HTTPException(status_code=504, detail=str(exc)) from exc
    except DownieImportUnsupportedContentError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except DownieImportError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


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


def _quality_assessment_read(quality_assessment: QualityAssessment) -> QualityAssessmentRead:
    """
    Built explicitly, not via model_validate - the ORM's photorealism_json
    doesn't match this schema's photorealism name, same "computed/renamed
    fields need explicit construction" reasoning as ImageValidationResultRead.
    Shared by generate_creative and list_generation_attempts (Phase 11.2,
    see MIGRATION_PLAN.md) so the two read paths can't drift apart.
    """
    return QualityAssessmentRead(
        id=quality_assessment.id,
        generated_image_id=quality_assessment.generated_image_id,
        image_validation_result_id=quality_assessment.image_validation_result_id,
        image_validation_result_ids=quality_assessment.image_validation_result_ids_json,
        photorealism=quality_assessment.photorealism_json,
        overall_confidence_score=quality_assessment.overall_confidence_score,
        accepted=quality_assessment.accepted,
        created_at=quality_assessment.created_at,
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


@router.post("/{slideshow_id}/analyze", response_model=SlideshowRead, status_code=202)
def analyze_slideshow(
    slideshow_id: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db)
) -> Slideshow:
    """
    Schedules the full Stage pipeline to run in the background (Phase 3.2
    of the async execution boundary work - see MIGRATION_PLAN.md) instead
    of blocking the request for the pipeline's full duration. Returns as
    soon as status flips to "queued" - 202 Accepted, not 200, since unlike
    every other endpoint in this router the work described by the request
    is deliberately not done yet when the response is sent. Poll
    GET .../blueprint (or the slideshow list) to observe progress through
    queued -> analyzing -> ready|failed.

    Claims the row with a single atomic UPDATE ... WHERE status NOT IN
    (...) rather than a separate read-then-write - caught live (via two
    genuinely concurrent requests against a real running server, not just
    TestClient) doing it as a plain read-check-then-write: two overlapping
    requests could both read the pre-queued status before either had
    committed, and both would pass the guard. SQLite serializes writer
    transactions, so the second of two concurrent UPDATEs against the
    same row always sees the first one's already-committed result.
    """
    result = db.execute(
        update(Slideshow)
        .where(Slideshow.id == slideshow_id, Slideshow.status.notin_((STATUS_QUEUED, STATUS_ANALYZING)))
        .values(status=STATUS_QUEUED)
    )
    db.commit()

    if result.rowcount == 0:
        if db.get(Slideshow, slideshow_id) is None:
            raise HTTPException(status_code=404, detail="Slideshow not found")
        raise HTTPException(status_code=409, detail="Analysis already in progress")

    slideshow = db.get(Slideshow, slideshow_id)

    background_tasks.add_task(run_pipeline_in_background, slideshow_id)

    return slideshow


@router.get("/{slideshow_id}/blueprint", response_model=AssembledSlideshowBlueprint)
def get_slideshow_blueprint(
    slideshow_id: str, db: Session = Depends(get_db)
) -> AssembledSlideshowBlueprint:
    slideshow = db.get(Slideshow, slideshow_id)
    if slideshow is None:
        raise HTTPException(status_code=404, detail="Slideshow not found")
    return assemble_slideshow_blueprint(db, slideshow)


_STAGE_NAMES = {stage.name for stage in SLIDESHOW_STAGE_PIPELINE}


@router.post("/{slideshow_id}/stages/{stage_name}/rerun", response_model=SlideshowRead, status_code=202)
def rerun_stage(
    slideshow_id: str, stage_name: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db)
) -> Slideshow:
    """
    Schedules a single stage rerun in the background (Phase 3.3 of the
    async execution boundary work - see MIGRATION_PLAN.md), mirroring
    analyze_slideshow's approach exactly: same atomic UPDATE ... WHERE
    claim (see that function's docstring for why a plain read-then-write
    isn't safe under concurrent requests), same 202 + SlideshowRead
    response shape, same polling contract via GET .../blueprint.
    """
    if stage_name not in _STAGE_NAMES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown stage '{stage_name}'. Known stages: {sorted(_STAGE_NAMES)}",
        )

    result = db.execute(
        update(Slideshow)
        .where(Slideshow.id == slideshow_id, Slideshow.status.notin_((STATUS_QUEUED, STATUS_ANALYZING)))
        .values(status=STATUS_QUEUED)
    )
    db.commit()

    if result.rowcount == 0:
        if db.get(Slideshow, slideshow_id) is None:
            raise HTTPException(status_code=404, detail="Slideshow not found")
        raise HTTPException(status_code=409, detail="Analysis already in progress")

    slideshow = db.get(Slideshow, slideshow_id)

    background_tasks.add_task(run_stage_in_background, slideshow_id, stage_name)

    return slideshow


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


@router.post(
    "/{slideshow_id}/slides/{slide_id}/generate-image",
    response_model=GeneratedImageRead,
    status_code=201,
)
def generate_image(slideshow_id: str, slide_id: str, db: Session = Depends(get_db)) -> GeneratedImage:
    """
    Phase 8.3 of the Generation -> Validation proof of loop (see
    MIGRATION_PLAN.md) - deliberately synchronous, not the
    background-task/polling pattern every pipeline stage uses (that
    pattern exists to keep /analyze's status polling coherent; this
    endpoint is a standalone, explicitly-triggered action with its own
    response, not part of that status machine). Real image-generation
    latency is comparable to the vision/text calls already awaited
    synchronously elsewhere in this codebase's tests.

    Only slide_id == slideshow.primary_slide.id is supported today - the
    architecture direction's explicit "one slide first" scope boundary,
    checked here rather than silently generating for whichever slide the
    Image Generation Stage happens to read.
    """
    slideshow = db.get(Slideshow, slideshow_id)
    if slideshow is None:
        raise HTTPException(status_code=404, detail="Slideshow not found")

    primary_slide = slideshow.primary_slide
    if slide_id != primary_slide.id:
        raise HTTPException(
            status_code=400,
            detail=(
                "Only the primary slide supports image generation today "
                "(Phase 8's 'one slide first' scope boundary)."
            ),
        )

    result = SlideImageGenerationStage().run(db, slideshow)
    if not result.succeeded:
        raise HTTPException(status_code=422, detail=result.error)

    generated_image = db.scalars(
        select(GeneratedImage).where(
            GeneratedImage.slide_id == primary_slide.id,
            GeneratedImage.is_current.is_(True),
        )
    ).first()
    return generated_image


def _create_generation_log(
    db: Session,
    slideshow: Slideshow,
    slide: Slide,
    payload: GenerateCreativeRequest,
    result: RetryLoopResult,
) -> GenerationLog:
    """
    Phase 12 (Human Feedback & Learning System, see MIGRATION_PLAN.md) -
    one row per generate-creative call, built from the RetryLoopResult
    the caller already has in hand - no changes needed to
    generate_with_retry.py/generation_engine.py themselves. Also
    archives this call's files to a permanent
    Generation Logs/{timestamp}/ folder and links every GenerationAttempt
    this call produced back to the new row.
    """
    creative_specification_id = result.attempts[0].attempt.creative_specification_id
    creative_specification = db.get(CreativeSpecification, creative_specification_id)

    bundle_product_ids = (
        [member.product_id for member in payload.bundle_members] if payload.bundle_members else None
    )
    product_id = None
    if bundle_product_ids is None:
        primary_appearance = resolve_primary_appearance(slide.current_product_appearances)
        product_id = primary_appearance.product_id if primary_appearance is not None else None

    winner = result.winner
    duration = sum(
        candidate.generated_image.generation_time_seconds
        for outcome in result.attempts
        for candidate in outcome.candidates
    )

    generation_log = GenerationLog(
        slideshow_id=slideshow.id,
        slide_id=slide.id,
        project_id=slideshow.project_id,
        product_id=product_id,
        bundle_product_ids_json=bundle_product_ids,
        winning_generated_image_id=winner.generated_image.id if winner is not None else None,
        final_output_id=result.final_output.id if result.final_output is not None else None,
        quality_mode=payload.quality_mode,
        creativity_level=payload.creativity_level,
        text_strategy=payload.text_strategy,
        ai_provider=winner.generated_image.provider if winner is not None else None,
        ai_model=winner.generated_image.model_name if winner is not None else None,
        prompt_used=winner.generated_image.prompt_used if winner is not None else None,
        creative_specification_id=creative_specification_id,
        creative_specification_schema_version=creative_specification.schema_version,
        retry_count=len(result.attempts) - 1,
        generation_duration_seconds=duration,
        archive_path="",
    )
    db.add(generation_log)
    db.flush()

    for outcome in result.attempts:
        outcome.attempt.generation_log_id = generation_log.id

    archive_folder = create_archive(db, generation_log, result, slide)
    generation_log.archive_path = str(archive_folder)

    db.commit()
    db.refresh(generation_log)
    return generation_log


@router.post(
    "/{slideshow_id}/slides/{slide_id}/generate-creative",
    response_model=GenerateCreativeResponse,
    status_code=201,
)
def generate_creative(
    slideshow_id: str, slide_id: str, payload: GenerateCreativeRequest, db: Session = Depends(get_db)
) -> GenerateCreativeResponse:
    """
    Phase 10.2 of AI Creative Engine vNext (see MIGRATION_PLAN.md's ADR
    §11-§14) - the candidate-count-aware, retry-looping counterpart to
    generate-image above. Deliberately synchronous, same reasoning as
    that endpoint: every candidate across every retry is a real, paid
    provider call, so the response only returns once the whole loop
    concludes (a candidate accepted, or the retry limit exhausted), not
    a queued/polled background status - the explicit "Generate
    Creative" action §14 calls for, with its real cost only spent once
    a caller deliberately triggers it.
    """
    slideshow = db.get(Slideshow, slideshow_id)
    if slideshow is None:
        raise HTTPException(status_code=404, detail="Slideshow not found")

    primary_slide = slideshow.primary_slide
    if slide_id != primary_slide.id:
        raise HTTPException(
            status_code=400,
            detail=(
                "Only the primary slide supports image generation today "
                "(Phase 8's 'one slide first' scope boundary)."
            ),
        )

    try:
        result = generate_with_retry(
            db,
            slideshow,
            payload.quality_mode,
            creativity_level=payload.creativity_level,
            bundle_members=(
                [member.model_dump() for member in payload.bundle_members]
                if payload.bundle_members
                else None
            ),
            text_strategy=payload.text_strategy,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if isinstance(result, StageResult):
        raise HTTPException(status_code=422, detail=result.error)

    generation_log = _create_generation_log(db, slideshow, primary_slide, payload, result)

    return GenerateCreativeResponse(
        attempts=[
            GenerationAttemptRead(
                id=outcome.attempt.id,
                quality_mode=outcome.attempt.quality_mode,
                retry_of_generation_attempt_id=outcome.attempt.retry_of_generation_attempt_id,
                created_at=outcome.attempt.created_at,
                candidates=[
                    GenerationCandidateRead(
                        generated_image=GeneratedImageRead.model_validate(candidate.generated_image),
                        quality_assessment=_quality_assessment_read(candidate.quality_assessment),
                    )
                    for candidate in outcome.candidates
                ],
            )
            for outcome in result.attempts
        ],
        winner=GeneratedImageRead.model_validate(result.winner.generated_image)
        if result.winner is not None
        else None,
        final_output=FinalOutputRead(
            id=result.final_output.id,
            generation_attempt_id=result.final_output.generation_attempt_id,
            generated_image_id=result.final_output.generated_image_id,
            text_assets=result.final_output.text_assets_json,
            created_at=result.final_output.created_at,
        )
        if result.final_output is not None
        else None,
        generation_log_id=generation_log.id,
    )


@router.get(
    "/{slideshow_id}/slides/{slide_id}/generation-attempts",
    response_model=list[GenerationAttemptRead],
)
def list_generation_attempts(
    slideshow_id: str, slide_id: str, db: Session = Depends(get_db)
) -> list[GenerationAttemptRead]:
    """
    Phase 11.2 (see MIGRATION_PLAN.md) - a real, additive gap the Phase
    11 audit found: generate-creative's response was the *only* place
    GenerationAttempt/candidate data was ever returned - the frontend
    held it in local component state, discarded the moment the
    blueprint modal closed or the page reloaded. No schema change - the
    data has always been persisted (generation_attempts/
    generated_images/quality_assessments); this just makes it readable
    independently of the one paid call that created it, most recent
    first, reusing the exact same GenerationAttemptRead/
    GenerationCandidateRead shape generate-creative's own response
    already uses via the shared _quality_assessment_read helper below.

    Real bug found and fixed during this endpoint's own live
    verification (not assumed correct from the code): one real
    historical GeneratedImage row in the dev DB has no matching
    QualityAssessment at all (the Quality Engine call for that specific
    candidate evidently never completed/persisted, in an earlier
    session, before this endpoint ever existed to read it back). A
    naive one-QualityAssessment-per-candidate assumption (`.one()`)
    500'd on that real row the moment this endpoint was clicked through
    the actual UI. Fixed to skip a candidate with no assessment rather
    than crash the whole history - a real, honest gap in that one old
    row, not something this read endpoint should hide by failing
    everything else around it.
    """
    slideshow = db.get(Slideshow, slideshow_id)
    if slideshow is None:
        raise HTTPException(status_code=404, detail="Slideshow not found")

    attempts = (
        db.query(GenerationAttempt)
        .filter(GenerationAttempt.slide_id == slide_id)
        .order_by(GenerationAttempt.created_at.desc())
        .all()
    )
    result = []
    for attempt in attempts:
        candidates = []
        generated_images = (
            db.query(GeneratedImage)
            .filter(GeneratedImage.generation_attempt_id == attempt.id)
            .order_by(GeneratedImage.candidate_index)
            .all()
        )
        for generated_image in generated_images:
            quality_assessment = (
                db.query(QualityAssessment)
                .filter(QualityAssessment.generated_image_id == generated_image.id)
                .first()
            )
            if quality_assessment is None:
                continue
            candidates.append(
                GenerationCandidateRead(
                    generated_image=GeneratedImageRead.model_validate(generated_image),
                    quality_assessment=_quality_assessment_read(quality_assessment),
                )
            )
        result.append(
            GenerationAttemptRead(
                id=attempt.id,
                quality_mode=attempt.quality_mode,
                retry_of_generation_attempt_id=attempt.retry_of_generation_attempt_id,
                created_at=attempt.created_at,
                candidates=candidates,
            )
        )
    return result


@router.get(
    "/{slideshow_id}/slides/{slide_id}/generated-image",
    response_model=GeneratedImageRead,
)
def get_current_generated_image(
    slideshow_id: str, slide_id: str, db: Session = Depends(get_db)
) -> GeneratedImage:
    """
    Phase 8.5 (see MIGRATION_PLAN.md) - lets the frontend show a
    slide's already-generated image on load without spending a real,
    paid regeneration call just to check whether one exists. 404 both
    when the slideshow/slide is unknown and when no image has been
    generated yet - the frontend treats both as "nothing to show".
    """
    slideshow = db.get(Slideshow, slideshow_id)
    if slideshow is None:
        raise HTTPException(status_code=404, detail="Slideshow not found")

    generated_image = db.scalars(
        select(GeneratedImage).where(
            GeneratedImage.slide_id == slide_id,
            GeneratedImage.is_current.is_(True),
        )
    ).first()
    if generated_image is None:
        raise HTTPException(status_code=404, detail="No generated image yet for this slide")
    return generated_image


@router.get("/{slideshow_id}/generated-images/{generated_image_id}/file")
def get_generated_image_file(
    slideshow_id: str, generated_image_id: str, db: Session = Depends(get_db)
) -> FileResponse:
    """Serves one generated image's file - mirrors get_slide_file/get_reference_image_file."""
    generated_image = db.get(GeneratedImage, generated_image_id)
    if generated_image is None or generated_image.slideshow_id != slideshow_id:
        raise HTTPException(status_code=404, detail="Generated image not found")
    return FileResponse(generated_image.file_path)


@router.get("/{slideshow_id}/final-outputs/{final_output_id}/file")
def get_final_output_file(
    slideshow_id: str, final_output_id: str, db: Session = Depends(get_db)
) -> FileResponse:
    """Serves one FinalOutput's composited file (Phase 10.8) - mirrors get_generated_image_file."""
    final_output = db.get(FinalOutput, final_output_id)
    if final_output is None:
        raise HTTPException(status_code=404, detail="Final output not found")
    generated_image = db.get(GeneratedImage, final_output.generated_image_id)
    if generated_image is None or generated_image.slideshow_id != slideshow_id:
        raise HTTPException(status_code=404, detail="Final output not found")
    return FileResponse(final_output.file_path)


@router.get(
    "/{slideshow_id}/generated-images/{generated_image_id}/reference-set",
    response_model=GenerationReferenceSetRead,
)
def get_generation_reference_set(
    slideshow_id: str, generated_image_id: str, db: Session = Depends(get_db)
) -> GenerationReferenceSetRead:
    """
    Phase 9.4 of Product Lock v2 (see MIGRATION_PLAN.md's ADR §8/§9) -
    exactly which Library images, with what role/rank, were sent to the
    provider for this specific generation - the "reference images used"
    strip's data source. Nullable-precondition tri-state, same style as
    get_current_generated_image: 404 if there's genuinely nothing to
    show (no Set - a pre-Product-Lock-v2 GeneratedImage), not a 200
    with empty/fabricated data.
    """
    generated_image = db.get(GeneratedImage, generated_image_id)
    if generated_image is None or generated_image.slideshow_id != slideshow_id:
        raise HTTPException(status_code=404, detail="Generated image not found")
    if generated_image.generation_reference_set_id is None:
        raise HTTPException(
            status_code=404, detail="This generated image has no Generation Reference Set"
        )

    generation_reference_set = db.get(GenerationReferenceSet, generated_image.generation_reference_set_id)
    if generation_reference_set is None:
        raise HTTPException(status_code=404, detail="Generation Reference Set not found")

    members = (
        db.query(GenerationReferenceSetImage)
        .filter(GenerationReferenceSetImage.generation_reference_set_id == generation_reference_set.id)
        .order_by(GenerationReferenceSetImage.rank)
        .all()
    )

    return GenerationReferenceSetRead(
        id=generation_reference_set.id,
        generated_image_id=generation_reference_set.generated_image_id,
        selection_method=generation_reference_set.selection_method_json,
        images=[
            GenerationReferenceSetImageRead(
                product_reference_image_id=member.product_reference_image_id,
                product_id=member.product_id,
                role=member.role,
                rank=member.rank,
            )
            for member in members
        ],
        created_at=generation_reference_set.created_at,
    )


def _to_validation_read(row: ImageValidationResult) -> ImageValidationResultRead:
    return ImageValidationResultRead(
        id=row.id,
        schema_version=row.schema_version,
        is_current=row.is_current,
        generated_image_id=row.generated_image_id,
        product_id=row.product_id,
        passed=row.passed,
        field_checks=[ImageValidationFieldCheckRead(**check) for check in row.field_checks_json],
        overall_explanation=row.overall_explanation,
        created_at=row.created_at,
        identity_passed=row.identity_passed,
        identity_checks=(
            [ImageValidationFieldCheckRead(**check) for check in row.identity_checks_json]
            if row.identity_checks_json is not None
            else None
        ),
    )


@router.post(
    "/{slideshow_id}/generated-images/{generated_image_id}/validate",
    response_model=ImageValidationResultRead,
    status_code=201,
)
def validate_generated_image(
    slideshow_id: str, generated_image_id: str, db: Session = Depends(get_db)
) -> ImageValidationResultRead:
    """
    Phase 8.4 of the Generation -> Validation proof of loop (see
    MIGRATION_PLAN.md) - synchronous, same reasoning as generate_image
    above. Closes the loop: judges a specific GeneratedImage against the
    canonical Product Profile's immutable fields.
    """
    generated_image = db.get(GeneratedImage, generated_image_id)
    if generated_image is None or generated_image.slideshow_id != slideshow_id:
        raise HTTPException(status_code=404, detail="Generated image not found")

    result = SlideImageValidationStage().run(db, generated_image)
    if not result.succeeded:
        raise HTTPException(status_code=422, detail=result.error)

    validation_result = db.scalars(
        select(ImageValidationResult).where(
            ImageValidationResult.generated_image_id == generated_image.id,
            ImageValidationResult.is_current.is_(True),
        )
    ).first()
    return _to_validation_read(validation_result)


@router.get(
    "/{slideshow_id}/generated-images/{generated_image_id}/validation",
    response_model=ImageValidationResultRead,
)
def get_current_validation_result(
    slideshow_id: str, generated_image_id: str, db: Session = Depends(get_db)
) -> ImageValidationResultRead:
    """
    Phase 8.5 (see MIGRATION_PLAN.md) - same "let the frontend show
    existing state without a wasted paid call" reasoning as
    get_current_generated_image above.
    """
    generated_image = db.get(GeneratedImage, generated_image_id)
    if generated_image is None or generated_image.slideshow_id != slideshow_id:
        raise HTTPException(status_code=404, detail="Generated image not found")

    validation_result = db.scalars(
        select(ImageValidationResult).where(
            ImageValidationResult.generated_image_id == generated_image_id,
            ImageValidationResult.is_current.is_(True),
        )
    ).first()
    if validation_result is None:
        raise HTTPException(status_code=404, detail="No validation result yet for this generated image")
    return _to_validation_read(validation_result)


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
        ensure_project_product_membership(db, slideshow.project_id, payload.product_id)

    db.commit()
    db.refresh(slideshow)
    return slideshow


@router.post("/{slideshow_id}/slides/{slide_id}/products", response_model=SlideshowRead)
def add_slide_product(
    slideshow_id: str,
    slide_id: str,
    payload: AddSlideProductRequest,
    db: Session = Depends(get_db),
) -> Slideshow:
    """
    Additive counterpart to assign-product (Phase 6.1 of multi per-slide
    product detection, see MIGRATION_PLAN.md) - adds a current
    ProductAppearance without clearing any existing ones, unlike
    assign-product's single-slot replace semantics. assign-product
    itself is untouched; this is new, parallel capability, not a
    modification of it.

    Idempotent: a second call with the same product_id is a no-op rather
    than creating a duplicate current appearance for the same product.
    """
    slideshow = db.get(Slideshow, slideshow_id)
    if slideshow is None:
        raise HTTPException(status_code=404, detail="Slideshow not found")

    slide = db.get(Slide, slide_id)
    if slide is None or slide.slideshow_id != slideshow_id:
        raise HTTPException(status_code=404, detail="Slide not found")

    if db.get(Product, payload.product_id) is None:
        raise HTTPException(status_code=404, detail="Product not found")

    already_current = db.scalars(
        select(ProductAppearance).where(
            ProductAppearance.slide_id == slide.id,
            ProductAppearance.product_id == payload.product_id,
            ProductAppearance.is_current.is_(True),
        )
    ).first()
    if already_current is None:
        db.add(
            ProductAppearance(
                slide_id=slide.id,
                product_id=payload.product_id,
                prominence="primary",
                confidence=1.0,
                is_current=True,
            )
        )
        ensure_project_product_membership(db, slideshow.project_id, payload.product_id)
        db.commit()

    db.refresh(slideshow)
    return slideshow


@router.delete("/{slideshow_id}/slides/{slide_id}/products/{appearance_id}", response_model=SlideshowRead)
def remove_slide_product(
    slideshow_id: str,
    slide_id: str,
    appearance_id: str,
    db: Session = Depends(get_db),
) -> Slideshow:
    """
    Removes exactly one ProductAppearance (Phase 6.1) - the additive
    counterpart's delete half. Unlike assign-product's null case (which
    clears every current appearance), this only flips off the one named.
    """
    slideshow = db.get(Slideshow, slideshow_id)
    if slideshow is None:
        raise HTTPException(status_code=404, detail="Slideshow not found")

    slide = db.get(Slide, slide_id)
    if slide is None or slide.slideshow_id != slideshow_id:
        raise HTTPException(status_code=404, detail="Slide not found")

    appearance = db.get(ProductAppearance, appearance_id)
    if appearance is None or appearance.slide_id != slide.id:
        raise HTTPException(status_code=404, detail="Product appearance not found")

    appearance.is_current = False
    db.commit()
    db.refresh(slideshow)
    return slideshow
