"""
Propose product masks and bounds for the benchmark extension.

**A benchmark annotation aid, not a production subsystem.** Nothing here runs
in the pipeline; it exists so that `appearance_bounds` can be *measured*
rather than eyeballed, because governance classes bounds as a measurable
field and case 1's fixture is wrong precisely because it was estimated.

## Defensibility rule

**One method, one parameter set, all four cases.** Every constant below is
either derived from the image (Otsu) or scaled to image size. If a case
needed its own thresholds, the measurement would be fitted to an answer I had
already decided by eye - which `docs/BENCHMARK_GOVERNANCE.md` §4 forbids -
and the honest outcome would be to report failure rather than tune.

## Method

1. Greyscale, downscale to a fixed working width (speed, and it suppresses
   sensor noise without a blur parameter).
2. Sobel gradient magnitude. Products have hard boundaries and internal
   detail; marble veining and soft shadows do not.
3. **Otsu** threshold on the gradient map - data-driven, not hand-set.
4. Morphological close, then flood-fill from the border and invert, so an
   object outline becomes a solid region.
5. Connected components (4-connectivity, iterative BFS).
6. Keep components that are large enough to be a product and not so large
   they are the background, and reject thin slivers - grout lines and tile
   edges survive step 3 but are thin, so an extent test removes them without
   naming them.
7. Surviving components are emitted as NUMBERED CANDIDATES.

## What this deliberately does NOT do

It does not decide which candidate is the product. The first version took the
union of everything that survived, and on case 3 that box spanned the mini AC
(found almost exactly), a decorative cushion, and the subtitle caption -
because "which of these objects is the product" is a semantic question and no
threshold answers it.

So selection is a declared, reviewable step: `SELECTIONS` below names the
candidate indices for each case, and `appearance_bounds` is the union of
those alone. **The coordinates are measured; only the choice is human.** That
is materially different from eyeballing coordinates, and it is what governance
means by a governed annotation review.

Everything the reviewer needs to disagree is emitted: the mask, a numbered
overlay, the parameters, every candidate with its geometry, the rejected
components with reasons, and the selection with its rationale.
"""

from __future__ import annotations

import argparse
import json
import pathlib
from collections import deque

import numpy as np
from PIL import Image, ImageDraw

BENCHMARKS = pathlib.Path(__file__).resolve().parents[1] / "backend" / "tests" / "benchmarks"
OUT = pathlib.Path(__file__).resolve().parents[1] / "docs" / "benchmark_review" / "segmentation"

#: The four cases the design approved. No per-case parameters - if one needed
#: them, that is a failure to report, not a knob to turn.
CASES = ("case02_books", "case03_mini_ac", "case06_meal_prep", "case08_fan_shelf")

#: Which candidates are the product, declared per case after looking at the
#: numbered overlay. Empty means "not yet reviewed" - the script then reports
#: candidates only and proposes no bounds, rather than guessing.
SELECTIONS: dict[str, dict] = {}

PARAMS = {
    "working_width": 320,        # px; fixed for every case
    "close_radius": 3,           # px at working scale
    "min_area_fraction": 0.004,  # of the frame; below this it is not a product
    "max_area_fraction": 0.60,   # above this it is the background, not an object
    "min_extent": 0.25,          # filled area / bbox area; rejects thin slivers
    "min_thickness": 0.02,       # of the frame's shorter side; rejects grout lines
}


def _otsu(values: np.ndarray) -> float:
    """Threshold that maximises between-class variance. No parameter."""
    hist, edges = np.histogram(values, bins=256)
    centres = (edges[:-1] + edges[1:]) / 2
    weight1 = np.cumsum(hist)
    weight2 = np.cumsum(hist[::-1])[::-1]
    with np.errstate(invalid="ignore", divide="ignore"):
        mean1 = np.cumsum(hist * centres) / weight1
        mean2 = (np.cumsum((hist * centres)[::-1]) / weight2[::-1])[::-1]
    variance = weight1[:-1] * weight2[1:] * (mean1[:-1] - mean2[1:]) ** 2
    return float(centres[:-1][np.nanargmax(variance)])


def _sobel(grey: np.ndarray) -> np.ndarray:
    kx = np.array([[-1, 0, 1], [-2, 0, 2], [-1, 0, 1]], dtype=float)
    ky = kx.T
    padded = np.pad(grey, 1, mode="edge")
    gx = sum(
        kx[i, j] * padded[i:i + grey.shape[0], j:j + grey.shape[1]]
        for i in range(3) for j in range(3)
    )
    gy = sum(
        ky[i, j] * padded[i:i + grey.shape[0], j:j + grey.shape[1]]
        for i in range(3) for j in range(3)
    )
    return np.hypot(gx, gy)


def _dilate(mask: np.ndarray, radius: int) -> np.ndarray:
    out = mask.copy()
    for _ in range(radius):
        shifted = out.copy()
        shifted[1:, :] |= out[:-1, :]
        shifted[:-1, :] |= out[1:, :]
        shifted[:, 1:] |= out[:, :-1]
        shifted[:, :-1] |= out[:, 1:]
        out = shifted
    return out


def _erode(mask: np.ndarray, radius: int) -> np.ndarray:
    return ~_dilate(~mask, radius)


def _fill_from_border(mask: np.ndarray) -> np.ndarray:
    """
    Solidify outlines: flood the background in from the frame edge, then
    invert. Anything the flood cannot reach is enclosed by an outline.
    """
    height, width = mask.shape
    reachable = np.zeros_like(mask)
    queue: deque = deque()
    for x in range(width):
        for y in (0, height - 1):
            if not mask[y, x] and not reachable[y, x]:
                reachable[y, x] = True
                queue.append((y, x))
    for y in range(height):
        for x in (0, width - 1):
            if not mask[y, x] and not reachable[y, x]:
                reachable[y, x] = True
                queue.append((y, x))
    while queue:
        y, x = queue.popleft()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ny, nx = y + dy, x + dx
            if 0 <= ny < height and 0 <= nx < width and not mask[ny, nx] and not reachable[ny, nx]:
                reachable[ny, nx] = True
                queue.append((ny, nx))
    return ~reachable


def _components(mask: np.ndarray):
    """4-connected labelling. Yields (pixel count, bbox) per component."""
    height, width = mask.shape
    seen = np.zeros_like(mask)
    for sy in range(height):
        for sx in range(width):
            if not mask[sy, sx] or seen[sy, sx]:
                continue
            queue = deque([(sy, sx)])
            seen[sy, sx] = True
            count = 0
            y0 = y1 = sy
            x0 = x1 = sx
            while queue:
                y, x = queue.popleft()
                count += 1
                y0, y1 = min(y0, y), max(y1, y)
                x0, x1 = min(x0, x), max(x1, x)
                for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    ny, nx = y + dy, x + dx
                    if (0 <= ny < height and 0 <= nx < width
                            and mask[ny, nx] and not seen[ny, nx]):
                        seen[ny, nx] = True
                        queue.append((ny, nx))
            yield count, (x0, y0, x1, y1)


def segment(path: pathlib.Path) -> dict:
    source = Image.open(path).convert("RGB")
    full_w, full_h = source.size
    scale = PARAMS["working_width"] / full_w
    work = source.resize((PARAMS["working_width"], max(int(full_h * scale), 1)), Image.LANCZOS)
    grey = np.asarray(work.convert("L"), dtype=float)
    height, width = grey.shape

    gradient = _sobel(grey)
    threshold = _otsu(gradient)
    edges = gradient > threshold

    solid = _erode(_dilate(edges, PARAMS["close_radius"]), PARAMS["close_radius"])
    filled = _fill_from_border(solid)

    frame_area = height * width
    shorter = min(height, width)
    kept, rejected = [], []
    for count, (x0, y0, x1, y1) in _components(filled):
        box_w, box_h = (x1 - x0 + 1), (y1 - y0 + 1)
        area_fraction = count / frame_area
        extent = count / (box_w * box_h)
        thickness = min(box_w, box_h) / shorter
        entry = {
            "bbox": [round(x0 / width, 3), round(y0 / height, 3),
                     round(x1 / width, 3), round(y1 / height, 3)],
            "area_fraction": round(area_fraction, 4),
            "extent": round(extent, 3),
            "thickness": round(thickness, 3),
        }
        if area_fraction < PARAMS["min_area_fraction"]:
            entry["reason"] = "too small to be a product"
        elif area_fraction > PARAMS["max_area_fraction"]:
            entry["reason"] = "occupies most of the frame - background, not an object"
        elif extent < PARAMS["min_extent"]:
            entry["reason"] = "too sparse for its bounding box - an outline, not a mass"
        elif thickness < PARAMS["min_thickness"]:
            entry["reason"] = "thin sliver - grout line or tile edge"
        else:
            kept.append(entry)
            continue
        rejected.append(entry)

    # Ordered by area so candidate numbering is stable across runs.
    kept.sort(key=lambda c: -c["area_fraction"])
    for index, entry in enumerate(kept):
        entry["candidate"] = index

    return {
        "candidates": kept,
        "rejected": rejected,
        "otsu_threshold": round(threshold, 2),
        "mask": filled,
        "work_size": [width, height],
    }


def apply_selection(case: str, result: dict) -> dict:
    """
    Turn a declared selection into proposed bounds.

    With no selection recorded the result stays candidates-only. Proposing a
    union of everything would repeat the case-3 error, where the box spanned
    the product, a cushion and a caption.
    """
    selection = SELECTIONS.get(case)
    if not selection:
        result["bounds"] = None
        result["review_status"] = "candidates only - no selection declared yet"
        return result

    chosen = [c for c in result["candidates"] if c["candidate"] in selection["candidates"]]
    if not chosen:
        result["bounds"] = None
        result["review_status"] = "selection names no surviving candidate"
        return result

    bounds = [
        round(min(c["bbox"][0] for c in chosen), 3),
        round(min(c["bbox"][1] for c in chosen), 3),
        round(max(c["bbox"][2] for c in chosen), 3),
        round(max(c["bbox"][3] for c in chosen), 3),
    ]
    covered = sum(c["area_fraction"] for c in chosen)
    box_area = (bounds[2] - bounds[0]) * (bounds[3] - bounds[1])
    result.update({
        "bounds": bounds,
        "selected_candidates": sorted(selection["candidates"]),
        "instance_count": selection.get("instance_count", len(chosen)),
        "selection_rationale": selection.get("rationale", ""),
        # How much of the proposed box the selected masses actually fill. Low
        # means the selection spans scattered regions, which a reviewer should
        # question rather than accept.
        "box_fill": round(covered / box_area, 3) if box_area else None,
        "review_status": "proposed - awaiting governed annotation review",
    })
    return result


def write_evidence(case: str, path: pathlib.Path, result: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    source = Image.open(path).convert("RGB")
    w, h = source.size

    mask = result.get("mask")
    if mask is not None:
        Image.fromarray((mask * 255).astype("uint8")).resize((w, h), Image.NEAREST).save(
            OUT / f"{case}_mask.png"
        )

    overlay = source.copy()
    draw = ImageDraw.Draw(overlay)
    for component in result["candidates"]:
        b = component["bbox"]
        draw.rectangle([b[0] * w, b[1] * h, b[2] * w, b[3] * h],
                       outline=(255, 200, 0), width=max(w // 400, 2))
        draw.text((b[0] * w + 8, b[1] * h + 8), f"#{component['candidate']}",
                  fill=(255, 200, 0))
    if result.get("bounds"):
        b = result["bounds"]
        draw.rectangle([b[0] * w, b[1] * h, b[2] * w, b[3] * h],
                       outline=(0, 220, 90), width=max(w // 180, 4))
        draw.text((b[0] * w + 10, b[1] * h + 10), "PROPOSED appearance_bounds",
                  fill=(0, 220, 90))
    overlay.save(OUT / f"{case}_overlay.png")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", nargs="*", default=list(CASES))
    parser.add_argument("--out", default=str(OUT / "proposals.json"))
    args = parser.parse_args()

    report = {"parameters": PARAMS, "cases": {}}
    for case in args.cases:
        path = BENCHMARKS / case / "original.jpg"
        result = apply_selection(case, segment(path))
        write_evidence(case, path, result)
        result.pop("mask", None)
        report["cases"][case] = result
        print(f"  {case:22} candidates={len(result['candidates'])}  "
              f"bounds={result.get('bounds')}  box_fill={result.get('box_fill')}  "
              f"{result['review_status']}")
        for c in result["candidates"]:
            print(f"      #{c['candidate']}  {c['bbox']}  area={c['area_fraction']:.3f}"
                  f"  extent={c['extent']}")

    pathlib.Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    pathlib.Path(args.out).write_text(json.dumps(report, indent=2))
    print(f"\nwrote {args.out} and evidence to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
