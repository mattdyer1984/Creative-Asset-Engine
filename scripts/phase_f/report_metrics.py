"""
Phase F3-F6 - cost, latency, confidence calibration and a failure catalogue,
all derived from what F1 measured and F2 scored.

No provider is called here and no threshold is tuned. Cost is never presented
as a single total: `estimated_cost_usd` is NULL for a model with no
configured rate, and adding NULLs as zero is exactly how an incomplete figure
gets reported as a complete one.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import statistics
from collections import defaultdict

FAILURE_CLASSES = (
    "ocr_failure",
    "provider_hallucination",
    "ownership_ambiguity",
    "composition_ambiguity",
    "typography_mismatch",
    "generation_failure",
    "cleanup_failure",
    "validation_failure",
    "benchmark_annotation_error",
    "scoring_limitation",
)


def cost_profile(run: dict) -> dict:
    """
    F3. Known subtotal, unknown-cost calls, and a per-stage breakdown.

    Never a bare "total spend" - see the module docstring.
    """
    per_stage: dict[str, dict] = defaultdict(
        lambda: {"calls": 0, "known_usd": 0.0, "unknown": 0,
                 "prompt_tokens": 0, "completion_tokens": 0}
    )
    per_case_known: list[float] = []
    unknown_total = 0

    for case in run["cases"]:
        case_known = 0.0
        for stage in case.get("stages", []):
            bucket = per_stage[stage["stage"]]
            for call in stage["provider_calls"]:
                bucket["calls"] += 1
                bucket["prompt_tokens"] += call["prompt_tokens"] or 0
                bucket["completion_tokens"] += call["completion_tokens"] or 0
                if call["estimated_cost_usd"] is None:
                    bucket["unknown"] += 1
                    unknown_total += 1
                else:
                    bucket["known_usd"] += call["estimated_cost_usd"]
                    case_known += call["estimated_cost_usd"]
        per_case_known.append(round(case_known, 6))

    stages = {}
    for name, bucket in per_stage.items():
        cases_run = sum(
            1 for c in run["cases"] if any(s["stage"] == name for s in c.get("stages", []))
        )
        stages[name] = {
            **{k: (round(v, 6) if isinstance(v, float) else v) for k, v in bucket.items()},
            "mean_known_usd_per_case": (
                round(bucket["known_usd"] / cases_run, 6) if cases_run else None
            ),
            "deterministic": bucket["calls"] == 0,
        }

    return {
        "known_cost_subtotal_usd": round(sum(per_case_known), 6),
        "unknown_cost_calls": unknown_total,
        "overall_cost": (
            "complete" if unknown_total == 0
            else f"incomplete - {unknown_total} call(s) have no configured rate"
        ),
        "per_case_known_usd": per_case_known,
        "mean_known_usd_per_case": round(statistics.mean(per_case_known), 6),
        "worst_case_known_usd": max(per_case_known),
        "best_case_known_usd": min(per_case_known),
        "per_stage": dict(sorted(stages.items(), key=lambda kv: -kv[1]["known_usd"])),
    }


def latency_profile(run: dict) -> dict:
    """
    F4. End to end, per stage, and provider wait versus our own CPU.

    **`duration_ms` is not stage wall-clock time for four of the stages.**
    OCR, Creative Fingerprint, Scene Intelligence and Composition Contract
    run their provider calls concurrently across slides and only then open
    an AnalysisRun, so `duration_ms` covers the bookkeeping (2-11 ms) while
    `provider_call_ms` covers the real work (14-26 s). The model's documented
    `duration_ms - provider_call_ms = overhead` derivation is therefore
    deeply negative for those stages and means nothing.

    So per-stage time is reported from `provider_call_ms`, which is measured
    correctly everywhere, and the discrepancy is reported rather than
    smoothed over - it is a real instrumentation defect that Phase F found.
    """
    per_stage: dict[str, list] = defaultdict(list)
    end_to_end = []
    mis_instrumented = set()

    for case in run["cases"]:
        end_to_end.append(case.get("end_to_end_ms") or 0.0)
        for stage in case.get("stages", []):
            duration = stage["duration_ms"] or 0.0
            provider = stage["provider_call_ms"] or 0.0
            if provider > duration * 1.5 and provider > 100:
                mis_instrumented.add(stage["stage"])
            per_stage[stage["stage"]].append({
                "duration_ms": duration,
                "provider_call_ms": provider,
                # The best available estimate of what this stage really cost
                # in wall clock: the provider call when that dominates, the
                # recorded duration when the stage is deterministic.
                "effective_ms": max(duration, provider),
            })

    stages = {}
    for name, rows in per_stage.items():
        effective = [r["effective_ms"] for r in rows]
        providers = [r["provider_call_ms"] for r in rows]
        stages[name] = {
            "runs": len(rows),
            "mean_effective_ms": round(statistics.mean(effective), 1),
            "max_effective_ms": round(max(effective), 1),
            "mean_provider_ms": round(statistics.mean(providers), 1),
            "share_of_case_wall": None,
            "duration_ms_is_wall_clock": name not in mis_instrumented,
        }

    total_effective_per_case = statistics.mean([
        sum(max(s["duration_ms"] or 0.0, s["provider_call_ms"] or 0.0)
            for s in case.get("stages", []))
        for case in run["cases"]
    ])
    for entry in stages.values():
        entry["share_of_case_wall"] = (
            round(entry["mean_effective_ms"] / total_effective_per_case, 3)
            if total_effective_per_case else None
        )

    deterministic = [
        r["duration_ms"] for name, rows in per_stage.items() for r in rows
        if name not in mis_instrumented and r["provider_call_ms"] == 0.0
    ]
    total_provider = sum(
        r["provider_call_ms"] for rows in per_stage.values() for r in rows
    )
    total_wall = sum(end_to_end)

    return {
        "mean_end_to_end_ms": round(statistics.mean(end_to_end), 1),
        "max_end_to_end_ms": round(max(end_to_end), 1),
        "min_end_to_end_ms": round(min(end_to_end), 1),
        "total_provider_wait_ms": round(total_provider, 1),
        "total_wall_ms": round(total_wall, 1),
        "provider_share_of_wall": (
            round(total_provider / total_wall, 3) if total_wall else 0.0
        ),
        "deterministic_cpu_ms_total": round(sum(deterministic), 1),
        "mis_instrumented_stages": sorted(mis_instrumented),
        "mis_instrumentation_note": (
            "these stages open their AnalysisRun after concurrent provider work "
            "completes, so duration_ms records bookkeeping only and "
            "`duration_ms - provider_call_ms` is negative and meaningless"
        ),
        "per_stage": dict(sorted(stages.items(), key=lambda kv: -kv[1]["mean_effective_ms"])),
    }


def calibration(scores: dict) -> dict:
    """
    F5. Does a confidence value predict correctness?

    Every confidence-bearing decision is bucketed and its verdict counted.
    A band whose accuracy does not fall as confidence falls is not carrying
    information, whatever number it prints.
    """
    bands = {
        "high (>=0.80)": (0.80, 1.01),
        "medium (0.55-0.79)": (0.55, 0.80),
        "low (<0.55)": (0.0, 0.55),
    }
    buckets = {name: {"n": 0, "correct": 0, "sources": defaultdict(int)}
               for name in bands}
    unscored = 0

    def record(confidence, correct, source):
        nonlocal unscored
        if confidence is None:
            unscored += 1
            return
        for name, (low, high) in bands.items():
            if low <= confidence < high:
                buckets[name]["n"] += 1
                buckets[name]["correct"] += int(correct)
                buckets[name]["sources"][source] += 1
                return

    for case in scores["cases"]:
        device = case["composition_contract"].get("device") or {}
        record(device.get("confidence"),
               device.get("verdict") in ("exact", "acceptable"), "device")

        profile = case["creative_project_profile"]
        mode = profile.get("primary_text_mode") or {}
        record(profile.get("text_mode_confidence"),
               mode.get("verdict") == "exact", "text_mode")

        for row in case["text_ownership"].get("detail", []):
            if row["verdict"] in ("exact", "disagreement"):
                record(row.get("confidence"), row["verdict"] == "exact", "ownership")

    return {
        "bands": {
            name: {
                "n": b["n"],
                "correct": b["correct"],
                "accuracy": round(b["correct"] / b["n"], 3) if b["n"] else None,
                "sources": dict(b["sources"]),
            }
            for name, b in buckets.items()
        },
        "decisions_with_no_confidence": unscored,
    }


def failure_catalogue(run: dict, scores: dict) -> list[dict]:
    """
    F6. Every disagreement classified, with the evidence that places it.

    Classification is by CAUSE, not by which stage surfaced it: an ownership
    decision that is wrong because OCR never saw the text is an OCR failure,
    and filing it under ownership would send the next person to fix the
    wrong thing.
    """
    findings: list[dict] = []
    by_case = {c["case"]: c for c in run["cases"]}

    for case in scores["cases"]:
        name = case["case"]
        artifacts = (by_case.get(name) or {}).get("artifacts") or {}
        ocr_texts = " ".join(
            (b.get("text") or "") for b in ((artifacts.get("ocr") or {}).get("blocks") or [])
        ).lower()

        for row in case["text_ownership"].get("detail", []):
            if row["verdict"] == "missing":
                words = [w for w in row["text"].lower().split() if len(w) > 3]
                seen = any(w in ocr_texts for w in words) if words else False
                findings.append({
                    "case": name,
                    "artifact": "text_ownership",
                    "klass": "ownership_ambiguity" if seen else "ocr_failure",
                    "summary": f"no decision for {row['text'][:50]!r}",
                    "evidence": (
                        "the text appears in OCR output but no decision matched it"
                        if seen else
                        "OCR never reported this text, so nothing could own it"
                    ),
                    "expected": row.get("expected_class"),
                })
            elif row["verdict"] == "disagreement":
                typography = case["typography_system"]
                capability = (typography.get("capability_level") or {})
                cap_wrong = capability.get("verdict") == "disagreement"
                findings.append({
                    "case": name,
                    "artifact": "text_ownership",
                    "klass": "typography_mismatch" if cap_wrong else "ownership_ambiguity",
                    "summary": (
                        f"{row['text'][:40]!r} owned by {row['inferred_owner']}, "
                        f"benchmark says {row['expected_owner']}"
                    ),
                    "evidence": (
                        f"capability inferred {capability.get('inferred')} but the "
                        f"benchmark says {capability.get('expected')}, so the "
                        "capability gate never fired"
                        if cap_wrong else
                        f"classified {row.get('inferred_class')} at confidence "
                        f"{row.get('confidence')}"
                    ),
                })

        for field in ("primary_family_class", "secondary_family_class", "capability_level"):
            entry = case["typography_system"].get(field) or {}
            if entry.get("verdict") == "disagreement":
                findings.append({
                    "case": name,
                    "artifact": "typography_system",
                    "klass": "typography_mismatch",
                    "summary": (
                        f"{field}: inferred {entry.get('inferred')!r}, "
                        f"benchmark says {entry.get('expected')!r}"
                    ),
                    "evidence": "single vision call, no cross-check against the render",
                })

        device = case["composition_contract"].get("device") or {}
        if device.get("verdict") == "disagreement":
            findings.append({
                "case": name, "artifact": "composition_contract",
                "klass": "composition_ambiguity",
                "summary": device.get("detail"),
                "evidence": f"device_confidence {device.get('confidence')}",
            })

        for unmatched in case["composition_contract"].get("zones", {}).get("unmatched", []):
            findings.append({
                "case": name, "artifact": "composition_contract",
                "klass": "composition_ambiguity",
                "summary": f"no inferred region for {unmatched['expected_id']!r}",
                "evidence": unmatched["detail"],
                "needs_adjudication": True,
            })

    for case in run["cases"]:
        if not case.get("pipeline_succeeded"):
            findings.append({
                "case": case["case"], "artifact": "pipeline",
                "klass": "validation_failure",
                "summary": f"pipeline failed at {case.get('failed_stage')}",
                "evidence": (case.get("pipeline_error") or "")[:300],
            })

    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True)
    parser.add_argument("--scores", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    run = json.loads(pathlib.Path(args.run).read_text())
    scores = json.loads(pathlib.Path(args.scores).read_text())

    report = {
        "cost": cost_profile(run),
        "latency": latency_profile(run),
        "calibration": calibration(scores),
        "failures": failure_catalogue(run, scores),
    }
    counts: dict[str, int] = defaultdict(int)
    for finding in report["failures"]:
        counts[finding["klass"]] += 1
    report["failure_counts"] = {k: counts.get(k, 0) for k in FAILURE_CLASSES}

    pathlib.Path(args.out).write_text(json.dumps(report, indent=2, default=str))
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
