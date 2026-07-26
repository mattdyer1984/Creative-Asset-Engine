# Candidate Review 001 — product bounds

**Suite v1. No fixture modified.** One case approved, three not.
Evidence: `segmentation/` · Tools: `scripts/segment_products.py`,
`scripts/targeted_measure.py`

---

## Summary

| Case | Status | Bounds |
|---|---|---|
| `case03_mini_ac` | **approved** | `[0.616, 0.389, 0.791, 0.670]` |
| `case02_books` | **needs_additional_measurement** | — |
| `case06_meal_prep` | **needs_additional_measurement** | — |
| `case08_fan_shelf` | **needs_additional_measurement** | — |

---

## case03_mini_ac — APPROVED

- **Image** `backend/tests/benchmarks/case03_mini_ac/original.jpg`
- **Overlay** `segmentation/case03_mini_ac_overlay.png`

| Candidate | Measured bounds | Area | Extent | Reading |
|---|---|---|---|---|
| **#0** | `[0.616, 0.389, 0.791, 0.670]` | 0.025 | 0.505 | **the mini AC** |
| #1 | `[0.188, 0.804, 0.812, 0.842]` | 0.015 | 0.601 | subtitle caption — reject |
| #2 | `[0.000, 0.495, 0.222, 0.634]` | 0.013 | 0.402 | decorative cushion — reject |

**Selection: #0 alone.** The box encloses the unit from the top of its
display panel to the base, and its left and right edges sit on the casing.
Confirmed against the overlay.

- **Missing product area:** none identified.
- **`instance_count`: 1** — supported; one unit is visible.
- **Status: `approved`.**

---

## case02_books — NEEDS ADDITIONAL MEASUREMENT

- **Overlay** `segmentation/case02_books_overlay.png`,
  `segmentation/case02_books_fifth_book.png`

| Candidate | Measured bounds | Reading |
|---|---|---|
| #0 | `[0.159, 0.134, 0.844, 0.246]` | caption plate — reject |
| #1 | `[0.459, 0.540, 0.753, 0.728]` | *The Courage to be Disliked* |
| #2 | `[0.188, 0.331, 0.388, 0.528]` | *Atomic Habits* |
| #3 | `[0.666, 0.298, 0.878, 0.526]` | *The Let Them Theory* |
| #4 | `[0.459, 0.310, 0.600, 0.477]` | *The Psychology of Money* |

**Missing product area: the fifth book**, *Don't Believe Everything You
Think* — a white cover on bright marble, whose boundary gradient falls below
the global Otsu threshold.

**Targeted measurement attempted and failed.** Local-contrast normalisation
(window 24 px, 82nd percentile, search region `[0.22, 0.50, 0.55, 0.85]`)
returned `[0.219, 0.500, 0.547, 0.847]` — the search region echoed back, at
0.18 coverage. It measured the region it was given, not the book inside it.

- **`instance_count`: 5** — **not supported.** Four of five books are
  measured. The field exists specifically to catch isolation picking one book
  and calling it the product, so a count asserted from four detections would
  defeat its purpose.
- **Status: `needs_additional_measurement`.**

---

## case06_meal_prep — NEEDS ADDITIONAL MEASUREMENT

- **Overlay** `segmentation/case06_meal_prep_overlay.png`

| Candidate | Measured bounds | Reading |
|---|---|---|
| #0 | `[0.512, 0.367, 0.922, 0.631]` | **top two containers of the right stack only** |
| #1 | `[0.559, 0.078, 0.997, 0.320]` | kitchen background — reject |
| #2 | `[0.125, 0.428, 0.438, 0.499]` | food inside a left container |
| #3 | `[0.000, 0.000, 0.181, 0.132]` | window — reject |
| #4 | `[0.125, 0.548, 0.434, 0.605]` | food inside a left container |
| #5 | `[0.000, 0.146, 0.087, 0.271]` | window — reject |

Cabinetry and window are cleanly rejectable, as asked. **But no candidate
represents a product stack.** The containers are translucent, so their walls
produce almost no gradient; what survived is the *food inside them* (#2, #4)
and the upper half of the right stack (#0). The left stack has no candidate
covering it at all, and both stacks extend to roughly y 0.86 while the best
candidate stops at 0.631.

- **Missing product area:** the lower half of both stacks, and the left stack
  in its entirety.
- **`instance_count`: 2** — **not supported.**
- **Status: `needs_additional_measurement`.** Not attempted: the user's
  targeted list did not cover this case, and translucency is a different
  problem from both low contrast and merged neighbours.

---

## case08_fan_shelf — NEEDS ADDITIONAL MEASUREMENT

- **Overlay** `segmentation/case08_fan_shelf_overlay.png`,
  `segmentation/case08_fan_shelf_front_package.png`

| Candidate | Measured bounds | Extent | Reading |
|---|---|---|---|
| #0 | `[0.225, 0.106, 0.997, 0.998]` | 0.256 | front package **merged** with the shelf, the box beside it and the box below — must not be used |
| #1 | `[0.163, 0.000, 0.997, 0.092]` | 0.439 | shelf edge — reject |
| #2 | `[0.431, 0.585, 0.662, 0.632]` | 0.667 | `for this...` caption — reject |
| #3 | `[0.306, 0.255, 0.512, 0.278]` | 0.744 | `Pedestal Fan` packaging text |

**Targeted measurement attempted and partially failed.** Colour-aware region
growing (seed `[0.40, 0.30]`, tolerance 26.0, search region
`[0.15, 0.08, 0.86, 0.86]`) returned `[0.256, 0.142, 0.856, 0.519]`,
box_fill 0.515.

It did what it was meant to do — it stopped at the seam and did **not** run
into the neighbouring boxes. But it also stopped at the package's own
horizontal colour band: the artwork is cream above and green below, so
growth from a cream seed halted at that internal boundary. The result is the
cream **upper portion** of the package, not the package.

- **Missing product area:** the green lower portion, roughly y 0.52 to 0.80.
- **`instance_count`: 1** — cannot be asserted from a partial extent.
- **Status: `needs_additional_measurement`.** A multi-seed grow (one seed per
  colour band, union of the results) is the obvious next step, but that is
  further algorithm work and I was asked to stop rather than iterate.

---

## What I am not doing

Not converting any partial candidate into a complete product bound. Case 8's
cream upper half and case 2's four-of-five are measurements of *part* of a
product, and recording either as `appearance_bounds` would put a knowingly
wrong number into the governed asset.

Case 3 can proceed on its own, but the extension design covers four cases and
`instance_count` is one of its load-bearing assertions. One approved case is
not enough to version the suite.

## Recommended next step

A **multi-seed region grow** would likely close case 8 (one seed per colour
band, union) and possibly case 6 (seed each container). Case 2 needs a
different remedy — the book is a white rectangle on white marble, and its
strongest cue is the thin drop shadow along two edges rather than the cover
itself.

All three are contained pieces of work. None requires a production
segmentation subsystem, and the runtime Product Isolation stage remains
untouched.
