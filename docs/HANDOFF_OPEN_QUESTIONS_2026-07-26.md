# Open questions — answer before changing code

Prioritised. **Q1–Q3 are blocking**: acting before answering them risks
fixing the wrong layer. None of Q1–Q8 requires paid image generation.

---

## BLOCKING

### Q1 — Is `f9e3348` the whole cause of the blank chat bubbles, or one of several?

**Why it matters**: determines whether a revert restores usable output or
merely swaps one failure for another.

**What is verified**: `_overlay_text` returns `[]` for `c9c68661` slide 0, and
the spec has `text_overlays: []`.

**What is NOT verified**: whether reverting alone produces usable output. The
same prompt *also* contained (a) `things_to_avoid: "Do not copy … message
content from the original"`, (b) the absolute `suppress_overlay_text`
instruction, and (c) no compositor to fill the emptied zones.
**Any one of those three could independently produce blank bubbles.**

**Diagnostic (free)**: check out `4a30418`, run analysis only on `c9c68661`'s
source images into an isolated `CAE_DATA_DIR`, and diff the resulting
`creative_specifications.structured_json` and compiled prompt against the
current ones.

---

### Q2 — Why did the product importer accept a bot-block page as a product?

**Why it matters**: C2 is arguably worse than C1. Seven distinct products
became one phantom named "Security Check", with a 25-image reference library.
There are **three** such products in the database.

**Questions**: Where in `app/services/product_source_import.py` is the page
title taken as a display name? Is there any check that a fetched page is a
product page? Why did no validation flag "one product, seven slides, seven
visibly different objects"? Should the import have failed closed?

**Diagnostic (free)**:
```sql
select id, display_name, created_at from products where display_name='Security Check';
select count(*) from product_reference_images where product_id='<id>';
```

---

### Q3 — Should the combination layer be built, or should the spec stage simply consume the narrative?

**Why it matters**: this is the difference between a small wiring change and a
new architectural layer.

**What is verified**: `SlideshowNarrativeStructureStage` exists
(`pipeline.py:57`), produces correct beats and arc summaries, and
`SlideCreativeSpecificationStage` does not read it
(`creative_specification_stage.py:211`, `grep -c narrative` = 0).

**The real question**: is passing `beat` + `arc_summary` into the spec prompt
sufficient, or does the owner's §13 requirement — *"the incidental brush can
be replaced with another low-cost beauty item but must not be replaced with
the promoted lash serum"* — need an explicit planner that reasons over both
analyses and emits per-slide constraints?

**My view (hypothesis, untested)**: wiring alone is insufficient. Nothing in
the current spec schema can express "this product is incidental and
replaceable by class" versus "this product's identity is locked". But this
should be tested cheaply — wire the narrative in, run analysis only, read the
resulting specs — before committing to a new layer.

---

## HIGH

### Q4 — Why did slide 0 of the haul stay close to the original while slides 1-7 collapsed?

**Hypothesis, not verified**: slide 0 has no product appearance, so it takes
`run_story_generation_attempt` (conditions on its own source image, no
substitution). Slides 1-7 take the product path with a phantom lock profile.

**Diagnostic (free)**: read `prompt_used` for `cc1476d5` slides 0 and 4 and
compare. If the hypothesis holds, the story path is the *better* behaviour and
worth understanding.

### Q5 — Does the `surface` field have any legitimate consumer?

If `surface` cannot distinguish "copy that is part of the advert" from "text
on a photographed object", what is it for? Is OCR's prompt definition itself
wrong for this domain, or is only my use of it wrong?

**Consider**: a screenshot creative and a product label are both "physical"
but need opposite treatment. The system may need a genuinely new concept —
*simulated interface* — rather than a reinterpretation of `surface`.

### Q6 — Why does `suppress_overlay_text` fire when the compositor is disabled?

`text_strategy = reuse_original` sets it; `typography_renderer_enabled` is
`False`. The two defaults contradict each other and the result is empty layout
zones shipping as final output. Should this be a hard startup error?

### Q7 — What should validation actually check?

Current story-path quality assessment accepted a blank chat mockup at 0.868
with empty `creative_fidelity_json` and `text_quality_json`. What is the
minimum semantic check that would have rejected it, and can it be done
without an extra provider call?

---

## MEDIUM

### Q8 — Is the pre-session baseline genuinely better?

The owner believes output was more coherent before the last 48 hours. **This
has not been tested.** Q1's diagnostic answers it for `c9c68661`. Worth
running for `cc1476d5` too.

### Q9 — Should the benchmark suite measure narrative preservation at all?

It currently measures composition, ownership and identity. The failure the
owner cares about is invisible to it. Adding narrative cases changes what
"suite vN" means — a governance decision, not just a fixture addition.

### Q10 — How should incidental products be modelled?

The haul needs three categories the schema cannot express: identity-locked
(the lash serum), class-level replaceable (six ranked items), freely
replaceable props (the candle, surfaces).

### Q11 — What is the image model's actual price?

Blocks the spend cap and makes cost-per-usable-asset unknowable. Requires
official provider documentation or a verified billing line item — **not** an
inferred figure.

---

## LOW

### Q12 — Should `vt.tiktok.com` be added to the allowlist?
Currently fails closed by deliberate choice. Add only on evidence.

### Q13 — The two benchmark disputes (case01 zone bounds, case06 primary family)
Open since Benchmark Review 001, unchanged, awaiting adjudication.

### Q14 — Should `run_variance.py` write to `provider_calls`?
It currently bypasses the ledger, so its image calls are invisible to cost
reporting.

---

## Questions I cannot answer and did not try to

- Whether the architecture as a whole is the right one. I was asked not to
  defend prior decisions, and I have no evidence either way.
- Whether a different image model would change the 12.5% ship rate.
- Whether the owner's §13 two-stage design is best implemented as two
  provider calls, one larger call, or a local planner over existing artefacts.
