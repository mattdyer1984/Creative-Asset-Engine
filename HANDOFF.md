# Project Hand-off — Creative Asset Engine

**Written:** 2026-07-25. **For:** whoever (human or AI session) picks this project up next, with no assumed prior context.

This document is the fast-orientation entry point. `MIGRATION_PLAN.md` is the exhaustive, dated, phase-by-phase build log (every design decision, every real-world bug and its root cause, every live-verification result) — read it when you need the full story behind something mentioned here. This doc tells you where things stand *right now* and what to do next.

---

## Architecture direction (read before major feature work)

`docs/adr/0001-creative-intelligence-engine.md` is the canonical V2
architecture: project-level analysis, the Composition Contract, the hybrid
typography architecture, and the baked-in-versus-overlay text product rule.
It supersedes the slide-level assumptions in MIGRATION_PLAN.md's "AI Creative
Engine vNext" ADR. Status is Proposed until its implementation gates pass.


## 1. What this is

A FastAPI/SQLAlchemy backend + React/TypeScript frontend that takes a TikTok slideshow ad (or a locally-uploaded set of images) plus a product, and uses AI to **recreate** each slide as a new, original marketing image — preserving the product's real identity (via reference-image-conditioned generation, not text description) while varying the scene, composition, and on-screen text. It also validates its own output (does the generated image actually preserve the product?) and composites marketing text back on top with its own rendering engine.

Solo project. Git user: Matt Dyer (`mdyer84@googlemail.com`). No team, no other contributors evident.

## 2. Current state, in one paragraph

The core pipeline — import a slideshow → analyze every slide (OCR, product isolation, product lock profile, creative fingerprint, scene intelligence, marketing analysis, narrative structure, creative specification) → generate a new image per slide via reference-conditioned AI generation → validate product identity → composite marketing text → export — is **built, live-verified against real TikTok slideshows, and working**, including multi-slide "Generate All" with per-slide regeneration, feedback-driven retries, concurrent analysis/generation, real color emoji in overlay text, and (as of the most recent fix) genuinely independent per-slide creative direction (no more cross-slide scene bleed). Every phase below marked `[completed]` has a live-verified, tested, committed implementation — this isn't a plan, it's what's actually running.

**Branch:** `phase-2-slideshow-migration`. **Pushed and clean** — `git status` is clean, local is even with `origin/phase-2-slideshow-migration`, latest commit `58cea03`.

## 3. How to run it

```bash
# Backend (port 8321)
cd backend && .venv/bin/uvicorn app.main:app --app-dir . --host 127.0.0.1 --port 8321 --reload --reload-dir app

# Frontend (port 5173)
cd frontend && npm run dev
```
(Or use the Claude Code preview tool with `.claude/launch.json`'s `backend`/`frontend` configs, which wrap the same commands.) **Dev servers are not currently running** — nothing was left up at the end of the last session.

Dev DB lives at `backend/data/creative_asset_engine.db` (SQLite, gitignored, contains real imported data from live testing — a P.Louise slideshow, a Colgate product, a Bellavita product, others). Alembic migrations: `cd backend && .venv/bin/alembic upgrade head`. Backend tests: `cd backend && .venv/bin/python -m pytest -q` (536 passing as of the last commit). Lint: `ruff check app tests` (backend), `npx tsc --noEmit && npx oxlint src` (frontend).

**Real money**: image generation (`generate-creative`/`generate-image`) and every AI analysis stage call a real paid provider (OpenAI, Google Gemini/Nano Banana) — there is no mock mode in the running app. Test suite uses fakes throughout; only manual live-testing spends real money.

## 4. Architecture, in brief

- **Entities**: `Slideshow` (top-level import) → `Slide`[] (ordered images) → `ProductAppearance` (which `Product` is on which slide, many-to-many) → `Product` owns a **Canonical Reference Library** (`ProductReferenceImage`, compute-on-read `is_current`/library status).
- **Analysis pipeline** (`backend/app/slideshow_stages/`, run via `SlideshowOrchestrator`, `SLIDESHOW_STAGE_PIPELINE` in `pipeline.py`): OCR → Product Isolation → Product Lock Profile → Creative Fingerprint → Scene Intelligence → Marketing Analysis → Narrative Structure → Creative Specification. Every stage's `run(db, slideshow)` signature is fixed; **per-slide looping is internal to each stage** (established pattern — mirror it exactly for any new per-slide stage). Per-slide artifacts (OCR, Creative Fingerprint, Creative Specification, Scene Analysis) live on `Slide.current_*_id` pointers; per-product artifacts (Product Lock Profile) have no pointer, resolved by `is_current` scoped to `product_id`; genuinely slideshow-wide artifacts (Marketing Analysis, Narrative Structure) live on `Slideshow.current_*_id`.
- **Generation**: `generate_with_retry.py` → `generation_engine.py` → `prompt_compiler.py` (pure function, Creative Specification dict + reference image paths → provider-agnostic `GenerationRequest`) → provider adapter (`ai_providers/`, currently Nano Banana 2 / `gemini-3.1-flash-image-preview` is the default `image_generation` model, OpenAI adapter also exists and is swappable via `providers.yaml`). `reference_selection.py` picks which Library images condition each call — product identity comes from **reference images, never text description** (a deliberate Product Lock v2 design point).
- **Validation**: two-stage — Stage 1 Identity (short-circuits on failure, checks product fields incl. `branding_text` verbatim-text preservation) → Stage 2 Creative Fidelity/Photorealism (Quality Engine). `Decision Engine` (`decision_engine.py`) drives candidate count + retry loop.
- **Text overlay**: `text_intelligence.py` (which OCR'd text belongs on the rendered image — gated on OCR's `surface: "overlay"` classification, not `role`) → `rendering_engine.py` (pure Pillow compositing: 2-line-preferring wrap, no orphaned last word, central-two-thirds/never-bottom-20% TikTok-UI-safe zone, real color emoji via Apple Color Emoji glyph compositing since Pillow can't mix fonts in one call).
- **Frontend**: single-session import flow (`CreateCreativeFlow.tsx`) — there is **no persistent "browse my slideshows" page**; each import lands you in that session's own review/generate UI. `SlideshowBlueprintModal.tsx` is the deep per-slide/per-stage inspector (every artifact, rerun-per-stage, staleness indicators). `GenerationResultsModal.tsx` is the multi-slide carousel review UI.

## 5. What's proven vs. what's designed-but-deferred

**Proven, live-verified, in production use** (all of Phases 0–12 core work, see `MIGRATION_PLAN.md` for exhaustive detail on each): entity model, async execution, multi-slide import, Product Intelligence (evidence model, canonical profile, listings/bundles), multi-product-per-slide detection, narrative pass with dependency-aware staleness, the full Generation → Validation loop, Product Lock v2 (canonical reference library + reference-conditioned generation + two-stage validation), Provider Capability Framework, Decision/Generation Engine with retry, Photorealism dimension, Scene Intelligence, Project-as-aggregation-root (a real, executed reversal of an earlier design decision — `project.py`'s docstring is up to date), native TikTok import (Playwright, with Downie as documented fallback), Bundle Composition (multi-product-in-one-scene, layered on top of a still product-centric Generation/Validation core — the user's explicit resolution to what was an open design question), Text Intelligence + Rendering Engine, Generate All (multi-slide generation/review/regenerate/ZIP export), real color emoji rendering.

**Explicitly gated, not started, low priority**: Phase 13 (Pattern v0 — trivial candidate capture) and Phase 14 (Pattern curation lifecycle + search) — both flagged `GATED` in the phase list, deliberately deferred, no open question blocking them, just not prioritized.

**Deferred by explicit, recent user decision (2026-07-25), not yet designed further**: an "Originality Plan" artifact — a structured per-slide classification (`slide_marketing_role`, `core_message`, `locked_elements`, `required_marketing_evidence`, `scene_preserving_changes`, `forbidden_changes`) intended to eventually replace Creative Specification's freeform-prose approach with explicit reasoning about what must/can/can't change. The user was explicit: build it as a **new, additive, feature-flagged artifact** (`generation_planning_mode` = `creative_specification` | `originality_plan`) alongside Creative Specification — not a rename/replace — so both can generate the same slideshow and be compared on real image-quality criteria (product fidelity, originality, marketing intent preservation, scene accuracy, OCR/text quality, human review score, generation success rate) before ever retiring the old one. **Nothing has been built for this yet** — this is the most likely "what's next" if the user wants to continue in this direction. The full schema sketch and reasoning are still in `/Users/apple/.claude/plans/jaunty-splashing-starfish.md` from that planning session (not committed to the repo).

## 6. Known open issues (real, not hypothetical)

- **A real Stage 1 Identity Validation failure, root cause identified but not fixed**: regenerating the real P.Louise slide 1 (`generated_image_id=47c2e72e-...`, `image_validation_result_id=a960869e-...`) failed on `branding_text`: the model reproduced most of the packaging text but not the full long quote ("WHOEVER SAID MONEY CAN'T BUY HAPPINESS HAS NEVER RECEIVED A P.LOUISE PARCEL...") verbatim/fully legible. Confidence score 0.0, rejected, retry attempt produced zero candidates. This is a **pre-existing gap in long-verbatim-text reproduction reliability**, unrelated to the cross-slide contamination fix that surfaced it — worth a dedicated investigation if branding_text reliability on long quotes becomes a recurring complaint.
- **Two pre-existing, unrelated `ruff` F821 errors**: `app/models/slide.py`/`slideshow.py`, forward-reference type hints (`Mapped["Slideshow"]` etc.) that ruff's checker doesn't resolve. Confirmed present before any of this session's changes (via `git stash` A/B compare) — cosmetic, not a real bug, just noise in `ruff check app tests` output.
- **`generate_image` endpoint stays primary-slide-only**, a known/deliberate boundary from the Generate All work — `generate-creative` is the multi-slide path, `generate-image` (the older, simpler single-call endpoint used by Advanced-mode) was explicitly left unfixed as out of scope at the time. Still true.

## 7. Standing directives — still in force, read before adding new architecture

- **"Bias toward proving the Generation → Validation loop over adding more architecture"** (2026-07-22, still active per the user's own words: don't propose new infrastructure without naming the concrete blocker it removes). Given the loop is now not just proven but in active real-world use with real bugs being found and fixed via live testing, the practical reading of this directive right now is: **keep fixing real bugs found via real use before building new capability** — which is exactly the pattern the last several sessions have followed (Generate All → live-test → fix → live-test → fix...). Stay in that loop.
- **Auto-mode / push discipline** (session convention, not written elsewhere): only `git push` when the user explicitly says "push"/"push it"; write a `MIGRATION_PLAN.md` report section and commit after each real fix; run full backend suite + `ruff` clean after every change; live-verify against real data before claiming success; when a fix's scope turns out much larger than expected, stop and ask rather than silently expanding (this happened once this session — the per-slide Creative Specification fix ballooned into a full "replace with Originality Plan" redesign proposal, and the user explicitly pulled it back to the minimal bug fix, deferring the redesign — see §5 above).

## 8. Suggested next steps, roughly in order

1. **If continuing bug-hunting**: restart the dev servers, live-test Generate All again on a real slideshow (multi-slide, multi-product if possible), see what breaks. This has been consistently the most productive activity this project has had — every recent phase came from a real bug found this way, not from planning ahead.
2. **If picking up the Originality Plan idea**: re-read `/Users/apple/.claude/plans/jaunty-splashing-starfish.md`'s full history in this session's transcript for the complete schema design and reasoning (it went through two full redesigns before landing on the deferred/additive shape) — a fresh Plan-mode pass to turn that into a committed implementation plan is the right next step, not diving straight into code.
3. **If the branding_text long-quote issue recurs**: worth its own investigation spike — is this a prompt-phrasing issue (the current instruction is a single flat "reproduce verbatim" line for every packaging text, regardless of length) or a genuine model limitation on long verbatim text in an image?
4. **Phase 13/14 (Pattern work)** stay gated — don't start without an explicit user go-ahead, per the standing directive above.
