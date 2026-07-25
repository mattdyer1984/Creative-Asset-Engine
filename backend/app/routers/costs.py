"""
Costs API — Phase 1 remediation (WP-2).

**One calculation path.** Every figure below is derived from
`ProviderCall` and nothing else. The previous version summed
`AnalysisRun.estimated_cost_usd` and `GeneratedImage.estimated_cost_usd`
separately, which had two problems: several real paid calls (photorealism
scoring, reference scoring, creative intelligence, text intelligence) had
no row in either table and were silently missing from spend entirely, and
a stage making two provider calls contributed one row, so per-call
attribution was impossible.

**Untrustworthy figures are never silently folded into a total.** Only
`estimated`/`exact` rows contribute to a cost total. `partial` rows (a
known under-count - e.g. a completion rate was missing) and `unknown`
rows are counted and surfaced separately, so a total never quietly
under-reports while looking authoritative.

**Reconstructed history is separable, and is never counted as per-call
evidence** (follow-up to Checkpoint B, item 4). `?include_legacy=false`
excludes `record_source='legacy_aggregate'` rows outright. But even when
they ARE included, they only ever contribute MONEY - never call counts,
provider latency, tokens or images. Those rows were reconstructed from
`AnalysisRun`, where one row can stand for several real calls and the
recorded latency is stage wall-clock, not provider time. Summing them
into a latency figure or dividing by them for a per-call average would
manufacture precision that does not exist. They are reported in their
own `legacy_aggregate_rows` field instead.

**Nothing here is called "total spend"** (item 5). A figure that
excludes partial and unknown costs is a subtotal of what is KNOWN, so
it is named `known_cost_subtotal_usd`, and `cost_completeness` says
plainly whether anything is missing from it.
"""

from collections import defaultdict
from datetime import date as date_type

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.provider_call import RECORD_SOURCE_LEGACY_AGGREGATE, ProviderCall
from app.schemas import CostBreakdownRead, DailyCostRead
from app.services.cost_estimation import CostStatus

router = APIRouter(prefix="/api/costs", tags=["costs"])

_TRUSTED = {str(CostStatus.EXACT), str(CostStatus.ESTIMATED)}


def _completeness(unknown: int, partial: int) -> str:
    """
    "complete" only when every call in scope has a trustworthy cost.
    Anything else is "incomplete" - the subtotal is a floor, not a
    total, and the caller is told so rather than left to infer it.
    """
    return "incomplete" if (unknown or partial) else "complete"


def _base_query(include_legacy: bool):
    stmt = select(ProviderCall)
    if not include_legacy:
        stmt = stmt.where(ProviderCall.record_source != RECORD_SOURCE_LEGACY_AGGREGATE)
    return stmt


@router.get("/daily", response_model=list[DailyCostRead])
def get_daily_costs(
    db: Session = Depends(get_db),
    include_legacy: bool = Query(
        True,
        description=(
            "Include rows reconstructed from pre-ProviderCall history. These are "
            "labelled legacy_aggregate and may each stand for more than one real call."
        ),
    ),
) -> list[DailyCostRead]:
    buckets: dict[date_type, dict] = defaultdict(
        lambda: {
            "analysis_cost_usd": 0.0,
            "image_generation_cost_usd": 0.0,
            "call_count": 0,
            "legacy_aggregate_rows": 0,
            "calls_with_unknown_cost": 0,
            "calls_with_partial_cost": 0,
        }
    )

    for call in db.scalars(_base_query(include_legacy)):
        bucket = buckets[call.created_at.date()]
        # A reconstructed row is not a call. Counting it as one would
        # overstate call volume and corrupt any per-call average.
        if call.record_source == RECORD_SOURCE_LEGACY_AGGREGATE:
            bucket["legacy_aggregate_rows"] += 1
        else:
            bucket["call_count"] += 1

        if call.cost_status == str(CostStatus.UNKNOWN):
            bucket["calls_with_unknown_cost"] += 1
            continue
        if call.cost_status == str(CostStatus.PARTIAL):
            # A real but knowingly incomplete figure - counted, not summed.
            bucket["calls_with_partial_cost"] += 1
            continue

        amount = call.estimated_cost_usd or 0.0
        if call.capability == "image_generation":
            bucket["image_generation_cost_usd"] += amount
        else:
            bucket["analysis_cost_usd"] += amount

    return sorted(
        (
            DailyCostRead(
                date=day.isoformat(),
                analysis_cost_usd=round(bucket["analysis_cost_usd"], 4),
                image_generation_cost_usd=round(bucket["image_generation_cost_usd"], 4),
                known_cost_subtotal_usd=round(
                    bucket["analysis_cost_usd"] + bucket["image_generation_cost_usd"], 4
                ),
                cost_completeness=_completeness(
                    bucket["calls_with_unknown_cost"], bucket["calls_with_partial_cost"]
                ),
                call_count=bucket["call_count"],
                legacy_aggregate_rows=bucket["legacy_aggregate_rows"],
                calls_with_unknown_cost=bucket["calls_with_unknown_cost"],
                calls_with_partial_cost=bucket["calls_with_partial_cost"],
            )
            for day, bucket in buckets.items()
        ),
        key=lambda row: row.date,
        reverse=True,
    )


@router.get("/breakdown", response_model=list[CostBreakdownRead])
def get_cost_breakdown(
    db: Session = Depends(get_db),
    group_by: str = Query(
        "capability",
        pattern="^(provider|model|capability|slideshow|slide)$",
        description="Reporting axis. WP-2 requires all of these to be queryable.",
    ),
    include_legacy: bool = Query(True),
) -> list[CostBreakdownRead]:
    """
    Cost and latency grouped along any of the axes WP-2 calls for:
    provider, model, capability, slideshow, slide.
    """
    attribute = {
        "provider": lambda c: c.provider,
        "model": lambda c: c.reported_model or c.model,
        "capability": lambda c: c.capability,
        "slideshow": lambda c: c.slideshow_id,
        "slide": lambda c: c.slide_id,
    }[group_by]

    buckets: dict[str, dict] = defaultdict(
        lambda: {
            "cost": 0.0,
            "calls": 0,
            "legacy": 0,
            "unknown": 0,
            "partial": 0,
            "latency_ms": 0.0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "images": 0,
        }
    )

    for call in db.scalars(_base_query(include_legacy)):
        key = attribute(call)
        if key is None:
            continue  # not attributable on this axis - excluded, not bucketed as "None"
        bucket = buckets[key]

        if call.record_source == RECORD_SOURCE_LEGACY_AGGREGATE:
            # Money only. Its latency is stage wall-clock reconstructed
            # from AnalysisRun, and it may stand for several calls -
            # so it contributes to no per-call figure. (item 4)
            bucket["legacy"] += 1
        else:
            bucket["calls"] += 1
            bucket["latency_ms"] += call.provider_latency_ms or 0.0
            bucket["prompt_tokens"] += call.prompt_tokens or 0
            bucket["completion_tokens"] += call.completion_tokens or 0
            bucket["images"] += call.image_count or 0

        if call.cost_status == str(CostStatus.UNKNOWN):
            bucket["unknown"] += 1
        elif call.cost_status == str(CostStatus.PARTIAL):
            bucket["partial"] += 1
        else:
            bucket["cost"] += call.estimated_cost_usd or 0.0

    return sorted(
        (
            CostBreakdownRead(
                group=group_by,
                key=key,
                known_cost_subtotal_usd=round(bucket["cost"], 4),
                cost_completeness=_completeness(bucket["unknown"], bucket["partial"]),
                call_count=bucket["calls"],
                legacy_aggregate_rows=bucket["legacy"],
                calls_with_unknown_cost=bucket["unknown"],
                calls_with_partial_cost=bucket["partial"],
                total_provider_latency_ms=round(bucket["latency_ms"], 1),
                prompt_tokens=bucket["prompt_tokens"],
                completion_tokens=bucket["completion_tokens"],
                image_count=bucket["images"],
            )
            for key, bucket in buckets.items()
        ),
        key=lambda row: row.known_cost_subtotal_usd,
        reverse=True,
    )
