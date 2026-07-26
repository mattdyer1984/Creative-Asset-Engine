"""
Targeted measurement inside a human-identified product region.

Authorised as case-specific because these measure an area a human has
already identified as product, rather than searching blindly for it. The
region below is the INPUT to the measurement, not its output: a reviewer
says "the product is somewhere in here", and the method measures its extent.

Two methods, each recorded with its parameters in the evidence:

  local_contrast  Otsu on a globally-normalised gradient discards a pale
                  object on a pale ground. Normalising the gradient by its
                  LOCAL maximum first makes a low-contrast edge as
                  significant as a high-contrast one. Used for case 2's
                  fifth book, a white cover on bright marble.

  region_grow     Gradient cannot split touching same-colour objects. Growing
                  a region from a seed, constrained by colour distance from
                  the seed, stops at the seam between two boxes even when
                  that seam is a weak edge. Used for case 8's retail display,
                  where the front package merges with the shelf and its
                  neighbours.
"""

from __future__ import annotations

import json
import pathlib
from collections import deque

import numpy as np
from PIL import Image, ImageDraw

BENCHMARKS = pathlib.Path(__file__).resolve().parents[1] / "backend" / "tests" / "benchmarks"
OUT = pathlib.Path(__file__).resolve().parents[1] / "docs" / "benchmark_review" / "segmentation"
WORKING_WIDTH = 320


def _load(case: str):
    source = Image.open(BENCHMARKS / case / "original.jpg").convert("RGB")
    w, h = source.size
    work = source.resize((WORKING_WIDTH, max(int(h * WORKING_WIDTH / w), 1)), Image.LANCZOS)
    return source, np.asarray(work, dtype=float)


def _sobel(grey: np.ndarray) -> np.ndarray:
    kx = np.array([[-1, 0, 1], [-2, 0, 2], [-1, 0, 1]], dtype=float)
    padded = np.pad(grey, 1, mode="edge")
    gx = sum(kx[i, j] * padded[i:i + grey.shape[0], j:j + grey.shape[1]]
             for i in range(3) for j in range(3))
    gy = sum(kx.T[i, j] * padded[i:i + grey.shape[0], j:j + grey.shape[1]]
             for i in range(3) for j in range(3))
    return np.hypot(gx, gy)


def local_contrast(case: str, region, window: int = 24, percentile: float = 82.0) -> dict:
    """
    Extent of a low-contrast object inside `region`.

    The gradient is divided by its local maximum over a `window`-px
    neighbourhood, so a faint edge on a bright ground scores as highly as a
    strong edge elsewhere. The extent is then the bounding box of the
    normalised response above `percentile`.
    """
    source, work = _load(case)
    grey = work.mean(axis=2)
    height, width = grey.shape
    x0, y0, x1, y1 = (int(region[0] * width), int(region[1] * height),
                      int(region[2] * width), int(region[3] * height))

    gradient = _sobel(grey)
    local_max = np.zeros_like(gradient)
    half = window // 2
    for y in range(height):
        ys, ye = max(y - half, 0), min(y + half + 1, height)
        for x in range(width):
            xs, xe = max(x - half, 0), min(x + half + 1, width)
            local_max[y, x] = gradient[ys:ye, xs:xe].max()
    normalised = np.where(local_max > 0, gradient / local_max, 0.0)

    patch = normalised[y0:y1, x0:x1]
    cut = float(np.percentile(patch, percentile))
    mask = patch >= cut
    rows = np.where(mask.any(axis=1))[0]
    cols = np.where(mask.any(axis=0))[0]
    if not len(rows) or not len(cols):
        return {"bounds": None, "method": "local_contrast", "note": "no response"}

    bounds = [round((x0 + cols.min()) / width, 3), round((y0 + rows.min()) / height, 3),
              round((x0 + cols.max()) / width, 3), round((y0 + rows.max()) / height, 3)]
    return {
        "bounds": bounds, "method": "local_contrast",
        "parameters": {"window_px": window, "percentile": percentile,
                       "search_region": list(region)},
        "coverage": round(float(mask.mean()), 3),
    }


def region_grow(case: str, seed, tolerance: float = 26.0, region=None) -> dict:
    """
    Extent of the object containing `seed`, grown by colour similarity.

    Stops where colour distance from the seed's local mean exceeds
    `tolerance`, which separates touching same-colour objects at their seam
    without needing a strong edge there. `region` bounds the search so growth
    cannot escape into the wider scene.
    """
    source, work = _load(case)
    height, width, _ = work.shape
    sx, sy = int(seed[0] * width), int(seed[1] * height)
    if region is None:
        region = (0.0, 0.0, 1.0, 1.0)
    rx0, ry0, rx1, ry1 = (int(region[0] * width), int(region[1] * height),
                          int(region[2] * width), int(region[3] * height))

    seed_colour = work[max(sy - 2, 0):sy + 3, max(sx - 2, 0):sx + 3].reshape(-1, 3).mean(axis=0)
    visited = np.zeros((height, width), dtype=bool)
    queue = deque([(sy, sx)])
    visited[sy, sx] = True
    ys, xs = [sy], [sx]

    while queue:
        y, x = queue.popleft()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ny, nx = y + dy, x + dx
            if not (ry0 <= ny < ry1 and rx0 <= nx < rx1) or visited[ny, nx]:
                continue
            if np.abs(work[ny, nx] - seed_colour).sum() <= tolerance:
                visited[ny, nx] = True
                ys.append(ny)
                xs.append(nx)
                queue.append((ny, nx))

    bounds = [round(min(xs) / width, 3), round(min(ys) / height, 3),
              round(max(xs) / width, 3), round(max(ys) / height, 3)]
    box_area = (bounds[2] - bounds[0]) * (bounds[3] - bounds[1]) * width * height
    return {
        "bounds": bounds, "method": "region_grow",
        "parameters": {"seed": list(seed), "tolerance": tolerance,
                       "search_region": list(region)},
        "pixels": len(xs),
        "box_fill": round(len(xs) / box_area, 3) if box_area else None,
        "mask": visited,
    }


def overlay(case: str, results: list[dict], suffix: str) -> None:
    source = Image.open(BENCHMARKS / case / "original.jpg").convert("RGB")
    w, h = source.size
    image = source.copy()
    draw = ImageDraw.Draw(image)
    for result in results:
        if not result.get("bounds"):
            continue
        b = result["bounds"]
        draw.rectangle([b[0] * w, b[1] * h, b[2] * w, b[3] * h],
                       outline=(0, 220, 90), width=max(w // 200, 3))
        draw.text((b[0] * w + 8, b[1] * h + 8), result["method"], fill=(0, 220, 90))
    OUT.mkdir(parents=True, exist_ok=True)
    image.save(OUT / f"{case}_{suffix}.png")


def main() -> int:
    report = {}

    # Case 2: the fifth book. Region is the lower-left quadrant a reviewer
    # can see contains it; the method measures its extent.
    report["case02_books"] = {
        "fifth_book": local_contrast("case02_books", (0.22, 0.50, 0.55, 0.85)),
    }
    overlay("case02_books", [report["case02_books"]["fifth_book"]], "fifth_book")

    # Case 8: the front package. Seed is inside it; growth is confined to the
    # left two-thirds so it cannot run into the neighbouring boxes.
    front = region_grow("case08_fan_shelf", (0.40, 0.30), tolerance=26.0,
                        region=(0.15, 0.08, 0.86, 0.86))
    mask = front.pop("mask", None)
    report["case08_fan_shelf"] = {"front_package": front}
    overlay("case08_fan_shelf", [front], "front_package")
    del mask

    (OUT / "targeted.json").write_text(json.dumps(report, indent=2))
    for case, entries in report.items():
        for name, result in entries.items():
            print(f"  {case:22} {name:14} {result.get('bounds')}  "
                  f"{ {k: v for k, v in result.items() if k in ('coverage','box_fill','pixels')} }")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
