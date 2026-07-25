"""
Costs API — Optimisation & Stability Pass, Tier 2.2 (see
MIGRATION_PLAN.md). The one small, honest aggregation the Phase 5 cost
ask calls for: "why did yesterday cost $X" answerable without opening a
provider dashboard. Deliberately just a read over AnalysisRun/
GeneratedImage's own estimated_cost_usd columns, grouped in Python (this
is a single-user local app on SQLite, not a case that needs a SQL-level
GROUP BY for scale) - no new write path, no new bookkeeping.
"""

from collections import defaultdict
from datetime import date as date_type

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.analysis_run import AnalysisRun
from app.models.generated_image import GeneratedImage
from app.schemas import DailyCostRead

router = APIRouter(prefix="/api/costs", tags=["costs"])


@router.get("/daily", response_model=list[DailyCostRead])
def get_daily_costs(db: Session = Depends(get_db)) -> list[DailyCostRead]:
    buckets: dict[date_type, dict] = defaultdict(
        lambda: {"analysis_cost_usd": 0.0, "image_generation_cost_usd": 0.0, "call_count": 0}
    )

    for run in db.scalars(select(AnalysisRun).where(AnalysisRun.finished_at.is_not(None))):
        day = run.finished_at.date()
        bucket = buckets[day]
        bucket["call_count"] += 1
        if run.estimated_cost_usd is not None:
            bucket["analysis_cost_usd"] += run.estimated_cost_usd

    for image in db.scalars(select(GeneratedImage)):
        day = image.created_at.date()
        bucket = buckets[day]
        bucket["call_count"] += 1
        if image.estimated_cost_usd is not None:
            bucket["image_generation_cost_usd"] += image.estimated_cost_usd

    return sorted(
        (
            DailyCostRead(
                date=day.isoformat(),
                analysis_cost_usd=round(bucket["analysis_cost_usd"], 4),
                image_generation_cost_usd=round(bucket["image_generation_cost_usd"], 4),
                total_estimated_cost_usd=round(
                    bucket["analysis_cost_usd"] + bucket["image_generation_cost_usd"], 4
                ),
                call_count=bucket["call_count"],
            )
            for day, bucket in buckets.items()
        ),
        key=lambda row: row.date,
        reverse=True,
    )
