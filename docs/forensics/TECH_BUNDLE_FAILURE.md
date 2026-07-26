# Forensic report: the tech-bundle recreation

Slideshow `c9c68661`, source `tiktok.com/@tokkkyshoppydeals/photo/7666587817794915606`,
generated 2026-07-26. All evidence below is read from stored artefacts in the
live dev database. No paid generation was run to produce this report.

---

## 0. The finding, stated first

**This is an analysis-and-planning failure, not generation variance.** The
image model did exactly what it was instructed to do. It was told, in four
separate places in the same prompt, to render no text.

**And the largest single cause is a change I made today** (commit `f9e3348`,
"Overlay copy comes from OCR"). It was written to stop the system inventing
copy. On this creative it does the opposite of its intent: it erases the
advert.

A second, important correction to the premise: **the system did understand
the strategy.** Its own stored analysis says slide 0 is

> "A simulated private chat conversation used as a hook, centered on a
> relatable frustration about high tech-related costs and a friend teasing an
> insider solution, with the product or solution intentionally hidden."

and its narrative artefact records slide 0 = `hook`, slide 1 = `reveal`, with
an arc summary naming the price comparison. The comprehension exists. It is
destroyed downstream, at the copy layer.

---

## 1. Artefact-by-artefact

### 1.1 OCR — **captured everything, perfectly**

Stored `raw_text` for slide 0:

```
8:42 / 73 / Twinzilla 🕶️🤝 / TODAY / TWINZILLA 🕶️🤝
Bro I've been meaning to get some new tech accessories but they all cost at least £67 😭😒
ME
Bro let me put you on...
```

Structured blocks, with the roles it assigned:

| text | role | **surface** |
|---|---|---|
| `Bro I've been meaning to get some new tech accessories but they all cost at least £67 😭😒` | headline | **physical** |
| `Bro let me put you on...` | subheadline | **physical** |
| `Twinzilla 🕶️🤝`, `TODAY`, `ME`, `8:42`, `73` | other | **physical** |

The £67 anchor and the curiosity line were both captured verbatim, with
sensible roles. **No information was lost at OCR.**

### 1.2 The `surface` classification — correct by its own rule, catastrophic in effect

Every slide-0 block is `physical`. The OCR prompt defines that term:

> `'physical'` if it's printed, molded, or displayed on a real object the
> camera photographed (product packaging, a shelf price tag, a sign, **a
> screen**)

A screenshot of a chat *is* text displayed on a screen. **OCR followed its
instructions correctly.**

Compare slide 1, where the distinction works as designed:

| slide | surface counts |
|---|---|
| 0 (chat) | `physical: 8`, `overlay: 0` |
| 1 (bundle) | `overlay: 8`, `physical: 5` |

Slide 1 correctly separates the TikTok-added headline (`overlay`) from the
box's own printed text (`physical`).

### 1.3 `_overlay_text` — **the defect**

`app/slideshow_stages/creative_specification_stage.py` filters
`surface == "overlay"`. Executed against the stored artefact:

```
_overlay_text(db, slide_0)  ->  []
```

**I used `surface` as a proxy for "copy the recreation should reproduce".
It does not answer that question.** It answers "was this text physically in
the scene, or composited on afterwards". For a creative whose entire content
*is* a rendered screen, everything is `physical`, and the filter returns the
advert as empty.

### 1.4 The empty-list branch made it worse

My own commit distinguished `None` ("caller did not look") from `[]` ("the
original genuinely has no overlay text"), and `[]` emits:

> "The original creative has NO overlay WORDS. Return an empty
> `text_overlays` array. Do not invent a headline or a call-to-action for
> it."

So the pipeline did not merely fail to pass the copy along — **it issued an
explicit instruction to produce none.** Before my change this slide would
have had invented copy (bad, but visible). After it, the advert is actively
suppressed.

### 1.5 Creative Specification — comprehension intact, copy gone

```
subject:        "A simulated private chat conversation used as a hook,
                 centered on a relatable frustration about high tech-related
                 costs and a friend teasing an insider solution, with the
                 product or solution intentionally hidden."
text_overlays:  []
```

The strategy is described accurately. The words are gone.

Slide 1, by contrast, kept its copy:

```
text_overlays: [{"content": "I got this bundle for a fraction of the store
                 prices on TIKTOK 🤩", "role": "top hook"},
                {"content": "£35...", "role": "individual item price anchor"},
                ... all six anchors ...]
```

### 1.6 The compiled prompt — **four instructions, all saying "no text"**

The stored `prompt_used` for slide 0 contains, in order:

1. **No copy to render.** `text_overlays` was empty, so nothing was compiled.
2. **`things_to_avoid`** — *"Do not copy Snapchat branding, exact UI,
   usernames, wording, avatar, or **message content** from the original."*
   The specification itself forbade reproducing the conversation.
3. **The absolute text suppression** (because `text_strategy = reuse_original`
   sets `suppress_overlay_text`):
   > "FINAL AND ABSOLUTE INSTRUCTION - TEXT: render NO text anywhere in this
   > image… Wherever the description above mentions a headline… treat that as
   > describing an EMPTY LAYOUT ZONE and render it as clean, uninterrupted
   > background with nothing in it. This instruction overrides every earlier
   > statement… All real copy is composited by the app afterwards, not by
   > you."
4. **The composition description itself**, which by then could only describe
   shapes: *"two or three short chat bubbles… should visually communicate a
   complaint or frustration through UI rhythm and expressive emoji-like
   symbols"*.

Point 3 is the decisive one. The system deliberately renders empty zones
because **the app is supposed to composite the real text afterwards.**

### 1.7 …but the compositor is switched off

```
CAE_TYPOGRAPHY_RENDERER_ENABLED = False
```

Fonts are not installed (production blocker #1). So the contract is:
*model leaves the text zones empty → app fills them in.* The first half ran.
The second half cannot run. **The blank bubbles you saw are the promised
empty layout zones that nothing ever filled.**

### 1.8 The pointing hand — **also mine**

The `PLATFORM LAYOUT` paragraph is present verbatim in the slide-0 prompt. I
added it unconditionally to every compiled prompt. Slide 0 has no CTA, no
buy-box relationship, and is explicitly a withholding slide.

Your diagnosis was exactly right: the system learned the rule and not its
scope.

### 1.9 Narrative structure — captured, then never used

Stored at slideshow level:

```json
{"slides": [{"slide_index": 0, "beat": "hook"},
            {"slide_index": 1, "beat": "reveal"}],
 "arc_summary": "The slideshow opens with a relatable chat about tech
   accessories being too expensive, then reveals a discounted all-in-one
   FullEra bundle as the affordable solution. Urgency is added through sale
   pricing and a 'sale ends soon' prompt."}
```

**The inter-slide relationship was correctly identified.** It appears nowhere
in either slide's compiled prompt. It is computed, stored, and dropped.

### 1.10 Validation — nothing checked the advert

| check | result |
|---|---|
| Identity validation | **0 rows** — skipped, correctly: story slide, no product |
| Quality assessment | `accepted = 1`, confidence **0.868** |
| `creative_fidelity_json` | **empty** |
| `text_quality_json` | **empty** |

The story-slide path (`assess_story_candidate`) accepts on photorealism
alone. It scored a blank chat mockup at 0.868 and passed it, because nothing
in that path asks whether the advert is present.

---

## 2. Your thirteen questions

| # | Question | Answer |
|---|---|---|
| 1 | Exact original copy captured? | **Yes** — verbatim, at OCR, including £67 and "Bro let me put you on…" |
| 2 | Meaning captured? | **Yes** — the `subject` field describes the hook, the frustration and the deliberate withholding |
| 3 | Advertising purpose captured? | **Partly** — purpose is in `subject` and `arc_summary`; it never becomes a constraint on output |
| 4 | Slide 1↔2 relationship captured? | **Yes, and then discarded** — `hook`/`reveal` + arc summary stored, absent from both prompts |
| 5 | TikTok UI separated from fake Snapchat UI? | **No.** Both are `physical`. No artefact distinguishes platform chrome from the creative device |
| 6 | Slide 1 identified as curiosity/setup? | **Yes** — `beat: hook`, and `subject` says "intentionally hidden" |
| 7 | Slide 2 identified as reveal/value comparison? | **Yes** — `beat: reveal`, arc summary names the comparison |
| 8 | £67 anchor treated as essential? | **No.** Captured, then dropped with all other slide-0 copy. Nothing marks it as load-bearing |
| 9 | "Bro let me put you on…" treated as essential? | **No.** Same path. Captured as `subheadline`, then erased |
| 10 | Bottom-left CTA rule scoped correctly? | **No.** Applied unconditionally to every slide. My defect |
| 11 | Where did copy become placeholders? | **`_overlay_text` → `[]` → the `no_overlays` prompt branch → `text_overlays: []`**, then reinforced by `things_to_avoid` and the absolute no-text instruction, and never restored because the typography renderer is off |
| 12 | Where was the pointing hand introduced? | **`platform_affordances.placement_instruction()`**, appended unconditionally in `compile_creative_intent` (commit `d613a2a`) |
| 13 | Why did validation allow it? | Identity validation skipped (no product — correct). Quality assessment accepted at 0.868 with **empty** fidelity and text-quality records. No check asks "is the advert present" |

---

## 3. Analysis failure or generation failure?

**Analysis and planning.** Established from the artefacts, not assumed:

- the copy existed at OCR and was correct;
- it was absent from the compiled specification;
- the prompt contained an explicit, absolute instruction to render no text;
- the prompt separately forbade reproducing the message content;
- the model produced exactly that.

The model cannot be blamed for omitting copy it was ordered four times not to
draw.

---

## 4. Isolated or systemic?

**Systemic, and newly so.** Three independent scopes:

1. **`_overlay_text` mis-scoping — systemic, introduced today.** Any creative
   whose text is *inside* the photographed scene rather than composited on
   top loses all its copy. That covers every screenshot-style creative:
   chats, DMs, notes-app screens, review screenshots, order confirmations.
   These are a large share of TikTok organic ad formats.
2. **Unconditional CTA rule — systemic, introduced today.** Every slide gets
   the buy-box pointer regardless of role.
3. **Suppression without a compositor — pre-existing.** Whenever
   `text_strategy` is set and the typography renderer is disabled, text zones
   are emptied and never refilled. This is a live contradiction between two
   defaults.

Slide 1 escaped only because OCR happened to classify its headline as
`overlay`.

---

## 5. Tests that passed while this was broken

| Test | Why it passed |
|---|---|
| `test_overlay_text_extraction.py` (8 tests) | I asserted that `physical` blocks are excluded — I encoded the defect **as the expected behaviour**, using a book cover as the example. It never occurred to me that a whole creative could be `physical` |
| `test_overlay_inventory.py` (10 tests) | Assert prompt wording, never that real copy survives to the prompt |
| `test_platform_affordances.py` (24 tests) | Test that the rule is stated and where a CTA belongs. None asks whether the slide should have a CTA at all |
| Prompt snapshot tests | Fixtures contain no screenshot-style creative and no emoji, so neither branch is exercised |
| The 1365-test suite | Contains no end-to-end assertion that source copy reaches the compiled prompt |

**The common failure: every test asserts the mechanism, none asserts the
outcome.** There is no test of the form "given a source creative with copy X,
the compiled prompt contains X or an instruction to composite X".

---

## 6. Minimal correction plan

Ordered, smallest first. No new subsystem.

### C1 — Stop using `surface` to decide what copy to reproduce *(fixes the blank bubbles)*

`surface` answers "was it physically in the scene". The question that matters
is "is this copy part of the advert". For a screenshot creative they are
opposite. Use OCR's `role` (`headline`, `subheadline`, `cta`, `price`) which
is already populated and was correct on slide 0, and treat `surface` as
supporting evidence rather than the gate.

### C2 — Never emit "the original has NO overlay words" from an empty filter

`[]` must mean "OCR found no copy at all", not "no copy survived my filter".
On slide 0, OCR found eight blocks. Emitting "there is no text" was a lie the
artefacts contradict.

### C3 — Scope the CTA rule to slides that have one

Condition `placement_instruction()` on the slide actually having a CTA or
pointer in its analysis. Slide 0's `beat: hook` and its own "product
intentionally hidden" both say it must not.

### C4 — Refuse to suppress text with no compositor available

If `text_strategy` is set but the typography renderer is disabled, that is a
misconfiguration that silently ships empty layout zones. It should fail
loudly, or fall back to letting the model render the copy. Right now the two
defaults contradict each other and the user gets blank boxes.

### C5 — One end-to-end test that would have caught all of this

Given a fixture slide whose OCR contains known copy, assert that copy (or an
explicit instruction to composite it) appears in the compiled prompt. Add a
screenshot-style fixture where every block is `physical`.

### C6 — Thread the narrative beat into the slide prompt

`hook` / `reveal` are computed and discarded. A hook slide should be told it
is withholding; a reveal slide should be told what it is paying off. This is
the smallest change that makes the cross-slide argument survive.

**Not proposed:** any new module, validator or subsystem. C1–C4 are
corrections to code written today; C5 is the test that should have existed;
C6 is wiring an artefact that already exists into a prompt that already
exists.
