# Product benchmark extension — design

**Approved in principle.** This is the design document required before
implementation. Suite v1 → **v2** on merge (or v3 if Benchmark Review 001 is
approved first — see §4).

---

## 1. Which cases gain Product Lock information

Four of the eight existing cases contain a real, identifiable product. No new
imagery is introduced.

| Case | Product | Product-native text | Why it is a useful test |
|---|---|---|---|
| `case02_books` | five paperback books | cover titles, author names | **many instances of one product class** — isolation must not pick one and call it the product |
| `case03_mini_ac` | portable air-conditioner | display readout, control labels | a **screen on the product** — the `screen` zone role and Product Lock must not fight |
| `case06_meal_prep` | two container stacks | none visible | **two competing products in one frame**; Product Lock must handle a product with no packaging text |
| `case08_fan_shelf` | boxed pedestal fan | packaging heading, feature list | **retail packaging plus a separate shelf price** — the price is scene text, not packaging |

The other four (`case01`, `case04`, `case05`, `case07`) gain **no** `product`
block. That absence is itself an expectation: Product Isolation must not
invent a product in a weather-TV scene or a posture diagram. Those four
become the negative controls, which is why this extension needs no new cases.

## 2. Exactly what is added

One optional top-level `product` block per case. **Nothing existing changes.**

```yaml
# ground_truth.yaml — NEW, optional.
# Absent means "this case has no product", which is asserted.
product:
  name: "16in pedestal fan"

  # MEASURED, not estimated (governance §2 classes bounds as measurable).
  # Where the product occupies the frame.
  appearance_bounds: [0.18, 0.12, 0.82, 0.70]

  # How many distinct instances of the product are present. 5 for the books,
  # 2 for the meal-prep stacks, 1 for the fan. Isolation picking one of five
  # books and calling it "the product" is a real failure this catches.
  instance_count: 1

  # Which Lock Profile fields must be populated for this product. Not the
  # VALUES - those are model prose and would make the fixture a
  # transcription. Which fields must not be empty is checkable and stable.
  expected_lock_fields:
    - product_category
    - product_type
    - packaging
    - colors

  # What must survive regeneration unchanged. Drawn from the case's existing
  # product_native text_blocks so the two cannot disagree.
  immutable_characteristics:
    - "boxed pedestal fan, upright, front-facing"
    - "blue and white retail packaging"

  # Reference conditioning. Crops of THIS image, not new photography:
  # measurable, adds no imagery to govern, and exercises the reference path
  # with genuinely correct inputs.
  reference_crops:
    - id: "front-pack"
      bounds: [0.18, 0.12, 0.82, 0.70]

  # What generation must not do. Expressed as the ownership vocabulary
  # already in use, so it is checkable against the manifest.
  generation_expectations:
    product_native_text_owner: "image"
    product_native_text_strategy: "product_lock"
    # Scene text that is ABOUT the product but not ON it.
    scene_text_not_product_locked:
      - "£30"
```

### Schema and fixture-test changes

- `schema.yaml` gains the `product` block, marked optional.
- `test_benchmark_fixtures.py` gains: `product` is optional; when present,
  bounds are normalised and non-empty; `instance_count ≥ 1`;
  `expected_lock_fields` are real `ProductLockProfile` columns;
  `generation_expectations` use the real `Owner` / `ImageStrategy`
  vocabularies; every `immutable_characteristic` is non-empty.
- A cross-check: every `scene_text_not_product_locked` entry must appear in
  that case's `text_blocks`, so the two annotations cannot drift.

## 3. What each capability is exercised by

| Capability | Exercised by | Assertion |
|---|---|---|
| **Product isolation** | 4 with `product`, 4 without | isolates within `appearance_bounds`; finds `instance_count`; the 4 without produce **no** product |
| **Product Lock** | `expected_lock_fields`, `immutable_characteristics` | every listed field non-empty; each characteristic present in the profile |
| **Reference conditioning** | `reference_crops` | a `GenerationReferenceSet` is built from them and is non-empty |
| **Generation planning** | existing analysis fields | a Creative Specification is produced and names the product |
| **Image generation** | the above | a candidate is produced and stored |
| **Ownership enforcement** | `generation_expectations` | product-native text is `image` + `product_lock`; `£30` is **not** product-locked |
| **Editorial rendering** | existing `typography_system` | manifest accounts for every block |
| **Validation** | existing quality gates | assessment runs and records a verdict |

## 4. Benchmark versioning

**The suite version bumps.** Governance §5: any change to a
`ground_truth.yaml` or to `schema.yaml` bumps it.

- If Benchmark Review 001 is approved first: v1 → v2 (review) → **v3** (this).
- If not: v1 → **v2** (this).

The two are deliberately separate versions even though both touch fixtures.
Mixing a *correction* with an *extension* in one version would make the
impact table meaningless — you could not tell which change moved which score.

## 5. How historical comparability is preserved

This extension is **purely additive**: no existing field changes value, and
no existing expectation is relaxed.

Therefore:

1. **Every v1 metric remains directly comparable.** Device, text mode, zone
   roles, ownership, typography, copy policy, overlay policy, capability
   level — all measured from unchanged annotations.
2. **The new product metrics have no v1 baseline**, and must be reported as
   such. `product_lock 3/4 @ suite v2` with no v1 column, not "improved from
   zero" — nothing was measured before, which is different from measuring
   zero.
3. **No re-scoring of v1 runs is required or meaningful** for the new
   metrics: the Phase F and O1 runs never executed the product stages, so
   there is no data to re-score. This is stated explicitly rather than left
   as an empty cell.
4. **The scorer gains a new section**, not a change to an existing one.
   Existing scoring functions are untouched, so a v1 score recomputed by the
   new scorer must be identical — which is asserted by a test that re-scores
   the stored O1 run and compares against `analysis_scores_o1.json`.

That last point is the real protection: it makes "the scorer changed and
moved the numbers" detectable rather than a matter of trust.

## 6. Migration path for previous benchmark results

| Artifact | Action |
|---|---|
| `docs/phase_f/REPORT.md` | unchanged; stays labelled suite v1 |
| `docs/OPTIMISATION_REPORT.md` | unchanged; stays labelled suite v1 |
| `docs/phase_f/run*.json` | kept; they are raw evidence and never rewritten |
| `analysis_scores*.json` | kept as the v1 baseline for the regression test in §5.4 |
| `CHANGELOG.md` | new entry: what was added, that it is additive, and that new metrics have no baseline |

No historical number is restated, recomputed or deleted.

## 7. Cost and gating

Analysis for the four product cases adds roughly **$0.05/case** (isolation +
Lock Profile). **Generation is unpriced** — the primary image provider still
has no configured rate — so a generation run reports an incomplete cost.

Therefore generation is **behind an explicit flag**
(`--include-generation`), off by default:

- the analysis suite stays cheap enough to run often;
- generation becomes a release gate, run deliberately;
- and no run silently spends unpriceable money.

## 8. Deliberately out of scope

**Multi-angle character continuity.** It needs new photography and a
different kind of annotation (the same product from front, three-quarter and
profile). It is a real remaining gap, and it should be its own decision with
its own review rather than being folded in here.

## 9. Implementation order

1. Measure `appearance_bounds` and `reference_crops` programmatically;
   commit the script and its output alongside the fixtures.
2. Add the `product` block to the four cases; bump VERSION; changelog entry.
3. Extend `schema.yaml` and the fixture-integrity tests.
4. Add the scorer section plus the §5.4 regression test.
5. Extend the harness with `--include-generation`.
6. Run P1 and report.
