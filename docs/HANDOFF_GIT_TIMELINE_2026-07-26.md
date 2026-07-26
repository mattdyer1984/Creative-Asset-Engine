# Git timeline — 2026-07-26 session

Commits `4a30418..d8177d7`, oldest first. Session start was `4a30418`
("P1: first complete end-to-end generation, and the quality gate rejected it").

Confidence key: **verified** = checked against stored artefacts or a test that
fails against the pre-fix code. **asserted** = I claimed it from a small
number of generated images. **unvalidated** = no end-to-end evidence.

---

## `2a65c51` — Suite v4: the real book covers, from the listing you supplied

| | |
|---|---|
| Files | `backend/tests/benchmarks/case02_books/references/{MANIFEST.yaml,book-let-them-theory.jpg,book-courage-disliked.jpg}`, `VERSION`, `CHANGELOG.md` |
| Intended | Replace two `edition_mismatch` references (Greek *Let Them Theory*, blue *Courage*) with the real editions from the seller's PDP |
| Observed | Case 2 goes 3/5 → 5/5 references. Later Lite run rendered *Let Them Theory* green for the first time |
| Tests | 212 reference/manifest/benchmark tests incl. SHA-256 |
| Confidence | **verified** (checksums, and the colour change is unambiguous) |
| Caveat | New references are angled photographs, not flat scans — recorded in the manifest, not like-for-like |
| **Recommendation** | **Retain** |

## `173edc1` — Wire tier routing into generation

| | |
|---|---|
| Files | `app/ai_providers/image_routing.py`, `app/services/generation_engine.py` (+`_route_image_provider`, `_product_instance_count`), `tests/test_generation_tier_wiring.py` (new, 6), `tests/test_image_routing.py` (+5) |
| Intended | Make the tier router actually reach the provider — it had 16 passing tests and zero effect |
| Implementation | Three defects fixed: dicts read with `getattr`; the `plan.provider` guard always firing (`decision_engine.py:112` sets it unconditionally); and `is_final_output=not is_draft` which I introduced and removed in the same commit |
| Observed | Live run selected `gemini-3.1-flash-image-preview` |
| Tests | 9 new, each verified to FAIL against the code it describes |
| Confidence | Routing **verified**. Quality benefit **asserted** — n≈2, later shown underpowered |
| **Recommendation** | **Retain**; re-evaluate the quality claim after analysis is fixed |

## `d613a2a` — The buy box is bottom left, so the CTA has to be

| | |
|---|---|
| Files | `app/services/platform_affordances.py` (new, 177 lines), `app/prompts/generation.py`, 6 snapshots, `prompts.lock`, `tests/test_platform_affordances.py` (new, 16) |
| Intended | CTA pointer must point at TikTok's bottom-left buy box |
| Implementation | `placement_instruction()` appended in `compile_creative_intent`. `generation.compiler` 5.0 → 6.0 |
| Observed | One live run moved the pointer to bottom-left |
| Contradicted later? | **Yes.** The instruction is unconditional and appears in the prompt of a slide that must have no CTA (`c9c68661` slide 0). Produced the invented pointing hand the owner flagged |
| Confidence | Rule correctness **verified**; scoping **wrong, verified** |
| **Recommendation** | **Review** — condition on the slide actually having a CTA. Do not revert the rule itself |

## `8ebe4c6` — A pointer emoji is an affordance, not copy

| | |
|---|---|
| Files | `app/services/platform_affordances.py` (+`strip_pointer_emoji`), `app/prompts/generation.py`, `prompts.lock`, `tests/test_platform_affordances.py` (+8), 2 evidence PNGs |
| Intended | Stop emoji rendering twice (once in caption, once at bottom) |
| Observed | Spec emitted `cta: "…gone 👇"`; compiled prompt carried it without the emoji — **verified on real data** |
| Important | **The snapshot and lock tests did not catch this change** — no fixture contains an emoji, so the content hash did not move. Version bumped by hand 6.0 → 6.1. A documented hole in the prompt guards |
| Confidence | Mechanism **verified**; effect on screenshot creatives **unvalidated** |
| **Recommendation** | **Review** after `f9e3348` is settled — they interact |

## `f9e3348` — Overlay copy comes from OCR, not from the model's imagination

| | |
|---|---|
| Files | `app/slideshow_stages/creative_specification_stage.py` (+`_overlay_text`, schema description), `app/prompts/generation.py` (+`overlay_inventory`, `no_overlays`), `app/ai_providers/openai_adapter.py`, `tests/fakes.py`, 2 snapshots, `tests/test_overlay_text_extraction.py` (new, 8), `tests/test_overlay_inventory.py` (new, 10) |
| Intended | Stop the spec inventing copy the original never had |
| Observed initially | Fixed the fabricated "Tap the link before it's gone" CTA — spec produced one overlay, the source caption verbatim |
| **Contradicted later** | **Yes, decisively.** `_overlay_text` gates on `surface == "overlay"`. OCR defines `physical` as including *"a screen"*, so a chat screenshot returns **zero** overlay blocks, and the `no_overlays` branch then instructs the model that the original has no text. **Verified cause of the blank chat bubbles** |
| Also | An earlier wording ("reproduce THESE blocks and only these") made the model drop the pointer emoji entirely; rewritten to "WORDS ONLY". **That repair is unvalidated for screenshot creatives** |
| Confidence | Defect **verified** against stored artefacts (`c9c68661` slide 0 → `[]`) |
| **Recommendation** | **REVERT-TEST FIRST.** Better fix: gate on OCR `role`, not `surface` |

## `482862f` — Project state assessment

| | |
|---|---|
| Files | `docs/PROJECT_STATE_2026-07-26.md` |
| Confidence | **Now known to be wrong in its central claim** — it says the main problem is generation variance. The forensics show variance is secondary to the analysis failures |
| **Recommendation** | **Retain as history; mark superseded** by `HANDOFF_2026-07-26.md` |

## `1e33920`, `12b890e`, `05db04f` — Variance harness and protocol

| | |
|---|---|
| Files | `docs/variance/CASE02_PROTOCOL.md`, `scripts/variance/{run_variance.py,prepare_references.py,__init__.py}` |
| Intended | Pre-register acceptance criteria *before* generating; hold provider, model, tier, prompt hash and references constant |
| Notable | `prepare_references.py` exists because reference scoring is gated behind `--include-generation` at `scripts/phase_f/run_benchmarks.py:275` |
| Known gap | `run_variance.py` calls `generate_with_failover` directly and **bypasses `record_provider_call`** — the 8 image calls are absent from the cost ledger |
| Confidence | **verified** (frozen config asserted per call) |
| **Recommendation** | **Retain**; fix the ledger bypass before reuse |

## `db6af61` — Case 2 variance study results

| | |
|---|---|
| Files | `docs/variance/CASE02_RESULTS.md`, 8 candidate PNGs, `variance.json` |
| Observed | **1 ship-ready, 3 repairable, 4 reject.** Dominant failure geometry/overlap at 75%. Promotional text correct 8/8; CTA bottom-left 8/8. Latency spread 9.6× |
| Honest caveat in the report | Two candidates drew fabricated TikTok UI, not covered by the pre-registered criteria. **Under a fabricated-UI check the rate is 0 of 8** |
| Confidence | **verified** (n=8, frozen inputs, nothing discarded) |
| **Recommendation** | **Retain.** Note that it measures generation variance only, with analysis frozen — and measures nothing about narrative |

## `dd9f79e` — Say which step is missing instead of just greying the button out

| | |
|---|---|
| Files | `frontend/src/components/CreateCreativeFlow.tsx`, `frontend/src/App.css` |
| Intended | The Generate button gave no reason for being disabled; a filled slideshow field above a dead button read as "it rejected my link" |
| Observed | Verified across all four states via DOM inspection |
| Confidence | **verified** |
| **Recommendation** | **Retain** |

## `a93d87f` — Accept the links people actually paste

| | |
|---|---|
| Files | `app/services/safe_fetch.py` (+`normalise_pasted_url`, +`vm.tiktok.com`), `app/importers/playwright_tiktok.py` (+`_resolve_short_url`, `_canonical_post_url`), `app/services/tiktok_import_chain.py`, `app/routers/slideshows.py`, `tests/test_tiktok_short_links.py` (new, 26) |
| Intended | Three defects: scheme-less URLs 500'd; `vm.tiktok.com` share links rejected; `UnsafeURLError` unhandled → bare 500 |
| Security | `http://` deliberately **not** upgraded. `vm.tiktok.com` added on evidence (already in `listings`). `vt.tiktok.com` deliberately excluded, fails closed. Redirect target still must survive `_normalize_post_url`'s rebuild |
| Observed | Live import of an 8-slide slideshow succeeded |
| Confidence | **verified** |
| **Recommendation** | **Retain** |

## `063d9a5` — Forensic report: the copy was captured, then my own change erased it

Documentation only. Read-only reconstruction. **Retain.**

## `d8177d7` — The haul slideshow: read correctly, then pointed at the wrong product

Documentation only. Records the "Security Check" phantom-product finding.
**Retain.**

---

## Summary

| Recommendation | Commits |
|---|---|
| **Revert-test** | `f9e3348` |
| **Review / rescope** | `d613a2a`, `8ebe4c6` |
| **Retain** | `2a65c51`, `173edc1`, `1e33920`, `12b890e`, `05db04f`, `db6af61`, `dd9f79e`, `a93d87f`, `063d9a5`, `d8177d7` |
| **Retain, mark superseded** | `482862f` |

**Nothing has been reverted.** Working tree clean at `d8177d7`.
