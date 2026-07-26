# Where this project actually is

Written 2026-07-26, after the Case 2 generation work. Deliberately blunt.
Nothing here is a status report designed to look good.

---

## 1. What the project is for

Take a TikTok slideshow ad that already works, and produce a **new** image
that sells the same product with the same marketing strategy — without being
a copy of the original.

Three constraints make this hard, and all three are real:

1. **Product identity must survive.** A book bundle ad has to show *those*
   five books, with the right covers. Getting "a book" is a failure.
2. **The marketing strategy must survive.** The hook, the offer, the reason
   it works. Not just the pixels.
3. **The image itself must be new.** If it were a copy, you would not need
   any of this — you would need a file copy.

The output is judged by whether it would work as an ad on TikTok, which is a
higher bar than whether it looks like the original.

---

## 2. What genuinely works

These are load-bearing and validated against real providers, not mocks.

| Capability | State |
|---|---|
| **Creative analysis** — OCR, scene, fingerprint, marketing, narrative, composition contract | Works. Runs concurrently, −27% wall clock, no accuracy change. |
| **Text ownership** — deciding who draws each text block (image / typography / caption) | Works. This was the biggest architectural win of the project. |
| **Composition Contract** — zones, relations, emphasis, closed vocabularies | Works. Relations are a real graph over declared zone ids. |
| **Product Lock / reference conditioning** | Works. 5/5 canonical references for Case 2 as of suite v4. |
| **Provider routing** — role-based, correct retry/escalation/fallback separation | Works, and is now actually reached by the pipeline. |
| **Cost & spend instrumentation** | Works. Every paid call recorded; unpriced work fails closed rather than counting as zero. |
| **Benchmark governance** — VERSION, CHANGELOG, comparability regression test | Works, and has repeatedly caught real problems. |
| **Prompt registry** — ids, semantic versions, content hashes, snapshots | Works, with one known gap (§5). |

1331 tests. 151 app modules. 99 test files. 8 benchmark cases.

---

## 3. What does not work

### 3.1 Output quality is unstable, and this is the main problem

Same prompt, same references, same model, same tier — two candidates from
one run:

| | Candidate A | Candidate B |
|---|---|---|
| The Let Them Theory | green, correct | white/gold, wrong |
| The Courage to be Disliked | white with red enso, correct | blue, wrong |
| Atomic Habits | correct | invented subtitle text |
| Layout | 3 above / 2 below, matches source | overlapping pile, covers obscured |

**This single fact invalidates most of how the project has been evaluated.**
Every improvement in this session — the tier routing, the reference fix, the
buy-box rule, the emoji fix — was judged on one or two images. With variance
this wide, n=1 cannot distinguish a real improvement from a lucky sample. I
declared wins on that basis more than once and then watched the next run
contradict them.

### 3.2 Three production blockers, unchanged

| # | Blocker | Why it blocks |
|---|---|---|
| 1 | **Fonts not installed** | Rendering resolves macOS-only system faces. Output depends on which machine drew it. Mechanism, gate and pinned installer are done; the 12 files are not fetched. |
| 2 | **Image model unpriced** | The daily spend cap cannot be enabled, so there is no cost ceiling on the most expensive part of the workflow. Needs official pricing or a deliberate ceiling. |
| 3 | **No acceptance threshold** | There is a quality engine, but no stated bar for "good enough to ship". Without one, §3.1 cannot even be scored. |

Blocker 3 was previously recorded as "generation unvalidated". That is no
longer accurate — generation runs end to end. The real gap is that nothing
defines what a passing result *is*.

---

## 4. The honest structural assessment

**The architecture is a long way ahead of the output.**

There are 151 modules, a governed prompt registry, a cost ledger, spend
forecasting, an ownership model, a composition contract with closed
vocabularies, ADRs, a versioned benchmark suite with a changelog and a
comparability regression test — and the actual deliverable, a usable
recreated ad, arrives roughly half the time.

That imbalance is not an accident of any one decision. It comes from
evaluating on single images. Each defect found produced a well-engineered
subsystem; none of them produced a measurement of whether output got better.
The subsystems are mostly *right* — text ownership in particular is the
correct model — but the project has been optimising the parts it can reason
about instead of the part it cannot yet see.

---

## 5. Known gaps in the guards

Recorded because a guard nobody knows is blind is worse than no guard.

- **Prompt snapshots protect wording, not assembly logic.** The pointer-emoji
  strip changed behaviour without moving any content hash, because no
  snapshot fixture contains an emoji. Neither the snapshot test nor the lock
  file failed. Version bumped by hand (6.0 → 6.1) with the reason recorded.
- **`ocr` was a declared dependency of the specification stage that nothing
  read** for the whole life of that stage. Declared dependencies are not
  checked for actual use.
- **Two benchmark disputes remain open** (case01 zone bounds, case06 primary
  family) and unchanged, awaiting adjudication.

---

## 6. Recommended course of action

In order. The first item is not optional — everything after it is
unmeasurable without it.

### Step 1 — Measure the variance (do this before anything else)

Generate **N = 8** candidates for one benchmark case from identical inputs.
Score each on: product identity per item, text accuracy, layout fidelity,
platform compliance. Report the distribution, not the best.

This is one run, and it answers the only question that matters right now:
*is the system 90% good with occasional misses, or 50/50?* Every decision
below depends on that number, and it is currently unknown.

### Step 2 — Write down the acceptance bar

One page. What must be true for an image to ship. Almost certainly:
- every product identity correct
- no invented or garbled text in overlay copy
- CTA affordance present and pointing at the buy box
- no duplicated or missing products

Without this, "better" has no definition and the quality engine has nothing
to enforce.

### Step 3 — Decide whether best-of-N *is* the product

If Step 1 shows wide variance, there are two honest routes:

- **(a) Accept it and industrialise it.** Generate 4–6, score automatically
  against Step 2's bar, present the best. Variance becomes a known cost per
  asset rather than a defect. This is how most production image systems
  actually work, and the scoring machinery mostly exists already.
- **(b) Attack the variance directly.** Seeds, tighter prompts, stronger
  reference conditioning. Slower, less certain, and only worth it if Step 1
  shows the failures are systematic rather than sampling noise.

**My recommendation is (a).** The quality engine, candidate loop and
reference scoring are already built; wiring them to a stated bar is a smaller
job than making a generative model deterministic, and it delivers a usable
product sooner.

### Step 4 — Clear the two mechanical blockers

`scripts/fetch_fonts.py` needs one network-connected run. The image model
needs either official pricing or a deliberate conservative ceiling. Both are
hours, not days, and both currently block any real deployment.

### Step 5 — Only then, resume subsystem work

The provider migration (Scene Intelligence and Composition Contract → Gemini,
~$0.145/run saving) is ranked and ready but should not move until output
quality is measurable. Same for the two open benchmark disputes.

---

## 7. What I would stop doing

- **Verifying prompt changes with full pipeline runs.** Each is ~5 minutes
  and real spend. Unit tests catch wording problems; live runs should be
  batched and reserved for validating a *set* of changes.
- **Adding subsystems in response to single-image defects.** Every one this
  session was a real defect, but the response should have been "how often
  does this happen?" before "here is a module that prevents it".
- **Declaring a result good from one image.** See §3.1.

---

## 8. Uncommitted work

The overlay-inventory change is in the working tree, not committed:

- The Creative Specification now receives the source's actual overlay text
  from OCR and is told to reproduce those lines and no others. This fixes the
  invented "Tap the link before it's gone" CTA.
- **Verified working**: spec produced exactly one overlay, the source caption
  verbatim.
- **Then broke the pointer emoji**: the constraint was read as covering every
  overlaid element, so the emoji row was dropped from both candidates. The
  instruction was rewritten to scope it to words only and say non-text
  affordances are out of scope. **That repair is unverified against a live
  run.**

1331 tests pass. Either finish it with one confirming run, or revert it —
but do not ship it unverified, because the failure mode is silent removal of
a real element.
