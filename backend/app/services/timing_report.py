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

**Reconstructed history never poses as a provider call** (follow-up to
Checkpoint B, item 4). Rows stamped `legacy_aggregate` were rebuilt from
`AnalysisRun`: one row can cover several real calls, and the latency
stored on it is stage wall-clock, not provider time. So they contribute
to money only, are counted in their own column, and are excluded from
call counts, provider latency and tokens - the figures a per-call
average would be built from.

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
from app.models.provider_call import RECORD_SOURCE_LEGACY_AGGREGATE, ProviderCall
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
                "legacy_rows": 0,
                "untrusted_calls": 0,
                "untrusted_legacy_rows": 0,
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
        is_legacy = call.record_source == RECORD_SOURCE_LEGACY_AGGREGATE

        if is_legacy:
            bucket["legacy_rows"] += 1
        else:
            bucket["calls"] += 1
            bucket["provider_latency_ms"] += call.provider_latency_ms or 0.0
            bucket["prompt_tokens"] += call.prompt_tokens or 0
            bucket["completion_tokens"] += call.completion_tokens or 0
            bucket["image_count"] += call.image_count or 0

        # Money is the one figure a reconstructed row can still support
        # honestly - it is what was spent, however many calls it covered.
        if call.cost_status in _TRUSTED and call.estimated_cost_usd is not None:
            bucket["cost_usd"] += call.estimated_cost_usd
            bucket["has_cost"] = True
        elif is_legacy:
            bucket["untrusted_legacy_rows"] += 1
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
                "known_cost_subtotal_usd": b["cost_usd"] if b["has_cost"] else None,
                "call_count": b["calls"],
                "legacy_aggregate_rows": b["legacy_rows"],
                "calls_without_trusted_cost": b["untrusted_calls"],
                "legacy_rows_without_trusted_cost": b["untrusted_legacy_rows"],
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

        TOTAL TIME             63.8s  (provider 61.2s)
        Overhead (inferred)     2.6s  = wall-clock minus provider time

        Known cost subtotal:   $0.5350
        Unknown-cost calls:    2
        Overall cost:          incomplete - the subtotal above is a floor

    **The money line is never labelled "total spend"** (follow-up to
    Checkpoint B, item 5). Calls whose cost is partial or unknown are
    excluded from the sum, so the sum is a SUBTOTAL of what is known.
    When any such call exists, the report says "incomplete" outright
    instead of presenting a figure that looks authoritative and is not.
    Only when every call is priced does it read "complete".

    The time total keeps the word TOTAL because it genuinely is one -
    every timed stage contributes.
    """
    if not breakdown:
        return "(no timed stages recorded)"

    any_cost = any(row.get("known_cost_subtotal_usd") is not None for row in breakdown)
    label_width = max(len(row["label"]) for row in breakdown) + 2

    lines = []
    total_seconds = total_latency = known_cost = 0.0
    untrusted_calls = untrusted_legacy = legacy_rows = 0

    for row in breakdown:
        total_seconds += row.get("duration_seconds", 0.0)
        total_latency += row.get("provider_latency_seconds", 0.0)
        untrusted_calls += row.get("calls_without_trusted_cost", 0)
        untrusted_legacy += row.get("legacy_rows_without_trusted_cost", 0)
        legacy_rows += row.get("legacy_aggregate_rows", 0)

        duration_s = row.get("duration_seconds", 0.0)
        latency_s = row.get("provider_latency_seconds", 0.0)
        untrusted = row.get("calls_without_trusted_cost", 0)
        line = (
            f"{row['label']:<{label_width}}{duration_s:>6.1f}s"
            f"  (provider {latency_s:.1f}s)"
        )
        if any_cost:
            cost = row.get("known_cost_subtotal_usd")
            known_cost += cost or 0.0
            line += f"   ${cost:.4f}" if cost is not None else "   $  --  "
        if untrusted:
            line += f"  [{untrusted} call(s) without a trusted cost]"
        lines.append(line)

    lines.append("")
    lines.append(
        f"{'TOTAL TIME':<{label_width}}{total_seconds:>6.1f}s  (provider {total_latency:.1f}s)"
    )

    overhead = max(total_seconds - total_latency, 0.0)
    lines.append(
        f"{'Overhead (inferred)':<{label_width}}{overhead:>6.1f}s"
        "  = wall-clock minus provider time, not directly measured"
    )

    # Money is reported as its own block, in the wording agreed at
    # Checkpoint B: a subtotal of what is known, an explicit count of
    # what could not be priced, and a plain completeness verdict.
    unpriced = untrusted_calls + untrusted_legacy
    if any_cost or unpriced:
        lines.append("")
        lines.append(f"{'Known cost subtotal:':<{label_width}}${known_cost:.4f}")
        lines.append(f"{'Unknown-cost calls:':<{label_width}}{unpriced}")
        if unpriced:
            lines.append(
                f"{'Overall cost:':<{label_width}}incomplete - real spend is at least the "
                "subtotal above, by an unknown margin (see pricing.yaml)"
            )
        else:
            lines.append(f"{'Overall cost:':<{label_width}}complete")

    if legacy_rows:
        lines.append(
            f"\nNote: {legacy_rows} row(s) above were reconstructed from pre-instrumentation "
            "history. They contribute to cost only - not to call counts, provider latency or "
            "any per-call average, since one row may cover several calls."
        )

    return "\n".join(lines)
