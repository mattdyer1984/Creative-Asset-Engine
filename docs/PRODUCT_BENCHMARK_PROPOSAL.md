# O4 — Proposal: extending the benchmark suite to the product path

**Status: proposal. No fixture has been modified.** Governance requires
sign-off before the suite changes (`docs/BENCHMARK_GOVERNANCE.md` §3).

---

## The gap

Phase F could not exercise three of eleven stages, or any generation:

- `product_isolation` hard-fails with *"No product assigned to any slide"*
- `product_lock_profile` depends on it
- `creative_specification` composes the recreation prompt
- image generation, quality assessment, cleanup, rendering — all downstream

The blocker is not a bug. The benchmark fixtures describe **creatives**; the
pipeline's product path requires a **Product** entity, which a user creates
in the app with a name, a source and reference images. Nothing in the eight
annotations describes one.

I did not fabricate products to close this. A `ProductLockProfile` inferred
from an invented product would validate the plumbing and nothing else, and it
would put fabricated data into the asset that governs everything else.

## What the product path actually needs

| Stage | Needs |
|---|---|
| Product Isolation | a slide with a `ProductAppearance` pointing at a `Product` |
| Product Lock Profile | isolated product crops from the above |
| Reference conditioning | a `GenerationReferenceSet` — canonical images of the product |
| Generation planning | a Creative Specification, which needs Marketing Analysis |
| End-to-end rendering | all of the above, plus a generated candidate |

## The smallest extension that exercises all five

**Four of the eight existing cases already contain a real, identifiable
product.** No new imagery is needed for the first three capabilities.

| Case | Product | Product-native text to lock |
|---|---|---|
| `case02_books` | five paperback books | cover titles and author names |
| `case03_mini_ac` | portable air-conditioning unit | display readout, control labels |
| `case06_meal_prep` | two meal-prep container stacks | none visible — a useful negative |
| `case08_fan_shelf` | boxed pedestal fan | packaging heading, feature list, `£30` shelf price |

### Proposed addition: one optional `product` block per case

```yaml
# ground_truth.yaml — new, optional. Absent means "this case has no product",
# which is itself an expectation worth asserting.
product:
  name: "16in pedestal fan"           # what a user would type
  # Where the product occupies the frame. MEASURED, not estimated -
  # governance §2 classes bounds as a measurable field.
  appearance_bounds: [0.18, 0.12, 0.82, 0.70]
  # What Product Lock must preserve exactly. Drawn from the existing
  # text_blocks whose class is product_native, so the two cannot disagree.
  immutable_characteristics:
    - "boxed pedestal fan, upright"
    - "blue and white packaging"
  expected_lock_fields:               # which Lock Profile fields must be non-empty
    - product_category
    - packaging
    - colors
  # Reference conditioning: crops of THIS image, not new photography.
  reference_crops:
    - id: "front-pack"
      bounds: [0.18, 0.12, 0.82, 0.70]
```

**Why crops of the existing image rather than new reference photography:**
it adds no new imagery to govern, it is measurable, and it exercises the
reference-conditioning path with genuinely correct inputs. It does not
exercise *multi-angle* character continuity — that is a real remaining gap
and I would keep it out of scope rather than fake it.

### What each addition buys

| Capability | Exercised by | Assertion |
|---|---|---|
| Product Isolation | 4 cases with `product`, 4 without | isolates within `appearance_bounds`; the 4 without must not invent one |
| Product Lock | `expected_lock_fields` | every listed field is populated; `immutable_characteristics` are present |
| Reference conditioning | `reference_crops` | a `GenerationReferenceSet` is built from them |
| Generation planning | existing fields | a Creative Specification is produced and names the product |
| End-to-end rendering | the above plus one generation | manifest accounts for every block; product-native text is `product_lock`-owned |

### Cost

The four product cases add roughly **$0.05/case** of analysis (isolation plus
lock profile). Generation is the expensive part and is **unpriced** — the
primary image provider still has no configured rate, so a generation
benchmark would report an incomplete cost. I would gate the generation cases
behind an explicit flag so the analysis suite stays cheap enough to run often.

## What I recommend

1. **Approve the `product` block** as an optional, additive field. Suite
   v1 → v2, changelog entry, no existing expectation altered.
2. **Measure `appearance_bounds` and `reference_crops` programmatically**,
   committing the measurement script — and take the same opportunity to
   settle case 1's zone bounds (§ governance, currently awaiting sign-off).
3. **Keep generation behind a flag.** Analysis stays a cheap, frequent check;
   generation is a release gate.
4. **Do not add multi-angle reference photography yet.** Character continuity
   across angles is a genuine gap, but it needs new imagery and a different
   kind of annotation, and it should be its own decision.

Nothing here changes an existing expectation. Every addition is a new
optional field, so scores measured against v1 remain comparable to v2 for
every field that already existed.
