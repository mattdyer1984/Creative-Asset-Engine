# Benchmark Review 001 — two disputed fixtures

**Benchmark suite version: v1** (`backend/tests/benchmarks/VERSION`)
**Status: awaiting approval. Neither fixture has been modified.**
**Approval of this review is independent of any implementation work.**

Governed by `docs/BENCHMARK_GOVERNANCE.md` §3. Both discrepancies were found
by inference disagreeing with the annotation, and in both the evidence
supports the inference. Both are recorded as **benchmark discrepancies, not
software failures**.

Both annotations were authored by eye during Package B rather than measured.

---

## Dispute 1 — `case01_weather_tv`, zone bounds

**Field class:** measurable (governance §2) — settled by measurement.

Source image `original.jpg`, 1206 × 1604.

### Pixel measurements

| Zone | Method | Measured | Fixture says | Error |
|---|---|---|---|---|
| `tv-screen` | blue-dominant pixels (`b>90`, `b−r>45`, `b−g>25`) | `[0.192, 0.239, 0.879, 0.559]` | `[0.08, 0.15, 0.92, 0.36]` | y_max off by **0.199** |
| `caption` | near-white rows (min channel > 225), > 150 hits across x 0.10–0.90 | y `0.136 – 0.200` | y `0.090 – 0.150` | off by **0.046** |
| `subtitle` | near-white rows (min channel > 235), lower half | y `0.607 – 0.676` | y `0.360 – 0.460` | off by **0.247** |

Measurement script and raw output: `measurements.json` in this directory,
reproducible with the snippet recorded there.

### What inference said

| Zone | Inferred | Measured | Error |
|---|---|---|---|
| `tv-screen` | `[0.18, 0.23, 0.89, 0.57]` | `[0.192, 0.239, 0.879, 0.559]` | ≤ **0.015** |
| `caption` | y `0.140 – 0.200` | y `0.136 – 0.200` | ≤ **0.004** |
| `bottom-copy` | y `0.600 – 0.730` | y `0.607 – 0.676` | ≤ **0.054** |

The model is accurate to within 1.5% of frame height on every zone. The
fixture is wrong by up to 24.7% — it places the television's lower edge
roughly where the screen is only 40% of the way down, and puts the subtitle
in the middle of the television.

### Proposed correction

```yaml
zones:
  - id: caption
    role: text
    bounds: [0.10, 0.136, 0.90, 0.200]    # was [0.10, 0.09, 0.90, 0.15]
  - id: tv-screen
    role: screen
    bounds: [0.192, 0.239, 0.879, 0.559]  # was [0.08, 0.15, 0.92, 0.36]
  - id: subtitle
    role: text
    bounds: [0.14, 0.607, 0.87, 0.676]    # was [0.10, 0.36, 0.90, 0.46]
  - id: room
    role: negative-space
    bounds: [0.00, 0.70, 1.00, 1.00]      # was [0.00, 0.46, 1.00, 1.00]
```

`room` moves consequentially: it currently starts at 0.46, which is inside
the television.

**Reason:** the annotation does not describe the image. Every other field of
this case (device, roles, relations, text blocks, policies) was reasoned
about rather than eyeballed and is unaffected.

**Evidence image:** `case01_zone_bounds_evidence.png` — measured bounds in
green, current fixture bounds in red, over the source.

---

## Dispute 2 — `case06_meal_prep`, `typography_system.primary_family`

**Field class:** judgement (governance §2) — settled by argument and a second
reader. I am one reader; this review asks you to be the second.

### The evidence

`case06_typeface_evidence.png` is a 3× enlargement of the "british meal prep"
headline, cropped from `[0.14, 0.22, 0.42, 0.32]` of the source.

The type has **no serifs on any glyph**. The terminals on `b`, `r`, `t`, `p`
are cut square; the `a` is double-storey with no bracketed foot; stroke
contrast is near-uniform. It is a **bold oblique sans**, consistent with a
grotesque or neo-grotesque.

| | Value |
|---|---|
| Fixture says | `serif` |
| Inference says | `grotesque` |
| My reading | `grotesque` |

### Proposed correction

```yaml
typography_system:
  primary_family: grotesque    # was: serif
```

**Reason:** `serif` is not a defensible reading of this type. Unlike a
device-class judgement, where two annotators can reasonably differ, the
presence or absence of serifs is close to observable.

**Additional observation, not proposed as a change:** the headline is also
**oblique/italic**, which the fixture does not record at all. I am not
proposing to add it, because italic is expressed per-role in
`typography_system.text_roles`, and this case's `text_roles` were never
populated. Worth noting for whoever revisits this case.

---

## Expected impact on historical scores

Measured by re-scoring the O1 concurrent run against a **copy** of the
fixtures with both corrections applied. The real fixtures were not touched;
`git diff` on `backend/tests/benchmarks` was verified clean afterwards.

| Metric | Current (v1) | With corrections | Change |
|---|---|---|---|
| Zones matched | 24 / 35 | **27 / 35** | +3 |
| Zone roles exact | 21 | 22 | +1 |
| Primary family class | 1 / 4 | **2 / 4** | +1 |
| Device | 8 / 8 | 8 / 8 | — |
| `case01_weather_tv` zones | **1 / 4** | **4 / 4** | +3 |

Every case-1 zone matches once the annotation describes the image.

### Comparability of historical scores

If approved, this becomes **suite v2**, and under governance §6:

1. Phase F and O1 scores stay attached to **v1** and are never restated.
   `docs/phase_f/REPORT.md` and `docs/OPTIMISATION_REPORT.md` remain
   correct as measured.
2. The next real-provider run is reported as `metric @ suite v2`.
3. Because the affected code did not change, the O1 run can be re-scored
   against v2 without spending anything — the table above **is** that
   re-score, and it separates the suite-attributable change from any
   software-attributable change.
4. `CHANGELOG.md` gains a v2 entry recording both corrections, this review
   as the evidence, the approver, and the impact table above.

**Fields not in the table are unaffected**, so every v1 score for text mode,
ownership, copy policy, overlay policy and capability level remains directly
comparable to v2.

---

## What is being asked

| Decision | Options |
|---|---|
| Dispute 1 — case 1 zone bounds | approve / reject / amend |
| Dispute 2 — case 6 primary family | approve / reject / amend |

They can be decided independently. Until both are decided the suite stays at
v1 and the fixtures stay exactly as they are.

If either is rejected, governance §3 step 6 applies: the disagreement is
recorded in that case's `notes` so it is not re-litigated, and the scorer
keeps reporting it as a disagreement.
