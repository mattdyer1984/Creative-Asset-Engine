# Segmentation Review 001 — proposed product bounds

**Benchmark suite v1. No fixture modified. No bounds accepted.**
Tool: `scripts/segment_products.py` · Evidence: `segmentation/`

---

## Outcome in one line

**Connected-component segmentation works, and selecting the product does
not.** It finds objects reliably; it cannot tell which object is the product,
and on one case it cannot separate the product from identical neighbours.
**Two of four cases have defensible candidates; two do not.**

## Method

One method, one parameter set, all four cases — no per-case tuning, which
would have been fitting the measurement to an answer already decided by eye.

Greyscale → Sobel gradient → **Otsu** threshold (data-driven, not hand-set) →
morphological close → flood-fill from the border → 4-connected components →
filter by area fraction, extent and thickness (all scaled to image size).

Dependency added: NumPy. No CV framework, no paid provider.

| Parameter | Value | Basis |
|---|---|---|
| `working_width` | 320 px | fixed for every case |
| `close_radius` | 3 px | at working scale |
| `min_area_fraction` | 0.004 | below this it is not a product |
| `max_area_fraction` | 0.60 | above this it is the background |
| `min_extent` | 0.25 | rejects outlines that are not masses |
| `min_thickness` | 0.02 | rejects grout lines and tile edges |

## The design change this forced

The first version took the **union of every surviving component** as
`appearance_bounds`. On case 3 that box spanned the mini AC (found almost
exactly), a decorative cushion, and the subtitle caption — because *"which of
these objects is the product"* is semantic, and no threshold answers it.

Selection is therefore a **declared, reviewable step**. The tool emits
numbered candidates and proposes nothing until a selection is recorded. **The
coordinates are measured; only the choice is human.**

## Per-case findings

| Case | Candidates | Verdict |
|---|---|---|
| `case03_mini_ac` | 3 | **usable** — #0 `[0.616, 0.389, 0.791, 0.670]` is the AC almost exactly. #1 is the subtitle caption, #2 a cushion; both clearly rejectable by eye |
| `case02_books` | 5 | **partly usable** — #1–#4 are four of the five books individually. #0 is the caption plate. The fifth book ("Don't Believe Everything You Think") did not survive: white cover on bright marble, so its boundary gradient fell below Otsu |
| `case06_meal_prep` | 6 | **needs review** — #0 and #2/#4 look like container stacks, but #1 and #3 are window and cabinetry. Not confirmed |
| `case08_fan_shelf` | 4 | **NOT usable** — #0 `[0.225, 0.106, 0.997, 0.998]` merges the front fan box with the shelf, the box beside it and the box below. `extent=0.256` flags it. The products are the same colour and touch, so no edge separates them |

## Why I am not proposing bounds

Three reasons, any one sufficient under governance:

1. **Case 8 has no defensible candidate.** It is also the case that tests
   retail packaging plus a separate shelf price — arguably the most valuable
   product case in the set.
2. **Case 2 is missing a product instance.** `instance_count: 5` cannot be
   asserted from four detections, and the design uses that field specifically
   to catch isolation picking one book and calling it the product.
3. **Case 6 is unconfirmed.** Accepting it would mean choosing by eye between
   candidates I have not verified.

Proposing bounds for two cases and eyeballing two would produce exactly the
mixed-provenance annotation that made case 1 wrong.

## What would close this

Ordered by expected effort:

1. **A colour-aware second pass for touching same-colour objects** (case 8).
   Gradient alone cannot split them; a region-growing pass seeded inside each
   candidate, constrained by colour distance, might.
2. **A lower-contrast path for pale objects on pale ground** (case 2's fifth
   book). Otsu on a global gradient histogram discards it; a local-contrast
   normalisation before thresholding is the standard remedy.
3. **A human selection UI** — the candidates are good enough that picking
   from a numbered overlay is a minute's work per case, and the coordinates
   would still be measured rather than estimated. This is the cheapest route
   to defensible bounds and needs no further algorithm work.

Option 3 is what I would recommend: the tool already produces the evidence a
reviewer needs, and the remaining gap is a decision, not a measurement.

## Review status

`proposed - candidates only`. No case has an accepted `appearance_bounds`.
The benchmark extension and P1 generation validation remain blocked on this.
