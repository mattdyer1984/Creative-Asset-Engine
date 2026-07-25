"""
Timing/cost breakdown reporting (Optimisation & Stability Pass, Tier 2 -
see MIGRATION_PLAN.md).

Reads whatever AnalysisRun rows already exist for a slideshow/slide -
every Stage already writes one via mark_succeeded/mark_failed
(app.stages.execution), so this is purely a read-side aggregation, not a
new write path. Produces the "Import / OCR / ... / TOTAL" breakdown
shape requested for Phase 1, with an added cost column for Phase 5's
"why did yesterday cost £X" ask - deliberately in the same report rather
than two separate ones, since the two directly inform each other (a slow
stage and an expensive stage are often, but not always, the same stage).
"""

from collections import OrderedDict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.analysis_run import AnalysisRun

# Display order/labels - not every AnalysisRun.analysis_type value a
# slideshow could have; unrecognized types still appear (title-cased
# verbatim), just not in this preferred order.
_STAGE_LABELS: "OrderedDict[str, str]" = OrderedDict(
    [
        ("ocr", "OCR"),
        ("product_isolation", "Product Isolation"),
        ("product_lock_profile", "Product Lock Profile"),
        ("creative_fingerprint", "Creative Fingerprint"),
        ("scene_intelligence", "Scene Intelligence"),
        ("marketing_analysis", "Marketing Analysis"),
        ("narrative_structure", "Narrative Structure"),
        ("creative_specification", "Creative Specification"),
        ("generated_image", "Image Generation"),
        ("image_validation", "Validation"),
    ]
)


def build_timing_breakdown(
    db: Session, *, slideshow_id: str | None = None, slide_id: str | None = None
) -> list[dict]:
    """
    One row per analysis_type that has at least one AnalysisRun matching
    the given scope, summed across every slide/attempt - e.g. "OCR"
    covers every slide's own OCR call, not just one. Rows with no
    duration_ms recorded yet (a row from before this instrumentation
    existed, or a run that never reached a terminal mark_*) are excluded
    from the sum but don't crash it.
    """
    if slideshow_id is None and slide_id is None:
        raise ValueError("build_timing_breakdown needs slideshow_id and/or slide_id")

    conditions = []
    if slideshow_id is not None:
        conditions.append(AnalysisRun.slideshow_id == slideshow_id)
    if slide_id is not None:
        conditions.append(AnalysisRun.slide_id == slide_id)

    stmt = select(AnalysisRun).where(*conditions) if len(conditions) == 1 else select(AnalysisRun).where(
        conditions[0] | conditions[1]
    )
    runs = list(db.scalars(stmt))

    totals: dict[str, dict] = {}
    for run in runs:
        bucket = totals.setdefault(
            run.analysis_type, {"duration_ms": 0.0, "cost_usd": 0.0, "has_cost": False}
        )
        if run.duration_ms is not None:
            bucket["duration_ms"] += run.duration_ms
        if run.estimated_cost_usd is not None:
            bucket["cost_usd"] += run.estimated_cost_usd
            bucket["has_cost"] = True

    ordered_types = [t for t in _STAGE_LABELS if t in totals] + [
        t for t in totals if t not in _STAGE_LABELS
    ]

    return [
        {
            "analysis_type": analysis_type,
            "label": _STAGE_LABELS.get(analysis_type, analysis_type.replace("_", " ").title()),
            "duration_seconds": totals[analysis_type]["duration_ms"] / 1000,
            "estimated_cost_usd": totals[analysis_type]["cost_usd"] if totals[analysis_type]["has_cost"] else None,
        }
        for analysis_type in ordered_types
    ]


def format_timing_breakdown(breakdown: list[dict]) -> str:
    """
    Renders the Phase 1 example's table shape:

        OCR                         1.9s
        Creative Fingerprint        2.7s
        ...
        TOTAL                      84.1s   $0.4231

    Cost is only appended per-row/on the total when at least one row has
    a real estimated_cost_usd (i.e. pricing.yaml has rates configured) -
    an all-None cost column would just be noise.
    """
    if not breakdown:
        return "(no timed stages recorded)"

    any_cost = any(row["estimated_cost_usd"] is not None for row in breakdown)
    label_width = max(len(row["label"]) for row in breakdown) + 2

    lines = []
    total_seconds = 0.0
    total_cost = 0.0
    for row in breakdown:
        total_seconds += row["duration_seconds"]
        line = f"{row['label']:<{label_width}}{row['duration_seconds']:>6.1f}s"
        if any_cost:
            cost = row["estimated_cost_usd"]
            total_cost += cost or 0.0
            line += f"   ${cost:.4f}" if cost is not None else "   $--"
        lines.append(line)

    lines.append("")
    total_line = f"{'TOTAL':<{label_width}}{total_seconds:>6.1f}s"
    if any_cost:
        total_line += f"   ${total_cost:.4f}"
    lines.append(total_line)

    return "\n".join(lines)
