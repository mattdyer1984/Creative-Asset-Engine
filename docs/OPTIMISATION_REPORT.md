# Optimisation phase report (O1–O5)

**Branch** `v2-creative-intelligence-engine` · **Suite** v1 ·
All numbers measured against the real provider unless marked otherwise.

Four commits: `6a391bf` (O1), `98825d8` (O2), `c312064` (O3), and this one
(O4/O5). 1135 tests passing. No architectural change was made; every change
below was forced by a measurement.

---

## 1. Latency: before and after (O1)

Stages now declare `depends_on` and the schedule is derived from the graph:

```
[ocr, product_isolation, scene_intelligence, composition_contract]
  -> [product_lock_profile, creative_fingerprint, narrative_structure]
  -> [creative_profile, marketing_analysis]
  -> [text_ownership, creative_specification]
```

| Case | Sequential | Concurrent | Change |
|---|---|---|---|
| case01_weather_tv | 91.8 s | 54.0 s | **−41.2%** |
| case02_books | 80.5 s | 79.2 s | −1.6% |
| case03_mini_ac | 48.8 s | 30.3 s | −37.9% |
| case04_posture | 69.5 s | 52.6 s | −24.3% |
| case05_ten_out_of_ten | 67.2 s | 59.9 s | −10.9% |
| case06_meal_prep | 67.0 s | 41.1 s | −38.6% |
| case07_gut_health | 70.0 s | 33.2 s | **−52.5%** |
| case08_fan_shelf | 74.0 s | 62.9 s | −15.0% |
| **mean** | **71.1 s** | **51.7 s** | **−27.3%** |

**The Phase F projection of ~52% was wrong, and the reason is the finding.**
It assumed per-stage latency was independent of scheduling. It is not:

| Stage | Sequential | Concurrent | Change |
|---|---|---|---|
| ocr | 11.7 s | 15.1 s | **+29.4%** |
| scene_intelligence | 13.6 s | 18.8 s | **+38.0%** |
| composition_contract | 18.8 s | 21.7 s | **+15.4%** |
| creative_fingerprint | 10.0 s | 10.1 s | +1.5% |
| creative_profile | 15.9 s | 15.5 s | −2.2% |

The three stages now issued **simultaneously** each got ~26% slower; the ones
that remained effectively serial did not move. The provider queues concurrent
requests. **Concurrency buys roughly half what serial timings predict**, and
that ratio — not the theoretical one — is what to plan with.

Variance across cases is wide (−1.6% to −52.5%) because it depends on how
balanced a case's wave-1 stages are.

## 2. Cost comparison

| | Sequential | Concurrent |
|---|---|---|
| Known cost subtotal | $1.0840 | $1.1538 (+6.4%) |
| Provider calls | 52 | 52 |
| Unpriced calls | 8 | 8 |

Call count is identical, so concurrency itself costs nothing. The +6.4% is
token variance between runs — the model returns different completion lengths
each time. **Overall cost remains incomplete**: `gemini-pro-latest`
(Creative Fingerprint) and the image model still have no configured rate.

## 3. Determinism and failure rate

| | Sequential | Concurrent |
|---|---|---|
| Pipelines succeeded | 8/8 | 8/8 |
| Stage-level failures | 0 | 0 |
| Device | 8/8 | 8/8 |
| Text mode | 8/8 | 8/8 |
| Zone roles | 20/22 | 21/24 |
| Typography fields | 10 | 10 |
| Ownership | 30/34 | 29/34 |

Accuracy is preserved within provider noise. The one ownership difference is
a single OCR block that came back differently — the provider is not
deterministic, and the same variation appears between two sequential runs.

**Scheduling determinism is guaranteed structurally**, which is the part we
control: waves are computed from declared dependencies, declaration order is
preserved within a wave, and 11 tests assert the schedule is stable and never
places a stage before its dependency.

Three correctness details the tests would not have caught by accident:

- **Worker threads must never touch an ORM object owned by another session.**
  Reading `slideshow.id` inside the thread triggered a cross-thread lazy
  refresh and surfaced as `ObjectDeletedError` far from its cause.
- **A dependency absent from a run is already satisfied**, not an error —
  otherwise every single-stage rerun breaks.
- **A wave cannot stop at the first failure**, so it runs to completion and
  reports the earliest-*declared* failure, keeping the reported failure
  stable regardless of thread finish order.

Rollback is `CAE_SEQUENTIAL_STAGES=1`; the full suite passes under both.

## 4. Typography inference (O2)

Categorised before changing anything, as instructed. The cause was **neither
prompt ambiguity, benchmark ambiguity nor a provider limitation** — it was an
internal contradiction:

| Field | Our prompt says | Our validator accepted |
|---|---|---|
| weight | light/regular/medium/bold/**black** | regular, bold |
| case | as-written/upper/lower/**title** | as-written, upper, lower |
| alignment | left/**center**/right | left, **centre**, right |

The model complied with the prompt and every compliant role was silently
dropped. `center` versus `centre` alone discarded entire roles.

**Three of four designed cases were producing a typography system with zero
text roles** — a system that cannot render anything. The family-class
mismatch had masked it entirely.

The renderer genuinely has only regular and bold faces, so the domain
vocabulary was right and the boundary was wrong. `TextRole` now normalises
(black→bold, light/medium→regular, center→centre, title→as-written, since
re-casing would change the words and copy policy is `preserve_verbatim`).
Genuine nonsense is still refused.

| Case | Roles before | Roles after |
|---|---|---|
| case04_posture | 5 | 5 |
| case05_ten_out_of_ten | **0** | 2 |
| case06_meal_prep | **0** | 2 |
| case07_gut_health | **0** | 5 |
| **total** | **5** | **14** |

A regression test asserts every value the prompt offers survives validation,
so prompt and schema cannot drift apart again.

**Primary family class is unchanged at 1/4** — a separate, harder problem.
And at least one of the four is not the model's error: case 6's type is
unmistakably a bold sans, the fixture says `serif`, the model said
`grotesque`. Not changed; see §6.

## 5. Confidence calibration (O3)

Confidence was `winner / (winner + loser)`. Signals fire on only one side in
almost every real block, so the loser was 0 and the value was **exactly 1.0**
— 76 of 79 decisions. It answered *"did anything contradict this?"*, not
*"how sure are we?"*.

It is now `agreement × strength`: the winner's share of fired signal weight,
times a saturating term for how much evidence fired at all.

| Band | Before | After |
|---|---|---|
| high | n=45, acc 0.978 | n=19, acc 0.947 |
| medium | **n=0** | n=10, acc 0.900 |
| low | n=2, acc 1.0 | n=2, acc 1.0 |

**Confidence now discriminates as a measure — but it still does not predict
correctness, and that result is worth keeping.** Low-evidence blocks are
rescued by the project text mode, which is itself 0.917 accurate. Correctness
on weak blocks comes from the *project prior*, not from block evidence.

So the honest answer to "should confidence become probabilistic?" is: **not
yet, and not for this purpose.** The useful job for confidence in this
architecture is deciding *whether to consult the project prior* — which is
exactly what the auto-override band does, and it only works now that the
number means something. A probabilistic reformulation would need a
correctness signal to fit against, and the benchmark currently supplies 31
matched blocks — far too few.

Two consequences, both measured:

- Re-scaling invalidated thresholds tuned against saturating values.
  `AUTO_OVERRIDE` moved 0.80 → 0.65, derived from the signal table rather
  than chosen: just below one strong signal, so an unambiguous `#fyp` still
  overrules the project default.
- One predicate was answering three questions. Separated into
  `spoke_for_itself` / `convincing` / `contested`. The first attempt sent
  case 4's headline and case 6's comparison labels — the core designed
  typography of the benchmark — to human review, and routed an unambiguous
  caption to the typography renderer. Both are now correct by construction.

Ownership on the real runs: **29 exact, 2 wrong, 0 needlessly reviewed.**

## 6. Benchmark governance (O5) and the two open fixtures

`docs/BENCHMARK_GOVERNANCE.md` is in force. The suite now carries a `VERSION`
(v1) and a `CHANGELOG.md`, and two tests enforce that a version exists and is
covered by a changelog entry.

The core rule: **a fixture may never be edited to make a score improve.** A
change that would raise a score is grounds for more scrutiny, not less. The
document distinguishes *measurable* fields (settled by measurement) from
*judgement* fields (settled by argument and a second reader), and requires a
scorer change to be committed separately from the code it scores.

**Two fixtures are awaiting your sign-off. Neither has been changed.**

| Case | Field | Fixture says | Evidence |
|---|---|---|---|
| case01_weather_tv | zone bounds | screen `y 0.15–0.36` | Measured `y 0.239–0.559`; inference said `0.23–0.57`, accurate to ~0.015 |
| case06_meal_prep | primary family | `serif` | The type is plainly a bold sans; inference said `grotesque` |

Both were authored by eye during Package B. Both changes would improve
scores, which is exactly why they need your decision rather than mine.

## 7. Product path (O4)

`docs/PRODUCT_BENCHMARK_PROPOSAL.md`. **No fixture modified.**

Four of the eight existing cases already contain a real product, so the
smallest extension is one optional `product` block per case — measured
appearance bounds, expected Lock Profile fields, and reference crops taken
from the existing image rather than new photography. That exercises Product
Isolation, Product Lock, reference conditioning and generation planning
without inventing anything.

Multi-angle character continuity is deliberately left out: it needs new
imagery and a different kind of annotation, and should be its own decision.

---

## 8. Recommendations for production enablement

Ranked by measured benefit.

| # | Recommendation | Evidence | Status |
|---|---|---|---|
| **P1** | **Sign off or reject the two open fixtures** | measured; blocks meaningful zone and typography scores | needs you |
| **P2** | **Approve the product benchmark extension** | 3 stages and all generation unvalidated | needs you |
| **P3** | **Price `gemini-pro-latest` and the image model** | 8 unpriced calls per run; generation entirely unpriced, so no cost gate is possible | needs official pricing |
| **P4** | **Fix `duration_ms` for concurrent stages** | 4 stages report 2–11 ms for 14–26 s of work | ready to do |
| **P5** | **Vendor open-licence fonts** | rendering is macOS-only; benchmark scores are not comparable across machines | ready to do |
| **P6** | **Put a small real-provider run in release validation** | two 100%-failure defects were invisible to 1000+ mocked tests | ready to do |
| P7 | Investigate primary family class (1/4) | the remaining typography gap, once P1 settles how much of it is real | after P1 |
| P8 | Merge scene_intelligence and composition_contract | $0.092/case, same image, both segment; now also the two slowest stages | needs proving |
| P9 | Content-hash cache for analysis | every re-run re-pays $0.115 | ready to do |

**P6 is the one I would not skip.** Phase F's two structured-output defects
failed four of eight cases at 100% against the real provider while the entire
mocked suite passed. A handful of real cases in release validation is the
only thing that catches that class.

### What blocks production today

1. **Fonts are macOS-only** (P5). Rendering fails loudly on Linux, by design.
2. **Cost cannot be capped** while the image model is unpriced (P3) — the
   spend cap is disabled precisely because enabling it would refuse most work.
3. **Generation is unvalidated** (P2).

None is architectural. All three are known, bounded, and named above.
