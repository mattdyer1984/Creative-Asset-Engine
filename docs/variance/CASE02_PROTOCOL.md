# Case 2 variance study — protocol

**Written and committed BEFORE any candidate was generated.** The acceptance
criteria below are pre-registered so they cannot be adjusted to suit the
results.

---

## 1. Question

For one creative, held completely fixed, how often does the pipeline produce
a usable ad?

Every improvement in this project has been judged on one or two images. At
the variance already observed informally, a single image cannot distinguish a
real gain from a lucky sample. This measures the distribution instead.

---

## 2. Frozen configuration

**Commit: `482862fa00451d75c92cffc98d04bf124991c2a3`** — working tree clean.
No code or fixture may change while candidates are generated.

| Parameter | Value | How it is held |
|---|---|---|
| Provider | `nano_banana` | routing config, `providers.yaml` |
| Model | `gemini-3.1-flash-image-preview` | high-quality tier, pinned by the harness, asserted per call |
| Tier | `HIGH_QUALITY` | resolved once, reused; no per-candidate routing |
| Compiled prompt | one string, SHA-256 recorded | compiled once, byte-identical for all 8 calls, asserted |
| References | 8 image paths, SHA-256 each | resolved once, reused |
| Benchmark suite | v4 | `backend/tests/benchmarks/VERSION` |
| Aspect ratio | `3:4` | `GenerationRequest.aspect_ratio` |
| Candidate dimensions | provider default for 3:4 | not settable |
| Retry policy | max 3 attempts, transient only, 2.0 s exponential backoff | `failover.DEFAULT_*`, recorded per candidate |
| Quality escalation | **DISABLED** | `high_quality=None` — the model is already the top tier |
| GPT Image fallback | **DISABLED** | `fallback=None` |
| Analysis stages | run **once**, reused | so candidates differ only by generation |

### Parameters that CANNOT be frozen, stated rather than glossed

- **Seed — not supported.** `nano_banana_adapter` calls
  `client.models.generate_content` with only `response_modalities=["IMAGE"]`
  and `image_config=ImageConfig(aspect_ratio=...)`. The SDK surface exposes
  no seed for this model, so sampling is unseeded and irreducible run-to-run
  variation is expected. This is the honest ceiling on reproducibility here.
- **Temperature / top-p — not sent.** Provider defaults apply and are not
  pinned or visible.
- **Safety settings — not sent.** Provider defaults apply.

**Scope.** This measures **generation** variance with analysis held fixed.
Analysis variance is real and separate — successive runs produced materially
different Creative Specifications from the same source — and is NOT measured
here. The true end-to-end variance is therefore at least this wide.

---

## 3. Method

1. Run the pipeline once through Creative Specification. Freeze the result.
2. Compile the generation request once. Record its SHA-256.
3. Make **8 independent provider calls** with that identical request.
4. One candidate per recorded provider call. No prompt mutation between
   calls. No regeneration of a disliked candidate. Every call that reaches
   the provider is reported, including failures.

---

## 4. Acceptance criteria (pre-registered)

Assessed per candidate against the source creative and the five canonical
references.

### 4.1 Per-book checks (×5: Atomic Habits, The Psychology of Money, The Let Them Theory, Don't Believe Everything You Think, The Courage to be Disliked)

| Check | Pass condition |
|---|---|
| **Present** | the book appears exactly once |
| **Edition** | dominant cover colour and key design element match the canonical reference (e.g. Let Them Theory green with yellow speckle; Courage white with red/black brush enso) |
| **Title** | title text legible and correct, no missing or substituted words |
| **Author** | author name legible and correct |

### 4.2 Whole-image checks

| Check | Pass condition |
|---|---|
| **No missing books** | all five present |
| **No duplicates** | no book appears twice |
| **Promotional text** | the main overlay reads as the source caption, correctly spelled, no invented additional copy |
| **CTA placement** | a pointer affordance exists AND sits in the bottom-left band (vertical centre ≥ 0.75, starts at x ≤ 0.35) |
| **Geometry** | no book substantially occluded by another; no cover cropped so title or author is lost |

### 4.3 Classification

Applied in order; first match wins.

- **ship-ready** — every check in 4.1 and 4.2 passes. Could be posted as-is.
- **repairable** — all five books present, correct editions, no duplicates,
  titles and authors correct; but fails on promotional-text detail, CTA
  placement, or geometry. Fixable by re-running typography/compositing or a
  targeted edit, without regenerating the scene.
- **reject** — any of: a missing book, a duplicate, a wrong edition, a wrong
  or illegible title or author. The product identity is wrong, and nothing
  short of regeneration fixes it.

**Rationale for the boundary.** Product identity is the one thing this system
exists to preserve; getting it wrong is not repairable by post-processing.
Text placement and layout are downstream concerns the codebase already has
machinery for, so they degrade a candidate rather than disqualify it.

---

## 5. Reported metrics

Distribution across all 8, plus: ship-ready / repairable / reject rates;
failure frequency by category; latency distribution (min, median, max);
model and provider actually used per call; retry count per call; estimated
cost or explicit unknown; and estimated cost per ship-ready output.

**No system change will be made on the evidence of any single candidate.**
