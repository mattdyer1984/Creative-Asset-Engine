"""
Phase F2 - score inferred analysis against the hand-authored benchmark truth.

Deliberately separate from the run harness, so a scoring bug cannot change
what was measured. It reads `run.json` and the fixtures; it never calls a
provider and never touches the pipeline.

Three verdicts, and the middle one carries the weight:

  exact         identical to the annotation
  acceptable    different wording, same meaning - a `text` zone the
                annotator called `caption`, a device that is a defensible
                reading of the same layout
  disagreement  a real difference that would change the output

`acceptable` is not a way to make numbers look better. Every acceptable
verdict records the rule that granted it, so the judgement is inspectable and
can be argued with. Anything with no rule is a disagreement.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

BACKEND = pathlib.Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(BACKEND))
BENCHMARKS = BACKEND / "tests" / "benchmarks"

EXACT, ACCEPTABLE, DISAGREEMENT, MISSING = (
    "exact", "acceptable", "disagreement", "missing"
)

#: Devices that are defensible readings of the same layout. Symmetric, and
#: each pair is justified rather than assumed - a product photographed in a
#: room with copy over it genuinely is both a product-hero and a
#: scene-with-caption, and which one an annotator picks is a judgement call.
DEVICE_NEIGHBOURS = {
    frozenset({"product-hero", "scene-with-caption"}),
    frozenset({"side-by-side-comparison", "split-comparison"}),
}

#: Zone roles that describe the same thing at different granularity.
ROLE_NEIGHBOURS = {
    frozenset({"text", "caption"}),
    frozenset({"subject", "product"}),
    frozenset({"callout", "graphic"}),
}


def _verdict(inferred, expected, neighbours=()) -> tuple[str, str]:
    if inferred == expected:
        # Includes both being None, which is agreement about ABSENCE - a
        # real answer, not a missing one. Scoring it as missing marked
        # "correctly has no secondary family" as a failure.
        return EXACT, ""
    if inferred is None:
        return MISSING, "nothing was inferred"
    for pair in neighbours:
        if {inferred, expected} == set(pair):
            return ACCEPTABLE, f"{inferred!r} is a defensible reading of {expected!r}"
    return DISAGREEMENT, f"inferred {inferred!r}, benchmark says {expected!r}"


def _contained(inner, outer) -> float:
    """How much of `inner` falls inside `outer`."""
    left, top = max(inner[0], outer[0]), max(inner[1], outer[1])
    right, bottom = min(inner[2], outer[2]), min(inner[3], outer[3])
    if right <= left or bottom <= top:
        return 0.0
    area = (inner[2] - inner[0]) * (inner[3] - inner[1])
    return ((right - left) * (bottom - top)) / area if area else 0.0


def _coverage(zones, target) -> float:
    """
    Share of `target` covered by `zones`, on a coarse grid.

    A grid rather than exact geometry because the zones overlap freely and
    summing their areas would double-count - which would let three
    overlapping guesses "cover" a region none of them fits.
    """
    if not zones:
        return 0.0
    steps = 40
    width, height = target[2] - target[0], target[3] - target[1]
    hits = 0
    for row in range(steps):
        for col in range(steps):
            x = target[0] + (col + 0.5) * width / steps
            y = target[1] + (row + 0.5) * height / steps
            if any(z["bounds"][0] <= x <= z["bounds"][2]
                   and z["bounds"][1] <= y <= z["bounds"][3] for z in zones):
                hits += 1
    return hits / (steps * steps)


def _iou(a, b) -> float:
    left, top = max(a[0], b[0]), max(a[1], b[1])
    right, bottom = min(a[2], b[2]), min(a[3], b[3])
    if right <= left or bottom <= top:
        return 0.0
    overlap = (right - left) * (bottom - top)
    union = ((a[2] - a[0]) * (a[3] - a[1])) + ((b[2] - b[0]) * (b[3] - b[1])) - overlap
    return overlap / union if union else 0.0


def score_composition(inferred: dict | None, truth: dict) -> dict:
    """
    Device, then zone coverage by geometry.

    Zones are matched by overlap, never by id: the model names its own zones
    and there is no reason its `hero-product` should be the annotator's
    `books`. What matters is whether it found a region in the same place
    playing the same role.
    """
    result: dict = {"artifact": "composition_contract"}
    if inferred is None:
        result.update(verdict=MISSING, detail="no contract was produced")
        return result

    verdict, detail = _verdict(
        inferred.get("device"), truth["device"], DEVICE_NEIGHBOURS
    )
    result["device"] = {
        "inferred": inferred.get("device"),
        "expected": truth["device"],
        "verdict": verdict,
        "detail": detail,
        "confidence": inferred.get("device_confidence"),
    }

    matched, unmatched = [], []
    available = list(inferred.get("zones") or [])
    for expected_zone in truth["zones"]:
        best, best_iou = None, 0.0
        for candidate in available:
            overlap = _iou(candidate["bounds"], expected_zone["bounds"])
            if overlap > best_iou:
                best, best_iou = candidate, overlap

        if best is None or best_iou < 0.3:
            # Before calling it missing: did the model DECOMPOSE this zone
            # rather than miss it? It routinely finds five individual books
            # where the annotation has one `books` region, or a dot and a
            # line where the annotation has one `bullets` block. That is
            # finer granularity, not an error, and scoring it as a miss
            # would be measuring the matching rule rather than the model.
            covering = [
                z for z in available
                if _contained(z["bounds"], expected_zone["bounds"]) >= 0.7
            ]
            covered = _coverage(covering, expected_zone["bounds"])
            if covering and covered >= 0.5:
                for zone in covering:
                    available.remove(zone)
                roles = {z["role"] for z in covering}
                role_verdict = (
                    EXACT if roles == {expected_zone["role"]}
                    else ACCEPTABLE if any(
                        {r, expected_zone["role"]} == set(pair)
                        for r in roles for pair in ROLE_NEIGHBOURS
                    ) or expected_zone["role"] in roles
                    else DISAGREEMENT
                )
                matched.append({
                    "expected_id": expected_zone["id"],
                    "inferred_id": "+".join(z["zone_id"] for z in covering),
                    "expected_role": expected_zone["role"],
                    "inferred_role": "+".join(sorted(roles)),
                    "iou": round(covered, 3),
                    "match_kind": "decomposed",
                    "verdict": role_verdict,
                    "detail": (
                        f"{len(covering)} inferred zone(s) cover {covered:.0%} of this "
                        "region - finer granularity than the annotation"
                    ),
                })
                continue
            unmatched.append({
                "expected_id": expected_zone["id"], "role": expected_zone["role"],
                "verdict": MISSING, "detail": f"best overlap {best_iou:.2f} < 0.30",
            })
            continue
        available.remove(best)
        role_verdict, role_detail = _verdict(
            best["role"], expected_zone["role"], ROLE_NEIGHBOURS
        )
        matched.append({
            "expected_id": expected_zone["id"], "inferred_id": best["zone_id"],
            "expected_role": expected_zone["role"], "inferred_role": best["role"],
            "iou": round(best_iou, 3),
            "verdict": role_verdict, "detail": role_detail,
        })

    result["zones"] = {
        "expected": len(truth["zones"]),
        "inferred": len(inferred.get("zones") or []),
        "matched": len(matched),
        "unmatched": unmatched,
        "extra": [z["zone_id"] for z in available],
        "role_exact": sum(1 for m in matched if m["verdict"] == EXACT),
        "role_acceptable": sum(1 for m in matched if m["verdict"] == ACCEPTABLE),
        "role_disagreement": sum(1 for m in matched if m["verdict"] == DISAGREEMENT),
        "detail": matched,
    }
    result["relations"] = {
        "expected": len(truth["relations"]),
        "inferred": len(inferred.get("relations") or []),
    }
    return result


def score_profile(inferred: dict | None, truth: dict) -> dict:
    result: dict = {"artifact": "creative_project_profile"}
    if inferred is None:
        result.update(verdict=MISSING, detail="no profile was produced")
        return result

    for field, expected in (
        ("primary_text_mode", truth["primary_text_mode"]),
        ("copy_policy", truth["copy_policy"]),
        ("production_value_strategy", truth["production_value_strategy"]),
        ("overlay_policy", truth["overlay_policy"]),
    ):
        verdict, detail = _verdict(inferred.get(field), expected)
        result[field] = {
            "inferred": inferred.get(field), "expected": expected,
            "verdict": verdict, "detail": detail,
        }
    result["text_mode_confidence"] = inferred.get("text_mode_confidence")
    return result


def score_typography(inferred: dict | None, truth: dict | None) -> dict:
    result: dict = {"artifact": "typography_system"}
    if truth is None:
        result["expected"] = None
        result["verdict"] = EXACT if inferred is None else DISAGREEMENT
        result["detail"] = (
            "no system expected and none produced" if inferred is None
            else "a system was produced for a project the benchmark says has none"
        )
        return result
    if inferred is None:
        result.update(verdict=MISSING, detail="a designed project produced no system")
        return result

    for field, expected in (
        ("primary_family_class", truth["primary_family"]),
        ("secondary_family_class", truth["secondary_family"]),
        ("capability_level", truth["capability_level"]),
    ):
        verdict, detail = _verdict(inferred.get(field), expected)
        result[field] = {
            "inferred": inferred.get(field), "expected": expected,
            "verdict": verdict, "detail": detail,
        }
    result["roles_inferred"] = sorted(inferred.get("text_roles") or {})
    result["colour_roles_inferred"] = inferred.get("colour_roles") or {}
    return result


def score_ownership(inferred: dict | None, truth: dict) -> dict:
    """
    Matched on TEXT, since the model's block ids mean nothing to the
    annotation. Text is normalised for case and whitespace only - not for
    content, because different words are a real difference.
    """
    result: dict = {"artifact": "text_ownership"}
    if inferred is None:
        result.update(verdict=MISSING, detail="no ownership artifact")
        return result

    expected_owner = {
        "product_lock": "image", "model_generated": "image",
        "deterministic_typography": "typography", "deterministic_overlay": "caption",
    }

    def norm(text):
        return " ".join((text or "").lower().split())

    by_text = {norm(d["text"]): d for d in inferred["decisions"]}
    rows, matched = [], 0
    for block in truth["text_blocks"]:
        key = norm(block["text"])
        decision = by_text.get(key)
        if decision is None:
            # Partial match: OCR legitimately splits a block across lines.
            for candidate_key, candidate in by_text.items():
                if candidate_key and (candidate_key in key or key in candidate_key):
                    decision = candidate
                    break
        if decision is None:
            rows.append({
                "text": block["text"][:60], "expected_class": block["class"],
                "verdict": MISSING, "detail": "no OCR block matched this text",
            })
            continue
        matched += 1
        want = expected_owner[block["expected_handling_mechanism"]]
        verdict, detail = _verdict(decision["owner"], want)
        rows.append({
            "text": block["text"][:60],
            "expected_class": block["class"], "inferred_class": decision["text_class"],
            "expected_owner": want, "inferred_owner": decision["owner"],
            "image_strategy": decision.get("image_strategy"),
            "confidence": decision.get("confidence"),
            "composition_zone_role": decision.get("composition_zone_role"),
            "verdict": verdict, "detail": detail,
        })

    result.update({
        "expected_blocks": len(truth["text_blocks"]),
        "inferred_blocks": len(inferred["decisions"]),
        "matched": matched,
        "exact": sum(1 for r in rows if r["verdict"] == EXACT),
        "disagreement": sum(1 for r in rows if r["verdict"] == DISAGREEMENT),
        "missing": sum(1 for r in rows if r["verdict"] == MISSING),
        "detail": rows,
    })
    return result


def score_intent(inferred_fingerprint: dict | None, truth: dict) -> dict:
    """
    Creative Intent has no dedicated inference stage yet. Recording that
    honestly is the point - a score of zero would read as "we tried and
    failed", which is a different fact from "nothing infers this".
    """
    return {
        "artifact": "creative_intent",
        "expected": truth["creative_intent"],
        "inferred": None,
        "verdict": "not_implemented",
        "detail": (
            "no stage infers Creative Intent; the Creative Fingerprint records "
            "a free-text 'marketing angle' but nothing maps it to the closed "
            "vocabulary"
        ),
        "nearest_evidence": (inferred_fingerprint or {}).get("marketing_angle"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    import yaml

    run = json.loads(pathlib.Path(args.run).read_text())
    scored = {"run_id": run.get("run_id"), "cases": []}

    for case in run["cases"]:
        truth = yaml.safe_load((BENCHMARKS / case["case"] / "ground_truth.yaml").read_text())
        artifacts = case.get("artifacts") or {}
        scored["cases"].append({
            "case": case["case"],
            "pipeline_succeeded": case.get("pipeline_succeeded"),
            "composition_contract": score_composition(
                artifacts.get("composition_contract"), truth["composition_contract"]
            ),
            "creative_project_profile": score_profile(
                artifacts.get("creative_project_profile"), truth
            ),
            "typography_system": score_typography(
                artifacts.get("typography_system"), truth["typography_system"]
            ),
            "text_ownership": score_ownership(artifacts.get("text_ownership"), truth),
            "creative_intent": score_intent(artifacts.get("creative_fingerprint"), truth),
        })

    pathlib.Path(args.out).write_text(json.dumps(scored, indent=2, default=str))
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
