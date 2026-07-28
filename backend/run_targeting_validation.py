#!/usr/bin/env python3
"""
Task 2 — targeted product-isolation validation harness (Check 1, lightweight).

Runs REAL, PAID vision calls, so it lives outside the deterministic test suite
and is invoked by hand in the backend venv (the one with the OpenAI key in the
macOS Keychain). It exists to answer one question before Task 2 is called done:

    Does the product-TARGETED isolation prompt actually DISCRIMINATE between the
    distinct products on a real multi-product creative — or does it just latch
    onto the single most visually-salient product no matter which one we asked
    for?

It implements the two hardening recommendations agreed for this task:

  (1) Negative / ambiguity discrimination. It doesn't just check that each target
      returns *a* box — it checks that two different targets return *different*
      regions. The failure mode it is built to catch is "the model returned the
      same salient-product region for every target". That is measured directly:
      the pairwise region overlap (IoU) between the boxes returned for different
      targets must be LOW. High cross-target overlap == not discriminating.

  (2) A full audit trail. Every single provider call — target string, the model's
      verbatim raw response, the parsed boxes, and the confidence/notes on each
      box — is captured (via the provider's `raw_sink` out-dict) and written to a
      timestamped JSON so a failing prompt can be diagnosed from evidence rather
      than re-run blind.

Success criterion (tightened), evaluated per requested product:
  • found            — the target returns at least one box (the product is present);
  • discriminates    — no returned box predominantly overlaps a DIFFERENT promoted
                       product's region (no salient-product latch);
  • stable           — repeated runs return reasonably consistent regions;
  • absent → empty   — a target known NOT to be in the image returns no detections.

Run discipline (do this, in this order):
  • This IS Check 1. Run it. It is lightweight (a handful of calls), so iterate on
    the targeted prompt HERE using its metrics + audit trail if it fails — do NOT
    re-run the full end-to-end stage repeatedly to tune a prompt.
  • Only when Check 1 PASSES on a real multi-product creative, run the end-to-end
    stage confirmation (Check 2) EXACTLY ONCE. When that single confirmation is
    green, Task 2 is operationally complete.

Usage:
  python run_targeting_validation.py \
      --image path/to/real_multiproduct_creative.jpg \
      --present "Colgate Total Whitening" "Colgate Optic White" \
      --absent  "Oral-B Pro 1000" \
      --repeats 3 \
      [--truth truth.json]        # optional ground-truth boxes, see below
      [--out audit.json]

--present : one or more product display names that ARE in the image. Quote each.
--absent  : zero or more names that are NOT in the image (negative controls).
--repeats : how many times to call each present target, for stability. Default 3.
--truth   : OPTIONAL JSON mapping a present target name -> its true box
            {"x_min":..,"y_min":..,"x_max":..,"y_max":..} in 0..1 fractions.
            When given, the harness can also assert automatically that every
            returned box overlaps the RIGHT product (the "every returned box
            overlaps that product" clause). Without it, that clause is left for
            you to confirm from the crops/audit, and PASS/FAIL rests on
            discrimination + stability + absent, which need no ground truth.

Exit code: 0 if every check passes (safe to proceed to Check 2), 1 otherwise.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Thresholds — deliberately explicit and tunable. These are the knobs you'd
# adjust while iterating on the prompt, not magic numbers buried in logic.
CROSS_TARGET_MAX_IOU = 0.50   # two DIFFERENT targets overlapping more than this == latch
STABILITY_MIN_IOU = 0.60      # repeats of the SAME target below this == unstable
TRUTH_OVERLAP_MIN = 0.50      # a returned box must cover >= this fraction of its true product


def _iou(a: dict, b: dict) -> float:
    """Intersection-over-union of two fractional boxes (0..1 coords)."""
    ix0, iy0 = max(a["x_min"], b["x_min"]), max(a["y_min"], b["y_min"])
    ix1, iy1 = min(a["x_max"], b["x_max"]), min(a["y_max"], b["y_max"])
    iw, ih = max(0.0, ix1 - ix0), max(0.0, iy1 - iy0)
    inter = iw * ih
    area_a = max(0.0, a["x_max"] - a["x_min"]) * max(0.0, a["y_max"] - a["y_min"])
    area_b = max(0.0, b["x_max"] - b["x_min"]) * max(0.0, b["y_max"] - b["y_min"])
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def _overlap_fraction(inner: dict, outer: dict) -> float:
    """Fraction of `inner`'s own area that falls inside `outer` — 'is inner mostly inside outer'."""
    ix0, iy0 = max(inner["x_min"], outer["x_min"]), max(inner["y_min"], outer["y_min"])
    ix1, iy1 = min(inner["x_max"], outer["x_max"]), min(inner["y_max"], outer["y_max"])
    iw, ih = max(0.0, ix1 - ix0), max(0.0, iy1 - iy0)
    inter = iw * ih
    area_inner = max(0.0, inner["x_max"] - inner["x_min"]) * max(0.0, inner["y_max"] - inner["y_min"])
    return inter / area_inner if area_inner > 0 else 0.0


def _best_box(boxes: list[dict]) -> dict | None:
    """The highest-confidence box (the model's own primary pick)."""
    return max(boxes, key=lambda b: b.get("confidence", 0.0)) if boxes else None


def _max_pairwise_iou(boxes_a: list[dict], boxes_b: list[dict]) -> float:
    return max(
        (_iou(ba, bb) for ba in boxes_a for bb in boxes_b),
        default=0.0,
    )


def _stability(runs: list[list[dict]]) -> float | None:
    """Mean pairwise IoU of the primary box across repeated runs. None if <2 usable runs."""
    primaries = [_best_box(r) for r in runs]
    primaries = [p for p in primaries if p is not None]
    if len(primaries) < 2:
        return None
    ious, n = 0.0, 0
    for i in range(len(primaries)):
        for j in range(i + 1, len(primaries)):
            ious += _iou(primaries[i], primaries[j])
            n += 1
    return ious / n if n else None


def main() -> int:
    ap = argparse.ArgumentParser(description="Task 2 targeted-isolation Check 1 validator")
    ap.add_argument("--image", required=True, type=Path)
    ap.add_argument("--present", nargs="+", required=True, metavar="NAME")
    ap.add_argument("--absent", nargs="*", default=[], metavar="NAME")
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--truth", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    if not args.image.exists():
        print(f"image not found: {args.image}", file=sys.stderr)
        return 2

    truth: dict[str, dict] = {}
    if args.truth is not None:
        truth = json.loads(args.truth.read_text())

    # Import the REAL adapter — this is where the paid calls happen.
    from app.ai_providers.openai_adapter import OpenAIProductIsolationAdapter

    adapter = OpenAIProductIsolationAdapter()
    image_bytes = args.image.read_bytes()

    audit: list[dict] = []          # every call's full record (recommendation 2)
    present_runs: dict[str, list[list[dict]]] = {}
    absent_runs: dict[str, list[list[dict]]] = {}

    def _call(target: str) -> list[dict]:
        sink: dict = {}
        boxes = adapter.isolate_product(image_bytes, target=target, raw_sink=sink)
        audit.append({
            "target": target,
            "raw_content": sink.get("raw_content"),
            "parsed": sink.get("parsed", boxes),
            "boxes": boxes,
            "confidences": [b.get("confidence") for b in boxes],
            "notes": [b.get("notes") for b in boxes],
        })
        return boxes

    print(f"== Check 1: targeted isolation on {args.image.name} ==")
    for name in args.present:
        runs = [_call(name) for _ in range(max(1, args.repeats))]
        present_runs[name] = runs
        counts = [len(r) for r in runs]
        print(f"  present  {name!r}: box counts over {len(runs)} run(s) = {counts}")
    for name in args.absent:
        runs = [_call(name)]  # one negative-control call is enough
        absent_runs[name] = runs
        print(f"  absent   {name!r}: box count = {len(runs[0])}")

    # ---- Evaluate the tightened criterion --------------------------------
    results: dict[str, dict] = {}

    # Representative box-set per present target = its first run's boxes.
    rep: dict[str, list[dict]] = {n: runs[0] for n, runs in present_runs.items()}

    for name in args.present:
        boxes = rep[name]
        found = len(boxes) > 0

        # discrimination: this target's primary box must NOT sit predominantly
        # inside, nor share a high IoU with, a DIFFERENT target's region.
        worst_other = None
        worst_metric = 0.0
        my_best = _best_box(boxes)
        for other in args.present:
            if other == name:
                continue
            other_best = _best_box(rep[other])
            if my_best is None or other_best is None:
                continue
            metric = max(_iou(my_best, other_best), _overlap_fraction(my_best, other_best))
            if metric > worst_metric:
                worst_metric, worst_other = metric, other
        discriminates = found and worst_metric <= CROSS_TARGET_MAX_IOU

        stab = _stability(present_runs[name])
        stable = stab is None or stab >= STABILITY_MIN_IOU

        # optional ground-truth clause: every returned box overlaps THIS product.
        truth_ok = None
        if name in truth:
            truth_ok = all(_overlap_fraction(b, truth[name]) >= TRUTH_OVERLAP_MIN for b in boxes)

        # four-outcome label
        if not found:
            outcome = "no_product"        # empty when expected present
        elif not discriminates:
            outcome = "latched_other"     # same/overlapping region as another product
        elif truth_ok is False:
            outcome = "wrong_region"       # boxes don't cover the true product
        else:
            outcome = "correct"

        ok = found and discriminates and stable and (truth_ok is not False)
        results[name] = {
            "kind": "present",
            "found": found,
            "discriminates": discriminates,
            "cross_target_worst_iou": round(worst_metric, 3),
            "cross_target_worst_other": worst_other,
            "stability_iou": None if stab is None else round(stab, 3),
            "stable": stable,
            "truth_ok": truth_ok,
            "outcome": outcome,
            "pass": ok,
        }

    for name in args.absent:
        boxes = absent_runs[name][0]
        empty = len(boxes) == 0
        results[name] = {
            "kind": "absent",
            "returned_boxes": len(boxes),
            "outcome": "correct" if empty else "false_detection",
            "pass": empty,
        }

    overall = all(r["pass"] for r in results.values())

    # ---- Report ----------------------------------------------------------
    print("\n== Result summary ==")
    for name, r in results.items():
        tag = "PASS" if r["pass"] else "FAIL"
        if r["kind"] == "present":
            extra = (f"outcome={r['outcome']} found={r['found']} "
                     f"discriminates={r['discriminates']} "
                     f"(worst cross-target overlap {r['cross_target_worst_iou']} "
                     f"vs {r['cross_target_worst_other']}) "
                     f"stability={r['stability_iou']} truth_ok={r['truth_ok']}")
        else:
            extra = f"outcome={r['outcome']} returned={r['returned_boxes']}"
        print(f"  [{tag}] {name!r}: {extra}")

    print(f"\n== OVERALL: {'PASS' if overall else 'FAIL'} ==")
    if overall:
        print("Check 1 passed. The targeted prompt discriminates on this creative.")
        print("Next: run the end-to-end stage confirmation (Check 2) EXACTLY ONCE.")
    else:
        print("Check 1 failed. Iterate on _targeted_isolation_prompt using the audit")
        print("trail + metrics below — do NOT run the full stage repeatedly to tune it.")

    # ---- Persist the audit trail (recommendation 2) ----------------------
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = args.out or Path(f"targeting_audit_{stamp}.json")
    out_path.write_text(json.dumps({
        "image": str(args.image),
        "generated_at": stamp,
        "thresholds": {
            "cross_target_max_iou": CROSS_TARGET_MAX_IOU,
            "stability_min_iou": STABILITY_MIN_IOU,
            "truth_overlap_min": TRUTH_OVERLAP_MIN,
        },
        "present": args.present,
        "absent": args.absent,
        "repeats": args.repeats,
        "results": results,
        "overall_pass": overall,
        "calls": audit,        # target, raw_content, parsed boxes, confidence, notes — every call
    }, indent=2))
    print(f"\nAudit trail written: {out_path}")
    return 0 if overall else 1


if __name__ == "__main__":
    raise SystemExit(main())
