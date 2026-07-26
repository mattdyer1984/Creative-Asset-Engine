# Phase F — Real Provider Validation

**Branch** `v2-creative-intelligence-engine` · **Head** `49ab6e5` ·
Run `docs/phase_f/run.json` · Scores `analysis_scores.json` ·
Metrics `metrics.json`

Eight benchmark cases, real providers, an isolated database. Measurement
first; the only code changed was what the run proved broken.

---

## 0. What happened, in one paragraph

The first two attempts failed four of eight cases at 100%. Both causes were
schema defects that **no unit test could ever have caught**, because a fake
provider does not validate the schema it is handed. Once fixed, all eight
cases completed. Inference then turned out to be strong where it is
structural — device 7/8 exact, text mode 8/8, ownership 30/34 — and weak
where it is aesthetic: typography families 1/4. Confidence was found to be
nearly constant and therefore uninformative. And the benchmark suite itself
was found to contain at least one provably wrong fixture, which I have **not**
changed — see §8.

---

## 1. Benchmark validation report (F1)

| Attempt | Result | Cause |
|---|---|---|
| 1 | 4/8 failed | `required` omitted 5 of 9 properties in the typography schema |
| 2 | 4/8 failed | strict mode cannot express open-ended maps; the schema used three |
| **3** | **8/8 succeeded** | — |

Both defects are now caught without a provider by
`backend/tests/test_response_schemas.py`, which validates every schema this
codebase sends, structurally, for both rules.

### Per case

| Case | Result | Wall | Device inferred | Zones | Ownership decisions |
|---|---|---|---|---|---|
| case01_weather_tv | ok | 91.8 s | screen-in-scene | 4 | 18 |
| case02_books | ok | 80.5 s | scene-with-caption | 9 | 23 |
| case03_mini_ac | ok | 48.8 s | scene-with-caption | 3 | 3 |
| case04_posture | ok | 69.5 s | diagram-with-callout | 12 | 5 |
| case05_ten_out_of_ten | ok | 67.2 s | grid-collage | 8 | 2 |
| case06_meal_prep | ok | 67.0 s | side-by-side-comparison | 8 | 3 |
| case07_gut_health | ok | 70.0 s | split-comparison | 9 | 5 |
| case08_fan_shelf | ok | 74.0 s | shelf-snapshot | 7 | 15 |

**Scope excluded, deliberately.** The three product stages
(`product_isolation`, `product_lock_profile`, `creative_specification`) were
not run: `product_isolation` hard-fails with *"No product assigned to any
slide"*, and the benchmark fixtures declare no product. Inventing one would
have meant fabricating input the annotation never described. **This is a real
gap in what the benchmark suite can exercise** — the entire product path is
unvalidated — and it is recommendation R4.

---

## 2. Analysis accuracy report (F2)

| Field | Exact | Acceptable | Disagreement / missing |
|---|---|---|---|
| Composition device | **7** | 1 | 0 |
| Zone roles (matched zones) | **20** | 1 | 1 |
| Primary text mode | **8** | 0 | 0 |
| Copy policy | **8** | 0 | 0 |
| Overlay policy | **8** | 0 | 0 |
| Production value strategy | 6 | 0 | 2 |
| Text ownership (per block) | **30** | 0 | 4 |
| Typography fields | 10 | 0 | 6 |
| Creative Intent | — | — | **not implemented** |

`acceptable` is granted only by a written rule recorded in the output, so
every one can be argued with. The single acceptable device is case 2, where
the model said `scene-with-caption` and the annotation says `product-hero` —
books photographed on a bed with copy over them are defensibly both.

### What is strong

**Text mode: 8/8, and the split is exactly right** — four designed, four
caption, matching the benchmark's own division. This is the deterministic
path (OCR blocks + source style), and it cost nothing.

**Device: 7/8 exact.** The vision model reads compositional device reliably.

**Ownership: 30/34 exact, 0 disagreements from ownership logic itself.** Of
the four that were not exact, three are OCR granularity and one is a
downstream effect of a typography error (§6).

### What is weak

**Typography: 1/4 exact on primary family class.** The model called case 5
`grotesque` (truth: condensed-sans), case 6 `grotesque` (truth: serif), case 7
`condensed-sans` (truth: grotesque). Capability level was right 3/4. This is
the weakest measured area and is recommendation R1.

**Creative Intent has no inference at all.** Nothing maps to the closed
vocabulary; the Creative Fingerprint records a free-text "marketing angle"
and nothing consumes it. Recorded as `not_implemented` rather than scored
zero — "we tried and failed" and "nothing infers this" are different facts.

**Production value 6/8** — but this is not really inference: the profile
returns the `refine` default because no stage infers it. Two cases whose
benchmark says `elevate` are therefore wrong by construction.

---

## 3. Provider cost report (F3)

**Known cost subtotal: $1.0840 for eight cases. Overall cost: incomplete —
8 calls have no configured rate.**

Mean **$0.1355** per case (known portion), worst $0.1682, best $0.0877.

| Stage | Calls | Known $ | $/case | Prompt tok | Completion tok |
|---|---|---|---|---|---|
| composition_contract | 8 | 0.4065 | 0.0508 | 23,628 | 9,611 |
| scene_intelligence | 8 | 0.3298 | 0.0412 | 19,932 | 7,673 |
| creative_profile | 4 | 0.1609 | 0.0201 | 9,358 | 3,803 |
| marketing_analysis | 8 | 0.0901 | 0.0113 | 4,571 | 2,240 |
| ocr | 8 | 0.0628 | 0.0079 | 10,184 | 6,343 |
| narrative_structure | 8 | 0.0339 | 0.0042 | 2,193 | 763 |
| **creative_fingerprint** | 8 | **unpriced** | — | 10,303 | 3,603 |
| **text_ownership** | **0** | **0.0000** | **0.0000** | 0 | 0 |

Two findings worth acting on:

1. **`composition_contract` is now the single most expensive stage**, at 37%
   of known cost. It is also the newest.
2. **`creative_fingerprint` is entirely unpriced.** It runs on
   `gemini/gemini-pro-latest`, which has no rate in `pricing.yaml`, so eight
   real calls are invisible to cost reporting. Image generation is unpriced
   for the same reason. Per the standing rule I have not inferred either rate
   from unofficial sources.
3. **`text_ownership` costs nothing and is the stage carrying the most
   architectural weight** — the whole ownership model runs for $0.

### Cache opportunities (measured, not speculated)

- `scene_intelligence` and `composition_contract` both send the same image
  and both segment it into regions, for $0.092/case combined. They are
  plausibly one call. **Not yet proven** — recommendation R2.
- Re-running analysis re-pays everything; nothing is keyed by image content
  hash. A content-addressed cache would make repeat runs free.

---

## 4. Latency report (F4)

**Mean end-to-end 71.1 s per single-slide case** (min 48.8 s, max 91.8 s).
**Provider wait is 99.8% of wall-clock time.** Our own deterministic CPU
across all eight cases totals **37 ms**.

| Stage | Mean | Max | Share of case | `duration_ms` valid? |
|---|---|---|---|---|
| composition_contract | 18.8 s | 26.0 s | 26.5% | **no** |
| scene_intelligence | 13.6 s | 25.8 s | 19.2% | **no** |
| ocr | 11.7 s | 23.8 s | 16.5% | **no** |
| creative_fingerprint | 10.0 s | 21.0 s | 14.0% | **no** |
| creative_profile | 7.9 s | 22.2 s | 11.2% | yes |
| marketing_analysis | 6.3 s | 8.6 s | 8.9% | yes |
| narrative_structure | 2.6 s | 4.2 s | 3.7% | yes |
| text_ownership | 0.0 s | 0.0 s | 0.0% | yes |

### An instrumentation defect this run exposed

Four stages open their `AnalysisRun` **after** their concurrent provider work
has completed. `duration_ms` therefore records 2–11 ms of bookkeeping against
14–26 seconds of real work, and `AnalysisRun`'s own documented derivation —
`duration_ms - provider_call_ms` = overhead — is **deeply negative and
meaningless** for exactly the four most expensive stages. The naive figure
was −432,763 ms of "our CPU". The report uses `provider_call_ms`, which is
measured correctly, and states the limitation. This is recommendation R3.

### Parallelisation opportunity

The seven provider stages are strictly sequential but only two orderings are
real: `creative_profile` needs OCR, and `text_ownership` needs the contract
and the profile. `ocr`, `creative_fingerprint`, `scene_intelligence`,
`composition_contract` and `marketing_analysis` have no dependency on one
another. Running them concurrently would take a case from ~71 s to roughly
the slowest of them plus the dependent tail — on these measurements about
**26 s + 8 s + 0 s ≈ 34 s, a 52% reduction**. Recommendation R2.

---

## 5. Confidence calibration report (F5)

| Band | n | Accuracy |
|---|---|---|
| high (≥0.80) | 45 | 0.978 |
| medium (0.55–0.79) | **0** | — |
| low (<0.55) | 2 | 1.000 |

**Confidence is not calibrated. It is nearly constant.**

- 45 of 47 decisions sit in the high band; the medium band is **empty**.
- The two low-confidence decisions were both **correct**, so low confidence
  did not predict disagreement either.
- Accuracy is essentially identical across the bands that have data.

The conclusion is not that the system is 97.8% accurate. It is that
**confidence currently carries almost no information**: it is close to a
constant 1.0, and a constant cannot discriminate. Every ownership decision
whose classifier signals fire at all reports 1.0, because the classifier
returns a normalised share rather than a calibrated probability.

This is precisely why `validation_status` was added as a separate concept —
see §7. Recommendation R5.

---

## 6. Failure catalogue (F6)

| Class | Count |
|---|---|
| composition_ambiguity | 13 |
| typography_mismatch | 6 |
| ocr_failure | 2 |
| ownership_ambiguity | 1 |
| provider_hallucination | 0 |
| generation_failure | not exercised |
| cleanup_failure | not exercised |
| validation_failure | 0 (final run) |

Classification is by **cause**, not by the stage that surfaced it.

**ocr_failure (2)** — case 1's weather-map place names and temperature grid
were never reported by OCR, so nothing could own them. The benchmark expects
them as `environmental`. Not an ownership defect.

**ownership_ambiguity (1)** — case 2's `👇👇👇` emoji row. OCR did not return
it as a block.

**typography_mismatch (6)** — three wrong primary families, one wrong
secondary, one wrong capability level, and **one ownership error caused by
it**: case 5's `10/10 man` was routed to the typography renderer because the
inferred capability was L1 while the benchmark says L2. The capability gate
built in Package E4 is correct; it never fired because its input was wrong.
This is the clearest causal chain in the run.

**composition_ambiguity (13)** — all zone-matching misses. These have **three
different causes** and the count should not be read as thirteen model errors:

1. **Scorer strictness.** Case 7's `headline` was decomposed by the model
   into three text strips plus two rules — better than the annotation — but
   thin strips never cover 50% of a tall box by area, so the decomposition
   rule did not fire.
2. **Genuine model misses.** Case 3's top caption was not found at all.
3. **Benchmark annotation error.** See §8.

---

## 7. Validation status

Every major inferred artifact now exposes **both** `confidence` and
`validation_status`, persisted (migration `b392e2c34de2`, round-tripped:
496/400/382 ms, integrity ok, row counts identical).

    validated            every applicable check passed
    partially_validated  usable, but something was dropped or unproven
    needs_review         a human must look before this is relied on
    failed               a check failed outright

Worst-check-wins; every finding is kept, not just the worst; and
`checks_applied` is recorded so `validated` can never mean *nothing was
checked*. 16 tests, including one that asserts the distinction directly: a
decision with confidence 1.0 that is routed to review is `needs_review`.

---

## 8. A benchmark fixture is wrong — I have not changed it

`case01_weather_tv`'s zone bounds are **provably incorrect**, and the model
was right. Measured directly from the pixels of `original.jpg` (1206×1604):

| Region | Measured | Benchmark says | Model said |
|---|---|---|---|
| TV screen | x 0.194–0.878, y **0.239–0.559** | [0.08, 0.15, 0.92, **0.36**] | [0.18, 0.23, 0.89, **0.57**] |
| Caption plate | y **0.136–0.200** | y 0.090–0.150 | y 0.140–0.200 |

The screen was detected by isolating strongly blue pixels; the caption plate
by finding the near-white band. The model is accurate to ~0.015. **My
annotation is wrong by up to 0.20** — it claims the television ends where it
is in fact only 40% of the way down.

These bounds were authored by me during Package B by eye, not measured. Three
of case 1's four zones therefore scored as misses against an annotation that
does not describe the image.

**Per your instruction I have stopped rather than changed it.** The suite is
authoritative and I will not edit a fixture to improve a score — but this one
is not a judgement call, it is a measurement error, and leaving it means
every future run is scored against a wrong answer.

What I recommend, for your decision:

1. **Re-measure the zone bounds of all eight fixtures programmatically**
   (edge/colour detection plus manual review), and record in each fixture
   that bounds are measured rather than estimated.
2. Leave every other field untouched — roles, devices, relations, text
   blocks, policies were reasoned about, not eyeballed, and nothing in this
   run casts doubt on them.
3. Re-run F2 afterwards so the zone numbers mean something.

I have not touched any fixture. Attempt-1 and attempt-2 run records are kept
alongside the final one as evidence of the schema failures.

---

## 9. Recommendations, ranked by measured benefit

| # | Recommendation | Evidence | Est. benefit |
|---|---|---|---|
| **R1** | **Fix typography family inference** | 1/4 exact; caused the only true ownership error | Largest accuracy gain available |
| **R2** | **Run the five independent stages concurrently** | provider wait is 99.8% of 71 s; 5 of 7 stages have no interdependency | ~52% latency cut, no cost change |
| **R3** | **Fix `duration_ms` for concurrently-executed stages** | 4 stages report 2–11 ms for 14–26 s of work | Makes per-stage latency measurable at all |
| **R4** | **Give the benchmark suite a product path** | 3 stages, and all generation, are unvalidated | Removes the largest blind spot |
| **R5** | **Make confidence calibrated or stop publishing it** | 45/47 in one band, empty medium band | Confidence becomes usable for routing |
| **R6** | **Adjudicate the fixture bounds (§8)** | measured, definitive for case 1 | Zone scores become meaningful |
| **R7** | **Price `gemini-pro-latest` and the image model** | 8 unpriced calls per run; image gen entirely unpriced | Cost reporting becomes complete |
| **R8** | **Merge scene_intelligence and composition_contract** | $0.092/case, same image, both segment | ~30% cost cut — needs proving first |
| R9 | Infer Creative Intent and Production Value | neither is inferred; 2/8 wrong by construction | Removes two known-wrong fields |
| R10 | Content-hash cache for analysis | every re-run re-pays $0.1355 | Free repeat runs |

R1 and R2 are the two that matter: one is the largest accuracy gap, the other
is a halving of latency for no money. Neither requires an architectural
change.

---

## 10. What this phase did not do

- **No generation.** Image generation, cleanup and validation were not
  exercised, so `generation_failure` and `cleanup_failure` have no data.
  Blocked by the same missing product path as §1.
- **No optimisation.** Nothing was tuned. The only code changed was the two
  schema defects that made the run impossible, plus `validation_status`,
  which you asked for.
- **No fixture changes.** See §8.
- **One run per case.** Variance across repeat runs is unmeasured, so every
  figure here is a single sample.
