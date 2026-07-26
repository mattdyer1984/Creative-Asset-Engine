# ADR 0001 — Creative Intelligence Engine (V2 architecture)

| | |
|---|---|
| **Status** | **Proposed** — becomes Accepted only when the gates in §17 pass |
| **Proposed** | 2026-07-26 |
| **Baseline commit** | `8f1b881318513f5c3438d19fd5991ac988a7a882` |
| **Benchmark fixture version** | `v0` — committed, 8 cases (WP-0.1) |
| **Supersedes** | Slide-level architectural assumptions in `MIGRATION_PLAN.md` §"ADR: AI Creative Engine vNext" (2026-07-23). Product Lock v2 remains in force and is extended, not replaced. |

---

## 1. Context

The engine currently recreates slides. It analyses one slide, generates one
slide, validates one slide, and repeats. A week of remediation fixed real
defects — style-aware rendering, colour fidelity, reference retirement,
product-URL acquisition, text duplication, transformation policy — and raised
the incident slideshow from 5/7 to 7/7 accepted candidates.

The output is still materially worse than the source. Every fix was measured
against *"did the validator accept it?"*, and none against *"is this as good
as the original?"* Two failures made that unmistakable:

1. Seven slides of one slideshow produced seven **different people**, where the
   original has one protagonist throughout.
2. Designed editorial typography (a red numeral, a serif headline, a red italic
   subhead, red-bulleted lists) was **stripped from the image and replaced with
   a generic bold-white-with-black-stroke caption style**.

Neither is a bug in any single component. Both follow from an architecture that
has no concept of a *project*, and no concept of text belonging to the creative.

Eight human recreations produced with Nano Banana (the "gold standard" set) are
adopted as the product specification. Their analysis drives every decision
below.

---

## 2. Superseded architectural assumptions

| Assumption | Status | Replaced by |
|---|---|---|
| A slideshow is a sequence of independent slides | **Superseded** | `CreativeProjectProfile` |
| Composition should be preserved literally | **Superseded** | Composition Contract (device / zones / relations / emphasis) |
| Marketing copy is an overlay the app composites | **Superseded** | Baked-in vs overlay product rule (§4) |
| Recreations should look like the original at the same production tier | **Superseded** | Production-value strategy (§7) |
| Preserve/transform is decided per slide by the specification model | **Superseded** | Deterministic transformation plan |
| One unconditional realism instruction | **Already superseded** in `8f1b881` | Source-style-aware rendering |
| Product identity is established by slideshow crops | **Already superseded** in `8f1b881` | Product-URL references, Product Lock v2 |

---

## 3. Evidence from the benchmark set

Text classification across all eight pairs:

| Pair | Designed typography | Platform caption | Product / environmental |
|---|---|---|---|
| 1 Weather TV | — | caption box, subtitle | map cities, temperatures, "Thursday" |
| 2 Books | — | caption box + emoji | covers, titles, authors |
| 3 Mini AC | — | caption box, subtitle | "88" display |
| 4 Posture | **numeral, serif headline, bullets** | — | — |
| 5 10/10 man | **title treatment** | — | — |
| 6 Meal prep | **comparison labels** | — | — |
| 7 Gut health | **headline stack, BAD/GOOD** | — | — |
| 8 Fan shelf | — | caption | box copy, spec icons, £30 shelf label |

**Findings**

1. **Text wording is preserved verbatim in 8/8 pairs.** Never reworded, never
   dropped, emoji included.
2. **The set splits cleanly**: four *designed editorial* projects with integral
   typography and no caption; four *UGC photographic* projects with a caption
   plus text living on real objects. No pair mixes the two. Text mode is
   therefore a **project-level property**, not a per-block guess.
3. **Human identity changes in 5/5 pairs containing people** — pair 1 changed
   gender — while **pose and framing are preserved** (pair 4's hunch, pair 7's
   crop).
4. **Composition is not preserved.** Pair 2 went overhead flat-lay → upright
   eye-level; pair 8 pulled the camera back; pair 5 reordered grid panels.
   What survives is the *communicative structure*.
5. **Typography is not always preserved.** Pairs 6 and 7 changed typeface
   family outright. Hierarchy, colour roles and emphasis survived; the face
   did not.
6. **Production value is deliberately raised in 2/8** (pairs 2 and 6 moved to a
   luxury high-rise setting). The remaining six were refined, not elevated.

---

## 4. Product rule: baked-in text versus overlay text

**This is a product rule, not an implementation detail.**

> **Baked-in text belongs to the creative and is preserved by default.
> Overlay text belongs to the post and is optional according to the user's
> decision.**

### 4.1 Baked-in creative text

Designed editorial typography; infographic headlines and bullets; comparison
labels; any text following the project's visual style; product-native text;
packaging; book covers; screens and app UI; shelf labels; environmental
signage; text embedded in television or application graphics.

**Default behaviour**

- preserve the wording verbatim;
- preserve its functional hierarchy;
- reconstruct or retain it in the finished creative;
- **never remove it by default**;
- change only through an explicit advanced edit.

### 4.2 Optional overlay text

Typically white text with a black stroke; bold centred social captions;
informal conversational copy; emoji; text sitting over an otherwise complete
photograph; caption boxes that appear added after the base image existed.
Overlay text may appear away from centre — **position alone is never
sufficient**.

**Default behaviour**

- detect and store separately from the base creative;
- expose controls to keep, edit, replace or remove;
- exclude from the generated image when deterministic rendering owns it;
- **removing it must leave a complete, usable base image.**

### 4.3 Classification signals

White-on-black-stroke is a strong indicator, never an absolute rule.
Classification must also weigh:

- whether the typography matches the project design system;
- whether the text is attached to an object;
- whether it interacts structurally with the layout;
- whether the wording is conversational or editorial;
- whether the same caption treatment recurs across the project;
- whether the underlying image remains conceptually complete without it.

### 4.4 Acceptance criteria (binding)

1. Baked-in text is **never removed by default**.
2. Overlay text can be removed **without damaging the underlying image**.
3. Text is **never duplicated** between generation and rendering.
4. Uncertain classifications are **surfaced for review**, never silently decided.
5. The user can set **one project-wide overlay policy** and **override
   individual blocks**.

---

## 5. Copy policy

Verbatim preservation is the observed behaviour in all eight pairs, but it must
be an explicit policy rather than an assumption.

```
copy_policy:
  - preserve_verbatim      (default, and the benchmark expectation)
  - preserve_meaning
  - user_replacement
```

Applies differently by class:

- **Baked-in creative text** — the policy governs reconstruction. It is always
  reconstructed; the policy decides whether the words may change.
- **Overlay text** — the policy governs wording, and the separate overlay
  policy may additionally remove it entirely.

---

## 6. Product-native text ownership

Product-native text is **owned by Product Lock and reference conditioning**,
not by deterministic typography. Explicit hierarchy:

1. **Preserve** through product reference imagery and Product Lock.
2. **Verify** key visible product text and identifying details.
3. **Regenerate or repair** only where verification fails.
4. **Never** reconstruct branded packaging as generic deterministic typography
   layered over an unrelated product image.

Critical for: book covers (pair 2), fan packaging and shelf price (pair 8),
appliance displays (pair 3), television maps and graphics (pair 1).

Rule 4 exists because a plausible-looking shortcut — "render the title text
ourselves" — would fabricate branded packaging. That is a correctness and
trust failure, not a quality trade-off.

---

## 7. Production-value strategy

Project-level, **suggested by the engine, chosen by the user**.

| Mode | Meaning | Benchmarks |
|---|---|---|
| `match` | Reproduce the production tier exactly, including deliberate rawness | — |
| `refine` **(default)** | Fix obvious weaknesses — lighting, clutter, framing — without changing register | 1, 3, 4, 5, 7, 8 |
| `elevate` | Deliberately raise setting and production tier | 2, 6 |

`elevate` must never be applied automatically to authentic UGC. Authenticity is
frequently the mechanism that makes such a creative work.

---

## 8. Creative Intent

Sits above narrative and explains *why* a slide tolerates some changes and not
others. The shelf slide is not about a fan; it is about **discovering an
expensive product in a retail environment** — which is why the camera may move
but the price label may not disappear.

Closed vocabulary: `discovery`, `comparison`, `education`, `warning`,
`aspiration`, `transformation`, `humour`, `social_proof`, `demonstration`,
`product_reveal`.

Influences generation without dictating layout.

---

## 9. Composition Contract

The intermediate abstraction between "preserve pixels" (too rigid) and
"preserve the device" (too loose).

```
DEVICE     split-comparison | grid-collage | side-by-side-comparison |
           product-hero | scene-with-caption | shelf-snapshot |
           diagram-with-callout | screen-in-scene

ZONES      role + normalised geometry:
           text-zone | subject-zone | product-zone | negative-space |
           callout-zone

RELATIONS  above | below | left-of | right-of | attached-to |
           points-to | splits | flanks | contains

EMPHASIS   ordered list — what the eye reaches first, second, third
```

Preserved: device, zone roles, relations, emphasis order.
Free: camera, arrangement within zones, room, lighting, props, decoration.

This permits pair 2's camera change and pair 5's panel reordering while
forbidding the failures actually observed — losing the spine overlay, dropping
the price label, breaking the split-face divider.

**Deliberately not a general relationship graph.** Nine relation types express
all eight benchmarks. The vocabulary is extended only when a real slide cannot
be represented, with the slide as evidence.

---

## 10. Typography as a design system

Typography is a design system alongside colour and illustration style — not a
text-rendering concern.

```
typography_system:
  primary_family, secondary_family, case_rules, weight_hierarchy,
  colour_roles, alignment, scale_ratios, line_spacing, tracking,
  decorative_rules, bullets, number_treatments, dividers, stroke,
  shadow, containers
```

### 10.1 Capability levels (graded, so pair 5 cannot block delivery)

| Level | Covers | Benchmarks |
|---|---|---|
| **L1 — flat structured** | family class, weight, italic, case, size hierarchy, alignment, line spacing, tracking, colour, bullets, basic rules/dividers | **4, 6, 7** |
| **L2 — styled** | stroke, shadow, gradient, containers, glow, simple layered effects | begins to cover **5** |
| **L3 — expressive lettering** | bevelled treatments, custom display type, lettering integrated into illustration or objects, perspective and environmental effects | later, or a specialised generation / inpainting path |

L1 is the Phase 1 deliverable. L3 may remain model-generated indefinitely.

### 10.2 Font strategy

Nearest-family mapping from a curated, licence-checked set. Exact face matching
is explicitly **not** a goal. Engineering effort belongs in hierarchy, spacing,
emphasis and alignment.

---

## 11. Text-zone reservation and fallback hierarchy

Deterministic typography requires clean zones. When a zone is not clean, the
fallback order is **strict** — model lettering is a late resort, not a
convenience:

1. **Regenerate** the base image with stronger zone constraints.
2. **Inpaint / reconstruct** the background to clear the required zone.
3. **Adapt the typography layout** within the permitted zone.
4. **Model-rendered lettering** only where deterministic rendering genuinely
   cannot represent the required design (typically L3).
5. **Flag for human review** if none of the above meets the benchmark.

Without this ordering the system would drift back to unreliable model lettering
whenever zone reservation is imperfect — reintroducing the defect this
architecture exists to remove.

---

## 12. Confidence, defaults and conflict resolution

### 12.1 Project text mode is a default, not an exclusive mode

A designed editorial project may still contain product packaging, screenshots
or embedded app UI. A UGC caption project may contain a designed promotional
graphic on one slide. The project mode establishes the **default
interpretation**; blocks override it when evidence is strong.

### 12.2 Thresholds

| Confidence | Behaviour |
|---|---|
| `≥ 0.80` | Block override applied automatically |
| `0.55 – 0.79` | Project default applied; block flagged for review |
| `< 0.55` | Project default applied; **surfaced to the user as uncertain** |

Project mode itself requires `≥ 0.60` agreement across slides; below that the
project is marked mixed and every block is classified individually.

### 12.3 Conflict resolution

- A block attached to an object (packaging, screen, shelf) is **product-native**
  regardless of project mode. This overrides everything else.
- A block matching the project design system is **baked-in**, even in a caption
  project.
- A block matching the caption treatment used elsewhere in the project is
  **overlay**, even in a designed project.
- **When uncertain, preserve and request review.** Preservation is the safe
  failure: keeping text that could have been removed is recoverable; removing
  text that should have been kept destroys the creative.

---

## 13. User decisions surfaced before generation

The blueprint is not merely editable after analysis — it must surface the
decisions that materially change the result **before** any paid generation:

| Decision | Options | Default |
|---|---|---|
| Overlay text | keep / remove / replace / review individually | **keep** |
| Production value | match / refine / elevate | **refine** |
| Copy policy | preserve verbatim / preserve meaning / user replacement | **preserve verbatim** |
| Character continuity | required / preferred / not applicable | **preferred** if a recurring cast is detected |
| Uncertain text classifications | per block | **preserve pending review** |
| Uncertain device classifications | per slide | surfaced |

Defaults are suggested. They must be visible and understandable, never silent.

---

## 14. Object model

```
CreativeProjectProfile         slideshow-scoped, AnalysisArtifactMixin
├── design_system              medium, palette, lighting, texture, setting
├── typography_system          §10
├── text_mode                  project default + confidence
├── copy_policy                §5
├── overlay_policy             §4
├── cast[]                     identity fields | behaviour fields
├── device_inventory
├── consistency_rules
├── production_value           §7
└── creative_intent[]          §8, per slide

CompositionContract            slide-scoped, AnalysisArtifactMixin
└── device | zones[] | relations[] | emphasis[]

TransformationPlan             slide-scoped, AnalysisArtifactMixin
└── per element: preserve | transform | originate | randomise
```

**No disposable architecture.** `CreativeProjectProfile` is introduced in
Phase 1 in minimal form (schema version, text mode, classification confidence,
typography system, production-value placeholder, provenance) and extended in
place through later phases. It uses `AnalysisArtifactMixin` exactly as the six
existing artifact types do, so provenance, versioning and staleness come for
free and no temporary table is created and retired.

---

## 15. Roadmap

Every work package is one revertible commit. Every schema change is an Alembic
migration in batch mode, round-tripped on a copy of the dev database via
`scripts/migrate.py`, with new columns nullable and never back-filled with
guesses.

### Phase 0 — Benchmark & measurement

#### WP-0.1 Benchmark fixture library
- **Purpose** Turn the eight pairs into the executable specification.
- **Data model** None. `backend/tests/benchmarks/<case>/` with `original.jpg`, `recreation.jpg`, `ground_truth.yaml`.
- **Pipeline** None.
- **UI** None.
- **Migration** N/A (additive files).
- **Benchmarks** All eight.
- **Validation** Two reviewers independently annotate cases 4 and 7; the schema must express both without free-text escape hatches.
- **Rollback** Delete directory.
- **Complexity** M — annotation is the work.
- **Dependencies** None.

#### WP-0.2 Per-stage scoring harness
- **Purpose** Localise regressions to a stage.
- **Data model** None. **Pipeline** `scripts/benchmark.py`. **UI** None. **Migration** N/A.
- **Benchmarks** All eight.
- **Validation** Deterministic stages score identically across two runs; vision-scored stages report variance across three so the noise floor is known.
- **Rollback** Delete script. **Complexity** M. **Dependencies** WP-0.1.

#### WP-0.3 Baseline capture
- **Purpose** A number to improve on.
- **Validation** Every stage has a recorded score, including zeros. Committed as `baseline.json`.
- **Rollback** Delete. **Complexity** S. **Dependencies** WP-0.2.

#### WP-0.4 Transitional protection for designed typography
- **Purpose** Stop destroying designed typography **before** the replacement exists.
- **Data model** None.
- **Pipeline** Text masking applies only where a platform caption is present; off by default until WP-1.1. **Marked transitional in code.**
- **UI** None. **Migration** None.
- **Benchmarks** 4 (must stop losing serif typography), 8 (genuine caption, unaffected).
- **Validation** *Until the style-aware renderer is available, designed typography must not be stripped or replaced with the generic caption style.* Model-retained typography is a **temporary safety measure, explicitly not the target architecture**.
- **Rollback** Revert; masking is additive.
- **Complexity** S. **Dependencies** None. **Do first — this is live damage.**

### Phase 1 — Creative Rendering

#### WP-1.1 Text classification + minimal CreativeProjectProfile
- **Purpose** Establish project text mode with block-level override; introduce the profile in minimal form.
- **Data model** New `creative_project_profiles` (AnalysisArtifactMixin, slideshow-scoped): `schema_version`, `text_mode`, `text_mode_confidence`, `typography_system_json` (nullable until WP-1.2), `copy_policy`, `overlay_policy`, `production_value` (placeholder, default `refine`). Extend `ocr_results.structured_blocks_json` with `text_class`, `text_class_confidence`, `text_class_source`.
- **Pipeline** Classification pass after OCR; thresholds and conflict rules per §12.
- **UI** Blueprint shows mode, per-block classes and every uncertain block.
- **Migration** New table + additive nullable JSON. Existing rows stay unclassified — honest, never back-filled.
- **Benchmarks** All eight; cases 2 and 6 discriminate.
- **Validation** 8/8 project modes correct; product-native blocks in 1/2/3/8 override the caption default; acceptance criteria §4.4 (1), (4), (5).
- **Rollback** Revert; table and columns unused and nullable.
- **Complexity** L. **Dependencies** WP-0.1.

#### WP-1.2 Typography system extraction
- **Purpose** Typography as a design system.
- **Data model** Populates `typography_system_json` on the profile.
- **Pipeline** Extraction from OCR geometry + one slideshow-scoped vision call.
- **UI** Displayed and editable in the blueprint.
- **Migration** None beyond WP-1.1.
- **Benchmarks** 4, 5, 6, 7.
- **Validation** Case 4 yields serif primary; red + black colour roles; italic secondary emphasis; red bullets; red rule divider; left alignment; ≈3:1 headline-to-body scale.
- **Rollback** Revert; renderer keeps current style. **Complexity** L. **Dependencies** WP-1.1.

#### WP-1.3 Curated font library and nearest-family mapping
- **Purpose** Hierarchy over fidelity.
- **Data model** Static config: font files + family-class metadata.
- **Pipeline** Deterministic family-class → available face.
- **UI** Font shown, manually overridable. **Migration** None (asset addition; licence check per face).
- **Benchmarks** 4, 6, 7.
- **Validation** serif→serif, grotesque→grotesque, condensed→condensed; never silently falls back to the caption face.
- **Rollback** Revert to single face. **Complexity** M. **Dependencies** WP-1.2.

#### WP-1.4 Style-aware Rendering Engine (L1)
- **Purpose** The largest visible quality gap. Replaces the single hardcoded style.
- **Data model** `final_outputs.typography_system_id`, `final_outputs.render_manifest_json`.
- **Pipeline** `rendering_engine` consumes the typography system per block: family, weight, case, colour role, alignment, tracking, leading, bullets, rules, containers. **L1 only.**
- **UI** Render manifest inspectable; per-block manual correction.
- **Migration** Additive nullable.
- **Benchmarks** 4, 6, 7 primary; 1, 3, 8 must not regress.
- **Validation** Case 4 renders a red numeral, black serif headline, red italic subhead, red-bulleted list and correct rule, scored against the original. **This is the programme gate (§17).**
- **Rollback** Revert; previous renderer intact. **Complexity** L. **Dependencies** WP-1.2, WP-1.3.

#### WP-1.5 Text-zone reservation and fallback hierarchy
- **Purpose** Clean zones for deterministic typography.
- **Data model** None (proper zones arrive in WP-2.2; interim uses OCR boxes).
- **Pipeline** Compiler emits explicit empty-zone geometry; fallback order per §11.
- **UI** Zone overlay on the candidate; review flag at fallback level 5.
- **Migration** None.
- **Benchmarks** 4, 6, 7.
- **Validation** Reserved-zone occupancy below threshold across three runs per case; fallback ladder exercised in order, with level 4 reached only when 1–3 fail.
- **Rollback** Revert. **Complexity** M. **Dependencies** WP-1.4.

#### WP-1.6 Overlay controls
- **Purpose** Overlay text belongs to the user.
- **Data model** `final_outputs.overlay_overrides_json`.
- **Pipeline** Renderer honours per-block keep / edit / replace / remove.
- **UI** Per-block controls plus one project-wide policy.
- **Migration** Additive nullable.
- **Benchmarks** 1, 2, 3, 8.
- **Validation** Acceptance criteria §4.4 (2) and (5): removing every caption leaves a complete, usable base image.
- **Rollback** Revert. **Complexity** S. **Dependencies** WP-1.4.

### Phase 2 — Composition Contract

#### WP-2.1 Device classification
- **Data model** New `composition_contracts` (AnalysisArtifactMixin, slide-scoped): `device`, `device_confidence`.
- **Pipeline** Classification after scene intelligence. **UI** Shown, overridable. **Migration** New table.
- **Benchmarks** All eight.
- **Validation** 8/8 correct; unknown returns low confidence rather than a guess.
- **Rollback** Revert. **Complexity** M. **Dependencies** WP-0.1.

#### WP-2.2 Zone extraction · WP-2.3 Relation extraction
- **Data model** `zones_json`, `relations_json` on the contract.
- **Pipeline** Extraction pass; nine relation types only. **UI** Overlay on the original. **Migration** Additive.
- **Benchmarks** 4 (`spine attached-to upper-back`), 8 (`price below product`), 7 (`divider splits face`).
- **Validation** Every ground-truth relation extracted; no invented relations.
- **Rollback** Revert. **Complexity** L combined. **Dependencies** WP-2.1.

#### WP-2.4 Contract into the compiler · WP-2.5 Contract verification
- **Data model** Verification result on `quality_assessments`.
- **Pipeline** Sectioned prompt from the contract; post-generation check that device and relations survived.
- **UI** Per-relation pass/fail. **Migration** Additive.
- **Benchmarks** All eight.
- **Validation** Deliberately removing the price label must fail verification.
- **Rollback** Revert; advisory before it gates. **Complexity** L. **Dependencies** WP-2.3.

### Phase 3 — Project profile completion and cast continuity

#### WP-3.1 Profile extension
- **Purpose** Extend the Phase 1 profile in place — design system, device inventory, consistency rules, creative intent.
- **Pipeline** Slideshow-scoped analysis before per-slide specification. **Replaces the style-consensus heuristic added in `8eef96b`.**
- **UI** Full profile view, editable, re-runnable. **Migration** Additive columns on the existing table.
- **Benchmarks** All eight.
- **Validation** Posture project: illustrated, one recurring male character, serif system, cream/red palette, designed-typography mode, intent `education`, production value `refine`.
- **Rollback** Revert; per-slide path still works. **Complexity** L. **Dependencies** WP-1.1, WP-2.1.

#### WP-3.2 Creative Intent · WP-3.3 Production-value strategy
- **Data model** `creative_intent` per slide; `production_value` promoted from placeholder.
- **Pipeline** Both inform the compiler; production value suggested, user-confirmed.
- **UI** Both editable; `refine` default. **Migration** Additive.
- **Benchmarks** 2 and 6 = `elevate`; the rest = `refine`.
- **Validation** Suggestions match ground truth; `elevate` never auto-applies to UGC.
- **Rollback** Revert; default `refine`. **Complexity** M. **Dependencies** WP-3.1.

#### WP-3.4 Cast extraction · WP-3.5 Character reference conditioning
- **Data model** `cast_json` (identity vs behaviour); new `character_reference_images`, mirroring `product_reference_images`.
- **Pipeline** Anchor slide generated first; accepted character conditions the rest.
- **UI** Cast shown; anchor selectable; character regeneratable. **Migration** New table.
- **Benchmarks** Posture slideshow (7 slides, one character); case 5.
- **Validation** Cross-slide identity check ≥ threshold across 7 slides. Partial success must degrade honestly ("we could not hold this character"), never fail the project silently.
- **Rollback** Revert; slides generate independently. **Complexity** XL. **Highest risk. Dependencies** WP-3.1.

#### WP-3.6 Deterministic transformation plan
- **Data model** New `transformation_plans` (AnalysisArtifactMixin, slide-scoped).
- **Pipeline** Derived in code from profile + contract + intent. Replaces the emergent avoid-list behaviour.
- **UI** Plan shown before generation. **Migration** New table.
- **Benchmarks** All eight.
- **Validation** A human reads the plan and predicts the output; two runs of one plan produce identical preserve/transform decisions.
- **Rollback** Revert. **Complexity** L. **Dependencies** WP-3.1, WP-2.3.

### Phase 4 — Project validation and explainability

- **WP-4.1** Set-coherence validation — character, typography, palette, device across slides. M. Depends WP-3.5.
- **WP-4.2** Rubric scoring replaces pass/fail as the headline metric. M. Depends WP-0.2.
- **WP-4.3** Full pipeline explainability: original → profile → contract → plan → prompt → candidates → validation → selection. M. Depends WP-3.6.

---

## 16. Benchmark fixture schema

Each case is the specification, not merely a test:

```yaml
case_id, source_project_type, primary_text_mode
text_blocks:            per block: text, class, confidence,
                        expected_handling_mechanism
overlay_policy, copy_policy, creative_intent
composition_contract:   device, zones, relations, emphasis
typography_system
production_value_strategy
required_invariants, allowed_transformations, forbidden_transformations
human_rationale, known_ambiguity
```

**Worked example — posture (case 4)**
designed typography · preserve verbatim · deterministic typography target ·
no platform caption · character identity transforms · pose and spine
relationship remain · typography hierarchy remains · exact face may change
within the serif family.

**Worked example — fan shelf (case 8)**
platform caption *optional* · product packaging text *required* · shelf price
*required* · supermarket discovery context *required* · exact supermarket
environment *transformable*.

---

## 17. Implementation gates

Status moves **Proposed → Accepted** only when all four pass:

1. ✅ **PASSED** — benchmark fixtures and ground truth committed (WP-0.1),
   8 cases with closed-vocabulary annotation.
2. ✅ **PASSED** — baseline captured (WP-0.3),
   `backend/tests/benchmarks/baseline.json`. `text_handling` 1.000 across 8
   cases; five of seven stages honestly report `not_implemented`.
3. ✅ **PASSED** — deterministic L1 typography reaches benchmark quality on
   case 4. Visual proof:
   `backend/tests/benchmarks/case04_posture/typography_gate.jpg`.
4. ⏳ **PENDING** — no schema change has been made yet. WP-1.1 introduces the
   first (`creative_project_profiles`); this gate is assessed then.

Gate 3 is the programme's premise. If deterministic L1 typography does not look
right on case 4, Phase 1's foundation is wrong and the roadmap must be revised
before further investment.

---

## 18. Decision log

| # | Decision | Rationale |
|---|---|---|
| D1 | Benchmarks are the specification | Validator-driven development produced accepted output that was worse than the source |
| D2 | Hybrid text architecture, not "model renders everything" | OCR verifies spelling but not typographic quality; deterministic rendering is controllable |
| D3 | Deterministic rendering owns designed typography and captions | The current renderer's single hardcoded style is the defect, not compositing itself |
| D4 | Product Lock owns product-native text | Reconstructing branded packaging deterministically would fabricate it |
| D5 | Composition Contract, not a general relationship graph | Nine relation types express all eight benchmarks; open graphs are hard to validate and prompt from |
| D6 | Project text mode is a default, blocks may override | Mixed projects are expected even though the benchmark set splits cleanly |
| D7 | Uncertain text is preserved and surfaced | Keeping removable text is recoverable; removing keepable text destroys the creative |
| D8 | Production value is a user choice, `refine` by default | Authenticity is often the mechanism; auto-elevating would break it |
| D9 | Typography graded L1/L2/L3 | Pair 5's expressive treatment must not block a renderer that solves pairs 4, 6 and 7 |
| D10 | Character continuity by reference conditioning | Prose cannot hold a face across seven slides |
| D11 | `CreativeProjectProfile` introduced minimal in Phase 1 | Avoids a disposable table and migration; `AnalysisArtifactMixin` already fits |
| D12 | Strict zone-fallback ordering | Prevents casual regression to unreliable model lettering |

---

## 19. Open risks and unresolved questions

| Risk | Package | Mitigation |
|---|---|---|
| Deterministic typography looks wrong despite correct extraction | WP-1.4 | Prototype case 4 end-to-end before building 1.5/1.6 — this is gate 3 |
| Character drift across slides | WP-3.5 | Multiple reference angles; degrade honestly rather than fail |
| Model will not leave zones clean | WP-1.5 | Measured occupancy; strict fallback ladder (§11) |
| Font licensing | WP-1.3 | Licence check per face before adoption |
| Profile becomes a large analysis layer that does not move quality | WP-3.1 | Phase 0 harness proves value per package |
| Project-level analysis cost at volume | WP-3.1 | Profile is one slideshow-scoped call; measure against the existing spend cap |

**Unresolved questions**

1. Can L1 deterministic typography reach benchmark quality on case 4? *(Gate 3.)*
2. How many character reference angles are needed to hold identity across
   front, three-quarter and profile views?
3. Does zone reservation hold reliably enough that fallback levels 1–3 cover
   the majority of cases?
4. What is the acceptable per-project cost ceiling for project-level analysis?
5. Should `preserve_meaning` copy policy ever be a default for any project type,
   or does it remain opt-in only?
