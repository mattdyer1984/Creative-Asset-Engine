# P1 — first complete end-to-end generation (case02_books)

**Suite v3 · `quality_mode=fast` · real providers · partial identity-validation case**
Run `run_p1_case02.json` · Outputs `p1_case02/`

---

## 1. Pipeline execution: SUCCESS

Every stage ran. This is the first time the Creative Intelligence Engine has
executed end to end.

| Stage | Result |
|---|---|
| OCR, Fingerprint, Scene, Contract, Profile, Ownership, Marketing, Narrative | succeeded |
| Product Isolation | succeeded |
| Product Lock Profile | succeeded |
| Creative Specification | succeeded |
| Canonical reference load | 3 supplied, 2 excluded |
| Reference Scoring | succeeded — **8 included** |
| Reference Conditioning | succeeded |
| Image Generation | **2 candidates produced** |
| Quality Assessment | succeeded — **both rejected** |
| Editorial Rendering | **did not run** (no winner) |

## 2. Cost and latency

| | Value |
|---|---|
| Analysis known cost | **$0.5800** (3 calls unpriced) |
| Image generation | 1 × `gpt-image-1` **$0.25** · 1 × `gemini-3.1-flash-image-preview` **unpriced** |
| **Overall cost** | **INCOMPLETE** — 4 calls have no configured rate |
| Generation wall clock | **208.8 s**, 2 attempts |
| Slowest single call | `gpt-image-1` at **139.9 s** |

**A provider fallback fired and worked.** Gemini returned `503 UNAVAILABLE`
mid-run; the pipeline fell back to `gpt-image-1` and completed. That path had
never been exercised under real load before.

## 3. Reference scoring and conditioning

3 canonical covers supplied through the production upload path
(`save_product_reference_image` + `ProductReferenceImage`, the same route
`POST /api/products/{id}/reference-images` uses). 2 excluded as
`edition_mismatch`.

**8 images ended up `included`** — the 3 canonical covers plus 5 crops
produced by Product Isolation from the creative itself.

**This changes how the run should be read.** The two "unsupported" titles
were not reference-free: their identity came from isolated crops of the
creative. My exclusion prevented the *wrong editions* conditioning
generation; it did not leave those titles unconditioned.

## 4. Creative resemblance: strong

Marble tile background, five paperbacks in the source's two-over-three
arrangement, white caption plate top, pointing-hand row bottom. Recognisably
the same creative.

Copy was **rewritten, not preserved**: *"All 5 bestsellers for the price of 1
/ Deal is live right now"* against the source's *"All 5 books for the price of
1 right now"*, and *"Tap below 👇👇👇"* replacing a bare emoji row. The
benchmark's `copy_policy` is `preserve_verbatim`, so this is a divergence
worth tracking.

## 5. Identity preservation, per title

### Supported (canonical reference supplied)

| Title | Result |
|---|---|
| **Atomic Habits** | **Good.** Cream cover, gradient dot lettering, "Tiny Changes, Remarkable Results", "James Clear", orange badge present. Badge text garbled |
| **The Psychology of Money** | **Good.** White cover, brain illustration, "TIMELESS LESSONS ON WEALTH, GREED, AND HAPPINESS", "MORGAN HOUSEL" |
| **Don't Believe Everything You Think** | **Partial.** Correct white cover and single-line head illustration, "JOSEPH NGUYEN" — but **the title is missing entirely** and the subtitle is garbled to "DON'T BELIEVE THING IS THIS BEGINNING & SND OF SUFFERING" |

### Unsupported (no canonical reference; conditioned on creative crops)

| Title | Result |
|---|---|
| **The Let Them Theory** | Green cover, "THE LET THE…" — right general identity, partially occluded by the neighbouring book |
| **The Courage to be Disliked** | Red/black brush circle on white, "THE COURAGE TO BE DISLIKED", "ICNIRO KISHIMI and FUMITAKE KOGA" — visually close, **author name hallucinated** ("ICNIRO" for "ICHIRO") |

**No wrong-edition substitution occurred.** Neither excluded cover appears.
The Greek *Let Them* art and the blue/trees *Courage* art are absent.

## 6. Final validation: correctly REJECTED

Both candidates: `accepted=False`, `identity_passed=False`,
`overall_confidence_score=0.0`.

> *"Identity validation failed — the generated image does not faithfully
> preserve the product's visual identity shown in its reference images."*

The per-field checks are discriminating rather than blanket: `silhouette`
passed on both (*"The items remain flat, rectangular portrait-format
paperback books like the references"*), while identity failed overall.

**This is the correct outcome.** Cover text is garbled or hallucinated on
three of five books. A pipeline that accepted this would ship recreations
with invented author names.

## 7. Editorial rendering: not reached

No candidate was accepted, so no `FinalOutput` was written and the L1
renderer never ran. `render_manifest_json` is null. Ownership enforcement,
zone occupancy and the fallback ladder are therefore **still unvalidated
end to end** — they run inside the rendering path this run never entered.

Note that `CAE_TYPOGRAPHY_RENDERER_ENABLED` is also off by default, so even
with a winner this run would have used the legacy renderer.

## 8. What this run establishes

**Validated for the first time:**
reference scoring · reference conditioning · image generation · provider
fallback under real 503 · quality assessment · identity validation ·
the decision to reject

**Still unvalidated:** ownership enforcement, editorial rendering, final
output — all gated behind an accepted candidate.

## 9. Findings

1. **Identity validation works, and it is strict.** It rejected output that
   looks convincing at a glance. Given the hallucinated author name, that is
   the right call.
2. **Text rendering is the binding quality constraint.** Every failure is
   text on a cover, not composition, colour or layout.
3. **`fast` mode gives one candidate per attempt and no selection pressure.**
   Two attempts, two rejections, no winner. `balanced` might find an
   acceptable candidate — a cost/quality question now worth asking.
4. **Copy was rewritten** despite `preserve_verbatim`.
5. **Isolated crops are doing real work** as references, which weakens the
   distinction between supported and unsupported titles here.

## 10. Status

**Case 2 is NOT promoted to a fully validated product case.** It remains
partial until correct covers for *The Let Them Theory* and *The Courage to be
Disliked* are supplied.

**Case 8 is retained as a negative control** — the fan is scene context, and
prominence is not producthood.
