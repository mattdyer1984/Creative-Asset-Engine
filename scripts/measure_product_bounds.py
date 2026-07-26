"""
Measure product bounds for the benchmark extension.

Governance §2 classes bounds as a MEASURABLE field, settled by measurement
rather than by eye. Case 1's fixture is wrong precisely because its bounds
were estimated, so these are derived from the pixels and the derivation is
committed alongside the numbers.

Method: the product regions are foreground against a near-uniform background
(marble worktop, bedroom wall, kitchen counter, shelf). For each case a
background colour is sampled from a region known to contain no product, and
pixels far from it in RGB distance are treated as foreground. The reported
box is the extent of the largest connected foreground mass within a search
window that excludes the caption band.

Run `--evidence` to write annotated images for visual confirmation. Numbers
that cannot be confirmed by eye should not be committed.

**STATUS: this does not yet produce usable bounds, and no product fixture has
been written from it.**

Two approaches were tried and both failed on these images:

1. *Background subtraction* (below). The backgrounds are not uniform enough -
   marble veining and tile grout differ from the sampled background by more
   than the products do, so the reported box collapses onto the search window.
2. *Brightness plus saturation.* Better, but it loses the top row of books in
   case 2: the marble behind them is as bright as a cream book cover, so the
   row-occupancy cut discards the genuine book rows.

Getting either to "work" would mean tuning thresholds per case until the
number matched what I could already see - which is fitting the measurement to
the answer, and is what `docs/BENCHMARK_GOVERNANCE.md` §4 forbids. Case 1's
fixture is wrong precisely because its bounds were eyeballed, so replacing
one set of estimates with another would repeat that error with more
ceremony.

What this needs is proper connected-component segmentation (numpy/scipy, or
a saliency model), scoring each candidate region and taking the largest
coherent mass rather than row/column occupancy over the whole window. That is
a real piece of work, not a threshold tweak.
"""

from __future__ import annotations

import argparse
import json
import pathlib

from PIL import Image, ImageDraw

BENCHMARKS = pathlib.Path(__file__).resolve().parents[1] / "backend" / "tests" / "benchmarks"

#: case -> (background sample box, search window, foreground distance threshold)
#: All boxes are normalised. The search window excludes caption furniture so
#: a white caption plate is not mistaken for product.
CASES = {
    "case02_books": ((0.02, 0.55, 0.12, 0.75), (0.10, 0.26, 0.95, 0.84), 46),
    "case03_mini_ac": ((0.02, 0.02, 0.10, 0.10), (0.35, 0.25, 0.95, 0.85), 52),
    "case06_meal_prep": ((0.02, 0.88, 0.12, 0.98), (0.02, 0.33, 0.98, 0.92), 46),
    "case08_fan_shelf": ((0.02, 0.02, 0.10, 0.10), (0.05, 0.05, 0.95, 0.92), 46),
}


def _measure(path: pathlib.Path, bg_box, window, threshold):
    image = Image.open(path).convert("RGB")
    width, height = image.size
    px = image.load()

    bx0, by0, bx1, by1 = (int(bg_box[0]*width), int(bg_box[1]*height),
                          int(bg_box[2]*width), int(bg_box[3]*height))
    samples = [px[x, y] for x in range(bx0, bx1, 3) for y in range(by0, by1, 3)]
    bg = tuple(sum(c[i] for c in samples) // len(samples) for i in range(3))

    wx0, wy0, wx1, wy1 = (int(window[0]*width), int(window[1]*height),
                          int(window[2]*width), int(window[3]*height))
    step = max(min(width, height) // 300, 1)

    # Row/column occupancy: a row counts as product-bearing when enough of
    # its sampled pixels are far from the background. Robust to speckle in a
    # way a raw min/max over foreground pixels is not.
    cols, rows = {}, {}
    for y in range(wy0, wy1, step):
        for x in range(wx0, wx1, step):
            r, g, b = px[x, y]
            if abs(r-bg[0]) + abs(g-bg[1]) + abs(b-bg[2]) > threshold:
                cols[x] = cols.get(x, 0) + 1
                rows[y] = rows.get(y, 0) + 1

    if not cols:
        return None, bg
    col_cut = max(cols.values()) * 0.12
    row_cut = max(rows.values()) * 0.12
    xs = [x for x, n in cols.items() if n >= col_cut]
    ys = [y for y, n in rows.items() if n >= row_cut]
    return (round(min(xs)/width, 3), round(min(ys)/height, 3),
            round(max(xs)/width, 3), round(max(ys)/height, 3)), bg


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", action="store_true")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    results = {}
    for case, (bg_box, window, threshold) in CASES.items():
        path = BENCHMARKS / case / "original.jpg"
        bounds, bg = _measure(path, bg_box, window, threshold)
        results[case] = {
            "appearance_bounds": list(bounds) if bounds else None,
            "background_rgb": list(bg),
            "background_sample_box": list(bg_box),
            "search_window": list(window),
            "threshold": threshold,
            "method": "foreground = RGB manhattan distance from sampled background "
                      "> threshold; box = rows/cols holding >=12% of peak occupancy",
        }
        print(f"  {case:22} {bounds}   background rgb={bg}")

        if args.evidence and bounds:
            image = Image.open(path).convert("RGB")
            w, h = image.size
            draw = ImageDraw.Draw(image)
            draw.rectangle([bounds[0]*w, bounds[1]*h, bounds[2]*w, bounds[3]*h],
                           outline=(0, 200, 80), width=max(w // 200, 3))
            draw.text((bounds[0]*w + 8, bounds[1]*h + 8), "MEASURED product", fill=(0, 200, 80))
            out = pathlib.Path(__file__).resolve().parents[1] / "docs" / "benchmark_review"
            out.mkdir(parents=True, exist_ok=True)
            image.save(out / f"{case}_product_bounds.png")

    if args.out:
        pathlib.Path(args.out).write_text(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
