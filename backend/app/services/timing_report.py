"""
Timing/cost breakdown reporting (Phase 1 remediation, WP-4).

Two sources, joined on purpose:

  * `AnalysisRun` supplies stage WALL-CLOCK - it is the stage-scoped
    record, and stage duration is genuinely a stage-level fact.
  * `ProviderCall` supplies PROVIDER LATENCY, tokens and cost - those
    are per-call facts, and one stage can make several calls (image
    validation makes two; generation makes one per candidate).

Reading cost from AnalysisRun would under-report for exactly that
reason, and would also miss the calls that belong to no run at all
(photorealism, reference scoring, creative intelligence, text
intelligence) - see provider_call.py's docstring.

**Overhead is labelled as inferred, never presented as measured.**
`overhead_seconds` is `stage wall-clock - summed provider latency`. That
is a subtraction, not a measurement: it silently absorbs DB writes, file
I/O, and any real time this process spent not waiting on a provider. The
formatter marks it, and the field name says so, because presenting a
derived figure as if it were instrumented is exactly the kind of
misleading precision this pass exists to remove.
"""

from collections import OrderedDict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.analysis_run import AnalysisRun
from app.models.provider_call import ProviderCall
from app.services.cost_estimation import CostStatus

# Display order/labels. Not exhaustive - unrecognised types still
# appear (title-cased verbatim), just after the ordered ones.
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

_TRUSTED = {str(CostStatus.EXACT), str(CostStatus.ESTIMATED)}


def _scope_filter(model, slideshow_id: str | None, slide_id: str | None):
    conditions = []
    if slideshow_id is not None:
        conditions.append(model.slideshow_id == slideshow_id)
    if slide_id is not None:
        conditions.append(model.slide_id == slide_id)
    if len(conditions) == 1:
        return conditions[0]
    return conditions[0] | conditions[1]


def build_timing_breakdown(
    db: Session, *, slideshow_id: str | None = None, slide_id: str | None = None
) -> list[dict]:
    """
    One row per analysis_type in scope, summed across every slide and
    attempt - "OCR" covers every slide's own OCR call, not just one.

    Rows missing duration_ms (predating instrumentation, or a run that
    never reached a terminal mark_*) are excluded from sums rather than
    crashing them.
    """
    if slideshow_id is None and slide_id is None:
        raise ValueError("build_timing_breakdown needs slideshow_id and/or slide_id")

    totals: dict[str, dict] = {}

    def bucket_for(key: str) -> dict:
        return totals.setdefault(
            key,
            {
                "duration_ms": 0.0,
                "provider_latency_ms": 0.0,
                "cost_usd": 0.0,
                "has_cost": False,
                "calls": 0,
                "untrusted_calls": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "image_count": 0,
            },
        )

    # Stage wall-clock, from the stage-scoped record.
    runs = db.scalars(
        select(AnalysisRun).where(_scope_filter(AnalysisRun, slideshow_id, slide_id))
    )
    run_type_by_id: dict[str, str] = {}
    for run in runs:
        run_type_by_id[run.id] = run.analysis_type
        bucket = bucket_for(run.analysis_type)
        if run.duration_ms is not None:
            bucket["duration_ms"] += run.duration_ms

    # Provider latency / tokens / cost, from the per-call record. A call
    # with no analysis_run_id (photorealism, reference scoring, ...) is
    # attributed by its capability so it is still visible rather than
    # dropped.
    calls = db.scalars(
        select(ProviderCall).where(_scope_filter(ProviderCall, slideshow_id, slide_id))
    )
    for call in calls:
        key = run_type_by_id.get(call.analysis_run_id) if call.analysis_run_id else None
        bucket = bucket_for(key or call.capability)
        bucket["calls"] += 1
        bucket["provider_latency_ms"] += call.provider_latency_ms or 0.0
        bucket["prompt_tokens"] += call.prompt_tokens or 0
        bucket["completion_tokens"] += call.completion_tokens or 0
        bucket["image_count"] += call.image_count or 0
        if call.cost_status in _TRUSTED and call.estimated_cost_usd is not None:
            bucket["cost_usd"] += call.estimated_cost_usd
            bucket["has_cost"] = True
        else:
            bucket["untrusted_calls"] += 1

    ordered = [t for t in _STAGE_LABELS if t in totals] + [
        t for t in totals if t not in _STAGE_LABELS
    ]

    rows = []
    for key in ordered:
        b = totals[key]
        duration_s = b["duration_ms"] / 1000
        latency_s = b["provider_latency_ms"] / 1000
        rows.append(
            {
                "analysis_type": key,
                "label": _STAGE_LABELS.get(key, key.replace("_", " ").title()),
                "duration_seconds": duration_s,
                "provider_latency_seconds": latency_s,
                # Inferred, not measured - see the module docstring.
                "inferred_overhead_seconds": max(duration_s - latency_s, 0.0),
                "estimated_cost_usd": b["cost_usd"] if b["has_cost"] else None,
                "call_count": b["calls"],
                "calls_without_trusted_cost": b["untrusted_calls"],
                "prompt_tokens": b["prompt_tokens"],
                "completion_tokens": b["completion_tokens"],
                "image_count": b["image_count"],
            }
        )
    return rows


def format_timing_breakdown(breakdown: list[dict]) -> str:
    """
    Renders, e.g.:

        OCR                     2.1s  (provider 1.9s)
        Image Generation       48.4s  (provider 48.1s)   $0.5000
        Validation              4.1s  (provider 3.9s)    $0.0350  [2 calls without a trusted cost]

        TOTAL                  63.8s  (provider 61.2s)   $0.5350
        Overhead (inferred)     2.6s  = wall-clock minus provider time

    The cost column only appears when at least one row has a trusted
    figure; an all-None column is noise. Calls whose cost is partial or
    unknown are never summed into the money total - they are called out
    so the total is not quietly wrong.
    """
    if not breakdown:
        return "(no timed stages recorded)"

    any_cost = any(row.get("estimated_cost_usd") is not None for row in breakdown)
    label_width = max(len(row["label"]) for row in breakdown) + 2

    lines = []
    total_seconds = total_latency = total_cost = 0.0
    total_untrusted = 0

    for row in breakdown:
        total_seconds += row.get("duration_seconds", 0.0)
        total_latency += row.get("provider_latency_seconds", 0.0)
        total_untrusted += row.get("calls_without_trusted_cost", 0)

        duration_s = row.get("duration_seconds", 0.0)
        latency_s = row.get("provider_latency_seconds", 0.0)
        untrusted = row.get("calls_without_trusted_cost", 0)
        line = (
            f"{row['label']:<{label_width}}{duration_s:>6.1f}s"
            f"  (provider {latency_s:.1f}s)"
        )
        if any_cost:
            cost = row.get("estimated_cost_usd")
            total_cost += cost or 0.0
            line += f"   ${cost:.4f}" if cost is not None else "   $  --  "
        if untrusted:
            line += f"  [{untrusted} call(s) without a trusted cost]"
        lines.append(line)

    lines.append("")
    total_line = (
        f"{'TOTAL':<{label_width}}{total_seconds:>6.1f}s  (provider {total_latency:.1f}s)"
    )
    if any_cost:
        total_line += f"   ${total_cost:.4f}"
    lines.append(total_line)

    overhead = max(total_seconds - total_latency, 0.0)
    lines.append(
        f"{'Overhead (inferred)':<{label_width}}{overhead:>6.1f}s"
        "  = wall-clock minus provider time, not directly measured"
    )
    if total_untrusted:
        lines.append(
            f"\nNote: {total_untrusted} provider call(s) had a partial or unknown cost and are "
            "excluded from the total above - see pricing.yaml."
        )

    return "\n".join(lines)
