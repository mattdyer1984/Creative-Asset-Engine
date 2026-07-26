# Canonical Product References — what to supply

Drop files into `backend/tests/benchmarks/<case>/references/` using the exact
filenames below. I compute the checksums and fill in the manifests.

**Every image must be:** the product only · no overlaid text or captions ·
nothing crossing or occluding it · front-on unless noted · plain or plainly
uncluttered background · branding legible where the product has any.

Phone photos are fine. So are product-listing images. Roughly 800px on the
long edge or better.

---

## Priority 1 — `case08_fan_shelf` (the case that proved the gap)

**Product:** a boxed 16-inch pedestal fan, retail packaging.

The packaging in the creative is cream on the upper two-thirds with a green
lower band, a photo of a white pedestal fan, `16"` and `Pedestal Fan` in dark
text, a feature list reading *3 speed settings / Adjustable height /
Oscillating function*, and three feature icons along the bottom. UK
supermarket own-brand — the aisle signage reads `HOME`.

| Filename | Shows |
|---|---|
| `fan-box-front.jpg` | the box front-on, whole box in frame, no shelf, no price label, no caption |

*Second-best if you can't find that exact box: any boxed pedestal fan
photographed front-on. Note the substitution and I will record it in the
manifest — a near-match still exercises the pipeline, and the manifest will
say it is not the identical product.*

---

## Priority 2 — `case03_mini_ac`

**Product:** a portable mini air-conditioner / air-cooler tower. White body,
rounded top, black front panel with a digital readout showing `88` and a row
of touch controls beneath it, dark vertical vent grille down the front.

| Filename | Shows |
|---|---|
| `mini-ac-front.jpg` | the unit front-on, whole unit, plain background |

---

## Priority 3 — `case02_books` (easiest to source)

**Product:** five specific paperbacks. Cover images are enough — a clean
front cover each.

| Filename | Book |
|---|---|
| `book-atomic-habits.jpg` | *Atomic Habits* — James Clear |
| `book-psychology-of-money.jpg` | *The Psychology of Money* — Morgan Housel |
| `book-let-them-theory.jpg` | *The Let Them Theory* — Mel Robbins |
| `book-dont-believe.jpg` | *Don't Believe Everything You Think* — Joseph Nguyen |
| `book-courage-disliked.jpg` | *The Courage to be Disliked* — Kishimi & Koga |

---

## Optional — `case06_meal_prep`

Two products, so two files. Lower value than the others because the creative
is a comparison rather than a product hero.

| Filename | Shows |
|---|---|
| `containers-plastic.jpg` | translucent plastic food containers with clip lids |
| `containers-glass.jpg` | glass food containers with black clip lids |

---

## What happens next

For each supplied file I will:

1. compute its SHA-256 and write the manifest entry with source and licence
   as you describe them;
2. load it through the production upload path, the same one
   `POST /api/products/{id}/reference-images` uses;
3. run reference scoring — **unmodified**, so an image that is not a clean
   reference will still be rejected, which is the point;
4. continue P1 through reference conditioning, image generation, ownership
   enforcement, editorial rendering and final validation.

Case 8 alone is enough to restart P1. The rest widen coverage.

## Note on provenance

The four creatives (`original.jpg`) carry no recorded source URL — they were
added during Package B as files. Worth correcting when convenient, so the
benchmark can state where its inputs came from.
