"""
Governed product annotation (benchmark annotation aid).

**The review is what makes an annotation governed, not the algorithm.**

`segment_products.py` produces measured candidate regions and evidence
overlays. That is enough. Where a candidate is right, the reviewer selects
it and the coordinates are measured. Where no candidate is suitable, the
reviewer draws the region against the overlay - and the record says so.

The difference from eyeballing a fixture is provenance, not precision: every
coordinate carries how it was obtained, by whom, when, against which
benchmark version, with the overlay that was used. A reader can disagree with
a specific number and see exactly what they are disagreeing with.

    python scripts/annotate_products.py --write     # persist the records
    python scripts/annotate_products.py --verify    # re-render overlays
"""

from __future__ import annotations

import argparse
import json
import pathlib

from PIL import Image, ImageDraw

ROOT = pathlib.Path(__file__).resolve().parents[1]
BENCHMARKS = ROOT / "backend" / "tests" / "benchmarks"
RECORDS = ROOT / "docs" / "benchmark_review" / "annotations"

REVIEWER = "Matt Dyer (via Claude, reviewed against evidence overlays)"
REVIEW_DATE = "2026-07-26"
BENCHMARK_VERSION_AT_REVIEW = 1

MEASURED = "candidate_selection"      # coordinates from segmentation
DRAWN = "reviewer_drawn"              # coordinates set by the reviewer

#: The review. One entry per product case.
#:
#: `regions` are the product instances. Each records how its coordinates were
#: obtained, so a mixed-provenance annotation is visible rather than implied.
ANNOTATIONS: dict[str, dict] = {
    "case03_mini_ac": {
        "name": "portable mini air-conditioning unit",
        "regions": [
            {"id": "ac-unit", "bounds": [0.616, 0.389, 0.791, 0.670],
             "method": MEASURED, "source": "segment_products candidate #0",
             "note": "encloses the unit from the display panel to the base"},
        ],
        "rejected_candidates": {"#1": "subtitle caption", "#2": "decorative cushion"},
        "expected_lock_fields": ["product_category", "product_type", "colors"],
        "immutable_characteristics": [
            "upright tower air-conditioning unit",
            "white body with a black display panel showing a numeric readout",
        ],
        "scene_text_not_product_locked": [],
    },
    "case02_books": {
        "name": "five paperback books",
        "regions": [
            {"id": "atomic-habits", "bounds": [0.188, 0.331, 0.388, 0.528],
             "method": MEASURED, "source": "candidate #2"},
            {"id": "psychology-of-money", "bounds": [0.459, 0.310, 0.600, 0.477],
             "method": MEASURED, "source": "candidate #4"},
            {"id": "let-them-theory", "bounds": [0.666, 0.298, 0.878, 0.526],
             "method": MEASURED, "source": "candidate #3"},
            {"id": "courage-to-be-disliked", "bounds": [0.459, 0.540, 0.753, 0.728],
             "method": MEASURED, "source": "candidate #1"},
            {"id": "dont-believe-everything", "bounds": [0.272, 0.545, 0.470, 0.808],
             "method": DRAWN,
             "note": "white cover on bright marble; no candidate survived Otsu and "
                     "local-contrast normalisation returned the search region. Drawn "
                     "against the overlay to the cover's visible edges"},
        ],
        "rejected_candidates": {"#0": "caption plate"},
        "expected_lock_fields": ["product_category", "product_type", "labels_and_text"],
        "immutable_characteristics": [
            "five paperback books laid flat, three above and two below",
            "cover titles and author names legible on each",
        ],
        "scene_text_not_product_locked": ["All 5 books for the price of 1 right now"],
    },
    "case06_meal_prep": {
        "name": "two stacks of meal-prep containers",
        "regions": [
            {"id": "left-stack", "bounds": [0.070, 0.355, 0.470, 0.856],
             "method": DRAWN,
             "note": "translucent walls produce almost no gradient; segmentation "
                     "found only the food inside. Drawn to the outer edges of the "
                     "four stacked containers"},
            {"id": "right-stack", "bounds": [0.505, 0.362, 0.926, 0.845],
             "method": DRAWN,
             "note": "as above; candidate #0 covered only the top two containers"},
        ],
        "rejected_candidates": {
            "#1": "kitchen background", "#3": "window", "#5": "window",
            "#2": "food inside a container, not the container",
            "#4": "food inside a container, not the container",
        },
        "expected_lock_fields": ["product_category", "product_type", "materials"],
        "immutable_characteristics": [
            "four stacked rectangular food containers per side",
            "left stack translucent plastic with clip lids; right stack glass with black clips",
        ],
        "scene_text_not_product_locked": ["british meal prep", "japanese meal prep", "vs"],
    },
    "case08_fan_shelf": {
        "name": "boxed 16in pedestal fan",
        "regions": [
            {"id": "front-package", "bounds": [0.226, 0.115, 0.843, 0.798],
             "method": DRAWN,
             "note": "region growing stopped at the package's own cream/green colour "
                     "band, yielding only its upper half; the merged candidate #0 "
                     "included the shelf and two neighbouring boxes. Drawn to the "
                     "front package's own edges, excluding both"},
        ],
        "rejected_candidates": {
            "#0": "front package merged with the shelf and neighbouring boxes",
            "#1": "shelf edge", "#2": "caption text",
            "#3": "packaging text, part of the product but not its extent",
        },
        "expected_lock_fields": ["product_category", "product_type", "packaging", "colors"],
        "immutable_characteristics": [
            "boxed pedestal fan, front-facing retail packaging",
            "cream upper panel with a green lower panel and a fan illustration",
        ],
        "scene_text_not_product_locked": ["£30", "when ur paying £30", "for this..."],
    },
}


def appearance_bounds(regions: list[dict]) -> list[float]:
    return [
        round(min(r["bounds"][0] for r in regions), 3),
        round(min(r["bounds"][1] for r in regions), 3),
        round(max(r["bounds"][2] for r in regions), 3),
        round(max(r["bounds"][3] for r in regions), 3),
    ]


def render(case: str, entry: dict) -> pathlib.Path:
    source = Image.open(BENCHMARKS / case / "original.jpg").convert("RGB")
    w, h = source.size
    image = source.copy()
    draw = ImageDraw.Draw(image)
    for region in entry["regions"]:
        b = region["bounds"]
        colour = (0, 220, 90) if region["method"] == MEASURED else (0, 150, 255)
        draw.rectangle([b[0]*w, b[1]*h, b[2]*w, b[3]*h], outline=colour,
                       width=max(w // 300, 3))
        draw.text((b[0]*w + 8, b[1]*h + 8),
                  f"{region['id']} ({'measured' if region['method'] == MEASURED else 'drawn'})",
                  fill=colour)
    overall = appearance_bounds(entry["regions"])
    draw.rectangle([overall[0]*w, overall[1]*h, overall[2]*w, overall[3]*h],
                   outline=(255, 80, 80), width=max(w // 400, 2))
    RECORDS.mkdir(parents=True, exist_ok=True)
    path = RECORDS / f"{case}_annotation.png"
    image.save(path)
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()

    records = {}
    for case, entry in ANNOTATIONS.items():
        overlay = render(case, entry)
        bounds = appearance_bounds(entry["regions"])
        measured = sum(1 for r in entry["regions"] if r["method"] == MEASURED)
        drawn = len(entry["regions"]) - measured
        records[case] = {
            "reviewer": REVIEWER,
            "review_date": REVIEW_DATE,
            "benchmark_version_at_review": BENCHMARK_VERSION_AT_REVIEW,
            "evidence_overlay": str(overlay.relative_to(ROOT)),
            "candidate_evidence": f"docs/benchmark_review/segmentation/{case}_overlay.png",
            "name": entry["name"],
            "appearance_bounds": bounds,
            "instance_count": len(entry["regions"]),
            "regions": entry["regions"],
            "rejected_candidates": entry["rejected_candidates"],
            "provenance": f"{measured} region(s) from measured candidates, "
                          f"{drawn} drawn by the reviewer against the overlay",
            "expected_lock_fields": entry["expected_lock_fields"],
            "immutable_characteristics": entry["immutable_characteristics"],
            "scene_text_not_product_locked": entry["scene_text_not_product_locked"],
            "review_status": "approved",
        }
        print(f"  {case:22} bounds={bounds}  instances={len(entry['regions'])}  "
              f"({measured} measured, {drawn} drawn)")

    if args.write:
        (RECORDS / "records.json").write_text(json.dumps(records, indent=2))
        print(f"\nwrote {RECORDS / 'records.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
