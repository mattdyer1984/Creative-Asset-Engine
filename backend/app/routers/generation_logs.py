"""
Generation Logs API — Phase 12 (Human Feedback & Learning System, see
MIGRATION_PLAN.md). The searchable index over every generate-creative
call's permanent archive (app.services.generation_log_archive), plus
the one human review each log can carry - the actual training signal a
future personalised quality model would learn from.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.app_setting import SINGLETON_ID, AppSetting
from app.models.generation_log import GenerationLog
from app.models.generation_review import GenerationReview
from app.schemas import (
    GenerationLogDetailRead,
    GenerationLogRead,
    GenerationReviewCreateRequest,
    GenerationReviewRead,
)
from app.services.generation_log_archive import write_review

router = APIRouter(prefix="/api/generation-logs", tags=["generation-logs"])

# The closed set from the spec - main_issue is an open string column
# (mirrors ProductReferenceImage.library_status's own "open column,
# closed set enforced here" design), never a DB-level enum.
VALID_MAIN_ISSUES = {
    "none",
    "product_accuracy",
    "composition",
    "realism",
    "lighting",
    "text",
    "background",
    "originality",
    "other",
}


@router.get("", response_model=list[GenerationLogRead])
def list_generation_logs(
    product_id: str | None = None, sort: str = "created_desc", db: Session = Depends(get_db)
) -> list[GenerationLog]:
    """
    The queryable store the spec asks for (highest/lowest scoring,
    product-specific, review history). score_desc/score_asc need a join
    to generation_reviews - a log with no review yet sorts last for
    score_desc and first for score_asc (nulls_last on both), never
    silently excluded from the list.
    """
    stmt = select(GenerationLog)
    if product_id is not None:
        stmt = stmt.where(GenerationLog.product_id == product_id)

    if sort in ("score_desc", "score_asc"):
        stmt = stmt.outerjoin(
            GenerationReview, GenerationReview.generation_log_id == GenerationLog.id
        )
        order_column = GenerationReview.overall_score
        stmt = stmt.order_by(
            order_column.desc().nulls_last() if sort == "score_desc" else order_column.asc().nulls_last()
        )
    else:
        stmt = stmt.order_by(GenerationLog.created_at.desc())

    return list(db.scalars(stmt))


@router.get("/{generation_log_id}", response_model=GenerationLogDetailRead)
def get_generation_log(generation_log_id: str, db: Session = Depends(get_db)) -> GenerationLogDetailRead:
    generation_log = db.get(GenerationLog, generation_log_id)
    if generation_log is None:
        raise HTTPException(status_code=404, detail="Generation log not found")

    review = db.scalars(
        select(GenerationReview).where(GenerationReview.generation_log_id == generation_log_id)
    ).first()

    return GenerationLogDetailRead(
        **GenerationLogRead.model_validate(generation_log).model_dump(),
        review=GenerationReviewRead.model_validate(review) if review is not None else None,
    )


@router.post("/{generation_log_id}/review", response_model=GenerationReviewRead, status_code=201)
def create_review(
    generation_log_id: str, payload: GenerationReviewCreateRequest, db: Session = Depends(get_db)
) -> GenerationReview:
    """
    The only write path into generation_reviews - a permanent,
    human-labelled verdict on this GenerationLog. Rejects a second
    review for the same log rather than silently overwriting one
    (the spec's own "permanently stored, do not discard" requirement) -
    the 1:1 unique constraint on generation_log_id would reject it at
    the DB layer anyway; this just gives a clear 400 instead of a raw
    integrity error.
    """
    generation_log = db.get(GenerationLog, generation_log_id)
    if generation_log is None:
        raise HTTPException(status_code=404, detail="Generation log not found")

    if payload.main_issue not in VALID_MAIN_ISSUES:
        raise HTTPException(
            status_code=422, detail=f"main_issue must be one of {sorted(VALID_MAIN_ISSUES)}"
        )

    existing = db.scalars(
        select(GenerationReview).where(GenerationReview.generation_log_id == generation_log_id)
    ).first()
    if existing is not None:
        raise HTTPException(status_code=400, detail="This generation has already been reviewed")

    settings_row = db.get(AppSetting, SINGLETON_ID)
    learning_mode_enabled = settings_row.learning_mode_enabled if settings_row is not None else True

    review = GenerationReview(
        generation_log_id=generation_log_id,
        overall_score=payload.overall_score,
        main_issue=payload.main_issue,
        comment=payload.comment,
        learning_mode_enabled=learning_mode_enabled,
    )
    db.add(review)
    db.commit()
    db.refresh(review)

    write_review(generation_log, review)

    return review
