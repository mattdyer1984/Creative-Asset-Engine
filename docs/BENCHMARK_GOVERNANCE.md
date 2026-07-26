# Benchmark governance

**Status: in force from 2026-07-26.** Applies to everything under
`backend/tests/benchmarks/`.

The benchmark suite is the reference specification for the Creative
Intelligence Engine. It behaves like a compiler test suite, not like
development data: **the software moves, the benchmarks do not.**

This document exists because the rule has already been tested twice. Phase F
found `case01_weather_tv`'s zone bounds provably wrong, and O2 found
`case06_meal_prep`'s primary family annotated `serif` for type that is
plainly a bold sans. Both were authored by eye during Package B. Neither was
changed. That is the behaviour this document makes routine rather than
heroic.

---

## 1. The standing rule

> A fixture may never be edited to make a score improve.

If a change would raise a score, that is grounds for **more** scrutiny, not
less. The question is never "does this help?" but "was the annotation wrong?"

A score that disagrees with reality is information. Editing the fixture
destroys the information and leaves the defect.

---

## 2. What may change, and on what evidence

| Change | Evidence required | Who decides |
|---|---|---|
| **Adding a new case** | The pair is a genuine human recreation; annotation follows `schema.yaml`; no existing case's score is affected | Author, with review |
| **Correcting measurable geometry** (zone bounds) | Pixel measurement from the source image, reproducible by a script committed alongside | Owner sign-off |
| **Correcting a judgement field** (device, family class, role, intent) | Written argument plus the image; a second reviewer independently reaching the same reading | Owner sign-off |
| **Adding a field to the schema** | A case that cannot be expressed without it | Author, with review |
| **Widening a closed vocabulary** | A case that needs the new term, cited by name | Owner sign-off |
| **Changing `expected_handling_mechanism`** | An ADR decision that changed the routing rule | Owner sign-off, ADR updated first |
| **Relaxing an expectation because inference disagrees** | **Never permitted** | — |

"Owner sign-off" means the person who owns the product decides, not the
person who wrote the code that disagreed with the fixture.

### Measurable versus judgement fields

The distinction matters because the evidence bar differs.

- **Measurable** — zone bounds, text content, colours present, image
  dimensions. These have a right answer recoverable from the pixels. A
  disagreement is settled by measurement, and whoever is wrong is wrong.
- **Judgement** — device, family class, capability level, creative intent,
  production value strategy. Two competent annotators may differ. A
  disagreement here is settled by argument and a second reader, and the
  outcome may legitimately be "the fixture is defensible and so is the
  model", recorded as `acceptable` in the scorer rather than changed.

---

## 3. Procedure for a suspected wrong annotation

1. **Stop.** Do not edit the fixture, and do not change the code to match it
   either.
2. **Measure or argue.** For a measurable field, write the measurement as a
   script and commit its output. For a judgement field, state the reading and
   why, with the image.
3. **Report it** with the evidence, naming the case, the field, the current
   value, the proposed value, and what the change would do to scores.
4. **Wait for sign-off.**
5. **If approved**: change the fixture, bump `suite_version` (§5), record the
   change in `CHANGELOG.md` under the new version, and re-run the full suite
   so the new baseline is captured.
6. **If declined**: record the disagreement in the case's `notes` so the next
   person does not re-litigate it.

The two open cases (case 1 bounds, case 6 family) are at step 4.

---

## 4. What the suite is allowed to be used for

**Permitted**: measuring inference accuracy; regression-checking a change;
deciding what to improve next; adjudicating whether a defect is real.

**Not permitted**: tuning a threshold until a case passes; selecting the
subset of cases that a change improves; reporting a score computed with a
scorer changed in the same commit as the code it scores.

That last one is procedural and easy to violate by accident. The Phase F
scorer lives in `scripts/phase_f/` deliberately apart from the pipeline, and
a change to the scorer must be committed and justified **separately** from a
change to the thing it measures.

---

## 5. Versioning

`backend/tests/benchmarks/VERSION` holds a single integer, the suite version.

- **Bump it** whenever any `ground_truth.yaml`, any source image, or
  `schema.yaml` changes.
- **Do not bump it** for changes to `README.md`, this document, or the
  scorer.

Every recorded score must carry the suite version it was measured against.
A score without one is not comparable to anything.

`CHANGELOG.md` in the same directory records, per version: what changed,
which cases, the evidence, who approved it, and the measured effect on
scores.

---

## 6. Keeping historical scores comparable

Scores are comparable only within a suite version. Across a version bump:

1. **Re-run the previous code against the new suite** where practical, so the
   change attributable to the suite is separated from the change attributable
   to the software. Record both numbers.
2. **Never restate a historical score** under a new suite version. Phase F's
   numbers are Phase F's numbers, measured against suite v1, and they stay
   that way.
3. **Report scores as `metric @ suite vN`** — for example `device 7/8 @ v1`.

Where a re-run is impractical (a paid run against a provider that has since
changed), say so and mark the comparison as indicative rather than measured.

---

## 7. Provider non-determinism

The provider is not deterministic. Two runs of identical code against an
identical suite differ — Phase F and O1 differed by one OCR block on the same
inputs.

Therefore:

- **A single run is a sample, not a measurement.** Treat a difference of one
  or two blocks as noise unless it repeats.
- **A regression is a change that repeats across runs**, or a change to a
  deterministic stage. `text_ownership` makes no provider call, so any change
  in its output is a real change in the software.
- Where a number is decision-relevant, run it more than once and say how many
  times.

---

## 8. What is deliberately not governed

The **scorer** is not a governed asset. It is expected to improve, and
improving it is not tampering — provided a scorer change is committed
separately from the code it scores, and the reason is written down. Phase F's
scorer was corrected twice mid-analysis (`None == None` was scoring as
missing; a decomposition rule was added) and both are recorded in its module
docstring.

The distinction: the fixtures say what the right answer is, and are governed.
The scorer says how close we got, and is engineering.
