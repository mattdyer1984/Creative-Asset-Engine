# Package E — Creative Analysis Pipeline

**Branch** `v2-creative-intelligence-engine` · **Head** `d0a8f31` ·
`phase-2-slideshow-migration` untouched.

Packages A–D built the machinery. Everything they built only worked on slides
a human had annotated by hand. Package E is the analysis that produces those
inputs from an image, so the chain runs on real work.

---

## 1. Commits

| Package | Commit | Files | Lines |
|---|---|---|---|
| E1 — Composition Contract inference | `a418b2f` | 7 | +665 |
| E2 — Creative Project Profile analysis | `0edbd53` | 13 | +915 / −119 |
| E3/E4 — Ownership stage, capability → Owner | `a16385d` | 5 | +450 / −4 |
| E5 — Live rendering gate | `d0a8f31` | 10 | +732 / −20 |

## 2. The pipeline is now eleven stages

| Stage | Cost |
|---|---|
| ocr, product_isolation, product_lock_profile, creative_fingerprint, scene_intelligence | provider call (unchanged) |
| **composition_contract** | provider call, one per slide |
| **creative_profile** | provider call **only for designed-typography projects** |
| **text_ownership** | **deterministic — no provider call at all** |
| marketing_analysis, narrative_structure, creative_specification | provider call (unchanged) |

Three new stages, two paid. `text_ownership` is the only stage in the pipeline
that makes no provider call: every input it needs already exists by the time it
runs, so it costs nothing and is not something that can fail when a provider is
down. `creative_profile` skips its vision call entirely for caption projects —
a UGC post has no design typography to read, and paying to be told so is waste.

## 3. Tests

| Point | Tests |
|---|---|
| Packages A–D | 978 |
| E1 | 1004 (+26) |
| E2 | 1038 (+34) |
| E3/E4 | 1052 (+14) |
| E5 | 1065 (+13) |

1065 passing, 0 failing. `ruff check app tests`, `npx tsc --noEmit` and
`npx oxlint src` all clean.

## 4. Migration

`1f46f688fc71` — `final_outputs.render_manifest_json`, nullable and additive.
Every existing row was produced by the legacy renderer and genuinely has no
manifest; back-filling one would invent an audit trail for work nobody audited.

Round-trip on a WAL-safe copy of the dev DB: upgrade **540 ms**, downgrade
**367 ms**, re-upgrade **370 ms**, all exit 0, `integrity_check` ok, row counts
identical (slideshows 45, slides 120, generated_images 94, final_outputs 26,
provider_calls 367, analysis_runs 638), nine pre-existing FK orphans unchanged.

The three new `analysis_type` values needed no migration — the column has no
constraint, and they are data.

## 5. Contract inference: validated, never trusted

The risk with this stage is not that the model answers badly. It is that a bad
answer **looks authoritative**, because a contract is structure and structure
reads as fact. So the response is constrained twice:

- **At the request** — device, zone role and relation type are JSON-schema
  enums generated from the closed vocabularies themselves, so they cannot
  drift from the code.
- **After the response** — relation endpoints must resolve to declared zones;
  emphasis must name declared zones; impossible or out-of-range bounds are
  **dropped, not clamped**, because clamping invents a zone the model never
  described and puts it somewhere plausible-looking.

Below a **50% zone-survival floor** the device is withdrawn to `unknown` with
zero confidence. Salvaging two zones out of six while still naming a confident
device is precisely how a misread image becomes an authoritative contract;
downstream then degrades to wording-only ownership, which is worse but not
wrong. Everything dropped is returned to the caller and logged — a silently
shortened contract is indistinguishable from a simple layout.

All eight hand-annotated fixtures round-trip through the same validator a
provider response gets. If a human annotation could not survive it, no model
ever would.

## 6. Capability level now reaches `Owner`

The one gap the Packages A–D report called genuine rather than an artifact.
Designed typography above `RENDERER_CAPABILITY` (today `L1`) routes to the
image instead of the deterministic renderer:

| Capability | Owner |
|---|---|
| unknown / L1 | `TYPOGRAPHY` |
| L2, L3 | `IMAGE` + `GENERATED` |

Benchmark 5's "10/10 man" is the case: annotated designed typography, but
integrated into the artwork, so L1 would draw it flat. Raising the constant as
the renderer gains L2 support changes the routing without changing code.

An unreadable capability level from the provider is treated as **L3, not L1**.
L1 is the optimistic answer and the dangerous one.

## 7. The live gate — and the fact that it first passed on an unusable image

Case 4 runs the whole chain on its real image. Ownership comes from the
persisted artifact, zones from the persisted contract, type from the persisted
profile — nothing re-derived at render time, so the manifest describes work
that actually happened.

**The first run passed all eight assertions and produced this:** headline text
at 124px inside an 81px box, wrapped to three lines, overlapping the bullets
below, the entire copy column illegible. Every structural check passed, because
the blocks *had* been rendered and the manifest *did* account for them.

That is a detector failure, so I fixed the defects and gave the gate assertions
that catch them. **Both new tests were verified to fail against the pre-fix
code** — a test that passes either way is not a detector.

### Three defects the gate caught

1. **Type never checked it fitted its zone.** `size_ratio` was honoured
   unconditionally. It now shrinks to fit and reports the block when even the
   minimum size will not. Overflow is not cosmetic: it lands on the neighbour
   and destroys both.

2. **Every accent rendered near-black.** A style's colour *role* (`accent`)
   was handed straight to a function that only knows named colours; the
   project's `colour_roles` map was never dereferenced. Benchmark 4's dark red
   came out black, and every schema-level test passed because they asserted
   only that the accent role *differed* from the body role. It did. Both were
   still drawn in the same colour.

3. **Enforcement deleted a design element.** It cleared the rule under the
   numeral, nothing redrew it, and the finished image had simply lost part of
   the design. Clearing a zone no owner will draw into does not clean it.
   Graphic zones are now enforced only when the typography system defines a
   rule or divider role, and the skip is recorded as a warning.

### What the gate now checks

Structure — every block accounted for, ids and concrete font faces pinned at
render time, the contract-declared rule zone enforced despite no OCR block
mentioning it, every ladder rung auditable — **plus** legibility: no block
drawn outside its own zone, the accent actually drawn in its accent colour,
an unresolvable colour role reported rather than silently blackened, and a
graphic zone nobody will redraw left alone.

Evidence: `backend/tests/benchmarks/case04_posture/package_e_live_gate.png`.
The recreation carries the red numeral, its rule, the black headline, the red
italic accent line and the red bullet markers, in the source's hierarchy.

## 8. Other defects found and fixed

- **The text classifier scored `pov:` and `#fyp` as designed typography**,
  which would have typeset a TikTok caption into the creative as if the
  designer had placed it. Hashtags, @mentions and `pov:` now decide on their
  own — deliberately stronger than the emoji rule, which still cannot, because
  benchmark 6 uses flag emoji inside designed comparison typography. Seven
  control cases assert designed type is not pulled across.
- **Several test files each kept a hand-written list of pipeline modules to
  patch.** That list had already let a real, paid vision call run from the test
  suite once. Replaced with `patch_pipeline_registries()`, derived from
  `SLIDESHOW_STAGE_PIPELINE`, so a stage added tomorrow is covered by
  construction.

## 9. Unresolved limitations

1. **No live provider run.** Every result here is against fixtures and stored
   images, with fake providers. The stages are wired into the real pipeline and
   the flag exists, but nothing in this package has spent money. Cost and
   latency for the two new paid stages are therefore **unmeasured**.
2. **Contract inference is untested against a real model.** The validator is
   thoroughly tested; what a real vision model actually returns for these eight
   images is unknown. That is the single biggest open risk in Package E.
3. **The gate uses a hand-written typography system for case 4.** E2 infers one
   from the image, but the gate supplies its own so that a renderer failure
   cannot be masked by an inference failure. The two have not been chained.
4. **OCR boxes are tighter than the design's optical space**, so fitted type
   comes out slightly smaller than the source. Visible in the evidence image.
5. **A faint residue remains** near (0.07, 0.375) in the rendered output — a
   reconstruction artifact, below the occupancy threshold in its zone.
6. **Cases 1, 2 and 8 have not been run through the live gate.** Only case 4.
7. **Fonts remain macOS-only.** `docs/FONT_PORTABILITY.md` unchanged. The gate
   skips itself where tokens do not resolve, so a font-less host silently gets
   less coverage — the ownership half still runs.
8. **`typography_renderer_enabled` is still off by default.**

## 10. Proposed next steps

1. **One live analysis run** on a real slideshow: contract inference and
   profile inference against a real provider, scored against the eight
   fixtures, with cost and latency recorded per stage against the spend cap.
   This is the gap that matters most.
2. **Chain E2's inferred typography into the gate**, so case 4 runs end to end
   with nothing hand-written.
3. **Cases 1, 2 and 8 through the live gate** — a caption project, a
   product-hero and a shelf snapshot exercise paths case 4 does not.
4. **L2 renderer capability** (outline, shadow, container), which would let
   `RENDERER_CAPABILITY` rise and stop routing benchmark 5 to the image.
5. **Vendored open-licence fonts**, without which none of this is deployable
   and benchmark scores are not comparable across machines.
