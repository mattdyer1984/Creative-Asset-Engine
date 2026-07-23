# Creative Asset Engine — Migration Roadmap

This document is the durable record of the architecture vision, the phased
plan to get there, and the standing authorization for autonomous work. It
exists so the plan survives independently of any one chat session — read
this first if picking the work back up cold.

## Frozen architecture vision

Decided and frozen across three rounds of review (see git history / prior
session transcripts for the full reasoning):

1. **Slideshow, not Creative, is the primary entity.** A Slideshow has
   independent Slides; product detection is optional per slide (a slide can
   have zero, one, or multiple products); narrative structure (hook, story,
   reveal, proof, CTA) is analyzed at the slideshow level, independently of
   per-slide asset detection.
2. **The long-term canonical reusable object is a "Persuasion Pattern"**,
   not a slideshow — a higher-level abstraction extracted from many
   slideshows, searchable across products/industries/audiences. Slideshows
   and their artifacts are the evidence base a pattern is extracted from,
   not the end product.
3. Implementation gets there through small, testable, production-safe
   refactors — no future abstractions before they're needed.

### 2026-07-22 revision: three independent systems

After Phase 4 landed, the user refined the vision further. The engine is
no longer framed as "analyze TikTok slideshows" - it's three systems:

1. **Product Intelligence** - **(2026-07-23 revision, see the "ADR: Canonical
   Product Reference" below)** everything required to recreate this exact
   product with high visual fidelity, built by combining evidence from
   multiple sources (official listing, Shopify/Amazon/TikTok Shop pages,
   official images, user-uploaded references, creator slideshows, future
   generated images), each attribute/image tagged with its source and a
   confidence/quality score. A **Canonical Product Reference** (a small,
   curated, scored set of real reference images - see the ADR) is now the
   *primary* representation - the images define the product. The
   canonical Product Profile (textual, structured: shape, dimensions,
   capacity, labels, branding, official colors, packaging, materials,
   category) is retained as supporting metadata, not the primary
   representation it originally was - text is not precise enough to
   encode exact geometry/silhouette, which real reference images are.
   Slideshows continue to supply what listings can't for the *contextual*
   (non-product-identity) side: camera angle, composition, lighting,
   marketing context, persuasion, emotional positioning. These complement
   rather than compete.
2. **Creative Intelligence** - understanding why a slideshow sells a
   product. This is what Phases 2-4 already built (Slideshow/Slide,
   OCR, Creative Fingerprint, Marketing Analysis, Recreation Prompt).
3. **Generation Engine** (Phase 8, done; Phase 9 in progress) - generate
   an original slideshow that preserves the marketing strategy while
   remaining visually original. Phase 8 proved the loop end-to-end
   (text-mediated); Phase 9 (see the ADR below) closes the gap Phase 8's
   own live-verification exposed: the validation loop (generate → analyze
   → compare against the Canonical Product Reference's real images →
   measure fidelity → regenerate if below threshold) needed real pixels,
   not a textual description of them, to actually validate visual
   identity rather than semantic description.

**Key finding from reviewing the existing roadmap against this**: old
Phase 5 ("multi per-slide product detection") and Product Intelligence
are orthogonal, not sequential. Old Phase 5 is about *breadth* (more
slides analyzed); Product Intelligence is about *depth* (more evidence
*sources* combined). Product Intelligence's first real increment doesn't
need per-slide detection first - it can ship using the existing
single-slide vision evidence as one input alongside a new listing-import
input. This is why Product Intelligence moves ahead of old Phase 5 in
the renumbered list below, rather than replacing it.

**No structural changes to already-completed work (Phases 0-4).**
`Product`, `ProductLockProfile`, `ProductReferenceImage`,
`ProductAppearance`, and the whole Slideshow/Slide/async/multi-slide
foundation all remain correct as-is - they become *inputs* to Product
Intelligence, not things to redo. See "Phase 5: Product Intelligence"
below for the specific, entirely prospective adjustments this implies
for new code, none of which touch Phase 2-4's existing models/stages.

**2026-07-22: catalogue layer frozen.** Real data (a live bundle listing)
exposed that atomic `Product` can't honestly represent a multi-item
listing. A dedicated ADR ("ADR: Catalogue layer for Product
Intelligence," further down this document) settled `Listing` (marketplace
identity/commercial facts) and `ProductBundle` (composition of `Product`s)
as additive entities sitting *above* Product Intelligence, with zero
change to `Product`/`ProductProfile`/`CANONICAL_FIELD_VOCABULARY`. Locked
as the architectural baseline - not to be revisited without a concrete
implementation/production limitation.

## Phase list

| # | Phase | Status |
|---|-------|--------|
| 0 | Characterization safety net | done |
| 1 | Orthogonal reliability fixes (1.1–1.4) | done |
| 2 | Entity split: Creative → Slideshow + Slide (2.1–2.7) | done, reviewed |
| 2.8 | Drop legacy Creative/CreativeBlueprint schema | **gated — explicit approval required, do not implement** |
| 3 | Async execution boundary (3.1–3.5) | done |
| 4 | True multi-slide import (4.1–4.4) | done |
| 5 | **Product Intelligence** (evidence model, listing import, canonical profile, catalogue layer) | done (5.1-5.12, live-verified — TikTok Shop deliberately unsupported, see 5.4; catalogue layer per the frozen ADR) |
| 6 | Multi per-slide product detection *(was Phase 5)* | done (6.1-6.5, live-verified) |
| 7 | Narrative pass with dependency-aware staleness *(was Phase 6)* | done (7.1-7.5, live-verified) |
| 8 | **Generation → Validation proof of loop** (ImageGenerationProvider, Prompt Compiler, single-slide generate/validate) | done (8.1-8.5, live-verified with real, paid OpenAI image-generation and vision-analysis calls — see reports log). Proves the loop end-to-end for one slide; Phases 9-12 below remain deprioritized per the standing 2026-07-22 directive unless one becomes a genuine blocker |
| 9 | Frontend consolidation *(was Phase 8, was Phase 7)* | not started — deprioritized per the 2026-07-22 directive |
| 10 | PerformanceRecord (additive) *(was Phase 9, was Phase 8)* | **explicitly out of scope for autonomous work — plan only if/when revisited, no implementation without direct review** |
| 11 | Pattern v0 (trivial candidate capture) *(was Phase 10, was Phase 9)* | **same as 10** |
| 12 | Pattern curation lifecycle + ContextEfficacy + search *(was Phase 11, was Phase 10)* | **same as 10** — now understood to sit above both Product and Creative Intelligence, not just Creative |

## Standing authorization (granted 2026-07-21/22, user away for an
extended, unspecified period)

**2026-07-22 update: the user has since returned and paused this
blanket authorization** to revisit the long-term architecture (see the
"three independent systems" revision above) before any further phases
proceed. Phases 3 and 4 were already completed under the original
authorization and remain shipped. For every phase from here on
(renumbered Phase 5 onward), the default reverts to the normal
plan-then-confirm discipline (same as how Phase 2 itself originally got
a dedicated plan-only round before any code) - no autonomous
implementation resumes until the user has reviewed the revised roadmap
and a phase's detailed sub-phase plan. The rest of this section is kept
as a historical record of what the original blanket authorization
covered, not a currently-active grant.

Originally permitted without further chat confirmation, for Phases 3–7
(pre-revision numbering) only:
- Writing detailed sub-phase plans.
- Implementing, testing, and committing small sub-phases to the
  `phase-2-slideshow-migration` branch, following the same discipline as
  Phase 1/2: after every sub-phase the app still runs, tests pass, DB
  stays migratable, and the previous commit is a safe rollback point.
- Local `git commit` on this branch.

Explicitly NOT permitted without the user present, regardless of tool
permission mode:
- `git push`, opening a PR, or any action visible outside this machine.
- Phase 2.8 (destructive schema drop).
- Any implementation work on Phases 8–10 (new product surface, not
  refactors — needs real design sign-off, not unilateral judgment calls
  made while unsupervised).
- Anything in the "Prohibited" or "Explicit permission required"
  categories of the standing safety rules (credentials, deletions of user
  data outside this repo, financial actions, etc. — none of which are
  expected to come up in this codebase, noted for completeness).

If a genuine design ambiguity comes up that materially affects the
architecture (not just an implementation detail), stop and log it in the
"Open questions" section below rather than guessing.

**2026-07-22: renewed, for Phase 5 onward.** The user confirmed the
Phase 5 plan (five rounds of refinement, all recorded above) and granted
autonomous implementation again, explicitly stating they will not be
reachable to approve or grant access going forward. Same discipline as
the original grant (small sub-phase, tested, verified, committed,
reported here), same standing exclusions (no push/PR, no Phase 2.8, no
implementation on Phases 9-11). One addition specific to Phase 5, which
is genuinely new territory - it involves fetching real content from the
open internet (5.3/5.4), not just local refactors:

- Fetching public URLs (product pages, a real TikTok Shop listing for
  5.4's investigation spike) proceeds as regular, read-only,
  reasonable-volume activity - not something requiring a check-in per
  fetch.
- **Hard stop, not a workaround**: if 5.4's spike concludes TikTok
  Shop's official Partner/Open API is required (not plain HTTP+parse),
  that needs developer registration/credentials this session cannot
  obtain - creating an account or supplying business/developer details
  to a third party stays out of scope regardless of how long the user is
  unreachable. If the spike lands there: do not attempt a workaround (no
  reverse-engineering internal endpoints, no scraping a JS-rendered SPA
  in a ToS-risky way to route around the credential requirement) - let
  TikTok Shop URLs fall back to the generic adapter, document the gap
  here, move on.
- Any other genuine product/business judgment call: keep resolving it
  the same way prior open questions were handled (conservative,
  additive, well-reasoned, logged) - but lean more conservative than
  before, since there's no longer a quick question to ask. Favor smaller
  commits and reversible choices over anything requiring a guess about
  intent.

**2026-07-22: user enabled the Claude Code app's "bypass permissions
mode"** (stops per-tool-call confirmation prompts) before stepping away
for an extended period. This does not change any of the boundaries
above — those are self-imposed, not enforced by the permission dialog,
and remain in force regardless of app-level permission mode.

**2026-07-22: "Senior Project Manager" framing, made explicit.** The
per-call approval prompts became a real bottleneck for unattended work -
the user wants zero stops for ordinary engineering judgment while away,
not just the Phase 5-specific carve-outs above. Made explicit rather than
re-derived each session: full authority over all Regular-category
work-architecture calls, schema/API design, test strategy, mid-
implementation bug fixes, commit boundaries, sub-phase sequencing,
writing and revising this plan document itself - proceed and report,
never pause to ask. This is not a new grant so much as a formal statement
of what every phase this session already did in practice (5.8-5.10 each
involved real design decisions and bug fixes made and executed without
asking first). The fixed boundaries from the original grant are
unchanged by this and are not "conservative defaults to reconsider" -
they are the actual edge of delegated authority: no `git push`/PR, no
Phase 2.8, no implementation on Phases 9-11, nothing in the standing
safety rules' Prohibited/Explicit-permission-required categories. Note
for whoever (including a future me) re-reads this cold: the per-tool-call
prompts the user was hitting are the Claude Code app's own permission
mode, external to this document and outside this agent's control to
change from within a session - this entry records delegated *decision*
authority, not a mechanism for suppressing the app's own approval UI.

## Open questions

_(none currently open - see resolved questions in the Phase 5 detailed
plan below)_

## Suggested future improvements

Non-blocking items noticed along the way, deliberately deferred rather
than fixed in the phase that found them - not urgent, but worth a look
eventually:

- **Startup reconciler for interrupted background runs** (found during
  Phase 3.5): a process restart mid-analysis leaves a `Slideshow` stuck
  in `queued`/`analyzing` forever. Pre-existing failure-mode class (the
  old synchronous path had the equivalent gap), not a Phase 3 regression.
- **`app.slideshow_stages` → `app.stages` package rename** (considered
  during the Phase 2 engineering review): cosmetic, ~20 files, real
  mechanical risk for a naming-only benefit. Revisit once Phase 2.8 lands
  and the "must stay parallel to the old pipeline" constraint is gone.
- **TikTok Shop Product Source support** (Phase 5.4's spike, 2026-07-22):
  hard-stopped, not abandoned. Two real paths exist if the user wants to
  revisit this: (a) a paid anti-bot-bypass/proxy scraping service (real
  ongoing cost, ToS considerations to weigh explicitly) or (b) TikTok
  Shop's official Partner API (free, but requires the user to register
  and OAuth-authorize a specific shop they own - only ever covers their
  own shop's products, not arbitrary TikTok Shop URLs, which is a
  materially narrower capability than what the generic fallback provides
  for every other platform). Either is a deliberate product/business
  decision for the user to make explicitly, not something to pursue
  unprompted.
- **Product-targeted isolation/profiling for multi-product slides**
  (found while implementing Phase 6.2, 2026-07-22): `isolate_product`
  and `analyze_creative`'s Product Lock Profile prompt both take a whole
  slide image and a generic, non-targeted "the featured product"
  framing - there's no way to tell either provider *which* of several
  assigned products to focus on. Phase 6 ships assigning/tracking
  multiple products per slide (6.1, 6.4, 6.5); it deliberately does NOT
  ship automated per-product isolation/profiling for the 2+-products
  case, since faking it (calling the same generic prompt twice, or
  guessing which detected bounding box belongs to which product) would
  silently produce plausible-looking but wrong data - worse than the
  honest gap. Real fix needs either region-hinted isolation (seed the
  call with a specific area of the image to focus on, e.g. from a
  manually-drawn or previously-detected bounding box) or reference-
  image-hinted profiling (seed the vision call with "does this look like
  <product's existing reference image>?") - both are real AI-provider
  interface design work, not an orchestration-loop change, and belong in
  their own phase once there's a real multi-product use case to design
  against, not guessed at here.
- **`prominence` doesn't yet distinguish primary from secondary on
  multi-product slides** (observed while live-verifying Phase 6.5,
  2026-07-22): the additive add-product endpoint (Phase 6.1) always
  writes `prominence="primary"` for every appearance it creates, so a
  slide with 2+ products added this way shows every one of them as
  "primary" (Recreation Prompt's `_resolve_primary_appearance` from
  Phase 6.3 still resolves deterministically in this case via the
  earliest-created tiebreak, so nothing is actually broken - but the
  stored `prominence` value itself doesn't yet carry a meaningful signal
  once there's more than one). Fixing this needs a real product decision
  (should adding a second product ever demote the first to "secondary"
  automatically, or does that require explicit user action, e.g. a
  "make primary" control in the picker?) - not guessed at here.
- **Product Isolation/Lock Profile/Creative Fingerprint still only
  operate on `slideshow.primary_slide`** (found while scoping Phase 7,
  2026-07-22): Phase 7.1 widens only `OCRStage` to run across every
  slide, deliberately not the other three per-slide stages - each
  additional widened stage means N vision/AI calls per multi-slide
  slideshow instead of one, a real cost/design tradeoff not required for
  Narrative Pass specifically. Revisit once there's a concrete need to
  analyze products/visual style across every slide, not just the first.
- **Narrative Structure (Phase 7.2) is text-only, not vision-based**
  (found while scoping Phase 7, 2026-07-22): classifies each slide's
  narrative beat (hook/story/reveal/proof/CTA) from that slide's OCR
  text alone, reusing the existing `TextGenerationProvider` rather than
  building a new multi-image AI-provider capability
  (`VisionAnalysisProvider.analyze_creative` only takes one image today -
  confirmed by reading `app/ai_providers/base.py`). A slide with no
  on-screen text gets an honest `unclassifiable` beat, not a guess. Real
  fix needs vision input (either a new multi-image provider capability,
  or per-slide Creative Fingerprint once that's widened per the item
  above) - genuine AI-provider design work, not attempted here.

## Phase 3: Async execution boundary — detailed plan

**Problem.** `POST /api/slideshows/{id}/analyze` and
`.../stages/{name}/rerun` currently call the orchestrator inline and block
the request for the full duration of a (potentially multi-minute,
multi-provider-call) pipeline run. `Slideshow.status` already has an
`analyzing` state, but it's currently unreachable from the outside — by
the time any response comes back, the slideshow is already `ready` or
`failed` (see the now-corrected comment this used to have in
`frontend/src/components/SlideshowGrid.tsx`).

**Empirical finding that shapes the whole plan:** verified via a throwaway
script that FastAPI's `TestClient` runs `BackgroundTasks` to completion
*before* `client.post(...)` returns (Starlette drives the ASGI call,
including scheduled background tasks, to completion within the test
call). This means the existing test suite mostly keeps working unchanged
even after moving to background execution — tests don't need real
polling/waiting logic, just re-fetching the blueprint by GET afterward
instead of trusting the analyze/rerun response body for content. Real
production traffic (uvicorn) behaves differently: the HTTP response
really is sent before the background task runs, so the frontend genuinely
needs to poll.

### 3.1 — Background-execution infrastructure (additive, zero behavior change)

- New `app/services/background_execution.py`: `run_pipeline_in_background`
  and `run_stage_in_background`, each opening its own `SessionLocal()`
  (a request-scoped session can't be reused after the response is sent),
  loading the `Slideshow` fresh, delegating to the existing
  `SlideshowOrchestrator`, and closing the session in a `finally`.
- Not wired into any route. No API/DB/behavior change to anything.
- New unit tests call the helpers directly and assert the same status
  transitions as calling the orchestrator directly (this is a wrapper,
  the orchestrator's own logic/tests are unchanged).
- Rollback: delete the new file. Nothing else references it yet.

### 3.2 — Wire `/analyze` to background execution

- Add a guard: if `slideshow.status` is already `queued` or `analyzing`,
  return `409 Conflict` rather than starting a second overlapping run —
  this failure mode was impossible before (the request thread itself was
  the lock) and is new now that two requests can race.
- Otherwise: set `status = queued` synchronously (so the response reflects
  it), commit, schedule `run_pipeline_in_background` via FastAPI's
  `BackgroundTasks`, and return `SlideshowRead` (not
  `AssembledSlideshowBlueprint` — there's nothing new to assemble yet).
  This is a deliberate, documented response-shape change.
- Test migration: existing tests asserting on the analyze response body's
  *analysis content* switch to asserting on `status == "queued"` from the
  response, then a separate `GET .../blueprint` call for content
  (`TestClient`'s synchronous background-task execution means the content
  is already there by then).
- Rollback: revert this commit; 3.1's helper stays dormant/unused.

### 3.3 — Wire `/stages/{stage_name}/rerun` to background execution

- Same pattern as 3.2, applied to the single-stage rerun endpoint.
- Rollback: revert independently of 3.2.

### 3.4 — Frontend polling

- `frontend/src/api.ts`: `analyzeSlideshow`/`rerunSlideshowStage` return
  types change from `AssembledSlideshowBlueprint` to `Slideshow`.
- `SlideshowBlueprintModal`/`SlideshowGrid`: after triggering
  analyze/rerun, poll (`getSlideshowBlueprint` on an interval, e.g. 1.5s)
  while status is `queued`/`analyzing`; stop on `ready`/`failed`.
- Remove/update the comment in `SlideshowGrid.tsx` that currently
  (accurately, pre-3.2/3.3) describes `analyzing` as unreachable — it
  becomes reachable and meaningful once this sub-phase lands.
- Rollback: revert; backend keeps working with a client that doesn't poll
  (it would just show a stale "queued" state until manually refreshed —
  degraded but not broken).

### 3.5 — Test migration completion, live verification, hardening

- Full backend suite green.
- New test: 409 when re-triggering analysis on an already-analyzing
  slideshow (set status directly, then call the endpoint, to exercise the
  guard without needing real concurrency).
- Live verification: start the real dev server (not just `TestClient`)
  and drive an actual import + analyze through the browser, confirming
  the UI shows "Analyzing…" and updates via polling — `TestClient`'s
  synchronous background-task execution means the test suite alone cannot
  prove the real async path works.
- Document as a known, pre-existing (not newly introduced) limitation: a
  process restart mid-analysis leaves a slideshow stuck in `analyzing`
  status with no automatic recovery. Not fixing this now (no reconciler
  exists for the old synchronous path either, which had the equivalent
  failure mode of a killed request) — noted as a suggested future
  improvement, not a Phase 3 blocker.

**Risks:** SQLite single-writer contention under concurrent background
writes — mitigated by the existing pattern of short, per-stage
transactions (already true of every stage today, unchanged by this
phase). Silent background-task failure (an exception inside a
`BackgroundTasks` callback doesn't propagate anywhere by default) — the
existing per-stage `try/except` + `mark_failed` already writes failure
state to the DB before any exception would occur, so a stage's own
failures still surface correctly in `Slideshow.status`; only a bug in the
orchestrator/wrapper itself outside those try blocks would fail silently,
same exposure the synchronous path already had.

## Phase reports log

Reports are appended here as each sub-phase completes, in addition to
being in the git commit messages themselves.

### Phase 3.1 — Background-execution infrastructure (done)

- Added `app/services/background_execution.py`
  (`run_pipeline_in_background`, `run_stage_in_background`) — not wired
  into any route yet.
- **Real bug caught during verification, fixed before it could bite**:
  `app.dependency_overrides[get_db]` (how `tests/conftest.py`'s `client`
  fixture isolates test DBs) only redirects the request-scoped session
  FastAPI injects via `Depends`. It does nothing for code that opens its
  own session directly — which is exactly what background execution has
  to do, since a request-scoped session is closed by the time a
  `BackgroundTasks` callback runs. Left as originally written, Phase 3.2's
  first test run would have silently written into the real dev SQLite
  file on disk instead of the per-test throwaway one. Fixed by (a) having
  `background_execution.py` look up `app.db.SessionLocal` via module
  attribute access at call time instead of `from app.db import
  SessionLocal` at import time, and (b) `tests/conftest.py`'s `db_session`
  fixture now also monkeypatches `app.db.SessionLocal` to the same
  per-test engine it already builds — automatically covering every
  existing test that uses `db_session` (directly or via `client`), no
  per-test-file changes needed.
- 6 new tests in `tests/test_background_execution.py`; one of them
  initially had a flawed premise (asserted "the other session's write is
  invisible without refresh" on an object that hadn't been loaded into
  the test session's identity map yet, so the assertion was really just
  testing a fresh query) — caught by the test actually failing, not
  assumed correct; rewritten to force the object into memory before the
  background run so staleness is genuinely observable.
- Full suite: 66/66 passing (60 pre-existing + 6 new). Ruff clean.
- Zero behavior change to any existing endpoint — this sub-phase is pure
  additive infrastructure, exercised only by its own tests.
- Commit: (see git log)

### Phase 3.2 — Wire `/analyze` to background execution (done)

Scope grew beyond the original plan's split (backend-only 3.2, frontend
polling deferred to 3.4): landing the backend change alone would have
left the app in a genuinely broken intermediate state (the modal calling
`setBlueprint()` on a response shape that no longer matched), violating
the "app still runs after every sub-phase" invariant. Folded the matching
frontend change into this sub-phase instead - each of 3.2/3.3 is now a
complete, working vertical slice. 3.4 is repurposed as polish/cleanup
rather than "add polling" (already done here).

- Backend: `POST /analyze` now claims the row atomically (see below),
  schedules `run_pipeline_in_background` via `BackgroundTasks`, and
  returns `SlideshowRead` with `202 Accepted` instead of blocking for the
  full pipeline and returning `AssembledSlideshowBlueprint`. New `409` if
  analysis is already in progress.
- **Real concurrency bug caught by live testing, not by the unit test
  suite**: verified against the actual running server (not just
  `TestClient`) with two genuinely concurrent `POST /analyze` calls -
  both came back `202`. The first implementation used a plain
  read-status-then-write, which races: two overlapping requests can both
  read the pre-queued status before either commits. Fixed with a single
  atomic `UPDATE ... WHERE status NOT IN (queued, analyzing)`, checking
  `rowcount` to distinguish "claimed it" / "already in progress" / "404".
  Re-verified live after the fix: `202` + `409`, consistently. Added a
  matching pytest (`test_analyze_atomically_claims_the_row_under_real_
  concurrency`) using two real threads with independent DB sessions
  against the route function directly - the existing `client` fixture's
  shared session isn't thread-safe to call concurrently and wouldn't
  have reproduced this anyway (see that test's docstring). Ran 5x locally
  with no flakiness.
- Frontend: `api.ts`'s `analyzeSlideshow` return type → `Slideshow`.
  `SlideshowBlueprintModal` re-fetches instead of trusting the POST
  response body, and polls (1.5s) while status is queued/analyzing.
  `App.tsx` gained a silent (no loading-spinner-flash) list refresh,
  polling the same way, so the grid view reflects progress without
  requiring the modal to be open. `SlideshowGrid.tsx`'s `ANALYZABLE_
  STATUSES` no longer includes `queued` (a real, sustained state now,
  not a transient one) and its stale "analyzing is unreachable" comment
  is corrected.
- Live-verified end-to-end against the real dev server/data (not just
  `TestClient`): clicked Retry, watched `202` → background run → the
  grid's own poll picking up the eventual `failed` status (this
  environment has no OpenAI API key configured, so the pipeline fails
  cleanly at OCR's "no API key" check - confirms the full async plumbing
  without spending real API cost). One caveat: because that failure is
  near-instant locally, this specific check didn't observe the *recurring*
  1.5s poll tick actually firing mid-flight (only the immediate
  post-trigger refresh) - the interval/cleanup logic itself is simple and
  type-checked/linted/built cleanly, but a slow-running analysis (a real
  provider key) is the more complete way to observe that specific detail,
  not done here.
- Full suite: 69/69 passing. Ruff clean. Frontend `tsc`/`oxlint`/`build`
  clean.
- Commit: (see git log)

### Phase 3.3 — Wire `/stages/{stage_name}/rerun` to background execution (done)

Exact same shape as 3.2, applied to the single-stage rerun endpoint - same
atomic `UPDATE ... WHERE` claim (reused the identical pattern, no new bug
this time since 3.2 already found and fixed it), same `202` +
`SlideshowRead`, same background-scheduling. `default_slideshow_
orchestrator` import removed from the router - no longer used directly by
either endpoint now that both go through `app.services.
background_execution`.

- Backend: `rerun_stage` claims atomically, schedules `run_stage_in_
  background`, returns `202` + `SlideshowRead`. New `409` matching
  `/analyze`'s.
- Added `test_rerun_atomically_claims_the_row_under_real_concurrency`
  (same two-real-threads pattern as `/analyze`'s equivalent test) -
  confirms the same fix covers this endpoint too.
- Frontend: `api.ts`'s `rerunSlideshowStage` return type → `Slideshow`.
  `SlideshowBlueprintModal`'s `handleRerun` re-fetches instead of trusting
  the response body, reusing the *same* polling effect already added in
  3.2 (it's generic - keyed off `blueprint.status`, not which action
  triggered it - so nothing needed duplicating). Every rerun button
  (including the "Re-crop product image" secondary action) is now also
  disabled while any run is in flight (`runInFlight`), not just its own
  specific `busyAction` - previously only the triggering button disabled
  itself, which would have let a second stage's rerun button be clicked
  while the first was still running.
- Live-verified end-to-end against the real dev server: clicked "Re-run
  OCR" in the blueprint modal, confirmed a single `202` (no double-fire),
  and confirmed the resulting UI state - this slideshow already had a
  real, successful OCR result from before (`is_current`), and the new
  failed attempt (no API key, same as 3.2's check) correctly left that
  prior result on screen while showing the new failure banner above it -
  proving the "never overwrite on failure" contract survives the async
  rewrite, not just the happy path.
- Also re-verified the atomic-claim fix's concurrent-request behavior
  live against this endpoint specifically (`202` + `409`), matching 3.2.
- Full suite: 72/72 passing. Ruff clean. Frontend `tsc`/`oxlint`/`build`
  clean.
- Commit: (see git log)

### Phase 3.4 — Polling UX polish + cleanup (done, no changes needed)

Original scope (add polling) was already folded into 3.2/3.3. Did a final
review pass looking specifically for: rough edges in disabled-state
consistency (already handled - every rerun button and the Analyze All
button share the same `runInFlight` guard), stale comments referencing
the old synchronous behavior (swept the whole `app/`/`src/` tree for
"runs synchronously" / "blocking behavior" / "blocks the request" -
zero hits), and anything left half-migrated (checked `SlideshowGrid.tsx`'s
own analyze button/state machine specifically - it disables itself during
the POST itself via local `analyzingIds` state, then disappears entirely
once status flips to queued/analyzing since `ANALYZABLE_STATUSES` no
longer includes those - no gap where a truly-in-flight run's button is
still clickable). No code changes were needed - this sub-phase is a
verification step, not an implementation one.

### Phase 3.5 — Test migration completion, live verification, hardening

Live verification (against the real dev server, not just `TestClient`)
already happened inline as part of 3.2 and 3.3, including the concurrency
bug/fix - see those reports above rather than a separate pass here, since
by the time 3.3 finished there was nothing meaningfully left to verify
live that hadn't already been. What remains from the original 3.5 scope:

- **Documented, not fixed**: a process restart mid-analysis (or
  mid-single-stage-rerun) leaves a `Slideshow` stuck in `queued`/
  `analyzing` status with no automatic recovery - nothing reconciles
  "an AnalysisRun/background task that was interrupted by a crash" back
  to a terminal state on the next startup. This is not a new regression
  from going async: the old synchronous path had the equivalent failure
  mode (a killed request left status wherever the last commit inside the
  stage left it, with the same lack of automatic recovery). Worth a
  startup reconciler eventually (e.g. any `AnalysisRun` with `status=
  pending` older than some threshold at boot time gets marked failed, and
  its `Slideshow`/`Slide` un-stuck) - not implemented now, since it's a
  pre-existing gap, not something this phase introduced, and this is a
  single-user local desktop-style app where a mid-analysis crash-then-
  restart is a rare, recoverable-by-hand ("click Retry again") situation.
  Listed under Suggested Future Improvements at the end of this phase.
- SQLite single-writer contention under concurrent background writes
  across *different* slideshows (not the same-row race the atomic claim
  fixes): reasoned about, not separately load-tested - SQLite serializes
  writer transactions regardless of which row/table they touch, and every
  stage already writes via short, promptly-committed transactions (this
  was already true before Phase 3; nothing here changes each stage's own
  transaction shape). The two live concurrency tests already performed
  (analyze and rerun, each racing two requests against the *same*
  slideshow) exercise this same serialization mechanism, just narrowed to
  the same row - sufficient confidence for this app's realistic
  concurrency level (one local user), not worth a dedicated multi-
  slideshow load test.
- Full backend suite: 72/72 passing (final count, unchanged since 3.3 -
  no code changed in 3.4/3.5). Ruff clean. Frontend `tsc`/`oxlint`/`build`
  clean.

**Phase 3 (async execution boundary) is complete.** `Slideshow.status`'s
`queued`/`analyzing` states are now real, observable, and reachable from
the UI for the first time since they were added in Phase 2 - the whole
point of this phase.

---

## Phase 4: True multi-slide import — detailed plan

**Problem.** Since Phase 2, every `Slideshow` has exactly one `Slide` -
`Slideshow.slide` (the convenience accessor every stage uses) actively
enforces this by raising if it's ever violated. Real TikTok Shop
slideshows have multiple images. The schema (`Slide.slide_index` +
`slideshow_id` FK) has supported N slides since Phase 2.1; nothing has
ever exercised that.

**Scope, grounded in an actual code read (not assumed)**: this phase is
narrower than it first looks. Checked every consumer of the 1:1
assumption before writing this plan:

- `app/services/slideshow_blueprint.py`'s `assemble_slideshow_blueprint`
  **already** does `[_assemble_slide(db, slide) for slide in
  slideshow.slides]` - it iterates every slide, not `slides[0]`. The
  blueprint API is already N-slide-correct today.
- `list_analysis_runs` and `get_slide_file` in the router already operate
  on `slideshow.slides`/an explicit `slide_id`, not the 1:1 accessor.
- The only real blocker is `Slideshow.slide` itself (raises if
  `len(slides) != 1`) and its 6 call sites - one in each stage file,
  always as the very first line of `run()`.
- The import path (`app/services/slideshow_import.py` +
  `app/importers/local_file.py`) only ever produces one `Slide` per
  `Slideshow` - `LocalFileImporter.import_source` returns a flat
  `list[MarketingCreative]`, one per uploaded file, and
  `import_slideshows` maps each 1:1 to its own `Slideshow`.
- `app/storage.py`'s `save_creative_original` is already keyed by the
  Slide's own id, not the Slideshow's - multi-slide storage needs no
  changes.

**Deliberately NOT in scope for this phase** (this is the load-bearing
judgment call, not a blocking ambiguity - see reasoning below): the 6
analysis stages continue operating on a single "primary" slide only, not
looping over every slide. That's genuinely a separate, later concern -
the roadmap already names it as its own phase (Phase 5, "optional multi
per-slide product detection"), which only makes sense as a later phase if
Phase 4 doesn't already do it. Rewriting all 6 stages plus the
orchestrator to loop per-slide is a materially bigger, riskier change
than "let a Slideshow legitimately have N slides" - bundling them would
violate "small, testable, production-safe refactors."

**A real design call made here, not left as an open question**: multi-
file-select in the import UI currently produces N independent Slideshows
(one per file) - this is almost certainly how today's real dev data (4
"independent" slideshow cards, imported close together) came to exist.
Silently changing multi-select to always group into one Slideshow would
retroactively reinterpret that existing behavior and could break the
"bulk-import many unrelated single-image ads at once" use case the tool
already supports. Resolution: keep that default completely unchanged:
add multi-slide grouping as an explicit, additional, opt-in choice (off
by default) - purely additive, matches the same judgment already applied
to storage.py's naming and the slideshow_stages package split.

### 4.1 — Rename/relax `Slideshow.slide` → `Slideshow.primary_slide`

- Rename the property; behavior changes from "raise if `len(slides) !=
  1`" to "return `slides[0]`, raise only if `slides` is empty" (a
  Slideshow should never have zero slides - that invariant stays
  enforced). For every Slideshow that exists today (all still exactly
  1:1, since 4.2 hasn't landed yet), this returns the exact same value as
  before - zero behavior change until multi-slide import actually exists.
- Update all 6 stage files' `slide = slideshow.slide` →
  `slide = slideshow.primary_slide`, and update each stage's own
  docstring/comments that reference `.slide` by name.
- Existing test suite should pass completely unchanged (same values,
  different property name) - this sub-phase's own tests just need one
  new characterization test proving `primary_slide` returns `slides[0]`
  once a slideshow has 2+ slides (impossible to construct via the API
  yet, but constructible directly via the ORM in a test).
- Rollback: revert the rename; nothing else changed.

### 4.2 — Opt-in multi-slide grouping on import

- `import_slideshows` gains a new parameter (e.g. `group_as_one:
  bool = False`). When `True`, all `MarketingCreative`s returned by the
  importer become Slides (`slide_index` 0..N-1) on a single new
  `Slideshow`, instead of N independent Slideshows. Default `False`
  preserves every existing call site and every existing test unchanged.
  `ImportProvider`/`LocalFileImporter` untouched - grouping is a concern
  of `import_slideshows` alone, not the provider interface (no premature
  abstraction for hypothetical future providers' own grouping needs).
- `POST /api/slideshows/import` gains a matching optional form field.
- New tests: grouped import produces one Slideshow with N ordered Slides;
  ungrouped (default) behavior is provably unchanged (existing tests
  already cover this, but add one explicit regression test naming the
  invariant).
- Rollback: revert; default-off means nothing already-imported is
  affected either way.

### 4.3 — Frontend: expose the grouping choice

- `ImportPanel.tsx` gains an explicit, clearly-labeled opt-in control
  (default off) - exact wording/placement decided during implementation,
  not prescribed here.
- `api.ts`'s `importSlideshows` passes the flag through.
- Rollback: revert; backend default already matches old behavior so no
  backend change is needed to roll back the frontend alone.

### 4.4 — Frontend: minimal multi-slide rendering (not a full carousel)

- `SlideshowGrid.tsx`: cards for a multi-slide Slideshow show a small
  indicator (e.g. slide count) alongside the existing single thumbnail -
  explicitly NOT a filmstrip/carousel (that's Phase 7, "frontend
  consolidation" - already named as its own phase in the original plan
  for exactly this reason).
- `SlideshowBlueprintModal.tsx`: currently hardcoded to `blueprint.slides
  [0]` throughout - needs at minimum a slide selector (e.g. "Slide 1 of
  3" with prev/next) so a multi-slide slideshow's per-slide data
  (already returned by the backend, per the scope note above) isn't
  simply invisible in the UI. Still minimal - no redesign of the
  section layout itself, just making which slide's data is showing
  switchable.
- Live-verify: import 2+ real files with grouping enabled, confirm the
  grid badge and modal's slide selector both work against real data.
- Rollback: revert; 4.1-4.3 alone leave grouped multi-slide Slideshows
  importable but with only slide 0's data visible in the UI - degraded,
  not broken (the data itself is safe, GET /blueprint already returns
  it).

**Risks:** none of this touches AI provider calls, migrations, or
existing single-slide behavior - the entire phase is additive/opt-in by
construction. The main risk is scope creep into Phase 5's territory
(actually running stages per-slide) or Phase 7's (a real carousel) -
guarded against explicitly above by naming what's deliberately excluded.

## Phase 4 reports log

### Phase 4.1 — Rename/relax `Slideshow.slide` → `primary_slide` (done)

- Renamed the property, relaxed the guard to "raise only if zero Slides"
  (was "raise unless exactly one"). Updated all 6 stage files' call sites
  plus `slideshow_stages/base.py`'s docstrings.
- Also renamed the same 6 test files' usages (`slideshow_with_slide.
  slide` → `.primary_slide`) - macOS's BSD `sed` silently no-ops on `\b`
  word-boundary patterns (a GNU extension it doesn't support), so an
  initial `sed -E 's/\.slide\b/.../'` pass across the 6 test files did
  nothing and was caught by checking the actual file content rather than
  trusting the exit code - redone with Python's `re` module instead,
  which does support `\b`, confirmed by counting real substitutions per
  file (3/3/3/6/9/8) before proceeding.
- New `tests/test_slideshow_model.py`: 3 tests, including the one new
  behavior no prior test exercised - `primary_slide` returning
  `slides[0]` when a Slideshow genuinely has 2+ Slides (constructed
  directly via the ORM, since the import API can't produce that yet -
  4.2's job).
- Full suite: 75/75 passing (72 + 3 new). Ruff clean (same 10 pre-existing
  F821 false positives, now naming `primary_slide` instead of `slide`).
- Zero behavior change for any Slideshow that exists today - every one is
  still exactly 1:1 until 4.2 lands.
- Commit: (see git log)

### Phase 4.2 — Opt-in multi-slide grouping on import (done)

- `import_slideshows` gained `group_as_one: bool = False`. Factored the
  per-slide persistence logic (create row, flush for an id, save the
  file, set `stored_file_path`) out into a shared `_persist_slide`
  helper used by both the existing 1:1 path and the new grouped path,
  rather than duplicating it.
- Grouped Slideshow's own `source_references_json` can't sensibly carry
  one file's `source_locator`/`raw_metadata` when there are N different
  files - each Slide already carries its own (unchanged); the Slideshow
  level now records just the shared `source_type` and a
  `grouped_slide_count`.
- `POST /api/slideshows/import` gained a matching `group_as_one` form
  field, default `False`.
- New `tests/test_slideshow_import_grouping.py` (4 tests): default
  behavior explicitly proven unchanged (3 files → 3 independent
  Slideshows, both with `group_as_one` unset and explicitly `false`),
  grouped behavior (3 files → 1 Slideshow with 3 ordered Slides, each
  file actually persisted to disk - checked via a follow-up GET of each
  Slide's file, not just the DB rows), and the single-file degenerate
  case.
- Full suite: 79/79 passing (75 + 4 new). Ruff clean.
- Commit: (see git log)

### Phase 4.3 + 4.4 — Frontend: grouping choice + minimal multi-slide rendering (done)

Landed together (both frontend-only, small, and 4.4 is what makes 4.3's
grouped import actually visible - splitting them would leave an
in-between state where a grouped import "succeeds" with no way to see
slides beyond the first).

- `ImportPanel.tsx`: explicit "These are one slideshow" checkbox,
  unchecked by default. `api.ts`'s `importSlideshows` gained a
  `groupAsOne` param passed through as the `group_as_one` form field.
- `SlideshowGrid.tsx`: a small slide-count badge on the thumbnail when a
  card's Slideshow has more than one Slide (still shows only slides[0]'s
  image - a real filmstrip is Phase 7).
- `SlideshowBlueprintModal.tsx`: a "Slide N of M" selector with Prev/Next
  when there's more than one Slide, replacing the hardcoded
  `blueprint.slides[0]`. Selecting a non-primary slide correctly shows
  "Not generated yet" everywhere (the Stages only ever analyze
  `primary_slide` until Phase 5) - not a bug, documented in the
  component's own docstring so it doesn't look like one later.
- Live-verified end-to-end against the real dev server: since the browser
  tool can't drive a real file-picker (a known, pre-existing limitation -
  same substitution used in Phase 2.6), posted a real 3-file multipart
  `group_as_one=true` request via the page's own `fetch` (canvas-generated
  JPEG blobs, not fabricated JSON) - got back one Slideshow with 3 ordered
  Slides (201). Reloaded the page: the grid showed the new card with a
  "3 slides" badge; opening its blueprint modal showed "Slide 1 of 3",
  and clicking "Next →" correctly swapped the hero image, filename, and
  all section content to slide-1.jpg's (empty, as expected). No console
  errors. This left one real grouped-import Slideshow in the dev
  database, consistent with how prior phases' live-data verification
  (e.g. Phase 2.6) was left in place rather than cleaned up.
- Full suite: 79/79 passing (frontend-only change, backend suite
  unaffected). Frontend `tsc`/`oxlint`/`build` clean.
- Commit: (see git log)

**Phase 4 (true multi-slide import) is complete.** A Slideshow can now
genuinely hold more than one Slide, end to end - imported, stored,
returned by the blueprint API, and at least minimally visible in the UI -
while every existing single-file import continues to behave exactly as
before. Per this phase's own explicit scope note, actually running the
analysis Stages per-slide is a later phase's job (renumbered to Phase 6
in the 2026-07-22 roadmap revision - see "Frozen architecture vision"
above), not done here.

---

## Phase 5: Product Intelligence — architecture direction

**Status: direction revised four times by the user on 2026-07-22 (see
revisions #2-#5 below) - each supersedes/refines what came before it.
Detailed sub-phase plan below reflects all four and is ready for
implementation to begin.**

### Standing design principle (2026-07-22, revision #4 - applies throughout implementation, not a one-time change)

The Product Profile is not a UI convenience - it is the canonical
representation of the product that future systems depend on. Every
design decision in Phase 5 (and any later work that touches the profile)
should assume it will be consumed by: the **Generation Engine** (to
preserve immutable product characteristics), the **Validation Engine**
(to compare generated outputs against the canonical product and measure
fidelity), and **future Product Sources** (additional adapters, not
built yet). **Where UI simplicity and profile semantic correctness
conflict, optimize for the profile - the UI can always adapt later.**
This is a standing tiebreaker for judgment calls made *during*
implementation (each sub-phase below), not something that changes the
sub-phase structure itself. One concrete change it does drive now (not
deferred - see 5.2/5.5): field values need enough structure to be
machine-comparable, not just human-readable strings - see below.

### Standing design principle (2026-07-22, revision #5 - vocabulary discipline, applies throughout implementation)

The canonical vocabulary (5.2) should stay intentionally small and
stable. Adapters normalize *into* the existing vocabulary wherever
possible - a new canonical field is added only when it represents a
genuinely new product concept the existing model cannot express, not
because one adapter's source happens to expose a field that doesn't map
cleanly. Long-term value comes from normalization quality, not
vocabulary size - a vocabulary that grows by one field per adapter
stops being canonical at all.

**Concrete consequence - exactly two destinations for anything an
adapter extracts, no third option**: it either maps to an existing
canonical field, or it goes into `ProductSourceImport.raw_response_json`
(5.1 - already planned to be kept, not discarded) and stays there. No
semi-structured "extras" bucket gets added as an escape hatch - that
would just relocate the same sprawl the vocabulary itself is meant to
avoid. Adding a genuinely new canonical field stays possible, but should
be rare and deliberate, not a per-adapter default.

**Illustrative example** (not a real finding - no TikTok Shop research
has happened yet, see 5.4): a marketplace listing is more likely than a
generic product page to expose data that *isn't* a product attribute at
all - shop rating, units sold, review count. That's marketplace
metadata, not something the Product Profile should model even as a new
field - it stays in `raw_response_json` or gets dropped, regardless of
how source-specific or "new" it looks.

**Concrete effect on 5.2's initial vocabulary**: seeded from exactly the
fields already named across this conversation, not speculatively
expanded - immutable: brand, product/category type, shape, dimensions,
capacity, materials, colors, labels/branding text, packaging;
contextual: camera/viewing angle, composition, lighting, background,
props, marketing context/emotional positioning. The vocabulary module's
own docstring records this discipline directly (map into existing fields
first; new fields are rare and deliberate; unmapped data goes to
`raw_response_json`, never a new field just to fit it in) so it's
visible to whoever - including a future me - touches this file next, not
only recorded in this planning doc.

**Problem.** `ProductLockProfile` is currently the only thing resembling
Product Intelligence, and it's a single AI-vision-derived blob: one
evidence source (crops from `slideshow.primary_slide`), no per-field
provenance, no confidence, wholesale-replaced on every regeneration
(`is_current` flips old→false). The goal is a canonical Product Profile
built by combining multiple evidence sources, each attribute individually
tagged with where it came from, how trustworthy that source is, and
whether it's expected to stay fixed or vary between creatives.

### 2026-07-22 revision #2: Product Source adapters, not "URL importers"

The first-pass direction (below, kept for its still-valid reasoning
about artifacts/merge/`ProductReferenceImage`) treated "import a product
URL" as a single, monolithic, platform-agnostic code path. The user
refined this: Product Intelligence should think in terms of **Product
Sources** (TikTok Shop listing, Shopify store, Amazon listing, brand
website, user-uploaded references, creator slideshows, future generated
images) - each exposing a **common normalized model** to Product
Intelligence. The Product Intelligence layer should never need to know
which platform an attribute came from; that translation belongs inside
the Product Source adapter, not the merge layer. This also explicitly
**revises the prior instruction** not to build dedicated platform
integrations yet: the first production-quality adapter should prioritize
TikTok Shop (the application's primary use case), with the generic
schema.org/OpenGraph path demoted from "the only path" to "the fallback
for any other supported URL."

**What this changes structurally**: normalization moves from the merge
layer (first-pass 5.3, "map each evidence source into canonical fields
at read time") to each adapter's own boundary (map to canonical fields
at *extraction* time). This is a real improvement, not just a rename -
it means the merge/profile-assembly service never sees a platform-
specific shape at all, only already-normalized evidence, which is
exactly what "Product Intelligence should never need to know whether an
attribute originated from TikTok Shop, Shopify, or Amazon" requires.

**Closest existing precedent, more so than `app/importers/`'s single-
provider-today `ImportProvider`**: `app/ai_providers/` - a `Protocol`
per capability, multiple concrete adapters, a registry keyed by config,
and every adapter normalizing into the *same* response shape regardless
of which underlying provider produced it. Two real adapters exist from
day one here (TikTok Shop + generic fallback), so - unlike the first-pass
reasoning, which correctly avoided building a registry for exactly one
implementation - the registry/Protocol pattern is now justified, not
premature.

**Honest technical caveat, not glossed over**: TikTok Shop's public
listing pages are very likely a JavaScript-rendered SPA, not
server-rendered HTML with embedded schema.org markup (which is why the
generic fallback path - simple HTTP GET + HTML parse - works well for
many Shopify-style storefronts but may not work at all for TikTok Shop).
Whether a production-quality TikTok Shop adapter needs headless-browser
rendering, reverse-engineered internal API calls (fragile, ToS-risk), or
TikTok Shop's official Partner/Open API (most robust, but scoped to
authenticated sellers managing their own shop in a lot of marketplace
APIs - not yet confirmed this supports arbitrary third-party listing
lookup by URL) is **not known yet** - no research has been done, and
none should be assumed. This is why the TikTok Shop sub-phase below
starts with an explicit investigation step before any extraction code is
written, rather than a confident implementation plan.

**Sequencing consequence**: build the shared Product Source contract and
the generic fallback adapter *first* (lower-risk, well-understood
mechanism, needed as the safety net regardless of what TikTok Shop
turns out to require), then tackle TikTok Shop as an explicitly
higher-uncertainty, separately-scoped sub-phase - so real Product
Intelligence capability ships via the generic path even if TikTok
Shop's mechanism takes longer to pin down.

### 2026-07-22 revision #3: semantic classification is part of the field, not inferred

One more refinement before implementation begins: every canonical field
in `CANONICAL_FIELD_VOCABULARY` (5.2) now *requires* a semantic
classification - `immutable` (a physical product attribute: brand,
dimensions, labels, packaging, colours, shape, etc.) or `contextual`
(creative information expected to vary between creatives: lighting,
composition, camera angle, props, background, emotional positioning,
etc.) - declared by the vocabulary itself, not inferred later from which
source happened to win a merge conflict. `ProductProfileField` (5.5) now
carries this `classification` as a real, visible output field alongside
`value`/`source`/`confidence` - not just an internal detail the merge
layer consults. This is what lets a future Generation/Validation engine
distinguish "must never change" attributes from "expected to vary"
ones directly from the profile, without re-deriving the distinction
itself. Purely additive to this not-yet-implemented phase's own design -
nothing in Phases 0-4 is touched. See 5.2 and 5.5 below for the concrete
mechanics.

### First-pass direction (2026-07-22, revision #1) - still valid where not superseded

- **New evidence artifact** (renamed in revision #2 - see 5.1 below):
  same shape discipline as every other artifact (id/is_current/
  created_at), owned by `product_id`. **Not** forced through the
  existing `AnalysisRun` table - that model requires non-nullable
  `provider`/`model_name` (AI-call-specific); a URL fetch isn't an AI
  call. Worth a small, parallel, purpose-built traceability record
  instead.
- **Canonical profile as compute-on-read**: e.g. `assemble_product_profile
  (db, product) -> ProductProfile`, mirroring `assemble_slideshow_
  blueprint` exactly - merges every current evidence artifact for a
  product into a field-level `{value, source, confidence}` view at read
  time, not a new persisted/versioned entity. Still correct in revision
  #2 - only the *input* to this merge changes (already-normalized
  evidence, not raw platform-specific data). Field-level provenance is
  what makes this generation-ready later - a future "compare generated
  image against the profile, score fidelity per field" step needs
  exactly this granularity.
  - Merge/precedence logic (which source wins per field) - e.g. official
    listing wins for immutable physical facts (shape, dimensions,
    capacity, labels, branding, colors, packaging), slideshow evidence
    wins for what listings can't capture (camera angle, composition,
    lighting, marketing context) - still lives in the merge layer, not
    by changing `ProductLockProfile`'s existing schema.
- **Extend, don't replace, `ProductReferenceImage`**: it already has
  nullable `source_creative_id`/`source_slide_id` for exactly this
  "which provenance" pattern (Phase 2.3's transitional design). A new
  nullable `source_product_source_import_id` extends the same pattern
  for officially-sourced images rather than inventing a separate image
  concept.

**Prospective adjustments this implies for future code (none touch
already-completed Phase 2-4 work):**
- The Product Lock Profile Stage doesn't currently emit per-field
  confidence at all (today's schema is facts only). Getting real
  per-field confidence out of the vision model is new work this phase
  needs to design, not something already available.
- Once a canonical profile exists, Recreation Prompt should eventually
  read from it instead of `ProductLockProfile` directly, for better
  fidelity on immutable facts. Flagged as a fast-follow within this
  phase, not a blocker to starting it.
- `ProductManager.tsx`'s existing "View Analysis" panel currently shows
  `ProductLockProfile.structured` as if it were settled fact - once a
  canonical profile exists, this should show it as one evidence source
  among several (e.g. "Slideshow-derived, 96% confidence"), not
  something to change until this phase's own frontend sub-phase.

## Phase 5: Product Intelligence — detailed sub-phase plan

**Problem** (same as above, restated for this section's self-
containment): build a canonical, multi-source Product Profile with
field-level provenance/confidence, without redoing any completed work.

### 5.1 — Additive schema: `ProductSourceImport` + `ProductReferenceImage` extension

- New model `ProductSourceImport` (renamed from the first-pass
  `ProductUrlImport` - "source," not "URL," now that TikTok Shop and the
  generic fallback are both adapters behind one concept): `id,
  product_id (FK), is_current, source_type (plain string - "tiktok_shop"
  | "generic_url" today, extensible without a migration), source_url,
  fetch_status ("succeeded"|"partial"|"failed"), error (nullable),
  raw_response_json (whatever the adapter's underlying fetch actually
  returned - kept for debugging/reprocessing if normalization logic
  improves later, not discarded), normalized_json (the common
  normalized shape - see 5.2 - this is what everything downstream
  actually consumes), created_at`.
  - Storing both raw and normalized (not just normalized) is a
    deliberate choice: if the canonical vocabulary or an adapter's
    mapping logic needs fixing later, the raw evidence is still there to
    reprocess without re-fetching.
  - Still not built on `AnalysisArtifactMixin`/`AnalysisRun` - same
    reasoning as the first pass.
- `ProductReferenceImage` gains a new nullable
  `source_product_source_import_id` FK (third provenance column,
  alongside the existing `source_creative_id`/`source_slide_id`).
- Alembic migration (additive only). New model-level tests only.
- **DB/schema changes**: two additive changes, no data migration needed.
- **Rollback**: downgrade the migration; nothing else references the new
  table/column yet.
- **Expected commit size**: small.

### 5.2 — Shared Product Source contract (Protocol + normalized model + registry, no adapters yet)

- `app/product_sources/base.py`: `ProductSourceAdapter` Protocol -
  `matches(url: str) -> bool` (can this adapter handle this URL) and
  `extract(url: str) -> NormalizedProductEvidence` (do the fetch +
  normalize). Mirrors `app/ai_providers/base.py`'s per-capability
  Protocol pattern.
- The canonical field vocabulary (which fields exist, and which source
  type each is preferred from during merge) moves here, since it's now a
  *shared contract* every adapter normalizes into, not something the
  merge layer infers after the fact.
  - **Governed by revision #5's vocabulary discipline** (see above): the
    initial field list is exactly the fields already named across this
    conversation - deliberately not expanded speculatively to anticipate
    every field a future adapter might someday expose. Adding a field
    later is a rare, deliberate act requiring a genuinely new product
    concept, not a per-adapter convenience.
  - **Refinement (2026-07-22, revision #3)**: the vocabulary is also
    where each field's **semantic classification** - `immutable` (a
    physical product attribute: brand, dimensions, labels, packaging,
    colours, shape, etc.) or `contextual` (creative information expected
    to vary between creatives: lighting, composition, camera angle,
    props, background, emotional positioning, etc.) - is declared, as a
    required property of the field definition itself, not inferred at
    merge time or left as an implicit side effect of "which source type
    is preferred." Concretely: `CANONICAL_FIELD_VOCABULARY: dict[str,
    FieldDefinition]` where `FieldDefinition` is a small, mandatory-
    fields dataclass/NamedTuple (`classification: Literal["immutable",
    "contextual"]`, plus the existing preferred-source-type
    classification) - declaring a new canonical field without a
    classification should be a type error, not a silent gap, so "defined
    by the vocabulary" is enforced, not just documented convention.
  - This is purely additive to the phase's own not-yet-implemented
    design (5.2 hasn't been built yet) - no completed work (Phases 0-4)
    touches this vocabulary, and nothing here changes `ProductLockProfile`
    or any other existing model.
  - **Refinement (2026-07-22, revision #4 - standing design principle)**:
    a field's `value` is not a bare string. The Validation Engine's whole
    job is comparing a generated output against the canonical product
    and measuring fidelity - comparing free-text strings ("red" vs.
    "crimson") is fragile in a way comparing structured values isn't. A
    small, closed `ProductAttributeValue` union (not an open-ended type
    system - exactly the shapes implied by the fields already discussed:
    `TextValue{text}`, `DimensionValue{length, width, height, unit}`,
    `ColorValue{label, hex}` (both a human label and a machine-comparable
    hex/RGB where extractable - a Validation Engine needs the latter, a
    human reading the profile needs the former, neither alone is
    enough), `NumberValue{value, unit}`, `ListValue{items}`) replaces a
    bare string/`Any`. The vocabulary declares which shape each canonical
    field expects, so every adapter normalizing into e.g. `"color"`
    produces the same shape regardless of source - which is also what
    keeps this consistent for *future* Product Source adapters (the
    third consumer named in the standing principle above): a new adapter
    knows exactly what shape to produce for each field it can populate,
    not by convention but by the vocabulary's own declared type. Exact
    per-field type assignment (which of the five shapes each canonical
    field uses) is implementation-time work for this sub-phase, not
    exhaustively enumerated here.
- `NormalizedProductEvidence` schema: `source_type, source_url, title,
  brand, images: list[NormalizedProductImage]` (`url`/bytes + role),
  `attributes: dict[str, NormalizedAttribute]` (canonical field name ->
  `{value: ProductAttributeValue, confidence}` - classification is *not*
  repeated here, since it's a property of the canonical field name
  itself, looked up from the vocabulary once at final profile assembly
  (5.5), not duplicated across every adapter's per-source output),
  `variants` (loosely typed for v1 - not over-specified before real
  adapters exist to validate the shape against).
- `app/product_sources/registry.py`: `PRODUCT_SOURCE_ADAPTERS: list[type
  [ProductSourceAdapter]]`, most-specific-first (TikTok Shop before the
  generic fallback), `get_product_source_adapter(url) -> 
  ProductSourceAdapter` - iterates the list, returns the first
  `matches()` hit. The generic fallback's `matches()` always returns
  `True`, so it's naturally the catch-all as long as it's last in the
  list.
- **No concrete adapters in this sub-phase** - contract and dispatch
  only, exercised by tests using a trivial fake adapter, not a real one
  yet.
- **Test strategy**: registry dispatch tests (URL matching a specific
  adapter, URL falling through to the generic catch-all, unknown/
  malformed URL handling).
- **Rollback**: revert the two new files; nothing depends on them yet.
- **Expected commit size**: small-medium.

### 5.3 — Generic fallback adapter (schema.org / OpenGraph / page metadata)

- Built before TikTok Shop deliberately (see "Sequencing consequence"
  above) - the well-understood mechanism, and the permanent safety net
  for "any other supported URL" regardless of what TikTok Shop's
  adapter ends up needing.
- New dependencies: `httpx` (promote from transitive to direct) and
  `beautifulsoup4` for HTML parsing (JSON-LD `<script
  type="application/ld+json">`, OpenGraph `<meta property="og:...">`,
  basic `<title>`/`<meta name="description">` fallback).
- `app/product_sources/generic.py`: implements `ProductSourceAdapter`.
  Bounded fetch (timeout + response-size limit - fetching arbitrary
  user-supplied URLs is real abuse-surface even in a local single-user
  app). Normalizes whatever it finds into `NormalizedProductEvidence`
  directly - no separate raw-to-canonical mapping step elsewhere.
  `matches()` always `True` (the catch-all). Follows revision #5's
  discipline: schema.org's own standard Product properties (name, brand,
  color, material, etc.) map onto the existing vocabulary field-for-
  field in the common case - anything schema.org exposes that doesn't
  map stays in `raw_response_json`, it doesn't become a reason to add a
  new canonical field on this adapter's say-so alone.
- `app/services/product_source_import.py`: `import_product_source(db,
  product_id, url) -> ProductSourceImport` - resolves the adapter via
  5.2's registry, calls `extract()`, persists both `raw_response_json`
  and `normalized_json`, downloads any discovered images into
  `ProductReferenceImage` rows. On any failure, records
  `fetch_status="failed"`/`error` rather than raising - the established
  "the artifact records the attempt, including failures" discipline.
- **Test strategy**: no real network calls - mock the HTTP transport,
  feed fixture HTML (schema.org JSON-LD fixture, OpenGraph-only fixture,
  no-markup fixture, unreachable-URL case, oversized-response case).
- **Rollback**: revert; the registry in 5.2 simply has no adapters
  registered, `import_product_source` has nothing to resolve to.
- **Expected commit size**: medium.

### 5.4 — TikTok Shop adapter: investigation spike (done) - hard stop, no adapter built

**Spike findings (2026-07-22), grounded in actually fetching real TikTok
Shop pages, not assumed:**

- Fetched `https://shop.tiktok.com/us/c` (category browsing) directly:
  the entire visible page content is a single heading, "Security Check"
  - no product data, no navigation, nothing else.
- Found a real, currently-shared individual product URL
  (`https://shop.tiktok.com/view/product/1729401937517121187`, sourced
  from a public social-media share, not fabricated) and fetched it
  directly too: identical result - "Security Check," no product title,
  price, images, description, JSON-LD, or any embedded JSON of any kind.
  This rules out the more optimistic hypothesis (that category pages are
  gated but individual product detail pages might be server-rendered for
  SEO, common on many e-commerce sites) - both hit the same wall.
- Independent, third-party corroboration: a commercial TikTok Shop
  scraper (Apify's "TikTok Shop Scraper") documents that its trending-
  products feature is slow specifically because "it need[s] to bypass
  TikTok's captcha." A separate paid scraping-infrastructure vendor
  (Bright Data) offers a dedicated `web_data_tiktok_shop` tool. Both are
  strong signals that this is active, general-purpose anti-bot defense,
  not an artifact of this session's specific fetch.
- Checked the credentialed path too, not just assumed it would solve
  this: TikTok Shop's Partner Center API requires a Partner Center
  account, app registration, **and OAuth authorization from the specific
  shop owner** whose data is being accessed. This is a seller-managing-
  their-own-shop API, not a general "look up any public product by URL"
  API - even with credentials, it would only ever cover shops the user
  themselves operates, not the general case (competitor listings,
  inspiration products, arbitrary creator-shared links) the schema.org
  fallback handles for every other platform. Worth stating plainly: **API
  credentials would not actually deliver the original ask** (paste any
  TikTok Shop URL, get evidence) - only a narrower one (pull data for a
  shop the user owns).

**Conclusion: hard stop, per the standing authorization's explicit
scenario for exactly this outcome.** Plain HTTP + parsing does not work
(confirmed, not assumed) - both the category and product-detail cases
are blocked by an active anti-bot wall, matched by independent evidence
that bypassing it is itself the hard part serious commercial scrapers
build entire products around. A headless browser alone is not a
confident fix either, for the same reason (bot-detection systems
commonly fingerprint headless browsers too) - evaluating that path
further would mean evaluating CAPTCHA-bypass/proxy infrastructure, which
is a real cost and ToS decision, not a coding one. The credentialed
official-API path exists but doesn't solve the general problem even if
pursued.

**No `TikTokShopAdapter` was built.** A stub that attempts the same
blocked fetch and fails would add ceremony without adding real
capability - functionally identical to what already happens today: a
TikTok Shop URL falls through to `GenericUrlAdapter` (nothing in
`PRODUCT_SOURCE_ADAPTERS` currently claims TikTok Shop domains
specifically), which will itself hit the same wall and correctly record
a `fetch_status=FETCH_STATUS_FAILED` `ProductSourceImport` - the
existing, already-tested failure path, not a crash. This is the
documented "degrade to the generic adapter" fallback the plan called for
if this scenario occurred, not a new behavior to build.

**No code changes in this sub-phase** - investigation and documentation
only, per the standing authorization's explicit instruction not to
attempt a workaround. If a real path forward emerges later (the user
obtains and wants to use their own shop's Partner API credentials, or
decides a paid anti-bot-bypass/proxy service is worth the cost and ToS
tradeoff), that's a fresh design decision for the user to make
explicitly - not something to revisit unprompted.

~~If plain HTTP + parsing turns out sufficient... a `TikTokShopAdapter`
alongside `generic.py`...~~ (superseded by the spike above - kept
struck through, not deleted, so the reasoning that was here before the
spike ran stays visible for anyone re-reading this history):

- Registered *before* the generic fallback in 5.2's adapter list
  (`matches()` on TikTok Shop domains specifically), so TikTok Shop URLs
  get the purpose-built adapter and everything else still falls through
  to generic.
- **Test strategy**: depends entirely on the spike's outcome - fixture-
  based if HTML/JSON parsing, mocked-API-response-based if the official
  API path, mocked-rendered-DOM if headless-browser. Cannot be fully
  specified before the spike runs.
- **Rollback**: revert; TikTok Shop URLs simply fall through to the
  generic adapter (degraded, not broken - it just won't extract as much
  from a JS-heavy page).
- **Expected commit size**: unknown until the spike - flag this
  explicitly rather than guessing a size for unresearched work.

**Actual outcome**: zero code. Commit is documentation-only (this
section itself), matching "no workaround" rather than any commit size
estimate above, which assumed code would be written.

### 5.5 — Canonical merge / profile assembly service

- Simpler than the first-pass version now that adapters normalize at
  the boundary (5.2/5.3/5.4) - this layer only does precedence
  resolution across already-normalized sources, no field-mapping.
- New Pydantic schema `ProductProfile` (`fields: dict[str,
  ProductProfileField]`, `ProductProfileField = {value:
  ProductAttributeValue, source_type, source_id, confidence,
  classification}` - `value` reuses 5.2's typed union, not a bare
  string, for the same reason: this response is what the Validation
  Engine eventually diffs a generated output against, and a structured
  `ColorValue{hex}` is comparable in a way a free-text string isn't).
  - **Refinement (2026-07-22, revision #3)**: `classification`
    (`"immutable"` | `"contextual"`) is a real, visible field on every
    `ProductProfileField` in the API response - not just an internal
    detail the merge layer consults to pick a winner. Populated by a
    direct lookup into 5.2's `CANONICAL_FIELD_VOCABULARY` for that
    field's name at assembly time - never inferred from which source
    won, never computed per-request. This is what lets a future
    Generation/Validation engine (or the UI) filter/distinguish "must
    never change" attributes from "expected to vary between creatives"
    ones without re-deriving that distinction itself.
- `app/services/product_profile.py`: `assemble_product_profile(db,
  product) -> ProductProfile` - reads the current `ProductLockProfile`
  (mapped into the same canonical vocabulary - the one existing evidence
  source that isn't a `ProductSourceImport`, still needs its own mapping
  step here since it predates this phase) and every current
  `ProductSourceImport` for the product, resolves conflicts per 5.2's
  preferred-source-type-per-classification rule (immutable fields prefer
  listing/URL evidence, contextual fields prefer slideshow evidence),
  and stamps each resulting field with its classification from the
  vocabulary. Compute-on-read, mirroring `assemble_slideshow_blueprint`.
- **Known simplification, flagged rather than solved here**: the Product
  Lock Profile Stage doesn't emit per-field confidence today. Start with
  a flat, documented default confidence per source type (e.g. vision
  evidence = 0.85, a successfully-normalized adapter field = 0.98) -
  real per-field confidence from the vision model is a reasonable
  fast-follow, not a prerequisite.
- **Test strategy**: unit tests per merge scenario (single source,
  agreeing sources, disagreeing sources - confirm documented precedence
  wins, no sources - field absent, not a crash).
- **Rollback**: revert the file; nothing calls it yet.
- **Expected commit size**: medium.

### 5.6 — API surface

- `POST /api/products/{id}/source-import` - accepts a URL, resolves the
  adapter automatically via 5.2's registry (the user never picks a
  platform manually - matches "Product Intelligence should never need to
  know" at the ingestion boundary too), triggers 5.3/5.4's extraction.
  Runs synchronously (a deliberate departure from Phase 3's backgrounded
  pattern - a single fetch+parse isn't the same operation shape as a
  multi-provider AI pipeline; revisit if real-world latency proves
  otherwise).
- `GET /api/products/{id}/profile` - returns 5.5's assembled
  `ProductProfile`, serializing `ProductAttributeValue`'s full typed
  structure (e.g. `ColorValue{label, hex}`), not a flattened display
  string - the API is the Generation/Validation Engine's future contract
  as much as it's the frontend's, per the standing design principle
  above; the frontend can flatten for display, the API response
  shouldn't pre-flatten on its behalf.
- New route-level tests (success, failure surfaced correctly, 404 for
  unknown product).
- **Rollback**: revert the two routes independently.
- **Expected commit size**: small.

### 5.7 — Frontend: submit a source URL + view the profile with provenance

- `ProductManager.tsx`'s existing "View Analysis" panel gains a URL
  input + submit control (no platform picker - the backend resolves the
  adapter), and a new profile view rendering each canonical field's
  value/source/confidence/classification (replacing today's raw
  `<pre>{JSON.stringify(lockProfile.structured)}</pre>` dump for this
  purpose).
- **Applying the standing design principle here**: render each typed
  `ProductAttributeValue` shape appropriately (e.g. a color swatch next
  to the hex for `ColorValue`, not just its label) rather than
  collapsing every value to a display string before it reaches the
  component - if a future sub-phase needs a change here, it should be
  because the UI wants to show the existing structure differently, not
  because the structure was flattened away in 5.5/5.6 to make this
  sub-phase easier.
- Live-verify against both a real TikTok Shop listing URL and a real
  generic-fallback-eligible URL (genuine URLs, not fabricated) - same
  live-server discipline used for every other phase's frontend
  sub-phase.
- **Rollback**: revert; backend keeps working with a client that doesn't
  expose the new capability.
- **Expected commit size**: medium.

**Risks**: fetching arbitrary user-supplied URLs is new I/O surface
(timeouts, oversized responses, malformed/hostile HTML, SSRF-shaped
concerns even locally) - 5.3's bounds are the mitigation for the generic
path; 5.4's mechanism (and therefore its own risk profile) is unknown
until its spike runs. Field vocabulary/classification (5.2) is a
judgment call with room to be wrong in ways that only show up with real
product data - expect to revisit it as real profiles get built.

## Phase 5 reports log

### Phase 5.1 — Additive schema (done)

- New `ProductSourceImport` model (`app/models/product_source_import.py`)
  - not built on `AnalysisArtifactMixin`, same reasoning documented in
  the plan (a URL fetch isn't an AI analysis run). `ProductReferenceImage`
  gained `source_product_source_import_id` (third provenance column).
- **Real gap found during implementation, not anticipated in the
  plan's prose**: `ProductReferenceImage` uses `AnalysisArtifactMixin`,
  which requires a non-nullable `analysis_run_id`. A URL-sourced
  reference image has no `AnalysisRun` to point at - same problem
  `ProductSourceImport` itself was designed around, but the plan's "just
  add a nullable provenance column" description didn't account for the
  *existing* non-nullable column that would block inserting such a row
  at all. Fixed precisely: overrode `analysis_run_id` to nullable on
  `ProductReferenceImage` specifically (SQLAlchemy declarative lets a
  subclass shadow a mixin's column), leaving the mixin itself - and
  every other artifact type using it - untouched.
- Migration `37e53bed7ec8`: full discipline applied - real dev DB backed
  up first, `upgrade()`/`downgrade()` both tested on an isolated scratch
  copy (`CAE_DATA_DIR`) before touching the real DB, content-diff
  verified byte-for-byte identical data before and after (all 4 existing
  `product_reference_images` rows, plus row counts on 5 other tables).
  One benign finding: the round-tripped schema's `CREATE TABLE` text
  differs cosmetically (FK constraint declaration order) from the
  original - a known SQLite batch-mode artifact (Alembic rebuilds the
  table under the hood), not a real difference; data and all column
  definitions confirmed identical regardless.
  Applied to the real dev DB and re-verified the same way.
- 4 new model-level tests (`tests/test_product_source_import_model.py`),
  mirroring `test_slideshow_model.py`'s style for Phase 4.1's equivalent
  additive-schema change.
- Full suite: 82/82 passing (78 existing + 4 new). Ruff clean. App boots
  cleanly with the new model registered.
- Zero behavior change to anything existing - purely additive schema.
- Commit: (see git log)

### Phase 5.2 — Shared Product Source contract (done)

- New `app/product_sources/` package: `base.py` (the `ProductAttributeValue`
  discriminated union - `TextValue`/`DimensionValue`/`ColorValue`/
  `NumberValue`/`ListValue`, tagged by a `kind` literal field so
  `NormalizedAttribute.value` resolves to the right concrete type from
  raw dict data, not just accepts anything; `CANONICAL_FIELD_VOCABULARY`;
  `NormalizedProductEvidence`/`NormalizedAttribute`/
  `NormalizedProductImage`; `ProductSourceAdapter` Protocol) and
  `registry.py` (`PRODUCT_SOURCE_ADAPTERS` + `get_product_source_adapter
  (url)`, dispatch by `matches()`, most-specific-first).
- **One simplification made during implementation, reasoned through
  explicitly rather than following the plan's prose literally**: the
  plan's `FieldDefinition` mentioned "preferred-source-type-per-
  classification" as its own vocabulary property. Implemented without
  it - with exactly two evidence categories today (URL-sourced,
  vision-sourced), "prefer listing evidence for immutable fields, vision
  evidence for contextual ones" already follows directly from
  `classification` alone; storing it a second time per field would be
  exactly the vocabulary bloat revision #5 exists to prevent. Noted in
  `base.py`'s own comment for whoever builds 5.5's merge service.
- Seeded the vocabulary with exactly the 15 fields named across the
  Phase 5 planning conversation (9 immutable, 6 contextual) - a test
  (`test_vocabulary_seeded_from_exactly_the_fields_already_named`)
  pins this down explicitly, so an accidental future expansion shows up
  as a failing test, not a silent drift.
- `images: list[NormalizedProductImage]` on the evidence shape carries
  URLs only, not raw bytes - downloading is 5.3's `import_product_
  source` service's job, keeping `extract()` a pure fetch+parse
  contract adapters don't each have to duplicate.
- **No concrete adapters yet** - `PRODUCT_SOURCE_ADAPTERS` is
  deliberately empty; a real call to `get_product_source_adapter` would
  correctly raise until 5.3 registers the generic fallback. Registry
  dispatch tests use two trivial fake adapters defined locally in the
  test file.
- 13 new tests: typed-value round-trip/discrimination, confidence bounds
  (0.0-1.0) enforced, vocabulary composition pinned down, `validate_
  attribute_value` accepts matching shapes and rejects both mismatched
  shapes and unknown field names, evidence defaults are empty collections
  not `None`, registry dispatch (specific match, generic fallback,
  unmatched-URL error path), and one test documenting the real registry
  is still empty.
- Full suite: 95/95 passing (82 existing + 13 new). Ruff clean (same 10
  pre-existing F821 false positives as always - SQLAlchemy string
  forward-refs, unrelated to this sub-phase). App boots cleanly.
- Zero behavior change to anything existing - new package, nothing
  wired up to it yet.
- Commit: (see git log)

### Contract fix (done, between 5.2 and 5.3)

`ProductSourceAdapter.extract()` changed from returning
`NormalizedProductEvidence` alone to `ProductSourceExtraction{raw,
normalized}` - a real gap found while starting 5.3, not caught when 5.2
was written: `ProductSourceImport.raw_response_json` (5.1) needs the raw
fetch result, and the original signature would have forced either a
second fetch per URL or some other way to smuggle raw data out. Fixed
before any adapter was built on top of it. Separate commit, not folded
into 5.2's (already pushed to this branch) or 5.3's.

### Phase 5.3 — Generic fallback adapter (done)

- `app/product_sources/generic.py`: `GenericUrlAdapter` -
  schema.org JSON-LD first (including `@graph`-bundled JSON-LD, a common
  real-world pattern), OpenGraph/page-`<title>` fallback if no JSON-LD
  `Product` block is found. Bounded fetch (10s timeout, 5MB response cap,
  streamed so the cap is enforced during download, not after). Injectable
  `httpx.BaseTransport` in the constructor so tests never hit real
  network.
- `app/services/product_source_import.py`: `import_product_source(db,
  product_id, url)` - resolves the adapter via the registry, persists
  both raw and normalized data, downloads discovered images into
  `ProductReferenceImage` rows (`isolation_method="product_url"`,
  `analysis_run_id=None`). Any failure (unreachable URL, adapter error)
  records a `ProductSourceImport` with `fetch_status=FETCH_STATUS_FAILED`
  and the error message rather than raising - the same "the artifact
  records the attempt" discipline used everywhere else. A single image
  failing to download does not fail the whole import - it's just
  skipped, since the primary value is the structured evidence, images
  are secondary enrichment (documented as a deliberate choice, not an
  oversight).
- `GenericUrlAdapter` registered in `PRODUCT_SOURCE_ADAPTERS` (the list
  was empty since 5.2) - the one existing "registry is still empty" test
  from 5.2 was replaced with one asserting the generic adapter stays
  *last*, so Phase 5.4 registering TikTok Shop in the wrong position
  would fail loudly rather than silently misrouting TikTok Shop URLs to
  the generic adapter.
- New dependencies added to `requirements.txt`: `httpx==0.28.1` (was
  already present transitively via FastAPI's stack, promoted to direct)
  and `beautifulsoup4==4.15.0` (new).
- **Test strategy exactly as planned**: no real network calls anywhere.
  `GenericUrlAdapter`'s own parsing tested via `httpx.MockTransport` with
  fixture HTML (schema.org JSON-LD, `@graph`-bundled JSON-LD, OpenGraph-
  only, no-markup, malformed-JSON-LD-still-falls-back, unreachable URL,
  4xx status, oversized response). `import_product_source`'s
  orchestration tested against a fake adapter (fast, no HTTP mocking
  needed for adapter resolution - that's what
  `test_generic_product_source_adapter.py` already covers); its own
  image-download logic tested separately with a real `MockTransport`,
  including the "one image fails, import still succeeds" path.
- 25 new tests across 3 files (9 adapter, 7 service, 9 updated/added in
  the base/registry file - one from 5.2 replaced, not just added to).
  Full suite: 111/111 passing (96 existing + entries above). Ruff clean
  (same 10 pre-existing F821 false positives, unrelated). App boots
  cleanly.
- Zero behavior change to anything existing - `import_product_source`
  has no caller yet (that's 5.6's job); purely additive.
- Commit: (see git log)

### Phase 5.4 — TikTok Shop adapter: investigation spike (done, hard stop)

- Fetched `https://shop.tiktok.com/us/c` (category page) and a real,
  currently-shared individual product URL
  (`https://shop.tiktok.com/view/product/1729401937517121187`) directly.
  Both return only a "Security Check" wall - no product data, no
  JSON-LD, no embedded JSON, nothing to parse.
- Corroborated independently (not just this session's own fetch): a
  commercial TikTok Shop scraper documents needing to "bypass TikTok's
  captcha"; a separate scraping-infrastructure vendor sells a dedicated
  tool for exactly this platform. Checked the credentialed path too:
  TikTok Shop's Partner API requires OAuth authorization from the
  specific shop owner being queried - a seller-manages-their-own-shop
  API, not a general "look up any product by URL" one, so it wouldn't
  actually deliver the original capability (arbitrary TikTok Shop URLs)
  even if pursued.
- **Conclusion: hard stop, exactly the scenario the standing
  authorization anticipated.** No workaround attempted (no headless-
  browser CAPTCHA-bypass, no reverse-engineered internal endpoints). No
  `TikTokShopAdapter` built - a stub that fails the same way
  `GenericUrlAdapter` already does for TikTok Shop URLs would add
  ceremony without adding capability. TikTok Shop URLs correctly fall
  through to the generic adapter today (already true, not a new change)
  and correctly record a failed `ProductSourceImport` via the
  already-tested failure path - degraded, not broken.
- Zero code changes - investigation and documentation only. Full detail
  in the "5.4" section above, including exactly what was checked and
  why the credentialed path doesn't fully solve this either.
- Commit: (see git log)

### Phase 5.5 — Canonical merge / profile assembly service (done)

- `app/services/product_profile.py`: `assemble_product_profile(db,
  product) -> ProductProfile` - compute-on-read, mirroring
  `assemble_slideshow_blueprint`. Merges the current `ProductLockProfile`
  and current `ProductSourceImport` for a product into one field-level
  `ProductProfileField{value, source_type, source_id, confidence,
  classification}` view.
- Precedence resolved exactly as base.py's comment described: `winner =
  (source or vision) if immutable else (vision or source)` - a one-line
  rule, confirming the earlier decision not to store "preferred source
  type" separately in the vocabulary was correct; falls back to whichever
  side actually has the field when the preferred one doesn't (tested
  explicitly, not just assumed).
- `ProductLockProfile` needed its own mapping into the canonical
  vocabulary (the one evidence source that predates it) - documented
  every field's fate individually: `product_category`,
  `shape_and_proportions`→`shape`, `packaging.{type,closure,notes}`
  joined→`packaging`, `materials`, `colors.primary[0]`→`color` (a
  list-to-single-value simplification, noted inline, not silent),
  `branding.brand_name`→`brand`, `labels_and_text[].text`→
  `branding_text`, `viewing_angle`+`perspective` folded into one
  `camera_angle` (two vision fields, one canonical field - revision #5
  discipline in action, not an oversight),
  `approximate_scale_in_frame`→`composition`,
  `lighting_characteristics`→`lighting`. Deliberately left unmapped:
  `surface_finish`, `distinguishing_features`, `immutable_characteristics`,
  `extensions` - none are a genuinely new canonical concept, all remain
  visible in `ProductLockProfile.structured_json` directly, just not
  promoted to a profile field.
- Vision-derived fields get a flat `VISION_DEFAULT_CONFIDENCE = 0.85`
  (the Product Lock Profile Stage doesn't emit real per-field confidence
  today - documented as a fast-follow, not solved here).
- `ProductAttributeValue` parsing reuses Pydantic's `TypeAdapter` against
  the same discriminated union `NormalizedAttribute.value` uses, rather
  than duplicating validation logic.
- 7 new tests: empty profile (no evidence), vision-only, source-import-
  only, immutable-prefers-source-on-disagreement, contextual-prefers-
  vision-on-disagreement, falls-back-to-the-other-side-when-the-
  preferred-one-lacks-the-field, only-current-rows-considered.
- Full suite: 118/118 passing (111 existing + 7 new). Ruff clean (same
  10 pre-existing F821 false positives). App boots cleanly.
- Zero behavior change to anything existing - `assemble_product_profile`
  has no caller yet (that's 5.6's job).
- Commit: (see git log)

### Phase 5.6 — API surface (done)

- `POST /api/products/{id}/source-import` (`ProductSourceImportRequest
  {url}` → `ProductSourceImportRead`, `200` not `202` - unlike
  `/analyze`, a single fetch+parse really is done by the time the
  response is sent, exactly the deliberate-departure reasoning the plan
  called for) - resolves the adapter automatically, returns the
  `ProductSourceImport` row itself (success or failure, matching
  `create_product`/`create_project`'s "return what you just created"
  convention) rather than the assembled profile.
- `GET /api/products/{id}/profile` → `ProductProfile` directly (no
  separate `*Read` schema needed - `ProductProfile`/`ProductProfileField`
  from `app/services/product_profile.py` already are Pydantic models;
  FastAPI doesn't care which module a `response_model` is imported
  from).
- 6 new route-level tests: success, failure surfaces cleanly (no 500),
  404 on both endpoints for an unknown product, empty profile for a
  product with no evidence yet, and profile correctly reflecting a
  successful import end-to-end through the real route → service →
  merge chain (not mocked at the profile-assembly level, only at
  adapter resolution - same "no real network calls" discipline as
  every other sub-phase, via the same `get_product_source_adapter`
  monkeypatch point 5.3/5.5's tests already established).
- Full suite: 124/124 passing (118 existing + 6 new). Ruff clean (same
  10 pre-existing F821 false positives). App boots cleanly, 26 routes
  registered (was 24).
- Zero behavior change to anything existing - two new endpoints, nothing
  else touched. Live-verification against a real product URL (not
  mocked) deferred to 5.7 as originally planned, alongside the frontend
  that will actually trigger it.
- Commit: (see git log)

### Phase 5.7 — Frontend: submit a source URL + provenance-aware profile view (done)

- `api.ts`: added the `ProductAttributeValue` discriminated union and
  `ProductProfile`/`ProductProfileField`/`ProductSourceImport` types,
  mirroring `app/product_sources/base.py` exactly - the standing design
  principle (revision #4) means the frontend keeps the real typed
  structure too, not a flattened string. Added `createSourceImport`/
  `getProductProfile`.
- `ProductManager.tsx`'s "View Analysis" panel gained a URL input +
  submit control and a Product Profile section rendering each canonical
  field via a new `AttributeValueDisplay` component - one render branch
  per `ProductAttributeValue` kind (a color swatch + label for
  `ColorValue`, `×`-joined dimensions, tags for `ListValue`, etc.),
  plus classification and confidence/source badges per field. The old
  raw `ProductLockProfile` JSON dump moved into a collapsed `<details>`
  ("raw evidence") - the merged profile is the primary view now, per
  the standing principle from revision #4.
- **Real bug found and fixed during live verification, not assumed
  correct**: imported the actual live TikTok Shop product URL used in
  5.4's spike through the real running app. The fetch itself succeeded
  (the "Security Check" interstitial is a real HTTP 200 page, not an
  error) but extracted nothing useful - yet the import was recorded as
  `fetch_status=FETCH_STATUS_SUCCEEDED`, which would mislead a user into
  thinking real product data was found. Fixed in
  `app/services/product_source_import.py`: a new `_fetch_status_for`
  helper marks an import `FETCH_STATUS_PARTIAL` unless `brand`,
  `attributes`, or `images` are non-empty - deliberately excluding a
  bare page `title` from counting as "found something," since even a
  bot-detection wall has a `<title>` tag. Re-verified live after the fix
  (now correctly shows `partial`). One backend test's fixture needed a
  `brand` added to keep asserting a genuine "succeeded" case; one new
  test added for the `partial` case at both the service and API layer.
- **Live-verified thoroughly, real network throughout, not mocked**:
  - A real 404 on a moved product URL → correctly recorded as `failed`
    with a clear error message, no crash.
  - A real, live, markup-free page (books.toscrape.com, chosen after
    discovering Allbirds' edge returns 404 to direct HTTP clients even
    with a realistic browser User-Agent - a real-world constraint noted,
    not a bug in this codebase) → `succeeded` (title-only, now correctly
    distinct from "found real evidence" per the fix above).
  - The real TikTok Shop product URL from 5.4's spike → `partial`,
    matching that sub-phase's conclusion exactly.
  - The full merge pipeline verified against **real, pre-existing vision
    data** (not synthetic fixtures) - the dev database's actual
    Bellavita product, analyzed months earlier by the real AI pipeline,
    produced a rich, correctly-classified, correctly-typed Product
    Profile (10 fields, list/text/color values, immutable/contextual
    badges, `vision · 85%` confidence) rendered correctly in the actual
    UI via a real click-and-screenshot check, not just an API response.
  - The URL-input form itself exercised via real typing + a real click
    (not just direct `fetch()` calls), confirming the interactive path
    works end-to-end.
- Full suite: 126/126 passing (124 existing + 1 new fixture fix + 1 new
  partial-status test). Ruff clean (same 10 pre-existing F821 false
  positives). Frontend `tsc`/`oxlint`/`build` all clean.
- Commit: (see git log)

**Phase 5 (Product Intelligence) is complete.** A canonical, multi-source
Product Profile now exists end-to-end: schema, shared adapter contract,
a real working generic adapter, an honest (not fabricated) investigation
of TikTok Shop that correctly concluded not to build one, the merge
service, the API, and a UI that shows the result with real provenance
and classification - not a flattened blob. TikTok Shop support remains a
documented, deliberate gap pending a future product/business decision
(see "Suggested future improvements" near the top of this document), not
an oversight.

---

## ADR: Catalogue layer for Product Intelligence (2026-07-22, frozen baseline)

**Status: locked.** Confirmed by the user as the architectural baseline for
all future catalogue work. Do not revisit or redesign unless real
implementation work or production data exposes a concrete limitation -
this section records the *design* decision; the detailed sub-phase plan
implementing it lives further down ("Phase 5: Product Intelligence -
Catalogue layer extension").

**Context.** Live data (a real, live-verified TikTok Shop listing for a
two-bottle BellaVita fragrance set) proved the atomic-`Product`
assumption breaks for bundles - a single `ProductLockProfile` was
awkwardly describing two physically distinct bottles as one object. This
ADR is the result of a multi-round design conversation (Bundle -> Listing
-> "is this really just bundles, or a broader catalogue?") that converged
on a stable model *before* any code was written, per this project's
standing "plan before code" discipline.

### 1. Final catalogue model

```
Marketplace URL
     |
     v
  Listing --owns (history)--> ProductSourceImport --> Evidence
     |
     +-resolves to (exactly one)-+
                                  v
                    +-------------+-------------+
                  Product                     Bundle --has members--> Product (xN)
                    |                            |
                    v                            v
              ProductProfile              Bundle View
           (Product Intelligence,      (list of member
              unchanged)                ProductProfiles)
```

| Entity | Responsibility |
|---|---|
| `Listing` | One marketplace's specific sellable page: commercial facts (price, seller, rating, units sold, shipping, source URL) + the resolution pointer to what it represents |
| `ProductSourceImport` | One fetch attempt's raw + normalized evidence, versioned (`is_current`) per `Listing` - history, not identity |
| `Product` | Canonical atomic physical-product truth (unchanged from Phase 5) |
| `ProductBundle` | Declares that N `Product`s are sold together as one unit; pure composition, no attributes of its own |
| `ProductBundleMember` | Join: which products, and how many of each, compose a `ProductBundle` |

**Ownership boundary**: Marketplace Ingestion owns *how things are sold*
(`Listing`, `ProductSourceImport`, price/seller/rating). Product
Intelligence owns *what things are and how they physically relate*
(`Product`, `ProductBundle`, `ProductProfile`). Nothing crosses that line
in either direction.

### 2. Identity

- `Product` / `ProductBundle`: opaque generated id, no natural key -
  deliberate, since "are these the same product" is exactly the hard,
  unautomated matching problem below.
- `Listing`: naturally identified by `(source_type, normalized
  source_url)`. Re-fetching the same URL updates the same `Listing`, not
  a new one.
- `ProductSourceImport`: no independent identity - "the nth fetch of this
  Listing," not a thing with its own meaning.

A `Listing` resolves to exactly one of `resolved_product_id` /
`resolved_bundle_id`. Two `Listing`s should resolve to the same
`Product`/`ProductBundle` **only on explicit human confirmation** - never
automatically, even for a high-confidence-looking match (GTIN/barcode, exact
brand+title). A false-positive automatic merge corrupts a `Product`'s
evidence with a different physical object's data - strictly worse than a
missed duplicate a human can still fix later. The only *non*-inferred
resolution is the case where a human has already navigated to a specific
`Product` before supplying a URL - that's accepting an instruction, not
inferring identity, and may resolve immediately.

### 3. Evidence flow

`Marketplace URL -> Listing -> ProductSourceImport -> Evidence -> Product
Intelligence -> Product Profile`. Everything from "Evidence" onward is
unchanged Phase 5 machinery (5.2/5.3/5.5/5.6) - this ADR's entire
contribution sits upstream of it. The fork for `ProductBundle` happens at
`Listing`'s resolution step, never inside Product Intelligence itself.

### 4. Marketplace independence

The same `Product`/`ProductBundle` can be sold on TikTok Shop, Amazon, and
Shopify simultaneously as three `Listing`s resolving to one `Product` - no
duplication, since identity lives on `Product`, not any `Listing`. Adding
a marketplace means adding an adapter that produces more `Listing`s;
`Product`/`ProductBundle`/Product Intelligence are never touched.
Marketplace data never enters Product Intelligence for a structural
reason, not a policy one: `CANONICAL_FIELD_VOCABULARY` stays closed to
physical-product concepts by its own standing discipline (revision #5),
and `assemble_product_profile` only ever queries `Product`-scoped
evidence - `Listing` fields are never in that code path's reach.

### 5. Bundle philosophy

`ProductBundle` is a composition relationship, not a `Product` subtype -
`Product`'s vocabulary is deliberately single-valued
(`ColorValue`/`DimensionValue`, one value per physical object), and a
bundle of differently-colored/shaped items has no honest single answer for
those fields. A "Bundle View" is therefore not a new persisted or
vocabulary-bearing thing - it's a read-time composition of each member's
real, unmodified `ProductProfile` (reusing 5.5's merge machinery once per
member), never a new merge/precedence system and never a new vocabulary.

### 6. `CatalogItem`: considered and rejected

A thin `CatalogItem` identity+discriminator table (so `Listing` needs only
one FK regardless of how many resolvable types eventually exist) was
seriously considered and initially leaned toward, then rejected on
closer inspection: every candidate "third resolves-to type" named across
the design conversation (Variant, Multipack, Gift Set, Subscription)
turned out to reduce to either "a `Product` plus an extra relationship"
(Variant) or "a `ProductBundle` special case" (Multipack, Gift Set) or "a
`Listing`-level fact, not a composition concept" (Subscription) - i.e.
exactly two resolves-to types are evidenced today, with no concrete third
one. **Decision: two nullable FKs on `Listing`** (`resolved_product_id`,
`resolved_bundle_id`), not `CatalogItem`. Revisit only if a genuine third
type appears that is neither of the two reductions above - the migration
to `CatalogItem` at that point is a well-understood, additive,
low-risk shape (same kind of change this project has executed
repeatedly), not something worth paying for speculatively now.

### 7. Non-goals (explicitly deferred, not decided)

- Variants / product families - named as a plausible future shape, not
  designed.
- Subscriptions as a catalogue concept - would be a `Listing` fact if ever
  built.
- Automatic cross-marketplace entity resolution/dedup - always
  human-confirmed; GTIN/barcode auto-*suggestion* (never auto-merge) is a
  possible future refinement, not decided.
- **How already-shipped `ProductSourceImport` rows/flow (keyed by
  `product_id`) relate to the new `Listing`-owned model** - this ADR
  describes the target conceptual shape only; resolved as an
  implementation decision in the sub-phase plan below (kept additive: the
  existing `product_id`-direct flow stays untouched, a new nullable
  `listing_id` FK is added alongside it for the new path - this is
  filling a gap the ADR deliberately left open, not revisiting the ADR's
  design conclusions).
- Any resolution/review UI (bundle member-hints, pending `Listing`s) -
  real, non-trivial future work.
- Listing price/rating history over time (snapshot vs. time-series) -
  unresolved.
- Any change to the future Generation/Validation Engine design.

---

## Phase 6: Multi per-slide product detection — detailed plan

**Problem.** `ProductAppearance` was designed since Phase 2.1 to support
zero, one, or several products per slide, but nothing actually exercises
more than one today - the assign-product API, the three product-related
Stages, and the blueprint assembly all silently assume exactly one.
Grounded in reading every actual consumer, not assumed:

- `POST .../assign-product` unassigns *every* existing current
  `ProductAppearance` for the slide before adding the new one -
  single-slot semantics baked into the API itself, not just the Stages.
- `Slide.current_product_appearance` is a singular convenience property
  (`next(a for a in appearances if a.is_current, None)` - the first
  match).
- `SlideProductIsolationStage`, `SlideProductLockProfileStage`, and
  `SlideRecreationPromptStage` all query for current appearances and
  take `.first()`.
- `assemble_slideshow_blueprint`'s `_assemble_slide` actually already
  lists *every* current appearance (`appearance_reads`, plural) - but
  then resolves reference images/lock profile only for
  `current_appearances[0]`'s product. The read side is halfway there
  already.

**A real judgment call made now, not left as an open question** (per
the renewed authorization's instruction to lean conservative rather than
guess on genuine ambiguity while unsupervised): **Recreation Prompt
stays single-product for this phase.** Making it genuinely multi-product
raises a materially bigger, harder-to-reverse question - does "recreate
this slide" mean one prompt per product, or one prompt referencing all
of them? - that deserves the same kind of real design conversation the
Product Profile work got, not a guess made alone. This phase's actual,
deliverable scope is what its own name says: **detection** - Product
Isolation and Product Lock Profile become genuinely multi-product;
Recreation Prompt keeps resolving exactly one product (via
`prominence="primary"` where set, else a deterministic fallback), with
its docstring updated to say so explicitly rather than leaving it looking
like an oversight once its two sibling stages change.

### 6.1 — Additive backend: plural product-appearance API + model accessor

- `Slide.current_product_appearances` (new, plural) returns every
  current appearance - the existing singular `current_product_appearance`
  stays exactly as-is (still "the first one found"), same non-breaking
  pattern as Phase 4.1's `Slideshow.primary_slide`.
- New endpoints, additive alongside the existing `assign-product` (which
  stays completely unchanged - existing tests/frontend flow unaffected):
  `POST /api/slideshows/{id}/slides/{slide_id}/products` (body
  `{product_id}`) adds a new current `ProductAppearance` without
  clearing existing ones - idempotent (no-ops if a current appearance
  for that exact product already exists, rather than creating a
  duplicate). `DELETE /api/slideshows/{id}/slides/{slide_id}/products/
  {appearance_id}` flips off exactly one appearance, not all.
- **DB/schema changes**: none - `ProductAppearance` already supports
  this structurally since Phase 2.1.
- **Test strategy**: model test for the new plural accessor with 2+
  appearances; route tests for add (including the idempotent-no-duplicate
  case) and remove (including removing one of several, confirming the
  others survive).
- **Rollback**: revert the two new endpoints; the existing single-slot
  `assign-product` flow is untouched either way.
- **Expected commit size**: small-medium.

### 6.2 — Product Isolation + Product Lock Profile stages: revised scope (real gap found during implementation)

**The original plan above ("loop over every current appearance, process
each distinct product") turned out not to actually work, and would have
silently produced wrong data if built as written - caught by reading the
provider call sites carefully before writing the loop, not after.**

Both `isolation_provider.isolate_product(image_bytes)` and
`vision_provider.analyze_creative(image_bytes=..., prompt_spec={"prompt":
PRODUCT_LOCK_PROFILE_PROMPT, ...})` take the whole slide image and a
generic, non-targeted prompt ("the featured product") - there is no way
to tell either provider *which* of several assigned products to focus
on. Calling either one twice for two different assigned products would
not produce two different results - it would produce the same
(or near-identical, given LLM non-determinism) crop/profile twice,
mislabeled under two different `product_id`s. Naively zipping N detected
bounding boxes against N assigned products in whatever order each
happens to come back was considered and rejected too - there's no
correspondence guarantee between detection order and assignment order,
so this would silently attach the wrong crop to the wrong product just
as easily as the right one. Both would violate the standing design
principle harder than not having the feature at all: the Product Profile
is a canonical contract, and plausible-looking wrong data is worse than
an honest gap.

**Revised, honest scope**: single-product slides (today's only real
case, and still the overwhelming majority even after 6.1) behave exactly
as before - zero change. A slide with 2+ current appearances gets a
clear, specific, honest failure from both stages
("Multiple products assigned to this slide - automated per-product
isolation/profiling isn't implemented yet; each product's Lock Profile
must currently be generated from a slide where it's the only one
assigned") instead of either crashing or silently writing incorrect
data. This is not a smaller version of the original goal so much as a
different, safer one: Phase 6's real, honestly-deliverable value is
letting multiple products be *assigned and tracked* per slide (6.1, 6.4,
6.5) - genuinely automating *detection and profiling* for more than one
product per slide needs product-targeted isolation/profiling (e.g.
region-hinted or reference-image-hinted provider calls), which is real,
undesigned AI-provider work belonging in its own future phase, not a
guess made here. Logged under "Suggested future improvements" below.
- No schema change needed either way.
- The zero-appearance case (today's "no product assigned" failure)
  stays unchanged - still correct.
- **Test strategy**: existing single-product tests must keep passing
  unchanged. New tests: 2+ current appearances (via 6.1's endpoint)
  produces the new, specific "multiple products assigned" failure from
  both stages, not a crash and not silently-wrong data.
- **Rollback**: revert; single-product slides (the only kind
  constructible before 6.1) are completely unaffected either way.
- **Expected commit size**: medium.

### 6.3 — Recreation Prompt stage: explicit primary-product resolution

- No change to which product it resolves when there's zero or one
  current appearance (unchanged). When there are 2+: prefer the one with
  `prominence="primary"`; if none is marked primary (e.g. two products
  added via 6.1's new endpoint, which doesn't let the caller set
  prominence), fall back to the earliest-created current appearance -
  small, deterministic, well-tested logic, not left to whatever order a
  query happens to return.
- Docstring/module comment updated to state this scope boundary
  explicitly - deliberate, not an oversight, now that its two sibling
  stages are genuinely multi-product.
- **Test strategy**: primary-marked-wins-over-others test; no-primary-
  marked falls back to earliest-created test.
- **Rollback**: revert; behaves exactly as before 6.1 existed (nothing
  before this phase could construct the "2+ appearances, no primary"
  case at all).
- **Expected commit size**: small.

### 6.4 — Blueprint assembly: every product's results, not just the first

- `_assemble_slide` extended to resolve reference images + lock profile
  for *every* current appearance's product, not just the first. Real
  response-shape change to `AssembledSlideBlueprint`: replaces the
  singular `product_lock_profile`/flat `product_reference_images` fields
  with a per-product grouping (e.g. `products: list[{product,
  lock_profile, reference_images}]`) - keeping each product's own data
  together, rather than flat lists the frontend would have to
  cross-reference by product_id itself.
- **This is a breaking API change - lands together with its frontend
  consumer in the same sub-phase** (6.5, not deferred), same "backend +
  frontend as one working slice" discipline used throughout Phases 3-5 -
  landing 6.4 alone would leave the blueprint modal broken.
- **Test strategy**: route/schema tests for 0/1/2-product slides.
- **Rollback**: revert 6.4 and 6.5 together (see 6.5).
- **Expected commit size**: medium.

### 6.5 — Frontend: multi-product picker + multi-product blueprint display

- `SlideProductPicker.tsx`: extends from single-select-plus-unassign to
  a real add/remove list (each current appearance shown with its own
  remove control, plus an "add another product" control), using 6.1's
  new endpoints. The existing single-slot `assign-product` call/UI is
  not reused here - this is new, additive UI, not a rewrite of the old
  picker's existing behavior (which some slides may still rely on/keep
  using for the common single-product case).
- `SlideshowBlueprintModal.tsx`'s "Product" section renders one
  sub-section per product from 6.4's regrouped response, instead of one
  flat section.
- Live-verify against real data: a slide with 2 assigned products,
  confirming both get isolated/profiled independently and both render
  correctly.
- **Rollback**: revert 6.4+6.5 together; the app reverts to single-
  product blueprint display, still fully working for that case.
- **Expected commit size**: medium.

**Risks:** 6.4's response-shape change is the main one - unlike most
prior additive sub-phases, this one has no way to stay backward-
compatible without carrying two parallel shapes, which would itself be
the kind of complexity revision #5's discipline (small, stable
contracts) argues against carrying elsewhere in this codebase. Landing
6.4+6.5 together, tested thoroughly, is the mitigation. See 6.2 above
for the real scope revision found while implementing it - multi-product
*assignment/tracking* ships this phase, multi-product *automated
isolation/profiling* does not (needs product-targeted provider calls,
undesigned, logged as future work).

## Phase 6 reports log

### Phase 6.1 — Additive plural product-appearance API + model accessor (done)

- `Slide.current_product_appearances` (new, plural) added alongside the
  unchanged singular `current_product_appearance` - same non-breaking
  pattern as Phase 4.1's `primary_slide`.
- `POST /api/slideshows/{id}/slides/{slide_id}/products` (idempotent -
  a second call with the same product_id no-ops rather than duplicating)
  and `DELETE .../products/{appearance_id}` added, `assign-product`
  itself completely untouched - verified with an explicit regression
  test proving it still replaces, not adds.
- 11 new tests: 3 model-level (plural accessor empty/populated/excludes-
  stale), 8 route-level (add creates a current appearance, two different
  products both stay current - the actual point of this sub-phase,
  idempotent re-add, 404s for unknown product/slide/appearance, remove
  one leaves the others, and the assign-product regression guard).
- Full suite: 137/137 passing (126 existing + 11 new). Ruff clean (11
  findings now, not the prior baseline's 10 - the one new instance is
  the new plural property's own string forward-ref, same already-
  characterized-safe SQLAlchemy pattern as every other one, not a new
  category of issue). App boots cleanly, 28 routes (was 26).
- Zero behavior change to anything existing - two new endpoints, nothing
  else touched.
- Commit: (see git log)

---

### Phase 6.2 — Product Isolation + Product Lock Profile stages reject multi-product slides honestly (done)

- Original plan ("loop over every current appearance, process each
  distinct product") was found unsafe before any code was written: neither
  `isolation_provider.isolate_product(image_bytes)` nor
  `vision_provider.analyze_creative(...)` takes any parameter to target or
  disambiguate which assigned product to focus on - calling either twice
  for two different products would produce the same (or near-identical)
  result both times, mislabeled under two different `product_id`s. A
  naive box-to-appearance zip was considered and rejected too (no
  correspondence guarantee, could silently attach the wrong crop to the
  wrong product). This finding was documented and the plan revised
  *before* implementation, in its own commit (`b414818`).
- Corrected, safe scope actually implemented: both
  `SlideProductIsolationStage` and `SlideProductLockProfileStage` now read
  `slide.current_product_appearances` (plural, from 6.1) instead of a
  single `.first()`-queried appearance. A slide with exactly one distinct
  current `product_id` behaves identically to before (byte-for-byte same
  code path, just resolved via the plural accessor). A slide with 2+
  distinct current `product_id`s now fails clearly and immediately - each
  stage has its own `_MULTI_PRODUCT_ERROR` message naming the stage
  ("...automated per-product isolation isn't implemented yet..." /
  "...automated per-product profiling isn't implemented yet...") - before
  any provider call or `AnalysisRun` is even created, so no partial/
  misleading artifact is ever written.
- `product_lock_profile_stage.py`'s now-unused
  `from app.models.product_appearance import ProductAppearance` import was
  removed (grep-verified no other reference remains in the file); both
  module docstrings updated to explain the Phase 6 scope decision and
  point at MIGRATION_PLAN.md.
- 2 new tests (one per stage): a second `ProductAppearance` for a distinct
  product is added to the existing `slideshow_with_product` fixture's
  slide, and the stage is asserted to fail with the exact
  `_MULTI_PRODUCT_ERROR` string and to have created zero `AnalysisRun`
  rows. All prior single-product tests for both stages pass completely
  unchanged (proving the single-product path is genuinely untouched, not
  just re-tested).
- Full suite: 139/139 passing (137 existing + 2 new). Ruff clean on all
  four changed/added files. App boots cleanly, 28 routes (unchanged - no
  new endpoints this sub-phase, only stage-internal logic).
- Added "product-targeted isolation/profiling for multi-product slides"
  to "Suggested future improvements": real fix needs region-hinted or
  reference-image-hinted provider calls (`isolate_product`/
  `analyze_creative` would need a way to say "focus on this area" or
  "focus on the product that looks like this reference image") - genuine
  AI-provider design work, not attempted here.
- Commit: (see git log)

---

### Phase 6.3 — Recreation Prompt explicit primary-product resolution (done)

- Unlike Product Isolation/Lock Profile (Phase 6.2), a recreation prompt
  doesn't fail outright on a multi-product slide - a prompt is inherently
  single-subject, so the stage now resolves one *primary* product to
  build it around instead of picking whichever appearance an unordered
  `.first()` query happened to return.
- New `_resolve_primary_appearance()`: prefers the current appearance with
  `prominence == "primary"` (ties broken by earliest `created_at`, then
  `id`, for determinism); falls back to the earliest-created current
  appearance if none is marked primary. Replaces the old direct
  `db.query(ProductAppearance)...first()` call - single-product slides
  are unaffected (one appearance in, that same appearance out).
  `slide.current_product_appearances` (the Phase 6.1 plural accessor) is
  now the entry point instead of a fresh query.
- This is an explicit scope boundary, documented in the module docstring:
  a slide with several equally-important products still only gets one
  recreation prompt, built around whichever one resolves as primary.
  Broader multi-product recreation-prompt support is future work.
- 9 new tests: 5 pure unit tests of `_resolve_primary_appearance` against
  lightweight fake appearances (empty list, single item, primary-beats-
  creation-order, fallback-to-earliest-created, tie-among-primaries), plus
  1 integration test building a real two-product slide (Lock Profiles
  persisted directly, since Phase 6.2 made the stage itself reject multi-
  product slides) and asserting the resulting RecreationPrompt references
  the *primary* product's Lock Profile, not the secondary one. All 6 prior
  tests pass completely unchanged.
- Full suite: 145/145 passing (139 existing + 6 new: 5 unit tests of
  `_resolve_primary_appearance` plus the 1 multi-product integration
  test). Ruff clean. App boots cleanly, 28 routes (unchanged - no new
  endpoints).
- Commit: (see git log)

---

### Phase 6.4 + 6.5 — Blueprint regrouped per-product + frontend multi-product UI (done, landed together per the plan)

Backend (6.4):

- `AssembledSlideBlueprint`'s old flat `product_appearances` /
  `product_reference_images` / `product_lock_profile` fields (the last
  two only ever populated for `current_appearances[0]` - Phase 6.1/6.4's
  actual gap) are gone, replaced by `products: list[AssembledSlideProductBlueprint]`
  - one entry per current `ProductAppearance` on the slide, each carrying
  its own `appearance`, `product_reference_images`, and
  `product_lock_profile`. A genuinely breaking response-shape change,
  landed deliberately (not deferred) per the plan.
  `_assemble_slide_product()` (new, in `slideshow_blueprint.py`) does the
  per-appearance lookup that `_assemble_slide` used to do once for
  `current_appearances[0]` only.
- Additive schema gap found and fixed while wiring the frontend: `SlideRead`
  only ever exposed the *singular* `current_product_appearance` - the
  plural accessor added in Phase 6.1 was never surfaced over the wire, so
  a multi-product picker had no way to know about a slide's second+
  product without fetching the whole assembled blueprint. Added
  `SlideRead.current_product_appearances` (plural), additive alongside
  the unchanged singular field - same non-breaking pattern used
  throughout this migration.
- Updated tests: the 3 tests in `test_slideshow_blueprint_api.py` and 4 in
  `test_slide_products_add_remove_api.py` that asserted the old flat
  shape now assert the grouped one; added
  `test_blueprint_regroups_artifacts_per_product_on_a_multi_product_slide`
  (2 real products, 2 Lock Profiles persisted directly since Phase 6.2
  made the stage itself reject multi-product slides, asserting each
  product's own Lock Profile shows up under its own entry - the actual
  point of this sub-phase) and
  `test_slide_read_exposes_the_plural_current_product_appearances`.

Frontend (6.5):

- `api.ts`: `AssembledSlideBlueprint.products: AssembledSlideProductBlueprint[]`
  mirrors the new backend shape exactly; `Slide.current_product_appearances`
  added (additive) mirroring the new `SlideRead` field; new
  `addSlideProduct`/`removeSlideProduct` methods calling the Phase 6.1
  endpoints.
- `SlideProductPicker.tsx` rebuilt around the plural list instead of a
  single replaceable slot: renders one removable pill per current
  appearance, an "Add another product…"/"Assign product…" dropdown that
  filters out already-assigned products, and a "+ New" create-and-add
  flow - all via the additive add/remove endpoints, not the old
  single-slot assign-product endpoint (which remains untouched and still
  live on the backend, per its own regression test).
  `SlideshowGrid.tsx` updated to pass the plural prop.
- `SlideshowBlueprintModal.tsx`'s Product section rebuilt as "Products":
  one sub-section per product (name + "primary" badge, its own reference
  images, its own Lock Profile or "not generated yet"), replacing the
  single flat section that only ever showed `product_appearances[0]`'s
  data. Header's product line now joins every current product's name.
  Product Isolation/Lock Profile rerun buttons stay slide-scoped (those
  stages still reject 2+-product slides per Phase 6.2) - their failure
  surfaces through the existing `failed_stage`/`failed_stage_error`
  mechanism, not a special case.
- New CSS: `.assigned-product-list`, updated `.assigned-product` (now a
  removable pill inside a list item), `.product-subsection`,
  `.product-subsection-title`, `.prominence-badge`.
- `tsc -b && vite build`: clean. `oxlint`: clean (exit 0).
- **Live-verified** against the real dev server and real dev DB (backend
  on :8000, vite dev server proxying to it): added a second product
  (Evoband) to a slide that already had one (Bellavita) via the picker -
  confirmed both stayed current, the dropdown correctly excluded both
  once assigned, and the grid card showed 2 removable pills. Opened the
  Blueprint modal on that same slide: header read "Products: Bellavita,
  Evoband"; the Products section rendered two distinct sub-sections -
  Bellavita's showing its real, pre-existing generated Lock Profile in
  full (this product's Lock Profile was generated in an earlier session,
  confirming real data renders correctly, not just fixture data), Evoband
  correctly showing "Lock Profile not generated yet." Removed Evoband via
  the grid's Remove button - confirmed it dropped back out of both the
  picker and (implicitly, via the same data path) the blueprint. No
  console errors at any point.
- Observed but out of scope for this sub-phase: the additive add-product
  endpoint (Phase 6.1) always writes `prominence="primary"` for every
  appearance it creates, so a slide with 2 products added this way shows
  a "primary" badge on both in the UI - not incorrect (it's an honest
  reflection of the stored data), but not yet a meaningful "which one is
  actually primary" signal either. Not fixed here; flagged in "Suggested
  future improvements" below since it would need its own design decision
  (should adding a second product ever demote the first to secondary
  automatically, or does that require an explicit user action?).
- Also added a `frontend` entry to `.claude/launch.json` (vite dev
  server on :5173) alongside the existing `backend` entry, so future
  frontend live-verification doesn't need an ad hoc setup.
- Commits: (see git log)

---

## Phase 5: Product Intelligence — Catalogue layer extension (5.8+) — detailed sub-phase plan

Implements the frozen ADR above. Numbered as a continuation of Phase 5
(not a new top-level phase) since it's genuinely an extension of Product
Intelligence's boundary, not a new concern - same reasoning Phase 6.2's
mid-implementation revision used to stay under Phase 6 rather than
spawning a new number. Same discipline as every other sub-phase this
project has shipped: small, additive, tested, live-verified where it
touches a real endpoint, one sub-phase per commit.

**Naming**: `ProductBundle`/`ProductBundleMember` (matching this
codebase's existing `Product*`-prefixed convention for anything in this
domain); `Listing` stays unprefixed (it's marketplace-scoped, not
product-scoped - matches the ADR's own terminology exactly).

**Implementation decision not settled by the ADR (its own Non-goals section
left this open deliberately)**: `ProductSourceImport.product_id` and the
existing `POST /api/products/{id}/source-import` flow are **left
completely untouched** - zero risk to shipped Phase 5 work, zero
migration of existing rows. A new nullable `listing_id` FK is added
alongside the existing `product_id`, used only by the new
unknown-URL/bundle-aware import path (5.10+). Same "extend, don't
replace" pattern used for every other provenance column in this
codebase (`ProductReferenceImage`'s three FKs, etc.).

### 5.8 — Additive schema: `Listing`, `ProductBundle`, `ProductBundleMember`

- New model `Listing`: `id, source_type, source_url (unique), resolved_product_id
  (nullable FK), resolved_bundle_id (nullable FK), price_amount (nullable),
  price_currency (nullable), seller_name (nullable), rating (nullable),
  units_sold (nullable), shipping_info (nullable), created_at`. Not built
  on `AnalysisArtifactMixin` (same reasoning as `ProductSourceImport` -
  this isn't an AI analysis run).
- New model `ProductBundle`: `id, display_name, project_id (nullable FK,
  mirroring `Product`'s own optional project scoping), created_at`.
- New model `ProductBundleMember`: `id, bundle_id (FK), product_id (FK),
  quantity (default 1), created_at`.
- `ProductSourceImport` gains a new nullable `listing_id` FK, additive
  alongside the existing `product_id` (see decision above) - existing
  rows/behavior completely unaffected.
- Alembic migration (additive only - 3 new tables, 1 new nullable
  column). Full discipline: real dev DB backup, upgrade/downgrade tested
  on an isolated scratch copy first, content-diff verified, then applied
  to the real dev DB and re-verified.
- **Test strategy**: model-level tests only (construct each new model,
  confirm FK relationships, confirm `ProductSourceImport` still works
  with `listing_id=None` exactly as before). No wiring to any
  service/route yet - mirrors Phase 5.1/5.2/6.1's "additive schema first,
  zero behavior change" pattern.
- **Rollback**: downgrade the migration; nothing references the new
  tables/column yet.
- **Expected commit size**: small-medium.

### 5.9 — Adapter contract: bundle + listing evidence (additive fields only)

- `NormalizedProductEvidence` (in `app/product_sources/base.py`) gains two
  new **optional** fields: `bundle: NormalizedBundleEvidence | None` and
  `listing: NormalizedListingMetadata | None`. Zero change to the
  `ProductSourceAdapter` Protocol or `extract()`'s signature - every
  existing adapter (`GenericUrlAdapter`) and every existing test is
  unaffected; both fields simply default to `None`.
- `NormalizedBundleEvidence = {title: str, member_hints:
  list[BundleMemberHint]}`, `BundleMemberHint = {label: str, attributes:
  dict[str, NormalizedAttribute]}` - member hints reuse the existing
  `CANONICAL_FIELD_VOCABULARY`/`ProductAttributeValue` types, per
  revision #5's discipline (no new vocabulary for bundle members).
- `NormalizedListingMetadata = {price_amount, price_currency, seller_name,
  rating, units_sold, shipping_info}` (all optional).
- `GenericUrlAdapter` gains a first, deliberately narrow bundle-detection
  heuristic: a JSON-LD `@graph` containing multiple `Product` entries
  (the adapter already parses `@graph`-bundled JSON-LD from 5.3) is a
  natural, low-effort signal - populate `evidence.bundle` from those
  entries when found. Not exhaustive; a listing with no such signal
  simply has `bundle=None`, same as today.
- **Test strategy**: fixture HTML with multi-`Product` `@graph` JSON-LD ->
  `evidence.bundle` populated correctly; existing single-product fixtures
  from 5.3 continue to produce `bundle=None` unchanged (regression guard).
- **Rollback**: revert; adapters simply stop populating the two new
  fields, nothing downstream depends on them yet.
- **Expected commit size**: small-medium.

### 5.10 — Listing resolution service

- New `app/services/listing_import.py`: `import_listing(db, url) ->
  Listing` - resolves the adapter (5.2's registry, unchanged), persists a
  `Listing` (get-or-create by `source_url`) and a `ProductSourceImport`
  scoped to it via `listing_id`, denormalizes `evidence.listing`'s fields
  onto the `Listing` row.
- Resolution branch: if `evidence.bundle` is `None`, evidence describes an
  ordinary single product - **do not auto-create a `Product`**; the
  `Listing` stays unresolved until a human links it to an existing
  `Product` or creates a new one (same conservative stance as the bundle
  case - the ADR's identity section is explicit that resolving anything
  from parsed content is inference, never automatic, regardless of
  whether it turns out to be one item or several).
- If `evidence.bundle` is present: member hints are persisted (on the
  `ProductSourceImport.normalized_json`, not a new table - no schema
  needed) as unresolved; a human reviews and links/creates each member
  `Product`, at which point a `ProductBundleMember` row is created and,
  once all hints are resolved, the `Listing.resolved_bundle_id` is set.
- New functions: `resolve_listing_to_product(db, listing_id, product_id)`,
  `resolve_listing_to_new_product(db, listing_id, display_name)`,
  `resolve_listing_to_bundle(db, listing_id, bundle_id, member_product_ids)`,
  `create_bundle_from_listing(db, listing_id, display_name,
  member_product_ids)`.
- **Test strategy**: unit tests per resolution path (ordinary product,
  bundle with all hints pre-resolved, bundle with some hints unresolved),
  get-or-create-by-URL behavior (re-importing the same URL updates the
  same `Listing`, doesn't duplicate), failure path (`fetch_status=failed`
  recorded, no resolution attempted).
- **Rollback**: revert the file; nothing calls it yet.
- **Expected commit size**: medium.

### 5.11 — API surface

- `POST /api/listings/source-import {url}` -> `ListingRead` (200, same
  synchronous-fetch reasoning as the existing product-scoped endpoint).
- `POST /api/listings/{id}/resolve-product {product_id}`,
  `POST /api/listings/{id}/resolve-new-product {display_name}`,
  `POST /api/listings/{id}/resolve-bundle {bundle_id, member_product_ids}`,
  `POST /api/listings/{id}/create-bundle {display_name,
  member_product_ids}`.
- `GET /api/bundles/{id}` -> bundle view: `{id, display_name, members:
  [{product_id, profile: ProductProfile}]}` - calls 5.5's existing
  `assemble_product_profile` once per member, unmodified, per the ADR's
  Bundle View definition (no new merge logic).
- `GET /api/listings/{id}` -> `ListingRead` with resolution status +
  unresolved member hints if any.
- New route-level tests: success/failure/404 per endpoint, an end-to-end
  bundle flow (import a bundle-shaped fixture -> resolve each hint to a
  new/existing product -> `GET /api/bundles/{id}` returns real member
  profiles).
- **Rollback**: revert the routes independently; nothing else depends on
  them.
- **Expected commit size**: medium.

### 5.12 — Frontend: unresolved-listing review + bundle view

- New minimal UI: submit a URL without picking a product first (mirrors
  5.7's existing per-product URL form, but scoped to `/api/listings/*`),
  a review list for unresolved `Listing`s showing member hints with
  link-existing/create-new controls per hint, and a Bundle view rendering
  each member's real `ProductProfile` (reusing 5.7's existing
  `AttributeValueDisplay` component per member, not a new renderer).
- Live-verify against a real bundle-shaped listing (a real, publicly
  reachable multi-`Product` JSON-LD page, not fabricated) - same
  live-server discipline as every other frontend sub-phase.
- **Rollback**: revert; the per-product flow (5.7) keeps working
  unaffected either way.
- **Expected commit size**: medium-large - this is the sub-phase most
  likely to reveal a real UX gap in the "surface, don't auto-link" design
  once it's actually used, per the ADR's own instruction to revisit only
  on a concrete limitation found through real implementation.

**Risks**: 5.9's bundle-detection heuristic is deliberately narrow
(one signal: multi-`Product` `@graph` JSON-LD) - real bundle listings that
don't use that pattern will simply import as an ordinary unresolved
single-product `Listing`, not crash or misbehave, just miss the bundle
signal (degraded, not broken, matching this project's established
fallback discipline). 5.10's "don't auto-create Product" stance is the
main design bet carried over from the ADR - if it proves too much manual
work in practice, that's the kind of concrete limitation the ADR
explicitly says should trigger revisiting it, not something to
second-guess preemptively here.

## Phase 5.8+ reports log

### Phase 5.8 — Additive schema: Listing, ProductBundle, ProductBundleMember (done)

- New models: `Listing` (`app/models/listing.py`), `ProductBundle`
  (`app/models/product_bundle.py`), `ProductBundleMember`
  (`app/models/product_bundle_member.py`) - exactly as specified in the
  frozen catalogue ADR. Commercial fields on `Listing`
  (price/seller/rating/units_sold/shipping) are plain nullable columns,
  deliberately not run through `CANONICAL_FIELD_VOCABULARY` - see the
  model's own docstring for why.
- **Real gap found during implementation, not anticipated in the ADR's
  own prose**: the ADR's Non-goals section left "how does
  `ProductSourceImport` relate to `Listing`" as a deliberate open
  implementation decision. Writing the actual test for "a fetch made
  before we know what it represents" exposed that `product_id` was still
  non-nullable - a Listing-scoped import genuinely can't know its Product
  yet (per the ADR, resolution is never automatic), so the row couldn't
  be persisted at all under the original plan's schema. Fixed by also
  relaxing `ProductSourceImport.product_id` to nullable in the same
  migration, backfilled once a human resolves the owning `Listing` (Phase
  5.10's job) - at which point Phase 5.5's existing merge service picks
  the row up completely unchanged, no new code needed there. This was
  caught and fixed *before* the migration was applied to the real dev DB
  (downgraded, fixed, re-tested, re-applied) - not shipped-then-patched.
- `ProductSourceImport` gains the new nullable `listing_id` FK alongside
  its existing `product_id` - the already-shipped
  `POST /api/products/{id}/source-import` flow (Phase 5.6) is completely
  untouched, verified by the existing `test_product_source_import_model.py`
  suite passing unchanged.
- Migration `d3bafd6a4965`: full discipline applied twice (once before
  the `product_id` fix was found, once after) - real dev DB backed up
  first, upgrade/downgrade tested on an isolated scratch copy
  (`CAE_DATA_DIR`), content-diff verified (all 15 existing tables' row
  counts identical before/after both the upgrade and the downgrade),
  then applied to the real dev DB and re-verified the same way. Batch
  mode used for the `product_source_imports` ALTER (SQLite requirement,
  same as 37e53bed7ec8).
- 10 new model-level tests (`tests/test_catalogue_layer_model.py`):
  unresolved `Listing` round-trip, resolves-to-product, resolves-to-bundle,
  two Listings resolving to the same Product (the actual point of Listing
  existing separately from Product), `ProductBundleMember` with
  quantity>1 (the multipack case, free from the existing shape - no new
  entity needed), a real multi-distinct-member bundle, quantity default,
  and the two new `ProductSourceImport` states (`listing_id` set with
  `product_id=None` vs. both set).
- Full suite: 157/157 passing (146 existing + 10 new + 1 pre-existing
  `test_product_source_import_model.py` file unaffected). Ruff clean on
  every new/changed file (11 pre-existing baseline findings elsewhere,
  unrelated - see Phase 6.1's report). App boots cleanly, 28 routes
  (unchanged - no new endpoints this sub-phase, purely additive schema).
- Zero behavior change to anything existing - three new, empty tables and
  two new nullable columns; nothing reads or writes them yet.
- Commit: (see git log)

### Phase 5.9 — Adapter contract: bundle + listing evidence (done)

- `NormalizedProductEvidence` (`app/product_sources/base.py`) gains two
  new optional fields exactly as planned: `bundle:
  NormalizedBundleEvidence | None` and `listing: NormalizedListingMetadata
  | None`. Zero change to the `ProductSourceAdapter` Protocol or
  `extract()`'s signature. `NormalizedListingMetadata`'s fields
  (price/seller/rating/units_sold/shipping) are deliberately NOT run
  through `ProductAttributeValue`/`CANONICAL_FIELD_VOCABULARY` - same
  reasoning as `Listing`'s own columns (5.8).
- **Real design refinement made during implementation, not exactly as
  first planned**: the plan's own text said member hints would cover
  "entries beyond the first," implicitly treating the first detected
  Product as special (already represented via the top-level
  title/brand/attributes/images). Building the actual test for this
  exposed why that's wrong: it would silently describe one arbitrary
  member's specific facts (e.g. one bottle's color) as if they were facts
  about the whole bundle - exactly the failure mode the catalogue ADR's
  Bundle-philosophy section exists to prevent. Fixed before shipping: when
  `GenericUrlAdapter` detects 2+ Product entities in one JSON-LD `@graph`,
  the top-level fields carry only the bundle's own title (page `<title>`
  fallback) - brand/attributes/images stay empty at that level, and every
  member (all of them, not "beyond the first") gets one uniform
  `BundleMemberHint`.
- `_find_product_jsonld` renamed to `_find_all_product_jsonld` (returns
  every detected Product entity, not just the first) - the existing
  single-product call site now takes `[0]` when there's exactly one, so
  the single-product path (schema.org JSON-LD, `@graph` with one Product,
  OpenGraph fallback) is byte-for-byte unchanged, verified by all 8
  pre-existing `test_generic_product_source_adapter.py` tests passing
  unmodified. Attribute-extraction logic (brand/color/materials) factored
  into a shared `_attributes_from_jsonld` helper, reused by both the
  single-product and per-member-hint paths - not a behavior change, a
  duplication removed while adding the second caller.
- Bundle-detection heuristic is deliberately narrow, as planned: one
  signal (multi-`Product` `@graph` JSON-LD). A bundle-shaped listing that
  doesn't use this pattern simply imports with `bundle=None` - degraded
  (missed signal), not broken.
- 6 new tests: 4 in `test_generic_product_source_adapter.py` (single-
  product `@graph` still has no bundle evidence - regression guard;
  multi-product `@graph` detected correctly with per-member attributes;
  top-level fields NOT polluted by one member's facts; `raw` carries all
  detected entities), 2 in `test_product_sources_base_and_registry.py`
  (`bundle`/`listing` default to `None`; both new types round-trip).
- Full suite: 163/163 passing (157 existing + 6 new). Ruff clean on every
  new/changed file. App boots cleanly, 28 routes (unchanged - no new
  endpoints this sub-phase).
- Zero behavior change to anything existing for the single-product
  path - `GenericUrlAdapter`'s only new behavior is additive (bundle
  detection), and nothing yet calls the two new evidence fields (that's
  5.10's job).
- Commit: (see git log)

### Phase 5.10 — Listing resolution service (done)

- New `app/services/listing_import.py`: `import_listing(db, url) ->
  Listing` (get-or-create by `source_url`, per the ADR's identity
  section - re-importing the same URL updates the same `Listing`, not a
  new one, verified by a dedicated test), plus four resolution functions:
  `resolve_listing_to_existing_product`, `resolve_listing_to_new_product`,
  `resolve_listing_to_existing_bundle`, `resolve_listing_to_new_bundle`
  (paired existing/new naming for both product and bundle, rather than
  the plan's originally-sketched four names, for symmetry - same
  capability, clearer contrast between "human is instructing" vs.
  "human is creating something new").
- **Real bug found and fixed before it shipped, not caught by the plan's
  own prose**: `fetch_status_for_evidence` (promoted from a private
  helper in `product_source_import.py` to a shared one, reused here) only
  checked `brand`/`attributes`/`images` - exactly the three fields Phase
  5.9 deliberately leaves empty for bundle evidence (see that phase's own
  report). A successfully-detected bundle would have been silently
  misreported as `FETCH_STATUS_PARTIAL`, contradicting the fact that real
  evidence (the member hints) was genuinely found. Fixed by also checking
  `evidence.bundle and evidence.bundle.member_hints`; caught by writing
  the dedicated regression test before shipping, not after.
- **Scope decision made explicit, not silently narrowed**: bundle member
  resolution is atomic (`resolve_listing_to_new_bundle` takes every
  member's resolution in one call via a small `BundleMemberResolution`
  dataclass - `existing_product_id` or `new_product_display_name`,
  exactly one set), not the per-hint incremental flow the plan's prose
  sketched. No real UI/API consumer exists yet to validate what
  incremental resolution should look like (that's 5.11/5.12's job) -
  building genuine incremental state tracking before there's a concrete
  need would be exactly the kind of speculative complexity this project
  avoids elsewhere. Documented in the module's own docstring as a scope
  note, revisit if 5.12's real UI exposes a concrete need.
- Resolving to a `Product` backfills `product_id` onto every
  `ProductSourceImport` scoped to that `Listing`, so Phase 5.5's existing
  merge service picks the evidence up completely unchanged - no new code
  needed there, verified directly by test. Resolving to a `ProductBundle`
  deliberately does **not** backfill `product_id` anywhere (verified by a
  dedicated test) - a bundle listing's evidence describes the whole
  bundle, not any one member, so there is no single correct `product_id`
  to backfill it to; each member's own Profile is assembled independently
  from that member's own evidence, never from the bundle listing's
  evidence directly, matching the ADR's Bundle View design exactly.
- Guard rails, all tested: resolving an already-resolved `Listing`
  raises; resolving to a nonexistent `Product`/`ProductBundle`/`Listing`
  raises; a member resolution with both fields set, or neither, raises.
- Reference-image download for `Listing`-scoped evidence is explicitly
  out of scope for this sub-phase (documented in the module's own
  docstring) - `ProductReferenceImage.product_id` stays non-nullable, so
  there's nothing to attach an image to before resolution, and a
  bundle-resolved `Listing` has no single product to attach one to
  afterward either. Left as a documented gap.
- A minor mistake caught and fixed before it ran: an initial draft used
  `dataclasses.field(default_factory=list)` as a *plain function's*
  default value (that's only valid inside a `@dataclass` field
  definition) - fixed by making `member_resolutions` a required
  parameter instead, which was the correct choice anyway since a bundle
  needs at least one member and the function already rejects an empty
  list.
- 15 new tests (`tests/test_listing_import_service.py`): unresolved-
  listing creation, get-or-create-by-URL, commercial-fact denormalization,
  failure-is-recorded-not-raised, the bundle/`fetch_status` regression
  above, both existing-product and new-product resolution (plus the
  product_id backfill), both existing-bundle and new-bundle resolution
  (plus the *no* backfill), a mixed existing+new bundle-member
  resolution, and all four guard-rail rejection paths.
- `fetch_status_for_evidence`'s promotion from private to shared also
  needed one stale test-comment fix (`test_products_source_import_and_
  profile_api.py`, no behavior change) and confirmed unchanged behavior
  via all pre-existing `test_product_source_import_service.py`/`test_
  products_source_import_and_profile_api.py` tests passing unmodified.
- Full suite: 178/178 passing (163 existing + 15 new). Ruff clean on
  every new/changed file. App boots cleanly, 28 routes (unchanged - no
  new endpoints this sub-phase, that's 5.11's job).
- Zero behavior change to the existing per-product import flow (Phase
  5.3/5.6) - `import_product_source` itself untouched beyond the shared
  helper's rename.
- Commit: (see git log)

### Phase 5.11 — API surface for listings/bundles (done)

- New `app/routers/listings.py` (`/api/listings`): `POST .../source-import`
  (200, same synchronous-fetch reasoning as the existing per-product
  endpoint), `GET .../{id}` (returns `ListingDetailRead` - `ListingRead`
  plus `pending_bundle_hints`, populated only when unresolved with
  bundle evidence), and the four resolve-* endpoints
  (`resolve-existing-product`, `resolve-new-product`,
  `resolve-existing-bundle`, `resolve-new-bundle`), named to match 5.10's
  service function names exactly rather than the plan's original sketch.
- New `app/routers/bundles.py` (`/api/bundles`): `GET .../{id}` only -
  bundles are created via `resolve-new-bundle`, never directly here. Calls
  5.5's `assemble_product_profile` once per member, completely unmodified
  - no new merge logic anywhere in this router, per the ADR's Bundle View
  definition.
- Error-handling convention, consistent across every new endpoint: 404
  when the path's `listing_id`/`bundle_id` itself doesn't exist (checked
  directly in the router, same pattern as every other router in this
  codebase); 400 for every other domain violation (unknown
  product/bundle in the request body, already-resolved listing,
  malformed member resolution) - 5.10's `ValueError`s, caught and
  translated here.
- New schemas in `app/schemas.py`: `ListingRead`, `ListingDetailRead`,
  `PendingBundleMemberHintRead`, the four resolve-* request schemas,
  `ProductBundleRead`, `BundleMemberProfileRead`, `BundleViewRead`.
  `BundleMemberProfileRead.profile` is `app.services.product_profile.
  ProductProfile` imported directly (no forward-ref needed -
  `product_profile.py` doesn't import `schemas.py`, confirmed before
  adding the import, no circular-import risk).
- New `get_pending_member_hints(db, listing_id)` in `listing_import.py` -
  reads the current unresolved import's `normalized_json["bundle"]` for
  display; read-only, never mutates resolution state.
- 15 new route-level tests (`tests/test_listings_and_bundles_api.py`):
  source-import success/failure/commercial-fact-denormalization, pending-
  hints exposure (present for bundle evidence, empty for ordinary),
  both product resolve paths (success, unknown-product 400, unknown-
  listing 404), already-resolved rejection, empty-members rejection,
  unknown-bundle 404, resolve-existing-bundle, and - matching the plan's
  own stated test strategy exactly - a full end-to-end bundle flow:
  import a bundle-shaped fixture, resolve one hint to an existing product
  and one to a new one, `GET /api/bundles/{id}` returns both real member
  profiles (not mocked at the profile-assembly level, only at adapter
  resolution, same discipline as every other Product Intelligence test).
- Full suite: 193/193 passing (178 existing + 15 new). Ruff clean. App
  boots cleanly, 35 routes (was 28 - 7 new: 6 on `/api/listings`, 1 on
  `/api/bundles`).
- Live-verification against the real dev server deferred to 5.12, same
  precedent as 5.6→5.7 (backend-API sub-phase, then the frontend
  sub-phase that actually exercises it end-to-end).
- Zero behavior change to anything existing - new routers, new schemas,
  nothing else touched.
- Commit: (see git log)

### Phase 5.12 — Frontend: unresolved-listing review + bundle view (done)

**Phase 5 (Product Intelligence, including the catalogue-layer extension
5.8-5.12) is now complete.**

- New `CatalogueImporter.tsx`: a URL-first import form (mirrors 5.7's
  per-product form, scoped to `/api/listings/*`), rendering exactly one
  of three states after import - already-resolved, unresolved-bundle
  (per-hint existing-product dropdown / new-product name input, a bundle-
  name field defaulting to the adapter-suggested title), or unresolved-
  single-product (the same existing/new choice, once). Wired into
  `App.tsx` right below `ProductManager`.
- **Real, small gap found and fixed before building the UI, not
  guessed at**: `ListingDetailRead` had no field for the adapter's
  suggested bundle title (`NormalizedBundleEvidence.title`, captured
  since 5.9 but never surfaced) - without it, the "name this bundle"
  form field would have no sensible default even when the adapter found
  a real one (e.g. the page's `<title>` tag, per `generic.py`'s own
  fallback). Fixed additively: new `pending_bundle_title` field, a new
  `get_pending_bundle_title` service function (sharing a `_current_
  pending_bundle_evidence` helper with the existing `get_pending_member_
  hints` rather than duplicating the lookup), one new backend test. Never
  authoritative - purely a suggested default the human can override, same
  as every other adapter-derived hint.
- `ProductManager.tsx` refactored, not rewritten: `AttributeValueDisplay`
  exported, and the field-grid rendering block extracted into a new
  exported `ProductProfileFields` component - so the Bundle view renders
  each member's `ProductProfile` with the **identical** renderer, not a
  duplicate one, making "a bundle's profile is a list of its members'
  real profiles" concrete on the frontend too, not just the backend.
  Zero behavior change to `ProductManager`'s own rendering - confirmed by
  the live-verification below re-testing the existing per-product flow
  unchanged.
- New CSS section (`.catalogue-importer-*`, `.listing-review-*`,
  `.bundle-review-*`, `.bundle-member-*`, `.bundle-view-*`) matching the
  existing app's visual language, no new design system introduced.
- `tsc -b && vite build`: clean. `oxlint`: clean (exit 0).
- **Live-verified against the real dev server and real dev DB**
  (backend on :8000, vite dev server proxying to it), three real,
  distinct scenarios:
  - **Ordinary single-product path, real network**: imported
    `books.toscrape.com`'s real "A Light in the Attic" page (same URL
    Phase 5.7 used) - correctly showed the single-product resolution
    form (no bundle detected), resolved to a new Product, confirmed the
    new product propagated live across the entire app (top Products
    list, every `SlideProductPicker` dropdown) via the existing
    `onProductsChanged` callback chain - no new propagation code needed.
  - **Bundle path, genuine HTTP round-trip**: a real, publicly reachable
    page using this exact markup (multi-`Product` `@graph` JSON-LD) could
    not be found after real search effort - confirmed, not assumed: web
    search results explicitly note this pattern is uncommon and actively
    discouraged by SEO guidance for single-topic product pages, which is
    itself real corroborating evidence for Phase 5.9's own "deliberately
    narrow, not exhaustive" framing of the detection heuristic. Rather
    than fabricate a mocked fixture disguised as a live test, served a
    small, self-authored two-`Product` `@graph` page over a real local
    HTTP server and imported it through the actual running app - a
    genuine HTTP fetch, real `BeautifulSoup`/JSON-LD parsing, real
    bundle-detection heuristic, real persistence, all through the real
    stack; only the page's origin (localhost, not the open internet) and
    authorship differ from an ideal live test, and that distinction is
    recorded here rather than glossed over.
  - Confirmed: bundle correctly detected ("This listing looks like a
    bundle of 2 items"); bundle-name field correctly prefilled from the
    page's `<title>` tag; mixing resolution modes per member worked
    live (linked one hint to the real pre-existing "Bellavita" product,
    left the other as "create new" for "CEO Man"); after submitting,
    the Bundle view correctly showed **both** members with the identical
    renderer - Bellavita's real, rich, pre-existing `ProductProfile`
    (vision-derived data from earlier in this session) rendered in full,
    CEO Man correctly showing "No evidence yet" - proving
    `assemble_product_profile` is genuinely reused unmodified per member
    against real data, not just empty fixtures, exactly as the ADR's
    Bundle View definition requires.
  - No console errors at any point across all three scenarios.
- Zero behavior change to `ProductManager`'s existing per-product flow -
  confirmed unaffected by both the refactor and the new component
  existing alongside it.
- Commit: (see git log)

---

## Phase 7: Narrative pass with dependency-aware staleness — architecture direction

**Status**: no prior detailed-planning history existed for this phase
(unlike every other phase, which had at least a first-pass direction
note) - the phase-list entry was a one-line placeholder from the original
pre-Phase-5-revision numbering. This section derives the actual scope
from the frozen architecture vision's own words plus a direct reading of
the current pipeline code, per the standing "plan before code"
discipline and the explicit delegated authority to make this call
without pausing to ask.

**What "Narrative pass" means, grounded in the frozen vision's own
text** (see "Frozen architecture vision" near the top of this document):
"narrative structure (hook, story, reveal, proof, CTA) is analyzed at
the slideshow level, independently of per-slide asset detection." This
is categorically different from the already-shipped `MarketingAnalysis`
(Phase 2.4d) - confirmed by reading its actual stage code, not assumed:
`MarketingAnalysisStage` generates one freeform `narrative_text` blob
from a *single* slide's (`primary_slide`'s) Creative Fingerprint alone -
no structure, no per-slide breakdown, no sequence awareness at all. A
true hook/story/reveal/proof/CTA analysis requires looking at the
*sequence* of slides - fundamentally different from and complementary
to Marketing Analysis's single-slide "why does this design work"
summary, not a replacement for it.

**Real prerequisite gap found while scoping this, not assumed**: every
per-slide Stage today - `SlideOCRStage`, `SlideProductIsolationStage`,
`SlideProductLockProfileStage`, `SlideCreativeFingerprintStage` - reads
`slideshow.primary_slide` only, even after Phase 4 (true multi-slide
import) made `slideshow.slides` a real ordered list. Confirmed by reading
every stage file directly. This isn't a new limitation Phase 7
introduces - it's a load-bearing gap that's been sitting unaddressed
since Phase 2.6/4 (a frontend docstring even flagged it, expecting "Phase
5" to fix it, before Phase 5 got redirected entirely to Product
Intelligence by the 2026-07-22 revision). A sequence-aware Narrative Pass
is impossible without per-slide data across *all* slides, so fixing this
is this phase's real first sub-phase, not scope creep.

**Scope decision, made deliberately narrow (mirrors Phase 6.2's
precedent of choosing the honestly-deliverable scope over a bigger,
riskier one)**: fixing "every stage operates on primary_slide only" for
*all four* per-slide stages is a materially bigger, more expensive change
(each additional stage widened to multi-slide means N vision/AI calls
per slideshow instead of one, with its own cost and design questions) and
isn't required for Narrative Pass specifically. **Only `OCRStage` gets
widened to all slides in this phase** - the minimum real prerequisite.
Widening Product Isolation/Lock Profile/Creative Fingerprint to
multi-slide is logged under "Suggested future improvements," not
attempted here.

**Narrative Structure's own design, chosen to avoid new AI-provider
work**: a vision-based "look at every slide image together" pass would
need a genuinely new AI-provider capability (`VisionAnalysisProvider.
analyze_creative` takes exactly one image, confirmed by reading
`app/ai_providers/base.py` - no multi-image capability exists today).
Rather than build that (real, undesigned AI-provider interface work,
same category this project has deferred before - see Phase 6's
product-targeted-isolation entry in "Suggested future improvements"),
Narrative Structure is designed as **text-only**, reusing the *already-
existing* `TextGenerationProvider` (exactly what Marketing Analysis
already uses) - it classifies each slide's narrative role from that
slide's OCR structured text alone (headline/CTA/dialogue, already
extracted and role-tagged by OCR), in slide-index order. **Documented
limitation, not solved here**: a slide with no on-screen text has
nothing for this pass to classify from - it gets an honest
"unclassifiable" beat, not a guessed one, matching this project's
standing "honest gap over plausible-looking wrong data" discipline. A
real fix needs vision input, logged as future work alongside the
per-slide-stage widening above.

**Dependency graph, derived from reading actual current code, not
invented**:

| Stage | Depends on |
|---|---|
| `ocr` | none |
| `product_isolation` | none (depends on product assignment, not another stage) |
| `product_lock_profile` | `product_isolation` (uses its current reference images at generation time) |
| `creative_fingerprint` | `ocr` (reads it as enrichment context if present - confirmed in the stage's own docstring) |
| `marketing_analysis` | `creative_fingerprint` |
| `narrative_structure` (new) | `ocr` (all slides) |
| `recreation_prompt` | `product_lock_profile`, `creative_fingerprint` |

**Real gap found in this graph**: `RecreationPrompt` already records
which `product_lock_profile_id`/`creative_fingerprint_id` it was built
from (existing FKs) - but `MarketingAnalysis` has **no**
`creative_fingerprint_id` column at all, confirmed by reading its model.
It can't be checked for staleness without first recording what it was
built from. Fixing this is a real, small, additive prerequisite
sub-phase, not new functionality.

**What staleness means concretely**: an artifact is stale if the
upstream artifact it recorded as its input is no longer the *current*
one for that slide/slideshow - e.g. Recreation Prompt was built from
Creative Fingerprint version A, but Creative Fingerprint has since been
regenerated to version B; the Recreation Prompt is now stale relative to
the slide's current state, even though its own content hasn't changed.
Compute-on-read (`is_stale`), same philosophy as `assemble_slideshow_
blueprint` itself - never a persisted flag that could itself go stale.

## Phase 7: Narrative pass with dependency-aware staleness — detailed sub-phase plan

### 7.1 — Extend OCR Stage to run across every slide

- `SlideOCRStage.run()` changes from `slide = slideshow.primary_slide` to
  iterating `slideshow.slides`, running OCR once per slide, writing each
  slide's own `current_ocr_result_id` - the schema already supports this
  (`Slide.current_ocr_result_id` has been a per-slide column since Phase
  2.1); this is purely an orchestration-logic change; **zero migration
  needed**.
- One slide's OCR failure: fails the whole stage (matches existing
  single-slide failure semantics - `AnalysisRun`/`mark_failed` already
  record exactly which attempt failed) rather than silently skipping a
  slide, consistent with "honest failure over silent partial data."
- **Test strategy**: existing single-slide-slideshow tests must keep
  passing unchanged (regression guard - a 1-slide slideshow behaves
  identically to today). New tests: a real multi-slide slideshow (Phase
  4's grouped import) gets OCR on every slide, each with its own
  `current_ocr_result_id`; one slide's OCR failure fails the stage
  cleanly.
- **Rollback**: revert; slideshows revert to primary-slide-only OCR,
  same as before this sub-phase.
- **Expected commit size**: small.

### 7.2 — Narrative Structure stage (new)

- New model `NarrativeStructure` (slideshow-scoped, mirrors
  `MarketingAnalysis`/`RecreationPrompt`'s shape): `id, analysis_run_id,
  slideshow_id, is_current, structured_json` (per-slide beats +
  overall arc summary), `ocr_result_ids_json` (the list of OCR result
  IDs, one per slide, it was built from - the provenance staleness in
  7.4 needs). New migration, additive only.
- New `NarrativeStructureStage`: text-only (`TextGenerationProvider`,
  same capability Marketing Analysis already uses - no new AI-provider
  work), reads every slide's current OCR result in `slide_index` order,
  prompts for a per-slide `beat` classification (`hook` | `story` |
  `reveal` | `proof` | `cta` | `other` | `unclassifiable`) plus a short
  overall arc summary. A slide with no OCR text (or OCR that failed)
  gets `unclassifiable`, not a guess.
- Added to `SLIDESHOW_STAGE_PIPELINE` after `marketing_analysis` (no
  ordering dependency on it either way - grouped there for pipeline
  readability, both being slideshow-scoped narrative-adjacent stages).
- **Test strategy**: single-slide slideshow (regression-shaped, still
  produces one beat), real multi-slide slideshow with distinct OCR text
  per slide (confirms per-slide beat classification, not one blob),
  a slide with empty OCR text produces `unclassifiable`, missing-OCR
  prerequisite failure (mirrors every other stage's prerequisite-check
  pattern).
- **Rollback**: revert; nothing else depends on this stage yet.
- **Expected commit size**: medium.

### 7.3 — Provenance backfill: `MarketingAnalysis.creative_fingerprint_id`

- New nullable FK column (nullable since existing rows have no way to
  backfill which fingerprint they were actually built from - additive,
  not a data migration). `MarketingAnalysisStage` sets it going forward
  from the fingerprint it already reads.
- **Test strategy**: new `MarketingAnalysis` rows record the id; existing
  rows (`None`) don't crash the staleness check in 7.4 - a `None`
  provenance means "can't determine staleness," not "stale" or "fresh."
- **Rollback**: revert; column drops, nothing else depends on it yet.
- **Expected commit size**: small.

### 7.4 — Dependency-aware staleness

- New `app/services/staleness.py`: the `STAGE_DEPENDENCIES` graph
  (the table above, as data) plus `is_stale(artifact, ...)` /
  `stale_because(artifact, ...)` compute-on-read functions - one per
  artifact type, since each records its provenance differently (FK
  columns vs. a JSON id list for Narrative Structure).
- Wired into `assemble_slideshow_blueprint`: every dependent artifact in
  the response (`product_lock_profile`, `creative_fingerprint`,
  `marketing_analysis`, `narrative_structure`, `recreation_prompt`) gains
  `is_stale: bool` and `stale_because: list[str]` (which upstream
  dependency moved on) fields on its `*Read` schema.
- **Test strategy**: unit tests per dependency pair (fresh - upstream
  unchanged since generation; stale - upstream regenerated since;
  unknown - `None` provenance, e.g. a pre-7.3 `MarketingAnalysis` row);
  route-level test confirming the blueprint response carries the new
  fields correctly for a real rerun-and-go-stale sequence.
- **Rollback**: revert; the blueprint response loses the two new fields,
  nothing else depends on them yet (until 7.5).
- **Expected commit size**: medium.

### 7.5 — Frontend: narrative beats + staleness indicators

- `SlideshowBlueprintModal.tsx`: a new "Narrative Structure" section
  showing each slide's beat (as a badge, e.g. next to the existing
  slide selector) and the overall arc summary; every existing section
  with a dependency (Product, Creative Fingerprint, Marketing Analysis,
  Recreation Prompt) gains a small "stale" indicator (reusing the
  existing `classification-badge`-style visual language, not a new
  design system) when `is_stale` is true, with its existing rerun button
  doubling as the fix.
- Live-verify against a real multi-slide slideshow: confirm distinct
  per-slide beats render, confirm rerunning an upstream stage (e.g.
  Creative Fingerprint) makes a downstream one (Recreation Prompt)
  visibly flip to stale without regenerating it.
- **Rollback**: revert; blueprint modal reverts to no staleness/beat
  display, still fully functional otherwise.
- **Expected commit size**: medium.

**Risks**: 7.2's text-only design is the main one - a slideshow that's
entirely on-screen-text-free will get all-`unclassifiable` beats, a real
but honestly-declared gap (see the architecture direction above), not
a silent wrong answer. 7.1's widening to all slides means OCR now runs N
times instead of once per multi-slide slideshow - a real, modest cost
increase, acceptable for OCR specifically (cheap relative to vision/
generation calls) but part of why the other three per-slide stages are
deliberately NOT widened in this phase.

## Phase 7 reports log

### Phase 7.1 — Extend OCR Stage to run across every slide (done)

- `SlideOCRStage.run()` changed from `slide = slideshow.primary_slide`
  (a single stage-scoped `AnalysisRun`) to iterating `slideshow.slides`
  (already ordered by `slide_index` via the relationship's own
  `order_by`), running OCR once per slide with its own `AnalysisRun`,
  writing each slide's own `current_ocr_result_id`. Zero schema/migration
  change - `Slide.current_ocr_result_id` has been a per-slide column
  since Phase 2.1, confirmed before writing any code.
- One slide's OCR failure fails the whole stage immediately - slides
  processed before the failing one keep their already-committed,
  already-current results (verified explicitly by test: slide 1 succeeds
  and keeps its result, slide 2 fails, slide 3 is never attempted).
- 2 new tests (`tests/test_slide_ocr_stage.py`): a real 3-slide slideshow
  gets distinct OCR text on every slide, proven via a
  `_SequentialFakeOCRProvider` that returns a different extraction per
  call (not one result silently reused three times); the failure-mid-run
  behavior above. All 3 pre-existing single-slide tests pass completely
  unchanged - confirms the single-slide case (still the overwhelming
  majority of real slideshows) is byte-for-byte unaffected.
- Full suite: 195/195 passing (193 existing + 2 new). Ruff clean. App
  boots cleanly, 35 routes (unchanged - no new endpoints this sub-phase).
- Zero behavior change to anything downstream - nothing yet reads more
  than `primary_slide`'s OCR result (that's Phase 7.2's job), so a
  1-slide slideshow's blueprint/pipeline output is identical to before.
- Commit: (see git log)

### Phase 7.2 — Narrative Structure stage (done)

- New model `NarrativeStructure` (slideshow-scoped, mirrors
  `MarketingAnalysis`/`RecreationPrompt`'s shape via
  `AnalysisArtifactMixin`): `structured_json` (`{slides: [{slide_id,
  slide_index, beat}], arc_summary}`), `ocr_result_ids_json` (one OCR
  result id per slide, in slide order - the exact provenance Phase 7.4's
  staleness check needs). New `Slideshow.current_narrative_structure_id`
  pointer, same plain-String pattern as the two existing ones. New
  migration `19b5c9909b3e`, additive only (no batch mode needed - a plain
  nullable column add, not an ALTER requiring a new FK constraint) -
  full backup/scratch-copy/round-trip discipline applied before touching
  the real dev DB.
- New `SlideshowNarrativeStructureStage`: text-only
  (`TextGenerationProvider`, the same capability Marketing Analysis
  already uses - zero new AI-provider work), added to
  `SLIDESHOW_STAGE_PIPELINE` after Marketing Analysis. Slides with no
  current OCR result or empty OCR text are never sent to the AI and are
  force-assigned `unclassifiable` by the stage's own code - not left to
  the model to self-report - verified by a dedicated test that gives the
  fake AI a plausible-but-wrong answer for an unsent slide and confirms
  the stage ignores it. If literally no slide has any OCR text, the whole
  stage fails cleanly ("No OCR text available on any slide yet"),
  mirroring every other stage's prerequisite-check pattern.
- `NarrativeStructureRead` schema + `AssembledSlideshowBlueprint.
  narrative_structure` field added to the blueprint response in this
  same sub-phase, matching how every other stage's artifact has always
  landed alongside its stage (not deferred to a later API sub-phase) -
  `assemble_slideshow_blueprint` resolves it from `slideshow.
  current_narrative_structure_id` exactly like Marketing Analysis/
  Recreation Prompt already do.
- **Real gap found and fixed while wiring the full pipeline, not
  anticipated in the plan's prose**: adding a 7th stage to
  `SLIDESHOW_STAGE_PIPELINE` broke the two existing "run the entire real
  pipeline" tests (`test_default_pipeline_runs_all_six_stages` in
  `test_slideshow_orchestrator.py`, `test_blueprint_reflects_full_
  pipeline_results` in `test_slideshow_blueprint_api.py`) - both iterate
  a fixed list of stage modules to monkeypatch and didn't know about the
  new one. Fixed by patching `narrative_structure_stage`'s own registry
  in both. Renamed the orchestrator test to `..._all_seven_stages` and
  added assertions for the new pointer, rather than just silencing the
  failure.
- **A second real gap found in shared test infrastructure**:
  `FakeTextGenerationProvider` (`tests/fakes.py`) had a hardcoded shape
  guard asserting every canned result matches `MARKETING_ANALYSIS_SCHEMA`
  exactly (`{"narrative": str}`) - correct when Marketing Analysis was
  the only real consumer of `TextGenerationProvider`, now wrong now that
  Narrative Structure is a second consumer with a different real schema.
  Fixed by scoping the guard to the class's own default canned result
  only (its original purpose) - an explicitly supplied `result=` is
  trusted as the caller's responsibility, since it's now genuinely
  ambiguous which of two schemas a fake author intends. Confirmed no
  existing test relied on the guard firing on a custom `result=` before
  making this change.
- 5 new tests (`tests/test_slide_narrative_structure_stage.py`): missing-
  OCR-everywhere prerequisite failure, single-slide gets one beat,
  real multi-slide slideshow gets distinct per-slide beats (not one
  blob), the no-OCR-text-forces-unclassifiable regression guard described
  above, rerun produces a new version and flips the previous one's
  `is_current`. Plus 1 new assertion added to the existing full-pipeline
  blueprint test confirming `narrative_structure` appears correctly in
  the response.
- Full suite: 200/200 passing (195 existing + 5 new). Ruff clean on every
  new/changed file (11 pre-existing baseline findings elsewhere,
  unrelated). App boots cleanly, 35 routes (unchanged - no new endpoints
  this sub-phase, the artifact is read via the existing blueprint
  endpoint). Pipeline confirmed to run all 7 stages in the correct order
  via direct inspection.
- Zero behavior change to the single-slide, no-narrative-structure-yet
  case beyond gaining the new stage itself - every other artifact's
  assembly/response shape is untouched.
- Commit: (see git log)

### Phase 7.3 — Provenance backfill: `MarketingAnalysis.creative_fingerprint_id` (done)

- New nullable FK column, exactly as planned: `MarketingAnalysisStage`
  now records which `CreativeFingerprint` it actually read when creating
  each row. Migration `15210f8f4d89`, batch mode (adding a column with a
  new FK constraint, same requirement as 37e53bed7ec8/d3bafd6a4965) -
  full backup/scratch-copy/round-trip discipline applied, including
  confirming both existing `marketing_analyses` rows correctly stay
  `None` after upgrade (nothing to truthfully backfill them with) and the
  column/constraint cleanly disappear on downgrade.
- `MarketingAnalysisRead` gained the field too (`None` for pre-7.3 rows,
  same nullable, `from_attributes`-compatible pattern as everywhere else)
  - `assemble_slideshow_blueprint` needed no code change, since it
    already builds this schema via `model_validate(row)`.
- 2 new tests: the stage's own success test now also asserts the
  recorded id matches the slide's actual current fingerprint; a
  dedicated test constructs a legacy-shaped row (no
  `creative_fingerprint_id` supplied) and confirms it round-trips as
  `None` cleanly, not a data-integrity error - exactly the tolerance
  Phase 7.4's staleness check needs (`None` means "unknown", never
  "stale" or "fresh").
- Full suite: 201/201 passing (200 existing + 1 new test file entry,
  plus 1 assertion added to an existing test). Ruff clean. App boots
  cleanly, 35 routes (unchanged - no new endpoints).
- Zero behavior change to anything existing beyond the one new column -
  every pre-7.3 `MarketingAnalysis` row and every consumer of it
  continues to work exactly as before.
- Commit: (see git log)

### Phase 7.4 — Dependency-aware staleness (done)

- **Real prerequisite gap found while implementing, not anticipated in
  the architecture-direction doc**: the dependency graph declared
  `creative_fingerprint: ["ocr"]`, but `CreativeFingerprint` had no
  column recording which OCR result it actually read - no way to check
  that edge at all. Fixed inline (not spun into a new sub-phase), same
  pattern as 7.3's `MarketingAnalysis.creative_fingerprint_id` fix: new
  nullable `CreativeFingerprint.ocr_result_id` FK, `SlideCreativeFingerprintStage`
  now records the OCR result it actually incorporated (`None` when none
  existed yet). Migration `4b599e19a719`, batch mode (new FK constraint),
  full backup/scratch-copy/round-trip discipline applied before touching
  the real dev DB.
- New `app/services/staleness.py`: `STAGE_DEPENDENCIES` graph (data,
  documentation of every edge) plus 5 compute-on-read functions, one per
  artifact type since each records its provenance differently -
  `product_lock_profile_staleness`/`narrative_structure_staleness`
  compare a recorded id set/list against a freshly-queried current one,
  `creative_fingerprint_staleness`/`marketing_analysis_staleness` walk a
  single FK and check `is_current`, `recreation_prompt_staleness` checks
  both of its two dependencies independently and reports both if both
  moved. `None`/missing provenance is always `is_stale=False` ("unknown",
  never asserted as either fresh or stale) - the same tolerance Phase
  7.3 built in.
- Wired into `assemble_slideshow_blueprint`'s 5 artifact-construction
  sites: every dependent `*Read` schema now carries real `is_stale`/
  `stale_because` values instead of the schema's own `False`/`[]`
  defaults. `MarketingAnalysisRead` switched from `model_validate(row)`
  to explicit field-by-field construction (matching the other 4) since
  the two new fields aren't real ORM columns and `model_validate` only
  pulls matching attribute names.
- 13 new unit tests (`tests/test_staleness_service.py`): fresh/stale/
  unknown for every one of the 5 dependency edges, including both of
  Recreation Prompt's dependencies going stale independently and
  together. 1 new route-level test
  (`test_blueprint_reflects_staleness_after_an_upstream_rerun` in
  `test_slideshow_blueprint_api.py`) runs the real 7-stage pipeline to a
  ready state, reruns only Creative Fingerprint via the actual HTTP
  rerun endpoint, and confirms through a real GET /blueprint that
  Marketing Analysis and Recreation Prompt both flip
  `is_stale=True`/`stale_because=["creative_fingerprint"]` without being
  regenerated themselves (same row id), while unrelated artifacts
  (Product Lock Profile, the fingerprint's own fresh state after rerun)
  stay unaffected - the actual end-to-end behavior the whole sub-phase
  exists to deliver, not just the isolated comparison functions.
- Full suite: 215/215 passing (201 existing + 13 staleness-service +
  1 route-level). Ruff clean on every new/changed file (11 pre-existing
  baseline findings elsewhere in untouched model files, unrelated -
  confirmed by running ruff scoped to just this sub-phase's files).
  App boots cleanly.
- Zero behavior change to any artifact's actual content - `is_stale`/
  `stale_because` are purely additive response fields; a client that
  ignores them sees byte-identical behavior to before.
- Commit: (see git log)

### Phase 7.5 — Frontend: narrative beats + staleness indicators (done)

- `frontend/src/api.ts`: added `is_stale`/`stale_because` (both optional,
  matching the backend's own defaulting for pre-7.4 callers) to
  `ProductLockProfile`, `CreativeFingerprintData`, `MarketingAnalysisData`,
  `RecreationPromptData`; new `NarrativeStructureData` type and
  `AssembledSlideshowBlueprint.narrative_structure` field (both existed
  on the backend since 7.2/7.4 but were never added to the frontend
  contract - a real gap found while wiring this sub-phase, not a
  regression).
- `SlideshowBlueprintModal.tsx`: new `StaleBadge` component (reuses the
  existing `classification-badge` visual language per the plan, new
  `.stale-badge` color modifier in `App.css`) rendered next to a
  section's title whenever that artifact `is_stale`, with the specific
  upstream stage name(s) as a hover tooltip; wired into all 5 dependent
  sections (Product Lock Profile, Creative Fingerprint, Marketing
  Analysis, Recreation Prompt, and the new Narrative Structure section
  itself). New "Narrative Structure" `BlueprintSection` (arc summary +
  a per-slide beat list, current slide bolded) inserted between
  Marketing Analysis and OCR Text, matching pipeline order. A small
  `.beat-badge` next to the existing slide-selector's "Slide X of Y"
  label shows the current slide's own beat at a glance without opening
  the new section.
- **Real infrastructure gap found and fixed while live-verifying, not
  anticipated in the plan**: `vite.config.ts`'s dev proxy still
  hardcoded `target: 'http://127.0.0.1:8000'`, stale from before
  `.claude/launch.json`'s backend config was moved to port 8321 earlier
  in this session - every `/api` call from `npm run dev` was silently
  502ing. Fixed by pointing the proxy at 8321 to match the already-
  correct launch config; also found and stopped an orphaned `vite`
  process from a prior session still holding port 5173.
- **Live verification**: real OpenAI-backed reruns weren't available in
  this environment (no API key configured, confirmed via the app's own
  real error banner: "No API key found for provider 'openai'" - the
  same failure-surfacing path every other stage already uses, so this
  incidentally re-confirmed that path still works correctly for the two
  newest stage names). Entering credentials is out of scope for
  autonomous work, so real end-to-end AI generation wasn't exercised
  here. Instead verified via a client-side `fetch` interception in the
  live browser tab (visual QA only, never touches persisted data) that
  fed the real blueprint response through with realistic
  `narrative_structure`/`is_stale`/`stale_because` values: confirmed via
  direct DOM inspection that the Narrative Structure section renders the
  arc summary and a correctly-labeled, correctly-highlighted beat list;
  that Marketing Analysis and Recreation Prompt both show a `stale`
  badge with an accurate, correctly-joined "Out of date since ..."
  tooltip (Recreation Prompt's showing both of its two dependencies);
  that Product Lock Profile shows its own stale badge; and that Creative
  Fingerprint - deliberately left fresh in the mock - shows no badge at
  all, confirming the badge is conditional and not always-on. Two live
  rerun attempts against the real backend (both failing cleanly on the
  missing API key, as intended) transiently flipped a real dev
  slideshow's status to `failed`; confirmed via direct sqlite3
  inspection that its artifact pointers were untouched (matching the
  non-destructive-failure guarantee every stage already provides) and
  restored its `status`/`last_failed_stage`/`last_failed_stage_error`
  columns to their prior values before finishing.
- `npx tsc --noEmit`, `npm run lint` (oxlint), and `npm run build` all
  clean.
- Zero behavior change for any pre-7.4 artifact or any slideshow that
  hasn't run Narrative Structure yet - `is_stale`/`stale_because` are
  optional on every frontend type and the new section's empty state
  ("Not generated yet.") matches every other section's.
- Commit: (see git log)

---

## Phase 8: Generation → Validation proof of loop — architecture direction

**Status: direction set 2026-07-22, ready for implementation.**

### 2026-07-22 standing directive (governs this phase and every phase after it until revisited)

"The infrastructure is now sufficiently mature. From this point onwards, bias towards proving the end-to-end Generation → Validation loop rather than adding more architectural capability. If additional infrastructure is genuinely required to support that loop, justify it with the concrete blocker it removes." Concretely: build against OpenAI's image generation API first, not optimizing for quality or cost; prove `Product Profile + Creative Specification → Prompt Compiler → ImageGenerationProvider → Generated Image → VisionAnalysisProvider → Validation → Pass/Fail` for **one slide** - no whole-slideshow generation, no multi-candidate generation, no automatic retry/regenerate loop. Once one slide can be generated, validated, and explained, the hardest unproven part of the platform is de-risked; everything past that is scaling, not proving the concept.

### What already exists and is reused as-is (no new infrastructure)

- `RecreationPrompt` (renamed to `CreativeSpecification` in 8.1 below) is already a generation-ready, provider-neutral spec: subject, composition, style_direction, color_palette, lighting, camera_and_perspective, background_environment, mood, text_overlays, things_to_avoid, aspect_ratio.
- The canonical `ProductProfile` (Phase 5.5) already classifies every field `immutable` (must be preserved) vs. `contextual` (expected to vary) - exactly the contract Validation needs, with zero design changes.
- `VisionAnalysisProvider.analyze_creative(image_bytes, prompt_spec, response_schema)` (already used by Product Lock Profile and Creative Fingerprint) is reused unchanged for Validation - a new prompt/schema, not a new provider.
- The provider registry/config pattern (`app/ai_providers/base.py` Protocols, `app/ai_providers/openai_adapter.py` concrete adapters, `app/ai_providers/registry.py`, `providers.yaml`) is reused unchanged in shape - `ImageGenerationProvider` is a sixth capability added the same way `prompt_generation` was added as a fifth in M6, not a new pattern.

### The one genuine new capability, and why it's unavoidable

No existing provider can produce an image - all 5 are analysis-only (image/text in, structured JSON out). `ImageGenerationProvider` is the one new interface this phase adds, because the loop cannot run at all without something that returns image bytes. This is the concrete blocker the user asked to have named before adding it.

### Rename: RecreationPrompt → CreativeSpecification

Once generation exists, "prompt" becomes ambiguous - there's the **Creative Specification** (what should be created: subject, style, composition - provider-neutral intent, persisted) and the **compiled provider prompt** (the literal string sent to OpenAI's API - provider-specific syntax, never the canonical persisted record). Renaming now avoids the wrong concept anchoring itself in the DB right as generation lands.

Scope of the rename: the *new-pipeline* entity only - model, table, stage, schema, staleness check, pipeline registration, frontend types/UI, and every new-pipeline test. **Explicitly not touched**: `app/models/creative_blueprint.py`'s `current_recreation_prompt_id` column (the legacy, Phase-2.8-gated old-pipeline schema) and `app/services/slideshow_backfill.py`'s read of that legacy column - both are frozen, out-of-scope-until-2.8 leftovers, not live code this rename needs to reach. Docstring-only mentions of "RecreationPrompt" as a historical design reference (`marketing_analysis.py`, `narrative_structure.py`) get a one-line wording update for accuracy, not a functional change.

### Prompt Compiler - what "provider-agnostic" means concretely here

`app/services/prompt_compiler.py` (new): a plain function, `compile_generation_request(creative_specification, product_profile, platform="generic") -> GenerationRequest`. `GenerationRequest` is a plain dataclass (`creative_intent: str`, `immutable_constraints: list[str]`, `things_to_avoid: list[str]`, `aspect_ratio: str`) - English-language intent, not provider syntax. It:
- Joins the Creative Specification's descriptive fields (subject, composition, style_direction, lighting, camera_and_perspective, background_environment, mood, color_palette, text_overlays) into `creative_intent`.
- Formats every `immutable`-classified field on the canonical `ProductProfile` (brand, product_category, shape, dimensions, capacity, materials, color, branding_text, packaging - whichever are populated) into `immutable_constraints`, so what must be preserved comes from the Product Profile itself, never re-derived from the Creative Specification.
- Passes `things_to_avoid` straight through.
- Resolves `aspect_ratio` from the Creative Specification, falling back to a small per-`platform` default dict if absent.

**Explicit scope decision on "Platform Rules"**: for one slide, one provider, proving the loop once, a full Platform Rules subsystem (persisted per-platform content-policy phrasing, exact pixel dimensions, etc.) is not required - `platform` is a plain string parameter with one small fallback table inside the compiler, not a new entity/table. This is deliberately minimal per the standing directive; a real Platform Rules concept is future work if a second platform ever needs different behavior, not built speculatively now.

The compiled `GenerationRequest` is handed to `ImageGenerationProvider.generate_image(request)`. Turning `GenerationRequest` into the literal OpenAI request (the actual prompt string, size parameter, etc.) happens **inside** `OpenAIImageGenerationAdapter`, never in the compiler - this is what keeps the rest of the system provider-agnostic per the user's explicit instruction.

### ImageGenerationProvider contract

```python
@dataclass
class GenerationRequest:
    creative_intent: str
    immutable_constraints: list[str]
    things_to_avoid: list[str]
    aspect_ratio: str

@dataclass
class GeneratedImageResult:
    image_bytes: bytes
    provider: str
    model: str
    prompt_used: str       # the actual compiled string sent to the API - persisted as metadata, not as its own canonical entity
    seed: str | None       # None for OpenAI today - its public image API doesn't expose one; the field exists for a future provider that does
    generation_time_seconds: float

class ImageGenerationProvider(Protocol):
    def generate_image(self, request: GenerationRequest) -> GeneratedImageResult: ...
```

Mirrors `ProductIsolationProvider`'s division of labor exactly: the provider returns facts about what it did (bytes + metadata), the Stage is responsible for persistence (saving the file via `app.storage`, recording the DB row) - the provider never touches storage or the DB itself.

### Validation - reuses VisionAnalysisProvider, no new provider

A new prompt/schema (`app/slideshow_stages/image_validation_stage.py`), not a new capability: lists every `immutable` field name + value from the canonical `ProductProfile`, asks the vision model to judge each as `preserved: bool` + `reason: str` against the generated image, plus one `overall_explanation`. `passed` is computed by our own code as `all(check.preserved for check in field_checks)` - never asked of the AI as a bare boolean, matching this codebase's standing rule that anything derivable from known facts is assembled directly, not left to the model to self-report (same discipline `RecreationPromptStage`/`SlideshowNarrativeStructureStage` already follow).

### Deliberately not built in this phase

- Automatic regenerate-on-fail loops or any threshold/retry logic - "generate once, validate once, see a real Pass/Fail with a real explanation" is the whole goal; a human re-triggering generation manually (via the same endpoint) is sufficient to prove "regenerate" works, without needing a new automated loop.
- Multi-candidate generation, whole-slideshow generation, reference-image-conditioned (image-to-image) generation - real quality improvements, explicitly out of scope per "not optimising for image quality... at this stage."
- Wiring these two new stages into `SLIDESHOW_STAGE_PIPELINE` or `Slideshow.status` - image generation costs real money per call in a way every existing stage doesn't as sharply, and "Analyze / Re-run All" must not silently start generating images. Both new stages get their own dedicated, explicitly-triggered endpoints instead (see 8.3/8.4), decoupled from the core pipeline's status semantics entirely. They still implement the same `SlideshowAnalysisStage`-shaped `name`/`run(db, slideshow)` contract for consistency and so pipeline integration is a small, deliberate future step if ever wanted - not a redesign.
- A background-task/polling wrapper for these two endpoints - every existing AI stage uses one because it's woven into the auto-pipeline's status polling; these two are synchronous, explicitly-triggered, single-call endpoints, so a blocking request/response (typical image generation latency is comparable to the vision/text calls already used synchronously elsewhere in tests, and this is a local single-user dev tool) is simpler and adequate. Revisit only if real latency proves this wrong.
- A `PlatformRules` entity, per above.

## Phase 8: Generation → Validation proof of loop — detailed sub-phase plan

### 8.1 — Rename RecreationPrompt → CreativeSpecification

- `app/models/recreation_prompt.py` → `app/models/creative_specification.py`: class `RecreationPrompt` → `CreativeSpecification`, table `recreation_prompts` → `creative_specifications`, columns unchanged in shape.
- `app/models/slideshow.py`: `current_recreation_prompt_id` → `current_creative_specification_id`.
- New Alembic migration: `op.rename_table`, batch-mode `op.alter_column` for the renamed Slideshow column (SQLite column rename, same batch-mode discipline as every prior column-level change this session) - full backup/scratch-copy/round-trip discipline before touching the real dev DB, matching every migration this entire engagement.
- `app/slideshow_stages/recreation_prompt_stage.py` → `app/slideshow_stages/creative_specification_stage.py`: class `SlideRecreationPromptStage` → `SlideCreativeSpecificationStage`, `.name` `"recreation_prompt"` → `"creative_specification"` (this changes the `/stages/{stage_name}/rerun` route value - a deliberate, visible rename, not hidden).
- `app/models/analysis_run.py`: `ANALYSIS_TYPE_RECREATION_PROMPT` → `ANALYSIS_TYPE_CREATIVE_SPECIFICATION`, value `"recreation_prompt"` → `"creative_specification"`.
- `app/ai_providers/base.py` / `openai_adapter.py`: `PromptGenerationProvider.generate_recreation_prompt` → `generate_creative_specification` (same signature); `OpenAIPromptGenerationAdapter` docstring/prompt text updated for the new name (no behavior change to the actual generated content).
- `app/schemas.py`: `RecreationPromptRead` → `CreativeSpecificationRead`; `AssembledSlideshowBlueprint.recreation_prompt` → `.creative_specification`.
- `app/services/slideshow_blueprint.py`, `app/services/staleness.py` (`recreation_prompt_staleness` → `creative_specification_staleness`, `STAGE_DEPENDENCIES` key), `app/slideshow_stages/pipeline.py`: updated to match.
- `app/services/slideshow_backfill.py`: only the new-side keyword (`current_recreation_prompt_id=` → `current_creative_specification_id=`) changes; its read of the legacy `blueprint.current_recreation_prompt_id` stays untouched (Phase 2.8 territory).
- Frontend: `RecreationPromptData` → `CreativeSpecificationData` in `api.ts`; `SlideshowBlueprintModal.tsx`'s "Recreation Prompt" section → "Creative Specification" (same fields, same `RecreationPromptFields` component renamed).
- All new-pipeline tests renamed/updated to match (`test_slide_recreation_prompt_stage.py` → `test_slide_creative_specification_stage.py`, plus references in `fakes.py`, `test_slideshow_blueprint_api.py`, `test_slideshow_orchestrator.py`, `test_staleness_service.py`).
- **Test strategy**: full existing test suite must pass unchanged in behavior (this is a rename, not a redesign) - a green suite after a global rename is itself the test.
- **Rollback**: revert the migration (rename back) and the commit.
- **Expected commit size**: large (mechanical, low-risk).

### 8.2 — ImageGenerationProvider contract + Prompt Compiler + OpenAI adapter

- `app/ai_providers/base.py`: add `GenerationRequest`, `GeneratedImageResult` dataclasses and the `ImageGenerationProvider` Protocol.
- `app/services/prompt_compiler.py` (new): `compile_generation_request(creative_specification: dict, product_profile: ProductProfile, platform: str = "generic") -> GenerationRequest`, per the architecture direction above.
- `app/ai_providers/openai_adapter.py`: `OpenAIImageGenerationAdapter` - calls OpenAI's image generation endpoint, does its own provider-specific prompt formatting (`_compile_openai_prompt`) from the `GenerationRequest`, times the call, returns `GeneratedImageResult`.
- `app/ai_providers/registry.py` / `config.py` / `providers.yaml`: sixth capability, `image_generation`, added the same way `prompt_generation` was added in M6 - one dict entry, one registry method (`default_registry.image_generation()`), no other registry code changes.
- **Test strategy**: unit tests for the compiler (given a Creative Specification + Product Profile, confirm `immutable_constraints` are exactly the profile's immutable fields, `things_to_avoid`/`aspect_ratio` pass through correctly, platform fallback works) using plain dicts - no AI provider involved. A fake `ImageGenerationProvider` for adapter-shape tests, mirroring `FakeVisionAnalysisProvider` etc. in `tests/fakes.py`. No real OpenAI image call in this sub-phase - that's proven live in 8.3.
- **Rollback**: revert; nothing else depends on this yet.
- **Expected commit size**: medium.

### 8.3 — GeneratedImage artifact + Image Generation Stage + API endpoint

- `app/models/generated_image.py` (new, `AnalysisArtifactMixin`): `slideshow_id`, `slide_id`, `creative_specification_id` (FK - which spec version produced it), `provider`, `model_name`, `prompt_used` (Text), `seed` (nullable String), `generation_time_seconds` (Float), `file_path` (String(1024), matching `ProductReferenceImage.file_path`'s exact convention).
- `app/storage.py`: `save_generated_image(slideshow_id, slide_id, generated_image_id, content, suffix=".png") -> Path`, same per-owning-entity layout pattern as `save_product_reference_image`.
- `app/models/analysis_run.py`: `ANALYSIS_TYPE_GENERATED_IMAGE = "generated_image"`.
- `app/slideshow_stages/image_generation_stage.py` (new): `SlideImageGenerationStage` - `SlideshowAnalysisStage`-shaped (`name = "generated_image"`, `run(db, slideshow) -> StageResult`) for consistency, but **not** added to `SLIDESHOW_STAGE_PIPELINE` (see architecture direction). Resolves the slide's primary product (reuses `_resolve_primary_appearance` from the renamed Creative Specification stage), the current Creative Specification, and `assemble_product_profile` for that product; calls `compile_generation_request` then `default_registry.image_generation().generate_image(...)`; saves the file; writes the `GeneratedImage` row; flips `is_current` on any prior `GeneratedImage` for the slide, same versioning pattern as every other artifact.
- `app/routers/slideshows.py`: `POST /api/slideshows/{slideshow_id}/slides/{slide_id}/generate-image` (synchronous, per architecture direction; returns the created `GeneratedImageRead`) and `GET /api/slideshows/{slideshow_id}/generated-images/{generated_image_id}/file` (mirrors `get_slide_file`/`get_reference_image_file`).
- `app/schemas.py`: `GeneratedImageRead`.
- **Test strategy**: stage unit tests with a fake `ImageGenerationProvider` (success, failure surfaced cleanly, missing-prerequisite failures mirroring the Creative Specification stage's own checks); route tests (success, 404s, file-serving). No real OpenAI call in automated tests, consistent with every other AI-backed stage's test discipline this whole engagement.
- **Live verification**: one real call against OpenAI's actual image generation API for one real slide, if a key is available in the environment - if not, this is flagged explicitly rather than silently skipped (same discipline as Phase 7.5).
- **Rollback**: revert; purely additive (new table, new endpoints, no existing endpoint changes).
- **Expected commit size**: medium-large.

### 8.4 — Validation Stage + API endpoint

- `app/models/image_validation_result.py` (new, `AnalysisArtifactMixin`): `generated_image_id` (FK), `product_id` (FK), `passed` (Boolean), `field_checks_json` (JSON: `[{field_name, preserved, reason}]`), `overall_explanation` (Text).
- `app/models/analysis_run.py`: `ANALYSIS_TYPE_IMAGE_VALIDATION = "image_validation"`.
- `app/slideshow_stages/image_validation_stage.py` (new): builds the field-check prompt/schema from the canonical `ProductProfile`'s immutable fields, calls `default_registry.vision().analyze_creative(...)` against the generated image's bytes, computes `passed` itself from the returned `field_checks` (never asked of the AI as a bare boolean, per architecture direction).
- `app/routers/slideshows.py`: `POST /api/slideshows/{slideshow_id}/generated-images/{generated_image_id}/validate` (synchronous, returns `ImageValidationResultRead`).
- `app/schemas.py`: `ImageValidationResultRead`.
- **Test strategy**: stage unit tests with a fake `VisionAnalysisProvider` (all-preserved → passed, one-violated → failed with the right reason surfaced, missing-generated-image 404); route tests.
- **Live verification**: real vision-analysis call against the real generated image from 8.3, if a key is available.
- **Rollback**: revert; additive only.
- **Expected commit size**: medium.

### 8.5 — Minimal frontend: trigger, view, explain

- `frontend/src/api.ts`: `GeneratedImage`, `ImageValidationResult` types; `generateImage`, `validateImage` methods.
- `SlideshowBlueprintModal.tsx`: a new "Generated Image" section per slide - a "Generate Image" button, the resulting image once present, a "Validate" button once an image exists, and the Pass/Fail result with each field's preserved/violated reason listed (this *is* the "explain why it failed" the user asked for - directly surfacing `field_checks`, not summarizing it away). Deliberately no retry/regenerate automation - re-clicking "Generate Image" is the manual regenerate path.
- **Live verification**: real browser check that one full cycle (generate → see image → validate → see Pass/Fail + reasons) renders correctly, following this session's established discipline (real preview server, real DOM inspection, honest about what needed a real API key vs. what was mocked for visual QA if a key isn't available in this environment).
- **Rollback**: revert; no other UI depends on this section.
- **Expected commit size**: medium.

**Risks**: OpenAI's real image-generation cost/latency profile is unknown until 8.3's live call - if it's materially slower than assumed, the synchronous-endpoint decision above gets revisited then, not preemptively. Prompt-compiler quality (does `immutable_constraints` phrasing actually produce a preservable result) is explicitly not being optimized in this phase - a first real Pass/Fail result, even a "Fail" with a clear reason, proves the loop; it does not need to reliably Pass.

## Phase 8 reports log

### Phase 8.1 — Rename RecreationPrompt → CreativeSpecification (done)

- Renamed the new-pipeline entity end to end: `app/models/recreation_prompt.py` → `app/models/creative_specification.py` (class + table), `Slideshow.current_recreation_prompt_id` → `current_creative_specification_id`, `app/slideshow_stages/recreation_prompt_stage.py` → `creative_specification_stage.py` (class + `.name` + the now-public `resolve_primary_appearance` helper, reused unchanged by Phase 8.3), `ANALYSIS_TYPE_RECREATION_PROMPT` → `ANALYSIS_TYPE_CREATIVE_SPECIFICATION`, `PromptGenerationProvider.generate_recreation_prompt` → `generate_creative_specification`, `RecreationPromptRead` → `CreativeSpecificationRead`, `recreation_prompt_staleness` → `creative_specification_staleness` (+ `STAGE_DEPENDENCIES` key), pipeline registration, frontend `RecreationPromptData` → `CreativeSpecificationData`, the "Recreation Prompt" UI section → "Creative Specification", and every new-pipeline test.
- New migration `a1c3e9f2b8d4`: `op.rename_table` + batch-mode `op.alter_column` for the Slideshow pointer column - full backup/scratch-copy/round-trip discipline (isolated `CAE_DATA_DIR` copy, upgrade, verified 2 rows survived with the new table/column names, downgrade, verified the original schema/names came back byte-for-byte except cosmetic batch-mode rebuild formatting), then applied to the real dev DB and re-verified before cleanup.
- **Explicitly not touched**, per the architecture direction: `app/models/creative_blueprint.py`'s legacy `current_recreation_prompt_id` column and `app/services/slideshow_backfill.py`'s read of it - both stay exactly as they were, Phase 2.8 territory.
- Full suite: 215/215 passing (pure rename, zero behavior change - a green suite after a global rename was the test, per the sub-phase's own test strategy). Ruff clean on every touched file (6 pre-existing baseline findings in untouched `slide.py`/`slideshow.py` forward-ref annotations, confirmed present on the pre-rename baseline via `git stash` before/after comparison - not introduced by this change). Frontend `tsc --noEmit`, `oxlint`, and `vite build` all clean.
- **Live verification**: real backend restarted to load the renamed models (a plain `uvicorn` process without `--reload` doesn't pick up code changes on its own - confirmed this was necessary, not just theoretical, since the first restart happened for exactly this reason). Confirmed via direct HTTP calls against the real dev DB: `GET .../blueprint` returns a populated `creative_specification` key (not `recreation_prompt`) for a real previously-generated row; `POST .../stages/recreation_prompt/rerun` now 400s ("Unknown stage"); `POST .../stages/creative_specification/rerun` is accepted. Confirmed via the real browser (DOM inspection) that the modal renders a "Creative Specification" section, with no "Recreation Prompt" anywhere in the rendered headers.
- Zero behavior change to anything else - every other artifact's assembly/response shape, and every existing stage's behavior, is untouched.
- Commit: (see git log)

### Phase 8.2 — ImageGenerationProvider contract + Prompt Compiler + OpenAI adapter (done)

- `app/ai_providers/base.py`: added `GenerationRequest` (`creative_intent`, `immutable_constraints`, `things_to_avoid`, `aspect_ratio` - English-language intent, never provider syntax), `GeneratedImageResult` (`image_bytes` + `provider`/`model`/`prompt_used`/`seed`/`generation_time_seconds`), and the `ImageGenerationProvider` Protocol (`generate_image(request) -> GeneratedImageResult`) - the one genuinely new capability the loop needs, per the architecture direction.
- `app/services/prompt_compiler.py` (new): `compile_generation_request(creative_specification, product_profile, platform="generic")`. `creative_intent` is joined from the Creative Specification's descriptive fields (subject/composition/style/lighting/camera/background/mood/color_palette/text_overlays); `immutable_constraints` is built *only* from the canonical Product Profile's `immutable`-classified fields (never re-derived from the Creative Specification), each formatted through a small per-value-kind renderer (`TextValue`/`ColorValue`/`DimensionValue`/`NumberValue`/`ListValue`); `things_to_avoid`/`aspect_ratio` pass through, with a one-entry platform-default fallback dict for aspect ratio (deliberately not a Platform Rules entity, per the architecture direction's explicit scope decision).
- `app/ai_providers/openai_adapter.py`: `OpenAIImageGenerationAdapter.generate_image` - calls `client.images.generate`, times the call, decodes `b64_json` (falling back to fetching a `url` if the response shape returns one instead - defensive, since which shape a given model returns wasn't verifiable without a real call at this sub-phase's own scope boundary). All provider-specific prompt formatting lives in `_compile_openai_prompt` (never in the compiler) and a small aspect-ratio-to-OpenAI-size mapping, both private to this adapter.
- `app/ai_providers/registry.py`/`config.py`, `providers.yaml`: sixth capability, `image_generation`, wired exactly like `prompt_generation` was in M6 - one `ProvidersConfig`/`ModelsConfig` field, one `IMAGE_GENERATION_ADAPTERS` dict, one `_image_generation` instance + `image_generation()` accessor on `AIProviderRegistry`. No other registry code changed.
- `tests/fakes.py`: `FakeImageGenerationProvider` + `image_generation()` on `FakeAIProviderRegistry`, matching every other fake provider's shape.
- **Test strategy** (matched exactly): `tests/test_prompt_compiler.py` (6 tests, plain dicts/model construction, zero AI provider involved) - immutable constraints come only from immutable-classified profile fields, each `ProductAttributeValue` kind formats readably, things-to-avoid/aspect-ratio pass through, platform-default fallback, creative-intent assembly, optional fields skipped rather than left blank. `tests/test_openai_adapter.py` gained 2 tests for `OpenAIImageGenerationAdapter` (real-SDK-shape mocking, same discipline as the existing OCR adapter test in that file - no real network call): confirms the compiled prompt's three sections, the aspect-ratio-to-size mapping, and that empty optional sections are omitted rather than rendered blank. No real OpenAI image call in this sub-phase, per the plan - that's 8.3's job, once there's a persisted `GeneratedImage` + endpoint to actually see the result through.
- Full suite: 223/223 passing (215 existing + 8 new). Ruff clean on every touched file. App boots cleanly with the sixth capability wired (`app/main.py`'s lifespan constructing `default_registry` on startup is the confirming check, per this codebase's own established discipline for registry wiring - no dedicated registry unit test exists for any of the other 5 capabilities either).
- Zero behavior change to anything existing - every new piece (types, compiler function, adapter class, registry capability) is purely additive; nothing yet calls any of it in the request path (that begins in 8.3).
- Commit: (see git log)

### Phase 8.3 — GeneratedImage artifact + Image Generation Stage + endpoint (done)

- `app/models/generated_image.py` (new, `AnalysisArtifactMixin`): `slideshow_id`/`slide_id`/`creative_specification_id` (FKs), `provider`/`model_name`/`prompt_used`/`seed`/`generation_time_seconds` (persisted verbatim from `GeneratedImageResult`), `file_path`. Deliberately `slide_id`-scoped (non-nullable), unlike the slideshow-scoped artifacts - matches the "one slide first" scope boundary. No `current_generated_image_id` pointer added to Slide/Slideshow - queried directly by `slide_id` + `is_current`, same pattern `ProductLockProfile`/`ProductReferenceImage` already use, since there's no existing pointer convention worth extending for a deliberately-not-auto-pipelined artifact type.
- `app/storage.py`: `save_generated_image(slide_id, generated_image_id, content, suffix=".png")`, same per-owning-entity layout as `save_product_reference_image`.
- `app/slideshow_stages/image_generation_stage.py` (new): `SlideImageGenerationStage` - `SlideshowAnalysisStage`-shaped (`name`, `run(db, slideshow) -> StageResult`) for consistency but **not** added to `SLIDESHOW_STAGE_PIPELINE`, per the architecture direction. Reuses `resolve_primary_appearance` (made public in 8.1 for exactly this) and `assemble_product_profile` (Phase 5.5) - no new resolution logic. Resolves the Creative Specification, the primary product's canonical Product Profile, compiles the request, calls the provider, saves the file, flips `is_current` on any prior `GeneratedImage` for the slide.
- New migration `b3d7e08f5a1c`: `create_table` only (no FK-adding ALTER, no batch mode needed) - full backup/scratch-copy/round-trip discipline, byte-for-byte schema match confirmed on downgrade, then applied to the real dev DB.
- `app/routers/slideshows.py`: `POST .../slides/{slide_id}/generate-image` (synchronous, 201, returns `GeneratedImageRead`) - validates `slide_id == slideshow.primary_slide.id` and 400s otherwise rather than silently generating for a different slide than the one requested; a stage failure surfaces as 422 with the real error message. `GET .../generated-images/{generated_image_id}/file` mirrors `get_slide_file`/`get_reference_image_file`.
- **Test strategy**: `tests/test_slide_image_generation_stage.py` (6 tests, `FakeImageGenerationProvider`) - missing-prerequisite failures (no Creative Specification, no product assigned), successful persistence (DB row + real file on disk with the right bytes), the compiled request actually reflects the real Creative Specification content, provider-error failure leaves no row behind, rerun flips `is_current` correctly. `tests/test_generated_image_api.py` (5 tests) - missing-prerequisite 422, unknown-slideshow 404, non-primary-slide 400, full success + real file round-trip through the serving endpoint, unknown-generated-image-id 404.
- **Live verification - a real OpenAI call, the first genuinely real AI-provider call made anywhere in this entire engagement** (every prior "live verification" in this project's history tested response-shape/error-surfacing with `FakeAIProviderRegistry`, or failed on a missing API key before this session): triggered `POST .../generate-image` against a real, previously-analyzed slideshow. **Two real, concrete blockers found and fixed, not anticipated in the plan**:
  1. `providers.yaml`'s configured model, `gpt-5.5`, is not a real OpenAI model - confirmed via a real `400` from OpenAI's Images API (`"The model 'gpt-5.5' does not exist"`). Fixed by changing `image_generation`'s model to `gpt-image-1`, scoped to only that one capability - the other 5 capabilities' `gpt-5.5` values are untouched, since this session never actually exercised them against the real API either (every earlier "success" in this engagement's history was against `FakeAIProviderRegistry`) and speculatively "fixing" values that were never confirmed broken is out of this sub-phase's scope.
  2. The real, AI-generated `aspect_ratio` value turned out to be free text (`"4:5 vertical marketing ad"`), not a bare ratio string like `"4:5"` - the adapter's exact-match size lookup silently fell through to a square image for every real Creative Specification. Fixed by matching on substring instead of exact equality; added a dedicated regression test using the exact real string that exposed the gap, rather than re-spending on a second live paid call to confirm it.
  - After both fixes: a real `201`, a real ~53-second generation, a real 1024×1536 PNG (1.5MB) verified via `file` and a direct fetch through the serving endpoint, persisted at `storage/slides/<slide_id>/generated_<id>.png` and left in place in the real dev DB as genuine proof of the loop's Generation half - not test data, not deleted.
- Full suite: 235/235 passing (223 existing + 11 new + 1 regression test for the substring-matching fix). Ruff clean on every touched file.
- Zero behavior change to anything existing - `SLIDESHOW_STAGE_PIPELINE`/`Slideshow.status` are untouched; this is a fully additive, separately-triggered surface.
- Commit: (see git log)

### Phase 8.4 — Validation Stage + endpoint (done) — the loop closes

- `app/models/image_validation_result.py` (new, `AnalysisArtifactMixin`): `generated_image_id`/`product_id` (FKs), `passed` (Boolean, computed in code), `field_checks_json` (list of `{field_name, preserved, reason}`), `overall_explanation`. `product_id` stored directly rather than re-derived on every read, since it's the same product the `GeneratedImage`'s Creative Specification was built around.
- `app/slideshow_stages/image_validation_stage.py` (new): `SlideImageValidationStage`. Deliberately **not** `SlideshowAnalysisStage`-shaped, unlike 8.3's stage - `run(db, generated_image)`, not `run(db, slideshow)`, since Validation targets one specific `GeneratedImage` instance, never "whichever is current." Resolves the product via `GeneratedImage -> CreativeSpecification -> ProductLockProfile -> Product` (no new `product_id` column needed on `GeneratedImage`), builds the canonical Product Profile, lists every `immutable`-classified field, asks `VisionAnalysisProvider.analyze_creative` (reused completely unchanged - no new AI capability, per the architecture direction) to judge each one, computes `passed = all(check.preserved ...)` itself. Fails cleanly (not a vacuous "passed") if the profile has zero immutable fields to check against.
- `app/services/prompt_compiler.py`: `_format_attribute_value` made public (`format_attribute_value`) so this stage can reuse the exact same per-value-kind rendering Generation used to compile its own request - what Validation displays as "the expected value" is guaranteed to match what Generation was actually told to preserve.
- New migration `c4e91a6d2f7b`: `create_table` only, same discipline as 8.3's - full backup/scratch-copy/round-trip, byte-for-byte schema match on downgrade, applied to the real dev DB.
- `app/routers/slideshows.py`: `POST .../generated-images/{generated_image_id}/validate` (synchronous, 201, returns `ImageValidationResultRead` with `field_checks` surfaced as a real list, not summarized - this is the "explain why it failed" the user explicitly asked for). Built explicitly in the router rather than via `from_attributes`, since the ORM's `field_checks_json` name doesn't match the schema's `field_checks` field (same reasoning `MarketingAnalysisRead` needed explicit construction for in Phase 7.4).
- **Test strategy**: `tests/test_slide_image_validation_stage.py` (6 tests, `FakeVisionAnalysisProvider`) - product-resolution failure, the genuinely-empty-immutable-fields case (built with a contextual-only fake Lock Profile result, not just asserted), all-preserved passes, one violation fails the whole validation with the real reason surfaced, provider-error leaves no row, rerun flips `is_current`. `tests/test_generated_image_api.py` gained 2 more tests - unknown-generated-image 404, full success with `field_checks`/`passed`/`overall_explanation` asserted verbatim in the response body.
- **Live verification - a second real AI-provider call, closing the loop for real**: triggered `POST .../validate` against the actual `GeneratedImage` produced live in 8.3. Result: a genuine, informative `passed: false` - the vision model correctly caught that the generated image's right bottle reads "BELLA MITA LUXURY" instead of "BELLA VITA LUXURY" (a real, characteristic AI-image-generation text-rendering flaw, not a contrived test case), alongside several correctly-judged `preserved: true` checks (product category, bottle shape, materials, color, packaging) and one more real text-fidelity miss (missing/altered occasion words and volume text). This is exactly what the phase set out to prove: a real generate → validate → explain cycle, with an honest, specific, actionable failure reason - not a reliably-passing demo. The real `ImageValidationResult` row is left in the dev DB alongside 8.3's `GeneratedImage`, both genuine artifacts of the loop actually working, not test data.
- Full suite: 243/243 passing (235 existing + 6 new stage tests + 2 new route tests). Ruff clean on every touched file.
- Zero behavior change to anything existing - fully additive, separately-triggered surface, same as 8.3.
- **This closes the loop the whole phase exists to prove**: `Product Profile + Creative Specification → Prompt Compiler → ImageGenerationProvider → Generated Image → VisionAnalysisProvider → Validation → Pass/Fail`, exercised end-to-end with two real, paid AI-provider calls against real data, for one real slide, with zero automated retry/regeneration - exactly the scope the architecture direction set. Remaining: 8.5, a thin frontend surface to see this without curl.
- Commit: (see git log)

### Phase 8.5 — Frontend: trigger/view/explain the loop (done)

- **Two small, justified backend additions found necessary while building this sub-phase, not anticipated in the plan**: `GET .../slides/{slide_id}/generated-image` and `GET .../generated-images/{generated_image_id}/validation` (both 404 when nothing exists yet). Concrete blocker: without them, the only way for the UI to show a slide's already-generated image/validation on modal open would be to call the paid `POST` endpoints just to check whether something exists - real money spent to answer "is there anything to show," not to generate anything new. Both added with the same `_to_validation_read` helper extracted to avoid duplicating the ORM→schema field-rename logic between the `POST .../validate` and new `GET .../validation` handlers.
- `frontend/src/api.ts`: `GeneratedImageData`, `ImageValidationFieldCheck`, `ImageValidationResultData` types; `generateImage`/`validateGeneratedImage` (synchronous, resolve with the finished artifact directly - no queued-status polling, unlike `analyzeSlideshow`/`rerunSlideshowStage`); `getCurrentGeneratedImage`/`getCurrentValidationResult` (new `handleOptional` helper resolves `null` on a 404 rather than throwing, since "nothing yet" is an expected, common state for these two reads specifically); `generatedImageFileUrl`.
- `SlideshowBlueprintModal.tsx`: new "Generated Image" section, deliberately outside the `blueprint` state and its polling machinery (generation/validation are synchronous, not queued, and scoped to the primary slide regardless of which slide the existing Prev/Next selector is showing - a small note in the section makes this explicit rather than leaving it implicit). "Generate Image" / "Regenerate Image" button; once an image exists, an image preview + provider/model/timing metadata + a "Validate" button; once a validation exists, a new `ValidationResultPanel` component - a Pass/Fail badge, the `overall_explanation`, and every `field_checks` entry rendered as its own row with a ✓/✗ icon and the real per-field reason. Deliberately no retry/regenerate automation, per the architecture direction - re-clicking "Generate Image" is the manual regenerate path.
- **Real gap found live-verifying against the actual Phase 8.3/8.4 data, not anticipated in the plan**: the vision model's `field_checks[].field_name` came back as the full `"brand: Bella Vita Luxury"` line (name and expected value concatenated) rather than just `"brand"` - the original prompt asked for "the exact field name given" while presenting each field as one combined `"name: value"` line, genuinely ambiguous about which part was "the field name." Fixed the prompt wording in `_build_prompt` to quote the field name and separate it from "expected value = ..." explicitly, with a new regression test (`test_build_prompt_asks_for_the_short_field_name_only`) locking in the corrected format. Confirmed against a second live vision-analysis call against the same real generated image: field names came back as clean short keys (`brand`, `product_category`, `shape`, `materials`, `color`, `branding_text`, `packaging`), then confirmed rendering correctly in the real browser DOM and via screenshot.
- Full suite: 248/248 passing (243 existing + 4 new GET-endpoint tests + 1 new prompt-wording regression test). Ruff clean, `tsc --noEmit`/`oxlint`/`vite build` all clean.
- **Live verification**: real browser, real preview server, real data - opened the blueprint modal for the same slideshow used throughout 8.3/8.4's live verification, confirmed the Generated Image section renders the real generated PNG, the real `Fail` badge, the real `overall_explanation`, and all 7 real field checks with correct ✓/✗ icons and reasons, via both DOM inspection and a visual screenshot.
- **Phase 8 is now complete end-to-end**: a real slide can be generated, validated, and explained entirely from the browser, with zero automated retry/regeneration, using real OpenAI image generation and real vision-analysis calls against real product/creative data - exactly what the standing 2026-07-22 directive asked for. What's next (Phase 9+) is scaling and refinement, not proving the concept.
- Commit: (see git log)

---

## ADR: Canonical Product Reference (Product Lock v2) — 2026-07-23

**Status: revised twice by the user on 2026-07-23 (see Revision #1 and Revision #2 below) - the sections below reflect the current, revised design. Design/planning only, per explicit instruction - no code, no migrations, no new files have been written for this ADR. Not to be implemented until confirmed.**

### Revision #1 (2026-07-23) - explicit scoring/selection stage, prompt compiler philosophy, Product Intelligence goal

Three refinements, agreed direction unchanged, requested before implementation begins:

1. **An explicit Reference Scoring and Canonical Selection Stage.** The original §4 described scoring/selection as something "the Reference Acquisition Engine" does as part of gathering. Split instead into two distinct responsibilities: **acquisition** (gathering *candidate* `ProductReferenceImage` rows from the priority-ordered sources - mostly already-existing code, per §0/§4's grounding) and **scoring & selection** (a new, explicit, first-class Stage that decides which candidates become canonical, and owns how that decision is scored, ranked, refreshed, and replaced over time). §4 below is rewritten around this split.
2. **Prompt Compiler philosophy change.** The Prompt Compiler should stop describing the product at all - no shape/materials/color/packaging text, however "secondary." The Canonical Reference Set's images are the *only* source of product identity in a generation call; the compiler's job narrows to scene, composition, and marketing intent - everything *around* the product, never the product itself. §6 below is rewritten around this. This turns out to align exactly with a distinction Phase 5 already built for an unrelated reason: `CANONICAL_FIELD_VOCABULARY`'s existing `immutable`/`contextual` classification (Phase 5.5, built to decide *evidence merge precedence* between listing and vision sources) already separates "physical product facts" from "creative facts expected to vary" - the same split the compiler now needs to decide what to drop versus what to keep. No vocabulary change needed; the existing classification already draws the right line, which is a good sign the Phase 5 design was sound, not a coincidence to gloss over.
3. **Product Intelligence's stated goal changes** from "a canonical description of the product" to "everything required to recreate this exact product with high visual fidelity" - reflected in the "Frozen architecture vision" section above (point 1) and threaded through the rewritten sections below.

### Revision #2 (2026-07-23) - Library vs. Generation Set, contextual/provider-aware selection, bundle-readiness

Prompted by thinking through bundles and long-term scale. Agreed direction unchanged again; this revision corrects a real conflation in Revision #1: `CanonicalProductReference` was doing two jobs at once - "the durable, growing pool of good images for this product" and "the specific images sent to the model for one generation call." Those are different lifetimes and different responsibilities, and collapsing them would have meant either the durable pool staying artificially small (capped at one image per role, forever) or every generation call receiving the *entire* pool regardless of relevance - neither is right, and bundles make the difference impossible to ignore (five products in a bundle could mean fifty candidate images total, but a single scene should only ever draw two or three per product).

1. **Split into a Canonical Reference Library (durable, growing) and a Generation Reference Set (small, per-request, ephemeral-but-recorded).** The Library is *not* reintroduced as a new persisted "snapshot" entity - see §3's rewrite: it is better modeled the same way `ProductReferenceImage.is_current` already models "the current state" for every other artifact in this codebase - a status tagged directly onto individual `ProductReferenceImage` rows, computed-on-read as a query, not a versioned artifact that gets wholesale replaced. This is a real course-correction from Revision #1's `CanonicalProductReference`/`CanonicalProductReferenceImage` tables, which don't survive this revision (see §1/§3). The Generation Reference Set *does* become a real, persisted, versioned artifact - because unlike the Library, a specific selection made for a specific generation call is exactly the kind of one-time event this codebase already always records (`AnalysisArtifactMixin`-shaped, matching `GeneratedImage`'s own precedent).
2. **Reference Selection becomes its own step, scene-aware, sitting between the Library and the Prompt Compiler**, not inside the compiler itself. §6 is restructured into two sub-sections (Reference Selection, then Prompt Compiler) to reflect this, with reasoning for why Selection needs to stay outside the compiler's pure-function boundary.
3. **Provider-capability-aware selection**, not a hardcoded count - `ImageGenerationProvider` gains a capability query so Selection asks the provider how many reference images it can use, rather than the architecture assuming today's specific limit forever.
4. **Bundle-readiness, explicitly bounded**: the schema (Generation Reference Set spanning multiple products) is shaped so it does not foreclose multi-product bundle generation later, but *implementing* multi-product generation is explicitly out of scope for this ADR/Phase 9 - see §6's bundle note. This is the same single-product scope boundary Phase 6.3 and Phase 8 already established for Creative Specification/Image Generation, not a new restriction invented for this ADR.

### 0. Diagnosis - restating the flaw precisely, grounded in what actually happened

Phase 8's real live-verification run is the concrete evidence: the generated Bella Vita image passed 5 of 7 immutable-field checks (`product_category`, `shape`, `materials`, `color`, `packaging`) and only failed on two text-legibility fields (`brand`, `branding_text` - the "BELLA MITA" typo). But per this request, the *shape/silhouette/proportions* were "visibly incorrect" despite the `shape` check passing. Reading exactly why, grounded in the real code path:

- `SlideCreativeSpecificationStage`/`compile_generation_request` never send pixels to the image model - only a text paragraph (`ProductLockProfile.structured_json["shape_and_proportions"]`, itself an English sentence a vision model wrote once, describing the *original* creative's product) plus `immutable_constraints` strings like `"shape: Each bottle is a broad, squat rectangular form with a flat front face..."`.
- `OpenAIImageGenerationAdapter.generate_image` calls `client.images.generate(prompt=...)` - **text-to-image only**, no reference image ever passed to the provider. The model has never seen the real bottle; it is reconstructing a silhouette from a paragraph.
- `SlideImageValidationStage` then re-describes the *generated* image with its own vision call and asks "does this match the text." A vision model judging "is this text description satisfied" is a fundamentally looser test than "is this the same object" - English is lossy for exact geometry (cap-to-body ratio, corner radius, shoulder angle) in a way it isn't for discrete facts like brand name or category. This is exactly why the loop failed on the *text-precision* fields (brand spelling) and passed the *geometry* fields (shape) despite the geometry being what actually looked wrong: text is a bad medium for encoding geometry, and both Generation and Validation are entirely text-mediated today.

This confirms the request's diagnosis exactly: **the current pipeline preserves what can be said about the product, not what the product looks like.** The fix has to put pixels - not descriptions of pixels - into both the generation call and the identity check. That is the single technical change everything below serves.

One grounding correction to the request's framing, worth being explicit about: this is not a case of the codebase having *no* reference images. `ProductReferenceImage` (Phase 2.4a/5.1) already exists, is already Product-scoped (not Creative-scoped, so it already accumulates and is reusable exactly as the request wants), already has three provenance sources (`source_slide_id` - cropped from an imported slideshow, `source_product_source_import_id` - downloaded from an official URL import, `source_creative_id` - legacy), and the URL-import path (`app/services/product_source_import.py:_try_download_and_save_reference_image`) already downloads *every* image URL an adapter reports and stores it as one of these rows today. **The raw material Reference Acquisition Priority 1 and Priority 4 need already exists and is already being collected - it has simply never been scored, selected, or passed to the image model.** This matters a great deal for scope: most of this ADR is "start using what's already being collected," not "build image collection from scratch." Section 4 below is explicit about which parts are genuinely new.

### 1. Changes to the domain model

**Revision #2 replaces the Revision #1 schema below** - `CanonicalProductReference`/`CanonicalProductReferenceImage` (proposed, never implemented) are dropped in favor of a leaner design: the Library lives as status columns on the existing `ProductReferenceImage` table (compute-on-read, no new snapshot entity), and a new, genuinely versioned artifact - `GenerationReferenceSet` - captures the small, per-generation-call selection instead.

**New tables:**
- `GenerationReferenceSet` (see §3) - a real, `AnalysisArtifactMixin`-shaped, per-generation-call artifact: exactly which Library images were selected for one specific generation, and why.
- `GenerationReferenceSetImage` - a join table between `GenerationReferenceSet` and `ProductReferenceImage`, carrying `product_id` explicitly per row (not just inherited from the parent) - the concrete schema hook that keeps this bundle-ready without implementing bundles now (see §6).

**Changed tables (all additive - no column removed, no existing column's meaning changed):**
- `ProductReferenceImage` gains nullable columns: `quality_score` (float), `quality_reasons_json` (list of short strings, e.g. `["sharp", "front-facing", "brand fully visible"]` - same "record the reasoning, not just the number" discipline `ImageValidationResult.field_checks_json` already established), `role` (string, e.g. `"hero"`/`"front"`/`"45_degree"`/`"packaging"`/`"branding_closeup"` - free string, matching `ProductSourceImport.source_type`'s "plain string, not a hardcoded enum" convention), `library_status` (string: `"candidate"` | `"included"` | `"rejected"` | `"superseded"` - the field that actually defines Library membership; see §3). All four written once per image by the Reference Scoring Stage (§4), not recomputed on every read.
- `GeneratedImage` gains a nullable `generation_reference_set_id` FK - which specific selection a given generation actually used, for the same provenance reasoning `CreativeSpecification` already established for `product_lock_profile_id`/`creative_fingerprint_id`. This is a strictly more precise provenance record than Revision #1's `canonical_product_reference_id` would have been - it names the exact images sent, not just "which Library state was current."
- `ImageValidationResult` gains `identity_passed` (nullable Boolean) and `identity_checks_json` (nullable list, same `{field_name, preserved, reason}` shape `field_checks_json` already uses). Nullable for the same pre-this-phase-row reason. The existing `passed`/`field_checks_json` columns are **repurposed in meaning, not shape**: `passed` becomes "identity passed AND creative passed" (see §7), `field_checks_json` continues to mean the creative/Stage-2 checks specifically.

**No table is dropped. No table is renamed. `ProductLockProfile` and `ProductReferenceImage` keep their current shape and current writers (Product Lock Profile Stage, Product Isolation Stage, the URL-import download path) completely unchanged** - this ADR changes what *consumes* them and adds a scoring/selection layer on top, not how they're produced. This is deliberate: every prior migration in this project used the same expand → backfill → switch-reads → contract discipline, and there is no reason to break that discipline for a change this consequential - if anything, less reason.

### 2. Database migration strategy

Two new tables (`GenerationReferenceSet`/`GenerationReferenceSetImage` - `create_table`, no batch mode needed). Four new nullable columns on `product_reference_images` (`quality_score`, `quality_reasons_json`, `role`, `library_status`, all nullable, no FK - no batch mode needed by this project's own precedent, e.g. `19b5c9909b3e`). One FK-adding batch-mode migration each for `generated_images.generation_reference_set_id` and the two new `image_validation_results` columns (batch mode required per this project's own established rule whenever a migration adds a column with a new FK constraint - `4b599e19a719`, `15210f8f4d89`). Net simpler than Revision #1's schema, not more complex - one fewer new table, the same handful of additive columns.

Every migration gets the exact same discipline every migration in this project has gotten without exception: real dev-DB backup, isolated `CAE_DATA_DIR` scratch copy, upgrade, direct sqlite3 schema/row-count verification, downgrade, byte-for-byte schema re-verification, only then applied to the real dev DB, re-verified, scratch cleaned up (backup kept). No reason to propose anything different here.

**Backfill is the one genuinely open decision, not a mechanical one** (see §11's explicit call-out) - whether to retroactively score/tag every `Product`'s existing `ProductReferenceImage` rows (`quality_score`/`role`/`library_status`) so their Library is populated without a fresh Reference Scoring run, and if so, whether that scoring uses free classical heuristics only or a real (paid, one AI call per candidate image) vision-scoring pass. This is a real-money, real-scope decision the user should make explicitly when implementation is authorized, not something decided inside a migration script.

### 3. The Canonical Reference Library and the `GenerationReferenceSet` entity

**Revision #2 rewrites this section entirely.** Revision #1's `CanonicalProductReference`/`CanonicalProductReferenceImage` are dropped - the reasoning below explains why the Library and the per-generation Set need genuinely different shapes, not just different names for the same table.

**The Canonical Reference Library is not a new table.** It is the *set of `ProductReferenceImage` rows for a product with `library_status = "included"`* - a query, computed on read, exactly the same pattern `assemble_product_profile`/`assemble_slideshow_blueprint` already use for "the current state of things" elsewhere in this codebase. This is a deliberate correction from Revision #1's framing, driven directly by the request: a Library that "continues growing and improving" over a product's lifetime is describing an *ongoing, incrementally-updated collection*, not a single versioned artifact that gets wholesale replaced each time something changes - `ProductReferenceImage.is_current` already models exactly this shape of fact (each image's own membership is its own independent, incrementally-updatable state), so extending that same table is more honest than wrapping it in a new snapshot entity whose version history would only ever describe the same, always-current information a plain query already gives for free.

```
ProductReferenceImage (existing table, four new nullable columns)
├── ...existing columns unchanged (product_id, source_*_id, file_path, isolation_method, is_current)...
├── quality_score (float, nullable) — from Reference Scoring (§4)
├── quality_reasons_json (list of short strings, nullable)
├── role (string, nullable — e.g. "hero"/"front"/"45_degree"/"side"/"packaging"/"branding_closeup")
└── library_status (string, nullable — "candidate" | "included" | "rejected" | "superseded")
```

*Library membership* (`library_status = "included"`) can hold **more than one image per role** - the request's own observation that "a single reference image rarely defines a product's identity" applies to the Library specifically: it should accumulate `hero`, `front`, `rear`, `left/right`, `45°`, `packaging`, `branding_closeup`, and multiple good candidates within a role where they exist, not collapse to one-per-role the way Revision #1 proposed. Revision #1's top-1-per-role selection now describes the **Generation Reference Set** below, not the Library - narrowing happens at generation time, per request, not at curation time.

**`GenerationReferenceSet` is the new, genuinely versioned artifact** - not "the Library," but a record of exactly which Library images Reference Selection (§6) chose for one specific generation call, and why:

```
GenerationReferenceSet (AnalysisArtifactMixin-shaped: id, is_current, created_at,
                         schema_version, analysis_run_id nullable — see note below)
├── generated_image_id (FK, nullable until the generation this set fed actually succeeds and is
│                        persisted — see §6 for the create-then-link ordering)
└── selection_method_json — how these images were chosen for this scene (role-keyword match / AI-
                             assisted / provider capability limit applied), for auditability

GenerationReferenceSetImage (join table, new)
├── generation_reference_set_id (FK)
├── product_reference_image_id (FK) — the underlying Library image actually used, not a copy
├── product_id (FK) — explicit per row, not just inherited from the parent set; this is the concrete
│                      schema hook that lets one Set span multiple products later (bundles, §6),
│                      without a redesign, while today every real Set only ever has one product_id
│                      value across its rows (Phase 6.3/Phase 8's single-product scope, unchanged)
├── role (string, snapshotted from the image's role at selection time — the image's own `role` could
│         theoretically be re-classified later; the Set records what it was told at the time)
└── rank (int — order within this product's portion of the set)
```

This is a strict improvement in provenance over Revision #1, not just a rename: `GeneratedImage.generation_reference_set_id` (§1) names the *exact images sent*, not "which Library version was current" - genuinely more precise, and it comes for free from modeling Selection as its own real event rather than folding it into the Library.

`OCR Results`, `Product Fingerprint`, and `Visual Embeddings` from the original request are addressed individually, unchanged from Revision #1's reasoning (still applies to the Library the same way it applied to `CanonicalProductReference`):

- **`Structured Attributes`/`Dimensions`/`Materials`/`Colours`/`Packaging`/`Brand Metadata`**: this is exactly what `ProductLockProfile.structured_json` and the canonical `ProductProfile` (Phase 5.5) already are - supporting metadata alongside the Library, no duplication, no new vocabulary (the request's own "Product Lock Role" section, §6 below).
- **`OCR Results`**: `ProductLockProfile.structured_json.labels_and_text` already captures a version of this today. **Recommendation unchanged: do not build a second, parallel OCR pipeline** - reuse the existing `OCRProvider` capability via a new Product-scoped Stage only if dedicated precision is genuinely wanted later.
- **`Product Fingerprint`**: would collide with the existing, differently-scoped `CreativeFingerprint` name. Extend `ProductLockProfile`'s existing fields (Phase 5 revision #5's vocabulary discipline) rather than invent a new entity.
- **`Visual Embeddings`**: **still deferred, for the same reason** - Reference Scoring's Tier 2 (§4) and Stage 1 Identity Validation (§7) both reuse the existing `VisionAnalysisProvider` capability, zero new provider. Embeddings remain real future work once candidate volume actually makes per-pair vision-call cost a bottleneck, not before.

On `AnalysisArtifactMixin`: `GenerationReferenceSet` is a real, versioned artifact (one row per generation call, `is_current` scoped the same way `GeneratedImage` scopes itself per slide), but the selection step producing it is not always an AI call (role-keyword matching needs none, see §6) - same reasoning `ProductSourceImport`/`ProductReferenceImage`'s URL-sourced rows already established for a nullable `analysis_run_id`, now a fourth precedent for the exact same pattern.

### 4. Reference Acquisition, and the Reference Scoring Stage (curates the Library)

**Revision #2 note**: this section still covers acquisition (unchanged from Revision #1) and scoring, but **"Selected" now means "included in the Library," not "chosen for one generation"** - per-generation narrowing moved to Reference Selection (§6), which operates on top of whatever the Library already contains. Reads §3 first for why the Library itself is compute-on-read, not a table this Stage writes a version of.

**Reference Acquisition (gathering candidates) - framed against what already exists, per the diagnosis in §0:**

| Priority | Request's description | What already exists today | What's genuinely new |
|---|---|---|---|
| 1. Official URLs | Amazon/TikTok Shop/Shopify/etc. | `ProductSourceAdapter.extract()` (Phase 5.2) already returns `NormalizedProductEvidence.images: list[NormalizedProductImage]`; `_try_download_and_save_reference_image` (Phase 5.1) already downloads *every* one and stores it as a `ProductReferenceImage` with `isolation_method="product_url"`, unconditionally | Nothing - acquisition itself is complete for this source today |
| 2. Reuse existing Library | Avoid duplicate work | N/A | Trivial: the Scoring Stage below only scores candidates with `library_status` still `null`/`"candidate"` - already-`"included"` images are never rescored just because acquisition ran again |
| 3. User-uploaded images | Official product photographs | No dedicated upload path exists today - images only enter the system via slideshow import or URL import | A genuinely new upload endpoint + storage path (small - same shape as `save_product_reference_image`, a new `isolation_method="user_upload"` value, no new concept) |
| 4. Slideshow extraction | Crop every slide, every angle | `SlideProductIsolationStage` (Phase 2.4a) already crops the featured product from every slide it's run on and stores each as a `ProductReferenceImage` with `isolation_method` describing the crop method; multi-slide slideshows already produce multiple crops today | Nothing - acquisition itself is complete for this source today |
| 5. Future search providers | Explicitly deferred by the request | N/A | Explicitly out of scope, per the request itself |

Acquisition, concretely, is therefore not a new pipeline - it is a query (`app/services/reference_acquisition.py`, the "candidate gathering" half only): given a `product_id`, return every current `ProductReferenceImage` row regardless of `isolation_method`, i.e. every image already downloaded/cropped/uploaded for that product, as the candidate pool. No fetching, downloading, or cropping logic lives here - that already exists in the Stages/services listed above and stays exactly as it is.

**Reference Scoring Stage (new, first-class Product-scoped Stage - `app/services/reference_scoring_stage.py`, alongside `product_profile.py`/`prompt_compiler.py`, matching how Stage-shaped logic that isn't literally `SlideshowAnalysisStage`-typed already lives outside `app/slideshow_stages/` in this codebase, e.g. `assemble_product_profile`).** This Stage owns everything the request asks a scoring stage to define, now scoped to curating the Library rather than picking a final generation set:

- **Scored.** Two-tier, not one AI call per image, per this codebase's standing "compute what can be computed, don't ask the AI for free facts" discipline (`staleness.py`'s `passed` computation, `SlideImageValidationStage`'s `passed`):
  - *Tier 1 (free, deterministic, always run):* resolution, aspect ratio, file size as a crude sharpness proxy, EXIF orientation if present. Filters out obviously-unusable candidates at zero cost.
  - *Tier 2 (one `VisionAnalysisProvider.analyze_creative` call per surviving candidate - real, deliberate cost):* front-visibility, occlusion, brand-readability, packaging-visibility, composition, and `role` classification. Same capability Stage 1 Identity Validation (§7) already uses - one more consumer of an existing provider, not a new one.
- **Ranked.** Candidates are ranked *within* a `role`, not against each other globally - a `packaging`-role image isn't competing with a `front`-role image.
- **Included (Library curation, not final selection).** Every candidate above a quality floor is written to the Library (`library_status="included"`) with its `role`/`quality_score`/`quality_reasons_json` - **multiple images per role are expected and welcome**, per the request's own "one reference image probably isn't sufficient" observation. Below-floor candidates get `library_status="rejected"` (kept, not deleted - real provenance of what was considered and why, same "record the attempt" discipline this codebase applies everywhere). A product with only front-angle candidates gets a Library of front-angle images only; that is a correct, honest result, not a failure state.
- **Refreshed.** The Stage is re-runnable, the same way every other Stage in this codebase is - triggered explicitly (new endpoint, §8) or automatically whenever acquisition produces genuinely new candidates. New candidates that clear the quality floor are simply added to the Library (`library_status="included"`) - **this is always additive now, not a replace decision**, because the Library no longer has a single "the canonical image for role X" slot to contend over; it holds several. The Replaced concern below only applies to one specific, narrower case.
- **Replaced/superseded.** The request's explicit "user later provides an Amazon URL" scenario still matters, but its scope narrows now that the Library can hold multiples: if a new candidate is *clearly* redundant with an already-included image in the same role (near-duplicate, meaningfully lower quality) it's marked `library_status="superseded"` rather than kept alongside a strictly-better duplicate - a low-stakes, automatable dedup decision, not the "does this change what the product visually means" decision Revision #1 was really worried about. That higher-stakes concern - "the new source is a fundamentally different/better view of the product than anything in the Library" - still **surfaces as a choice, never auto-applies**, matching the catalogue ADR's Listing-resolution discipline.

Runs synchronously or in the background depending on candidate volume - a single URL import's handful of images can stay synchronous (Phase 8's own precedent for single-call latency); a slideshow with many slides scoring many crops should use the existing background-task infrastructure (Phase 3.1, already built, already proven).

### 5. How existing Product Lock Profiles migrate

They do not migrate in the sense of being transformed or replaced - **they stay exactly as they are, forever, as supporting metadata alongside the Library, never consulted by the compiler again** (§6). No `ProductLockProfile` row's shape, meaning, or writer changes. The only "migration" is the backfill question in §2/§11: whether to retroactively tag existing `ProductReferenceImage` rows with `quality_score`/`role`/`library_status` so their Library is populated without a fresh Reference Scoring run. This is additive scaffolding around existing data, not a transformation of it - if the backfill is skipped entirely, nothing breaks; those products simply have an empty Library (no `"included"` rows) until Reference Scoring is triggered (same "not generated yet" empty-state discipline every artifact in this app already uses).

### 6. Changes required to Reference Selection and the Prompt Compiler

**Revision #2 splits this into two steps** - Reference Selection (new) runs first and narrows the Library down to a small, scene-appropriate `GenerationReferenceSet`; the Prompt Compiler (as revised in Revision #1) then compiles that Set plus the Creative Specification into a `GenerationRequest`. Both are covered here since they're pipeline-adjacent and the boundary between them is exactly the design question the request raised.

**Reference Selection - why it's a separate service, not inside the compiler.** The request explicitly asks whether this belongs in the Prompt Compiler (which "already understands the requested scene") or a dedicated service. **Recommendation: a dedicated service** (`app/services/reference_selection.py`), for a concrete reason: `compile_generation_request` is, and should stay, a pure function - no I/O, no DB queries, no provider calls, trivially unit-testable with plain dicts (its actual test suite today proves this is a real, kept property, not just an aspiration). Reference Selection genuinely needs to (a) query the Library - a DB read - and (b) ask the configured `ImageGenerationProvider` how many reference images it can accept - a provider-capability query. Folding either into the compiler would break its pure-function guarantee for no real benefit; keeping Selection separate means the compiler's existing tests keep working completely unchanged, and Selection gets its own, independently testable unit-test surface (fake Library rows in, expected Set out - no AI provider needed for the classical path, see below).

Selection works in two steps, matching the "compute what can be computed" discipline this whole ADR keeps returning to:
1. **Scene-aware filtering (classical first).** The Creative Specification's own `composition`/`camera_and_perspective` text is matched against each Library image's `role` tag - keyword/role matching (e.g. composition mentioning "45-degree" or "three-quarter" prefers `role="45_degree"` candidates; "packaging" or "box" prefers `role="packaging"`), free and deterministic. **If this proves too crude in practice, upgrade to one `TextGenerationProvider.generate` call** (already exists, zero new capability - the same provider Marketing Analysis already uses) that takes the composition text plus the Library's available `(role, quality_score)` pairs and returns a ranked subset - proposed as a fallback/upgrade path, not built speculatively now, matching this ADR's own "prove it before building for it" discipline used everywhere else in it.
2. **Provider-capability limiting.** `ImageGenerationProvider` (Phase 8.2) gains one new method - `max_reference_images(self) -> int` - so Selection asks the *configured provider*, not a hardcoded architecture-wide constant, how many images it can use. `OpenAIImageGenerationAdapter.max_reference_images` returns whatever the real, verified-during-implementation `images.edit` limit turns out to be (§12 already flags this as unverified - this design directly resolves that risk rather than leaving it as a hardcoded guess). This is a **provider-capability query**, not provider-specific formatting - it's fine for Selection to call it without violating Phase 8.2's "provider-specific stuff stays in the adapter" rule, because Selection only ever sees a plain integer back, never anything OpenAI-shaped.

**Bundle-readiness, explicitly bounded.** The request's bundle scenario (five products, fifty candidate images total, two or three selected per product) is real and the schema is shaped for it: `GenerationReferenceSetImage` carries `product_id` per row (§3), so one `GenerationReferenceSet` *can* span multiple products' selections without a schema change. **Implementing multi-product selection/generation is explicitly out of scope for this ADR and Phase 9**, for the same reason Phase 6.3 and Phase 8 already scoped Creative Specification/Image Generation to exactly one product: `SlideCreativeSpecificationStage` still resolves a single primary product per slide today, and nothing in this ADR changes that. Phase 9 implements Reference Selection for that same single-product scope; a later phase (not designed here) would extend Creative Specification/Selection/Generation/Identity Validation to loop over every product in a bundle the way Phase 6.2 already loops Product Isolation/Lock Profile over every product appearance on a multi-product slide - a real, precedented pattern in this codebase, just not one this ADR builds now.

**The compiled `GenerationReferenceSet` output feeds the Prompt Compiler, whose own contract from Revision #1 is otherwise unchanged**: `compile_generation_request(creative_specification, generation_reference_set, platform="generic")` - `product_profile` stays dropped entirely, `GenerationRequest.immutable_constraints` stays removed, `reference_images` stays a hard prerequisite (`SlideImageGenerationStage` fails cleanly - "No Generation Reference Set available - Reference Selection must run first" - rather than compiling a product-blind prompt). `creative_intent` still narrows to exactly the `contextual`-classified concerns (`camera_angle`/`composition`/`lighting`/`background`/`props`/`marketing_context` - `CANONICAL_FIELD_VOCABULARY`'s existing split, Phase 5.5). The necessary `generate_creative_specification` prompt re-scoping (drop the product-descriptive `subject` text) from Revision #1 is unchanged and still flagged for the same implementation sub-phase (§11).

**Provider-side, `OpenAIImageGenerationAdapter` still switches to `images.edit`** when reference images are present, unchanged from Revision #1, confirmed against the installed SDK (`openai` 2.46.0): `client.images.edit(image=<one or a sequence of files>, prompt=str, input_fidelity="high"|"low", ...)`, with `input_fidelity="high"` as the explicit "preserve input details closely" lever. All provider-specific branching (including the new `max_reference_images` value) stays inside the adapter.

This is worth being explicit about: **`images.edit`'s reference-image conditioning is a real, direct answer to the actual observed failure mode (§0) - it targets geometry/silhouette specifically, which text-only generation is structurally bad at.** It does not guarantee perfect results (see §12) - text-rendering precision (the "BELLA MITA" typo) is a separate, partially-independent weakness of current image models that reference-image conditioning does not fully solve - but it is the correct, well-matched fix for the specific problem this request diagnosed.

### 7. Changes required to the Validation Engine

`SlideImageValidationStage` splits into two sequential checks inside the same stage run (not two separate stages/endpoints - a single `POST .../validate` call still produces one `ImageValidationResult`, per the request's own "Identity should always be validated before creativity" ordering):

- **Stage 1 - Identity Validation.** Input: the generated image bytes + reference image bytes drawn from the **same `GenerationReferenceSet` that was actually used to generate the image** (via `GeneratedImage.generation_reference_set_id`, §3) - not a fresh, independent pull from the Library. One `VisionAnalysisProvider.analyze_creative` call, structurally identical to the existing Stage-2 pattern but comparing two *images* directly rather than an image against a text description - a new schema/prompt, zero new provider capability. Produces `identity_checks_json` (same `{field_name, preserved, reason}` shape, fields being silhouette/aspect_ratio/cap_geometry/corners_edges/brand_placement/typography_placement/color/materials/packaging - the request's own list) and `identity_passed` (computed in code from the per-field judgments, never asked of the AI as a bare boolean - the same rule `passed` already follows).
- **A real, acknowledged nuance in reusing the Generation Set for validation**: this is the most *direct* test available - "did the model faithfully render the exact images it was given" - but it is an easier test than fully independent identity verification, because it never checks the generated image against Library views the model wasn't shown. A generated image compared against only its own `front`-role input would legitimately look different in a `45_degree`-role Library image even for a perfectly faithful generation - cross-angle comparison is a genuinely harder problem this ADR does not solve. Flagged here and in §12 as a known limitation, not glossed over; reusing the Generation Set is still the right default because it's the direct, honest test of what actually happened, not a false claim of doing more than that.
- **Short-circuit, per the request's explicit design**: if `identity_passed` is false, the stage returns immediately with `passed=False` and Stage 2 (the existing creative/field_checks logic, unchanged) never runs - saving a real vision-model call on every clear identity failure, not just matching the request's stated design but making it cheaper than always running both.
- **If the `GeneratedImage` has no `generation_reference_set_id`** (a real, expected state for every `GeneratedImage` produced before this ADR ships, including the two rows already in the dev DB from tonight's live verification): Stage 1 is skipped, `identity_passed`/`identity_checks_json` stay `null` ("unknown," not "failed" - the same tri-state discipline `creative_specification_staleness`'s `_unknown()` already established for missing provenance), and Stage 2 runs exactly as it does today. This is what makes the whole ADR backwards-compatible in practice (§10) rather than a hard cutover.

### 8. API changes

- `GET /api/products/{id}/reference-library` - new, returns every current `ProductReferenceImage` with `library_status="included"` for the product, with `role`/`quality_score` - a plain list, not a single artifact (there is no "the" Library version to fetch by id, per §3's compute-on-read design).
- `POST /api/products/{id}/score-references` - new, explicitly triggers the Reference Scoring Stage (§4). Background-task-based given realistic candidate volume (unlike Phase 8's deliberately-synchronous single-call endpoints).
- `POST /api/products/{id}/reference-images/upload` - new, Priority 3 (user uploads).
- `POST /api/products/{id}/reference-images/{image_id}/library-status` - new, the human-in-the-loop override this ADR's Replaced/superseded section (§4) requires - lets a user manually mark an image included/rejected/superseded rather than trusting the automatic score, and confirms an offered upgrade.
- `GET .../generated-images/{id}/reference-set` - new, returns the `GenerationReferenceSet` (which exact Library images, with what role/rank, were sent for this specific generation) - lets the UI show precisely what the model was given, not just what exists in the Library.
- `POST .../slides/{slide_id}/generate-image` (existing, Phase 8.3) - internally now runs Reference Selection (§6) before compiling, and the created `GeneratedImage` row's `generation_reference_set_id` is populated; `GeneratedImageRead` gains that field (additive, mirrors `creative_specification_id`).
- `POST .../generated-images/{id}/validate` (existing, Phase 8.4) - `ImageValidationResultRead` gains `identity_passed: boolean | null` and `identity_checks: ImageValidationFieldCheckRead[] | null` (additive fields, both nullable per §7's tri-state).
- Existing `POST /api/products/{id}/source-import` (Phase 5.6) - **unchanged externally.** Internally, a successful import becomes one more trigger Reference Scoring can react to, but the endpoint's request/response contract does not change.

### 9. UI changes

- Product-level view gains a "Reference Library" panel: every included image grouped by `role`, with `quality_score`, an explicit "why was this scored this way" surface (from `quality_reasons_json`), and manual include/reject/supersede controls - matching the request's own emphasis that this becomes the product's primary visual identity, so a user should be able to see and correct it directly, not just trust an opaque score. Multiple images per role render as a small group, not a single slot, per §4's Library design.
- When a higher-quality source is detected (§4), a non-blocking prompt offering to upgrade - never a silent swap, matching the catalogue ADR's established human-in-the-loop discipline for consequential product-identity decisions.
- The Blueprint modal's "Generated Image" section (Phase 8.5) gains a distinct **Identity** badge, shown above the existing creative Pass/Fail, so a user immediately sees *which kind* of failure occurred - "wrong product" reads completely differently from "wrong lighting," and conflating them in one badge would be a real regression from what Phase 8.5 just built. The section also gains a small "Reference images used" strip - exactly the `GenerationReferenceSet` that fed this specific generation (via the new `GET .../reference-set` endpoint, §8) - so a user can see precisely what the model was shown, not just trust the Identity badge's verdict. When no Library exists yet, the section says so honestly ("Generation requires a Reference Library - none exists yet for this product") rather than silently proceeding as if nothing changed - same "never silently degrade" instinct this session has applied consistently (e.g. Narrative Structure's forced `unclassifiable`, staleness's tri-state).

### 10. Backwards compatibility

Everything in §1-§9 above is additive by construction, and this section exists to state that as a testable claim, not just an intention. **One correction from Revision #1's version of this section**: `compile_generation_request`'s reference-images parameter is *not* optional with a safe fallback - Revision #2 keeps Revision #1's tightening (§6: no images means a hard prerequisite failure, not a degraded text-only generation). Backwards compatibility here means *existing data stays valid and readable*, not that *new generations can silently skip the new requirement*:
- No existing table, column, endpoint, or response field is removed or renamed.
- Every new FK (`generation_reference_set_id`, `product_id` on the new join table) is nullable where it needs to be for legacy rows - `GeneratedImage.generation_reference_set_id` specifically, since every row created before this ADR ships genuinely has none.
- Every new response field (`identity_passed`, `identity_checks`, `generation_reference_set_id`) is nullable/optional, defaulting to `null`/absent for any row created before this ADR ships - a pre-existing `GeneratedImage`/`ImageValidationResult` from Phase 8.3/8.4 (including the two real rows already sitting in the dev DB from tonight's live verification) remains a fully valid, readable historical record exactly as it is today.
- The existing `POST /source-import`, `POST /generate-image`, `POST /validate` contracts are unchanged for any caller that doesn't opt into the new fields - **`POST /generate-image` itself does start behaving differently once this ships** (it now requires a populated Library, per §6), which is a deliberate, real behavior change for *new* calls, not a compatibility break for *existing data*. Worth stating plainly rather than letting "backwards compatible" imply more than it does.
- `SLIDESHOW_STAGE_PIPELINE` is untouched - Reference Scoring, like Image Generation/Validation before it, is deliberately not part of the automatic analysis pipeline, for the same real-cost-per-call reason Phase 8's architecture direction already established.

### 11. Migration plan from the current architecture

Proposed as a phased plan **for approval, not as authorization to start** - matching this session's own established discipline (an architecture-direction doc, then a detailed sub-phase plan, only implemented after this kind of document is reviewed). If approved, this would become a new **Phase 9: Canonical Product Reference (Product Lock v2)**, ahead of the current Phase 9 (Frontend consolidation) and its renumbered successors (→ 10/11/12), on the same reasoning Phase 8 itself was inserted ahead of Frontend consolidation: the standing 2026-07-22 directive prioritizes proving/hardening the Generation → Validation loop over further architecture elsewhere, and this ADR is a direct continuation of that same loop's correctness, not a new, separate initiative.

Proposed sub-phases, expand → backfill → switch-reads → contract. Revision #2's split of Scoring (curates the durable Library) from Selection (assembles one disposable Set) now maps onto two distinct sub-phases where Revision #1 had one combined stage - the sub-phase boundary follows the architectural boundary from §6, not the other way around:
1. **9.1 - Schema (expand):** `GenerationReferenceSet` + `GenerationReferenceSetImage` (new tables) + four new nullable columns on `product_reference_images` from §1/§2, fully additive, no behavior change to anything reading today's tables.
2. **9.2 - Reference Scoring Stage, over Priority 1+4 candidates only (§4):** acquisition (the candidate query) plus the new Stage's scoring/ranking/curation logic, run over *already-existing* `ProductReferenceImage` rows from URL imports and slideshow crops, writing `quality_score`/`role`/`library_status` back onto those rows - deliberately excludes Priority 3 (user upload, genuinely new UI+endpoint) to prove the Stage against real data before adding a new ingestion path. This sub-phase is a hard prerequisite for 9.3 - there is no populated Library (no rows with `library_status="included"`) to select from until this Stage exists and has run.
3. **9.3 - Reference Selection service + Prompt Compiler rewrite + `ImageGenerationProvider` reference-image support (§6):** new `app/services/reference_selection.py` (classical role-keyword matching against the scene, `ImageGenerationProvider.max_reference_images()` query, writing the actual `GenerationReferenceSet`/`GenerationReferenceSetImage` rows used), then the Prompt Compiler's `product_profile` → `generation_reference_set` parameter swap, `immutable_constraints` removal, `images.edit` wiring - live-verified with a real paid call against a real `GenerationReferenceSet` assembled from 9.2's Library, same live-verification discipline as Phase 8.3. Includes the `generate_creative_specification` prompt re-scoping flagged in §6 (drop product-descriptive `subject` text) as part of the same sub-phase, since leaving it undone would just be dead weight in the same commit's own output.
4. **9.4 - Stage 1 Identity Validation (§7):** the short-circuit two-stage validation, reusing the *same* `GenerationReferenceSet` recorded on `GeneratedImage.generation_reference_set_id` rather than re-querying the Library independently, live-verified against the *same* Bella Vita slideshow this ADR's diagnosis (§0) is based on - the natural regression check: does the same product now generate with correct geometry, and does Stage 1 correctly gate on it if not. The cross-angle comparison nuance flagged in §7 and §12 below is a known limitation to observe during this live verification, not something this sub-phase is expected to solve.
5. **9.5 - Frontend (§9):** Reference Library panel (grouped by role, multiple images per role) + "reference images used" strip on the Generated Image section + Identity badge.
6. **9.6 - User upload path (Priority 3) + lifecycle upgrade detection (§4's "offer to replace/supersede"):** the two pieces deliberately deferred out of 9.2, once the core loop is proven.
7. **Backfill (timing TBD, real cost decision):** whether/how to retroactively run the Reference Scoring Stage over existing products' already-stored `ProductReferenceImage` rows (populating `library_status`/`role`/`quality_score` so a Library exists for them) - proposed as its own explicit go/no-go decision after 9.1-9.5 are live-verified, not bundled into the schema work.

Bundle-readiness stays explicitly bounded throughout this plan: `GenerationReferenceSetImage.product_id` (§1) means the schema doesn't foreclose a future multi-product sub-phase, but no sub-phase above implements multi-product generation - Creative Specification, Image Generation, and Identity Validation remain hard-scoped to one product per slide, matching Phase 6.3/Phase 8's existing boundary.

Each sub-phase gets its own commit, its own tests-first-then-live-verification treatment, and its own report in a "Phase 9 reports log," exactly matching every phase this entire engagement has used - no new process, no exception.

### 12. Risks and trade-offs

- **Cost and latency**: `images.edit` with reference images is a heavier call than `images.generate` (more input tokens, likely slower) - real, unmeasured until 9.3's live call; Phase 8.3's own real call already took ~53s text-only, so this needs headroom, not just an assumption it'll be similar. Reference Selection itself (§6) adds a step before that call, but the classical role-keyword matching is cheap/local - only the optional `TextGenerationProvider` fallback for ambiguous scenes adds real cost, and only when the classical pass can't confidently match.
- **Reference-image conditioning is not a complete fix**: per §6, it directly addresses geometry/silhouette (the actual observed flaw) but does not guarantee text-rendering precision (the "BELLA MITA" typo is a separate, partially-independent model weakness). Framing this ADR as "solves Phase 8's problem" would overclaim; framing it as "targets the specific class of error that was actually observed, on top of Phase 8's already-working text-precision checks" is accurate and should be the standard the team holds it to.
- **Library quality-scoring accuracy**: Tier 1 heuristics (resolution/file-size-as-sharpness-proxy) are crude and will misrank some real candidates; Tier 2 (vision-scored) is more accurate but costs real money per candidate image, and cost scales with how many candidates a product has (a 10-slide slideshow could mean 10 vision calls just to score crops from one import). Revision #2 makes this slightly worse in absolute call count (multiple images per role are now kept in the Library rather than narrowed to one at curation time) but the added cost is a one-time Library-curation cost, not a per-generation cost - Selection itself (§6) is a cheap local query over already-scored rows.
- **Provider reference-image limits are now queried, not assumed - but the query itself is a real unknown**: `ImageGenerationProvider.max_reference_images()` (§6) resolves the *design* gap from Revision #1 (don't hardcode a guess), but whether OpenAI's SDK/API actually exposes a documented, enforceable limit - versus this needing to be empirically discovered by triggering a real error and hardcoding the result - is not yet verified. 9.3's live call is where this gets resolved, same as the size-mapping/model-name issues Phase 8.3 already found and fixed live.
- **Cross-angle Identity Validation is a narrower test than true independent verification**: newly identified in §7 - Stage 1 compares the generated image against the *same* `GenerationReferenceSet` that was fed into generation, not an independent reference. If the Set's only front-role image was used to generate a 45°-angle creative, Identity Validation is really asking "does this resemble the input we gave it," which is an easier and less rigorous test than "does this genuinely match the real product from an angle we never showed the model." This is a known, unsolved limitation to carry into 9.4's live verification and state plainly in the UI (§9), not a design flaw to silently paper over.
- **Embeddings deferral is a real, acknowledged bet**: acceptable at today's scale (one slide, few products), a genuine future need once Library candidate volume grows - deferring is the right call per this project's own "prove it before building for it" discipline, but it is a deferral, not a decision that embeddings are unnecessary forever.
- **Two-stage validation changes user-visible failure semantics**: a generated image can now fail for "wrong product" reasons distinct from "right product, weak creative" reasons - a real improvement in diagnostic honesty, but only if the UI (§9) keeps the two clearly separated; conflating them back into one badge would quietly regress the clarity Phase 8.5 just built.
- **Backfill cost is an open, real-money decision** (§2/§11) - explicitly not decided in this document, flagged for the user's own call before 9.1 ships, not assumed to be "score every existing product's images automatically."
- **Bundle-readiness is a schema accommodation, not a scope commitment**: `GenerationReferenceSetImage.product_id` (§1) exists so a future multi-product Set doesn't require another migration, but the risk is scope creep during implementation - seeing that field on the table is not license to start building multi-product generation inside Phase 9's sub-phases. Creative Specification, Image Generation, and Identity Validation all stay hard-scoped to one product per slide throughout §11.
- **Migration discipline risk is low, by design, and Revision #2 lowers it further**: every change in §1-§10 is additive, and modeling the Library as status columns on the existing `ProductReferenceImage` table (rather than a new snapshot entity, as Revision #1 had proposed) means fewer new tables and no new duplication of image storage. The highest-risk part of this whole ADR remains the judgment calls in scoring/selection logic (§4/§6) and the real cost/latency of reference-image-conditioned generation (above) - which is exactly why this is being proposed as a reviewed plan first, per the explicit instruction, rather than implemented directly the way Phase 8's own sub-phases were once their direction was set.

---

## ADR: AI Creative Engine vNext — 2026-07-23

**Status**: design-only, awaiting review. Does not modify, supersede, or implement anything in the "ADR: Canonical Product Reference (Product Lock v2)" above - that ADR is treated here as a dependency this document builds on, not a document this one edits. **No code, migration, or new file has been written for this ADR.** Every claim about "what exists today" below was verified by direct code investigation on 2026-07-23 (four parallel codebase surveys covering the domain model, the AI-provider abstraction, the product-source/evidence-ingestion code, and the stage pipeline/frontend), not assumed from the user's framing - several of the user's implicit assumptions about the current system turned out to be wrong in specific, important ways, documented inline below rather than silently corrected. Revised twice by the user on 2026-07-23 (see Revision #1 and Revision #2 below); sections rewritten in place to stay internally consistent, no renumbering.

### Revision #2 (2026-07-23)

Downie 4's actual automation surface, requested as a concrete input to §5's TikTok-slideshow-download proposal - *"please do not assume how Downie 4 can be automated... base the recommendation on its documented functionality."* Investigated directly rather than assumed, three ways: (1) inspecting the real, licensed copy installed on this machine (`/Applications/Downie 4.app`, version 4.12.9) - its `Info.plist`, AppleScript dictionary (`Downie.sdef`), and Shortcuts/SiriKit intent definitions (`Intents.intentdefinition`) are all plain, readable files, the strongest possible source since they describe this exact copy, not a possibly-different documented version; (2) the vendor's own release notes at `software.charliemonroe.net`, which corroborate and date specific capabilities; (3) confirming `/usr/bin/shortcuts` (Apple's own Shortcuts CLI) is present and reading its real `--help` output rather than guessing its flags. Full findings and the resulting `DownieImportProvider` design replace §5(a) below - nothing in the original draft's "Downie" mentions was based on this investigation, since it hadn't been done yet at that point.

### Revision #1 (2026-07-23)

Two additional first-class concepts, requested after the initial draft above: **(1) preserve creative intent, not incidental detail** - the recognition that a kitchen product needs *a* good kitchen, not *the original* kitchen, and that every region of a slide (product, human subject, environment, props, decoration, negative space) carries a different level of importance to what's actually being communicated; and **(2) photorealism by default** - every generated image should be indistinguishable from real photography unless explicitly told otherwise, and that objective should influence prompt construction, provider selection/settings, reference selection, generation strategy, and validation, not just be a nice-to-have quality bar.

Both are incorporated as genuine architecture, not implementation detail, per the explicit instruction:
- Added as principles 5 and 6 in §2, checked against reality the same way the original four were.
- §1's grounding table gains two new rows for Scene Intelligence and Photorealism, since both were checked against the actual codebase before being designed (Scene Intelligence in particular is confirmed genuinely new - `ProductIsolationProvider` today only isolates the product itself, nothing else in a scene).
- §8 (Creative Intelligence) is rewritten as **"Scene Intelligence & Creative Intelligence"** - Scene Intelligence is the new detection/scoring layer (region taxonomy, five-tier importance scoring); Creative Intelligence, as already scoped, becomes the layer that decides what to do with each region's score. This didn't need a new top-level section number - the user's own framing ("Creative Intelligence should then determine how these regions should be transformed") makes the two tightly coupled, one section with two clearly labeled parts.
- Photorealism touches five already-existing sections rather than getting one section to itself, matching the seven touchpoints named in the request: §7 (Reference Selection), §8 (prompt construction), §10 (Provider Framework - provider settings), §11 (Decision Engine - generation strategy), and §13 (Quality Engine - a rewritten Photorealism dimension, absorbing what was previously a thinner "Image Quality" dimension, since the two overlapped substantially and photorealism is the more rigorous, better-specified version of the same concern).
- No section was renumbered; every cross-reference elsewhere in this ADR (§17's review, §16's long-term architecture, §18's success-criteria mapping) still points at the right place.

### 0. What this ADR is - and what "vNext" actually spans

The request asks for the platform's next major evolution: from a slideshow-recreation tool into an autonomous creative engine, under the guiding philosophy *"provide as much evidence as you have, and the engine will produce the highest quality creative it can."* Four design principles are asked to run through the whole document - Evidence First, Autonomous Quality, Provider Independence, Product Fidelity is Mandatory - plus a large set of new subsystems (Project, Evidence Engine, TikTok Import Pipeline, extended Product Intelligence, Creative Intelligence, Text Intelligence, Provider/Capability Framework, Decision Engine, Generation Engine, Quality Engine, Rendering Engine) and a closing review.

Before designing any of that, it's worth stating plainly what this document found once it went and looked: **some of these subsystems are substantial extensions of things that already exist and work; some are new names for things that already exist under different names; and some are genuinely new, unbuilt architecture.** Conflating the three would make this ADR either redundant with Product Lock v2 (re-specifying the Reference Library) or dishonest about effort (implying Text Intelligence is a small addition when it's a new rendering subsystem). §1 makes that split explicit before any design begins.

### 1. Current-state grounding - what exists vs. what's being proposed

| vNext concept | Current reality | Verdict |
|---|---|---|
| **Project** | Already exists (`models/project.py`) - `id/name/notes/created_at` only, no relationships, deliberately documented as *"NOT the owner... everything in the domain model is built outward from Creative/Slideshow, not downward from Project"* (project.py:1-8). Nullable, one-directional `project_id` label on `Slideshow`/`Product`/`ProductBundle`. UI treats it as a flat, non-navigable filter tag. | **Reversal of an existing, documented design decision**, not a new concept. Must be called out explicitly (§3), not silently reinterpreted. |
| **Evidence Engine** | No unified evidence abstraction. Two separate, non-communicating registries exist: `ProductSourceAdapter` (URL → normalized product evidence, `product_sources/registry.py`, only `GenericUrlAdapter` registered) and `ImportProvider` (file/URL → slide images, `importers/registry.py`, only `LocalFileImporter` registered). `assemble_product_profile` already does real evidence-merging-by-classification across two sources (vision vs. URL import), field-by-field, provenance-preserving - this is a working, proven pattern, not a gap. | **Partially exists.** The merge philosophy is proven; the unification of adapter registries and the Project-level accumulation model is new (§4). |
| **TikTok Shop product-URL import** | **Confirmed hard technical blocker** (Phase 5.4 spike, MIGRATION_PLAN.md:1163-1220): real fetches against TikTok Shop hit an anti-bot wall; no JSON-LD/product data returned; corroborated by third-party scraper vendors. Explicitly left as a deliberate, unpursued business decision (pay for scraping/proxy, or use TikTok's narrow owner-only Partner API). | **This ADR does not remove that blocker.** Repeating the vision's "TikTok Shop Product URL" bullet without restating this would overclaim (§6). |
| **TikTok slideshow download** (via Downie 4) | Zero references to "Downie" anywhere in the codebase - entirely different domain from TikTok Shop product scraping, never attempted, never blocked. *(Revision #2)* Downie 4.12.9 (the user's real, licensed, installed copy) was directly inspected: no CLI, but real AppleScript (no destination control), a real `downie://` URL scheme with a destination-folder parameter, and real Shortcuts/SiriKit intents (destination-capable, but success/failure-only, no returned file path, and requiring manual per-user Shortcut setup) - all confirmed via the app's own `Info.plist`/`.sdef`/`Intents.intentdefinition`, corroborated by the vendor's release notes. The `ImportProvider` Protocol's own docstring already names a future `TikTokSlideshowImporter` as the expected extension point. | **A clean, unbuilt extension point, now with a concrete, evidence-based trigger mechanism** - genuinely new work, but the architecture already anticipated it and the automation surface is no longer a guess (§5). |
| **Product Intelligence** ("everything required to faithfully recreate this exact product") | This exact responsibility, this exact phrase, was already the design goal Product Lock v2 Revision #1 established, and Revision #2 (immediately above) already fully designed the Canonical Reference Library / Generation Reference Set split the vision describes. | **Fully covered by Product Lock v2.** This ADR references it, does not redesign it (§7). |
| **Reference Selection** (Library vs. Set) | Same - already designed in Product Lock v2 §6/§11, including provider-capability-aware selection via a proposed `max_reference_images()` method. | **Fully covered.** Referenced, not redesigned (§7). |
| **Creative Intelligence** | Doesn't exist as a named subsystem, but `CreativeFingerprint` (per-slide visual style), `MarketingAnalysis` (slideshow strategy), and `NarrativeStructure` (per-slide narrative beat: hook/story/reveal/proof/cta) already cover most of the requested scope (storytelling, hook structure, visual hierarchy, colour usage, creative style). | **Mostly exists under different names** - propose consolidating the responsibility, not the tables (§8). |
| **Text Intelligence** | Nothing separates text content from text presentation today. `OCRResult` captures `raw_text`/`structured_blocks` but no typography/positioning/styling/semantic-role modeling. | **Genuinely new** (§9). |
| **Rendering Engine** (app renders text, not the model) | Today the image model generates the *entire* raster image, text included - there is no background/text split anywhere in the pipeline. | **Genuinely new, and a real behavioral reversal for marketing-overlay text specifically** - see the boundary this ADR draws against Product Lock v2's product-packaging-text handling (§9, §14 conflict c). |
| **Provider Framework / Capability Framework** | Six `Protocol`s exist (`OCRProvider`, `VisionAnalysisProvider`, `ProductIsolationProvider`, `PromptGenerationProvider`, `TextGenerationProvider`, `ImageGenerationProvider`), each resolved to **exactly one provider, statically, from `providers.yaml`**, at process start. Zero capability-advertisement methods exist anywhere (confirmed by grep - `max_reference_images` appears only as a Product Lock v2 proposal, never implemented). | **Real architecture gap.** Multi-provider-per-capability selection and capability advertisement are both genuinely new (§10). |
| **Decision Engine, candidate counts, automatic retry** | `SlideImageGenerationStage` generates exactly one image per explicit call. No candidate concept, no scoring loop, no retry logic anywhere. | **Genuinely new** (§11-§13). |
| **Scene Intelligence** (region detection + importance scoring) | Doesn't exist under any name. `ProductIsolationProvider.isolate_product` (confirmed via direct read of `base.py`/`openai_adapter.py`) detects and crops exactly one thing - the product - and returns bounding boxes with notes. Nothing detects human subjects, environment, props, decorative elements, or negative space, and nothing scores regional importance. | **Genuinely new** - not a rename of anything (§8). |
| **Photorealism** (as an explicit objective + validation dimension) | Nothing today targets or measures it. `OpenAIImageGenerationAdapter.generate_image` calls `images.generate`/`images.edit` with no `quality`/`style` parameter set (confirmed via direct inspection of the installed `openai==2.46.0` SDK - both calls accept `quality: "standard"\|"hd"\|"low"\|"medium"\|"high"\|"auto"`, and `generate` alone additionally accepts `style: "vivid"\|"natural"`, the SDK's own docstring: *"natural causes the model to produce more natural, less hyper-real looking images"*). Neither parameter is wired anywhere in `providers.yaml`, `config.py`, or the adapter. The original vNext draft's "Image Quality" Quality Engine dimension covered AI-artefact detection but not lighting/shadow/material/texture/anatomy realism. | **Real, verified provider lever, currently unused** - and a genuinely new Quality Engine dimension (§10, §13). |

### 2. The design principles, checked against reality

- **Evidence First**: the "accumulate, don't replace" behavior already exists and works (`assemble_product_profile`'s per-field classification merge). The gap is scope (only 2 of the vision's ~6+ evidence categories are wired in) and unification (two disconnected adapter registries), not philosophy - the philosophy is proven, extend it (§4).
- **Autonomous Quality**: does not exist today in any form - generation is a single explicit call with no acceptance criterion beyond "did the API call succeed." This is the biggest, most novel piece of this ADR (§11-§13).
- **Provider Independence**: exists at the *interface* level (Protocols already decouple calling code from `openai_adapter.py` internals) but not at the *selection* level (one provider per capability, hardcoded, no runtime choice). Half-built (§10).
- **Product Fidelity is Mandatory**: already the explicit, hard-won conclusion of Product Lock v2 (identity validation as a short-circuiting Stage 1, before creative validation). This ADR inherits that conclusion rather than re-deriving it (§7).
- **Preserve Creative Intent, Not Incidental Detail** *(added in Revision #1)*: nothing today distinguishes "this element must stay" from "this element can be improved or replaced" - every pixel is currently either fully preserved (via reference-image conditioning, Product Lock v2) or fully regenerated (via the Prompt Compiler's scene description), with nothing in between. This principle is the reason Scene Intelligence exists (§8) - it's the mechanism, not just a slogan, and it directly reframes what "similarity" should mean throughout this document (§13's Creative Fidelity dimension in particular).
- **Photorealism by Default** *(added in Revision #1)*: half-real in the same way Provider Independence is - the *lever* is real and verified (`quality`/`style` params exist on OpenAI's Images API), but nothing today sets it, prompts for it, or validates for it. Touches §7 (Reference Selection), §8 (prompt construction), §10 (provider settings), §11 (Decision Engine), and §13 (Quality Engine) - listed once here so those five sections can each stay focused on their own responsibility rather than re-explaining why photorealism matters every time it comes up.

### 3. The Project Model

**This is a deliberate reversal of an existing design decision, stated plainly rather than smuggled in.** `project.py`'s own docstring currently says Project exists *"purely so related Creatives can be grouped in the UI"* and that the domain model is built *"outward from Creative/Slideshow, not downward from Project."* The vision in this request inverts that: Project becomes the aggregation root everything belongs to. Both cannot be true at once - if this ADR is approved, `project.py`'s docstring itself becomes wrong and needs updating as part of implementation, not left stale (the same "don't leave the code lying about its own design" discipline this project already applies to itself).

**Proposed shape, keeping what already works:**

- `Project` gains real structure: it becomes the container for **Evidence Sources** (§4) and the aggregation point for **Generation History**, **Validation Results**, and **Final Outputs** for one creative effort.
- `Product` and its Canonical Reference Library **do not move into Project's ownership**. `product.py`'s existing design rationale - *"the same Product can be the target of many Creatives... the whole point of the Product Lock Profile being reusable"* - is worth preserving deliberately: a product's Library is durable knowledge that should outlive any single Project, exactly the way it's designed to outlive any single Slideshow today. Project instead gets a **membership join** (`ProjectProduct: project_id, product_id`) recording which Products are in scope for this creative effort, without claiming ownership. This is the same "reference, don't own" pattern `ProductBundleMember` already uses.
- `Slideshow` (Creative Evidence) becomes genuinely Project-scoped rather than optionally labeled - `project_id` moves from decoration to a real foreign key a Project's assembled view walks.
- **Creative Intelligence** (§8) and **Text Intelligence** (§9) outputs are inherently about a specific set of creatives being produced for a specific effort, so they live at the Project level, not the Product level - this mirrors today's existing split where `MarketingAnalysis`/`NarrativeStructure` are already `slideshow_id`-scoped, not `product_id`-scoped.
- **Generation History, Validation Results, Final Outputs** become Project-level assembled views (compute-on-read, same philosophy as `assemble_slideshow_blueprint`/`assemble_product_profile`) over the `GenerationAttempt`/`GeneratedImage`/quality-assessment/rendered-output rows introduced in §11-§15, scoped by the Slides that belong to that Project's Slideshows.

This keeps the valuable cross-Project reuse Product Intelligence already has, while making Project a real workspace rather than a label - and it means implementing this section requires a genuine, reviewed decision (does the team want Project's role reversed?), not just a migration.

### 4. Evidence Engine

Rather than a new pipeline, this is proposed as **the unification of two registries that already do the right thing separately**, plus generalizing `assemble_product_profile`'s merge-by-classification pattern beyond its current two sources.

- A new `EvidenceSource` row (Project-scoped): `id, project_id, evidence_type (slideshow_upload | tiktok_slideshow_url | product_url | reference_image_upload | brand_asset | manual_correction), source_locator, status, created_at`. This is deliberately a thin **event log**, not a duplicate store - the actual heavy artifacts (`Slideshow`, `ProductSourceImport`, `ProductReferenceImage`) remain owned by `Product`/`Slideshow` exactly as today; `EvidenceSource` just records that a piece of evidence was submitted to this Project and routes it.
- `EvidenceRouter` (new service): given an `EvidenceSource`, classifies it and dispatches to the correct existing mechanism - a URL goes through `get_product_source_adapter` or the new `TikTokSlideshowImporter` (§5) depending on shape; a file upload goes through `import_slideshows`; a reference-image upload (§6 - **no endpoint exists for this today**, a real gap) goes through a new upload path onto `ProductReferenceImage`. This is the layer that unifies `product_sources/registry.py` and `importers/registry.py` without merging their actual Protocols, which serve genuinely different evidence shapes (normalized product facts vs. raw slide images).
- The merge-by-classification pattern (`product_profile.py:76-82`) generalizes: today it's hardcoded to two sources (vision vs. source-import). Proposed: a small precedence table per evidence type, extensible as new types (brand assets, manual corrections) are added, without new special-case code per source - manual corrections, notably, should always win regardless of classification, a new precedence tier this ADR should add explicitly rather than let fall out of the existing immutable/contextual split by accident.

### 5. TikTok Import Pipeline - two different capabilities, one confirmed blocked

The vision's own bullet list already separates these (Creative Evidence: "TikTok slideshow URL" vs. Product Evidence: "TikTok Shop Product URL") but the narrative text discusses them as one pipeline. They are not the same problem and have very different feasibility:

**(a) TikTok slideshow/post download, via Downie 4** *(rewritten in Revision #2 - see below for the investigation this replaces)*.

**What Downie 4.12.9 (the user's actual licensed, installed copy) actually supports, confirmed by direct inspection - not assumed:**

| Mechanism | Confirmed present? | What it can actually do | What it genuinely cannot do |
|---|---|---|---|
| Standalone CLI binary | **No** - only one Mach-O executable ships in the app bundle (`Contents/MacOS/Downie 4`, the GUI app itself); no `downie-cli` or equivalent anywhere in the bundle | - | No command-line tool exists to invent a wrapper around |
| AppleScript | **Yes** - `NSAppleScriptEnabled=true`, real dictionary at `Contents/Resources/Downie.sdef` | Exactly two app-specific commands: `open all URLs in text <text>` (detects links in text, adds them to the download queue, returns 1/0 for "found any") and `start queue` (begins downloading queued items, returns 1/0/-1) | No parameter for destination folder; no command to query download status or retrieve the resulting file path once done - genuinely fire-and-forget |
| URL scheme (`downie://`) | **Yes** - registered in `Info.plist`'s `CFBundleURLTypes`, corroborated independently by the vendor's own release notes: v4.3.9 *"Custom Downie URLs has been extended to include a custom destination folder"*, v4.12.4 *"You can now specify a custom title when using the automation URL"* | Trigger a download from a URL; **can direct output to a specific destination folder** (the one capability AppleScript lacks); can set a custom title | Still fire-and-forget by nature (opening a URL scheme returns nothing to the caller); the exact query-parameter grammar is not confirmed from a primary vendor doc page in this investigation (search results quoting it were secondary/AI-summarized, not a direct quote) - **needs a quick empirical confirmation** (one real triggered download, inspecting what parameter names actually work) before implementation relies on it, same as every other "verify against the real thing" step this project already takes |
| Shortcuts / SiriKit Intents | **Yes** - `Intents.intentdefinition` defines two real, fully-specified intents, also declared in `Info.plist`'s `INIntentsSupported`: `DownloadURLs` (parameters: `urls` list, `postprocessing` enum [default/none/mp4/audio/permute/custom], optional `destination` folder) and `DownloadURLsInText` (same, with a `text` input instead of `urls`). Both are marked `INIntentParameterCombinationSupportsBackgroundExecution=true` - genuinely headless-invocable, not GUI-only. Apple's own `/usr/bin/shortcuts` CLI is present on this machine (confirmed via `shortcuts run --help`: `shortcuts run <shortcut-name-or-identifier> [--input-path ...] [--output-path ...]`) and can trigger a **user-authored** Shortcut non-interactively | Accepts a real `destination` parameter (the vendor's own release notes record a real historical bug where this silently didn't work, fixed in v4.9.2 - evidence it's a genuinely exercised, real feature, not vestigial) | **`INIntentResponse` defines only `success`/`failure` result codes - no output parameters at all.** Even a Shortcut built around this intent cannot hand back a downloaded file's path; `shortcuts run --output-path` has nothing to capture. Also requires the *user* to pre-author and save a Shortcut in Shortcuts.app first (there is no documented API for a backend process to create a Shortcut programmatically) - a one-time manual setup step outside this codebase |
| Automator action | **Yes** - `Open URLs in Downie.action` ships in the bundle | GUI-workflow equivalent of the AppleScript enqueue command | Same no-completion-signal limitation as AppleScript; Automator is a legacy Apple technology being superseded by Shortcuts - weak recommendation, not pursued further |
| Completion notification | **Yes**, per `Info.plist`'s own usage-description string ("Downie posts notifications about completed or failed downloads") | Real, user-facing signal | Not exposed via any documented API for a third-party process to consume - macOS has no supported way for one app to intercept another app's user notifications; not pursued |
| `.downiepart` in-progress marker | **Yes** - Downie registers a real Uniform Type Identifier (`com.charliemonroe.downie.partial.download`, extension `downiepart`) for its own in-progress-download package format | A genuine, concrete, folder-watchable signal: a file still ending `.downiepart` is not finished | Not an official "completion API" - an inference from a declared file type, not a documented promise; worth empirically confirming (does a finished download reliably leave behind a stable, non-`.downiepart` file every time) before treating it as a hard guarantee |

**Development recommendation, as requested:** trigger via **the `downie://` URL scheme with an explicit destination folder**, not AppleScript and not Shortcuts, for one specific reason each competing option lacks: AppleScript has no destination-folder parameter at all (every download would land in Downie's shared global download folder, making it impossible to reliably associate a finished file with the request that triggered it, especially under concurrent imports); Shortcuts requires a manual, one-time, out-of-band setup step (the user authoring and saving a Shortcut in Shortcuts.app before our backend can call it) that the URL scheme doesn't need, since the backend can construct and open the URL entirely on its own. The URL scheme is also the more actively-maintained of the two per the release-note history (a title parameter was added as recently as v4.12.4). This should not be treated as risk-free, though: because the exact query-parameter grammar wasn't independently confirmed from a primary vendor doc in this investigation, **the first implementation step must be a small, real, empirical spike** (trigger one real download via a hand-constructed `downie://` URL, confirm the destination-folder parameter actually lands the file where expected) before any `DownieImportProvider` code is written - not a re-run of Phase 5.4's TikTok Shop spike, but the same discipline. **Regardless of which trigger mechanism is used, completion detection is the same problem and needs the same solution**: neither the URL scheme nor Shortcuts returns a file path or a "done" signal to the caller, so `DownieImportProvider` must open each accepted URL into a **unique, per-request scratch folder** (never Downie's shared default folder, to avoid disambiguation problems under concurrent imports) and poll that folder for a new file that (a) doesn't end in `.downiepart` and (b) has a stable size across two consecutive checks, with a timeout that fails the import cleanly (a normal `StageResult`-shaped failure, not a hang) rather than waiting forever - mirroring this codebase's own existing discipline that every stage resolves to a clear success/failure, never silently stalls.

**This is deliberately local/macOS-only glue**, and should stay optional rather than a hard dependency: `DownieImportProvider` only makes sense while the backend runs on the same Mac as a licensed Downie 4 copy - true today (the user's own stated setup), but not guaranteed to stay true if the backend is ever deployed elsewhere. This is exactly why the `ImportProvider` abstraction the user is asking for matters architecturally, not just as a nice-to-have: `DownieImportProvider` becomes one interchangeable implementation, registered alongside `LocalFileImporter` in `importers/registry.py` and a future `YtDlpImportProvider`/official-API-backed provider, with the downstream pipeline (slide extraction → OCR → product detection → Creative Intelligence → Project population, all already automatic today per §0/§1) staying completely unaware of which one ran. Selecting `DownieImportProvider` specifically (vs. a future alternative) is a deployment-environment decision, not something the calling code branches on.

**Feasibility, separate from mechanism**: the *trigger* mechanism is now well-understood; whether Downie 4 can actually download a given TikTok slideshow post at all (TikTok's own restrictions, not Downie's automation surface) is a different, still-open question this investigation didn't test - confirming that stays a real feasibility spike, not assumed just because the automation mechanism is now clear.

**(b) TikTok Shop product-page import** - **remains blocked**, per Phase 5.4's confirmed anti-bot wall. This ADR proposes nothing new here; the existing documented paths (paid scraping/proxy service, or the narrow owner-only Partner API) remain the only options, and remain a deliberate business decision left to the user, not something this ADR should promise past what's technically real.

**The pipeline** (paste URL → download → extract slides → OCR → layout → detect products → populate Project) is proposed as fully automatic for (a)'s output up through OCR/creative-fingerprint/narrative-structure analysis - this is exactly what already happens automatically today once slides exist (the 7-stage pipeline already runs unattended). **Where it must stop short of "automatic" is product resolution**: this codebase has an existing, hard architectural rule that *"resolution is never automatic except when a human has already chosen the target"* (established for Listing→Product/Bundle resolution). Detected products from a TikTok import should create `ProductAppearance` rows and a provisional candidate suggestion, exactly like Listing resolution's `get_pending_member_hints` today - never silently create or link a canonical `Product` without confirmation. "Populate Project automatically" in the vision's pipeline diagram is accurate for slides/OCR/analysis, and needs this explicit carve-out for product identity.

### 6. Product Intelligence - reference, don't redesign

Product Lock v2 (Revision #2, above) already fully specifies this responsibility: Canonical Reference Library (compute-on-read status columns on `ProductReferenceImage`), Reference Scoring, Generation Reference Set, and the "maintain everything required to faithfully recreate this exact product with high visual fidelity" goal - verbatim the same design goal this request restates. **This ADR does not re-specify any of that.** The one genuine gap this ADR surfaces that Product Lock v2 didn't need to cover: **there is no reference-image upload endpoint today** - `ProductReferenceImage` rows are only ever created by the Product Isolation stage (cropped from an analyzed slide) or by auto-download during source-import. "Uploaded product reference images" as an evidence type (§4) requires a genuinely new upload path - small, additive, but real, and worth flagging as a Product Lock v2 follow-up rather than inventing it twice.

### 7. Reference Selection - reference, don't redesign

Same conclusion as §6: the Library vs. Set distinction, the provider-capability-aware selection design (`max_reference_images()`), and the scene-aware role-keyword matching are all already fully designed in Product Lock v2 §6/§11. The one new consideration this ADR adds: once §10's multi-provider Decision Engine exists, *which* provider's capability gets queried is no longer fixed - Reference Selection needs the chosen provider (from the Decision Engine, §11) as an input, not a hardcoded single registry accessor. This is a small sequencing dependency, not a redesign: Decision Engine must run *before* Reference Selection, not after.

**Photorealism touchpoint** *(Revision #1)*: Reference Scoring's existing Tier 1/2 heuristics (Product Lock v2 §4) already score candidate images for sharpness/usability - this ADR proposes one additional scoring signal, whether a candidate is itself a genuine photograph versus a rendered/stylized/illustrated product shot (common in some marketing source material), since conditioning generation on a non-photographic reference image works against the photorealism objective (§2, §13) before generation even starts. This is a small, additive scoring signal to raise with Product Lock v2's own scoring design, not a reason to reopen it here.

### 8. Scene Intelligence & Creative Intelligence

*(Revision #1 - originally just "Creative Intelligence"; Scene Intelligence is added here as its direct input, per the user's own framing that Creative Intelligence "should then determine how these regions should be transformed.")*

**Scene Intelligence (the detection/scoring layer) is genuinely new** - confirmed via §1: `ProductIsolationProvider` detects and crops exactly the product, nothing else. Nothing in this codebase today segments a slide into regions or scores their importance.

Proposed as a new per-slide analysis artifact, `SceneAnalysis` (slide-scoped, `AnalysisArtifactMixin`-shaped like `CreativeFingerprint`), holding a list of `SceneRegion`s: `region_type (primary_subject | secondary_subject | product | human_subject | environment | background | prop | decorative_element | negative_space)`, `bounding_box`, `importance_tier (essential | important | context | incidental | replaceable)`, `notes`. The five-tier scale is taken directly from the request (★★★★★ Essential down to ★ Replaceable) and mapped onto the region-type examples given (product/hands/positioning = essential; pose/action/composition = important; room-type = context; furniture/decor = incidental; wall art/clutter = replaceable). One hard constraint carried over from Product Lock v2, worth stating explicitly rather than leaving implicit: **the product region is always essential and is never a candidate for replacement or transformation** - Scene Intelligence's whole value is in correctly identifying what's *safe* to change, and getting the product region wrong would directly undermine Product Lock v2's identity-fidelity work, not just this ADR's originality goal.

**Creative Intelligence (the decision layer), consuming Scene Intelligence's output**: `CreativeFingerprint`, `MarketingAnalysis`, and `NarrativeStructure` already cover most of the *understanding* half of what's asked for (creative style/colour usage/visual hierarchy via fingerprint; strategy via marketing analysis; hook/story/reveal/proof/cta via narrative structure, which is literally "hook structure" already implemented) - two real gaps, **object placement** and **emotional trigger**, are more granular than anything captured today and are proposed as additive fields on `CreativeFingerprint.structured_json` rather than a fourth artifact table. What's newly added in Revision #1 is the *decision* half: given `SceneAnalysis`'s per-region tiers, Creative Intelligence decides, per region, whether to **preserve** (essential/important - keep as-is or closely matched), **contextually match** (context tier - same *category* of environment, different actual instance: "a kitchen" not "the kitchen"), or **replace/improve** (incidental/replaceable - free to substitute for something more aesthetically effective). This is the mechanism behind "context rather than background" and "creative optimisation rather than recreation" (the request's points 3 and 6) - not a new concept beyond region-tier-driven decisions, just their concrete output.

**Feeds the Prompt Compiler as a new input, without redesigning it**: Product Lock v2's Prompt Compiler (§6 there) already deliberately describes only scene/composition/marketing intent, never the product itself - Creative Intelligence's region decisions are additive detail *within* that existing scene-description responsibility (e.g. "premium modern kitchen, natural daylight, clean worktops" instead of a literal description of the original kitchen), not a new parameter or a new call to a different function. The Decision Engine's "creativity level" (§11) is proposed as the dial that controls how aggressively context/incidental/replaceable regions actually get changed versus loosely matched - a low creativity level stays close to the original room type and staging; a high one leans harder into "improve the environment," bounded always by keeping the context-tier category correct (a kitchen product still gets a kitchen).

### 9. Text Intelligence + the Rendering Engine boundary

This is genuinely new, and it's where this ADR found the most important conflict to flag before implementation (also listed in §14c).

**The vision asks for two different things that must be kept separate:** (1) *marketing-overlay text* - headlines, captions, CTAs layered onto a creative, the kind of text a designer would set in a design tool - and (2) text that's physically printed on the product's own packaging (a bottle's brand name, a label's ingredient list) - which Product Lock v2 already treats as an **immutable Product Profile field** (`branding_text`) that the image model must preserve, because it's part of product fidelity, not creative styling. The vision's own motivating example (the "BELLA MITA" typo) is case (2), not case (1) - it was the model mis-rendering *product packaging* text, which Product Lock v2's reference-image-conditioning already targets.

**If Text Intelligence + the Rendering Engine are scoped only to case (1) - marketing-overlay text - there is no conflict**: the image model still generates the product (packaging text included, per Product Lock v2), and the app separately composites headline/CTA text on top, giving precise typographic control over the text the model is worst at (arbitrary marketing copy) without touching the text the model is being specifically improved at (product branding). **If Text Intelligence is scoped to "the app renders all text, full stop," it directly conflicts** with Product Lock v2's `branding_text` preservation strategy, which relies on the model, not the app, to get packaging text right (the app has no way to render text that's wrapped around a 3D bottle silhouette it didn't generate). This ADR proposes the narrower scope - **marketing-overlay text only** - as the only version that doesn't reopen Product Lock v2.

**Design, given that scope:**
- Each text asset (new `TextAsset` entity, Project/Slide-scoped): `wording`, `typography (font family/size/weight - extracted or chosen)`, `positioning (x/y/anchor)`, `styling (color/stroke/shadow)`, `hierarchy (rank - headline/subhead/cta)`, `semantic_role (hook/proof/cta/other - reusing `NarrativeStructure`'s existing beat vocabulary rather than inventing a parallel one)`.
- Three strategies as a field on the generation request, not three code paths: `text_strategy: reuse_original | ai_rewrite | no_text`. `reuse_original` extracts `TextAsset`s from existing OCR/layout data (already largely available via `OCRResult.structured_blocks_json`); `ai_rewrite` uses `TextGenerationProvider` (already exists) with an explicit prompt preserving persuasive intent/reading speed/layout, producing new `wording` while keeping the extracted `typography`/`positioning`; `no_text` skips `TextAsset` generation entirely and the Rendering Engine (§15) does a straight pass-through of the background image.
- The image-generation prompt (Prompt Compiler, Product Lock v2 §6) needs one new instruction regardless of strategy: **don't render marketing-overlay text into the background at all** - leave that area clean/uncluttered, since the app will composite it. This is a real, new prompt-compiler change this ADR introduces (not covered by Product Lock v2, which never had a text-suppression concept). *(Revision #1)* A second, unconditional instruction belongs alongside it: an explicit photorealism directive (§2) - "photograph, not illustration," avoiding stylized/cartoon/plastic-texture language - added to every generated prompt regardless of `text_strategy`, unless a future opt-out is explicitly requested.

### 10. Provider Framework + Provider Capability Framework

**Grounded reality**: strictly one provider per capability today, statically resolved from `providers.yaml` at process start, zero capability-advertisement mechanism anywhere in the code (only proposed, unbuilt, in Product Lock v2). Building a full N-provider capability-negotiation framework for a second provider that doesn't have code yet risks exactly the kind of premature abstraction this project's own standards warn against - so this is scoped deliberately narrow:

1. **Registry becomes multi-provider-per-capability, but only for `image_generation` initially** (the only capability with a real second candidate right now). `IMAGE_GENERATION_ADAPTERS` (`registry.py`) already structurally supports multiple dict entries - the real work is `ProvidersConfig`/`ModelsConfig` (currently one string field per capability) gaining a way to express "more than one provider may serve this capability," and `AIProviderRegistry.image_generation()` gaining a selection parameter instead of returning a single cached instance.
2. **Capability advertisement as data, not a growing method list**: a single `ProviderCapabilities` dataclass (`supports_reference_images: bool, max_reference_images: int, supports_masking: bool, supports_inpainting: bool, supported_resolutions: list[str]`) returned by one new `capabilities` property on `ImageGenerationProvider` - this both satisfies Product Lock v2's already-proposed `max_reference_images()` need and avoids bolting on a new Protocol method every time a new capability axis is discovered.
3. **Photorealism-relevant provider settings, verified real** *(Revision #1)*: direct inspection of the installed `openai==2.46.0` SDK confirms both `images.generate` and `images.edit` accept a `quality: "standard"|"hd"|"low"|"medium"|"high"|"auto"` parameter (the SDK's own docstring: *"high, medium and low are supported for the GPT image models"* - i.e. genuinely applicable to `gpt-image-1`, the model actually configured in `providers.yaml`), and `images.generate` alone additionally accepts `style: "vivid"|"natural"` - but the SDK docstring for `style` says *"this parameter is only supported for dall-e-3,"* **not confirmed to apply to `gpt-image-1`**. Proposed: add `preferred_quality`/`preferred_style` fields to `ProviderCapabilities`, wire `quality="high"` immediately (it's real and applicable), and treat `style="natural"` as a real unknown requiring the same live-call verification discipline Product Lock v2 already used for `images.edit` itself - not assumed to work just because the SDK exposes the field.
4. **Sequencing recommendation**: implement `ProviderCapabilities` fully and correctly for the OpenAI adapter first (real, verifiable via the live-call discipline this project already uses), and treat "Nano Banana Lite" as a real adapter to build only once its actual API is being integrated - not speculatively designed against an API this document hasn't inspected. This mirrors the exact caution Product Lock v2 already applied to embeddings ("prove it before building for it").
5. Every other Protocol (OCR, vision, prompt/text generation) stays single-provider for now - multi-provider selection is only justified where there's an actual second candidate, per the standing 2026-07-22 directive to justify new infrastructure with the concrete blocker it removes.

### 11. Decision Engine

Entirely new - nothing today chooses a provider, reference set composition, creativity level, candidate count, or retry strategy; every one of those is currently either hardcoded or absent. Proposed as a new service (`app/services/decision_engine.py`), not a `SlideshowAnalysisStage` - like `image_validation_stage` before it, its unit of work (one generation attempt) doesn't fit the "operates on a whole Slideshow" Protocol shape. Given a Project/Slide/CreativeSpecification plus a quality-mode input (Fast/Balanced/Maximum Quality, §12), it produces a `GenerationPlan`: chosen provider (from §10's capability data - e.g. only a provider whose `supports_reference_images` is true is eligible once a Library exists), provider settings (§10.3's `quality`/`style`, defaulting to the photorealism-favoring choice unless the request opts out, §2), candidate count, creativity-level parameters passed to the Prompt Compiler (§8 - how aggressively context/incidental/replaceable regions get transformed), and - on a retry - what to change based on *why* the previous attempt failed (§13's Quality Engine output), not just "try again with the same inputs." This last point matters: a blind resample-and-hope retry is much weaker than one that reads the failure reason (e.g. identity kept failing → narrow the Reference Set to sharper images; photorealism was weak → try `quality="high"` or a different provider; creative fidelity was weak → loosen the creativity-level dial) - the Decision Engine's real value is in closing that loop adaptively, not just counting attempts.

### 12. Generation Engine

Extends `SlideImageGenerationStage`/`ImageGenerationProvider.generate_image`, made candidate-count-aware. New grouping entity, `GenerationAttempt` (Project/Slide-scoped, additive, not a modification of `GeneratedImage`): `id, slide_id, creative_specification_id, generation_reference_set_id, decision_json (the GenerationPlan that produced this attempt), retry_of_generation_attempt_id (nullable self-FK, chains the retry loop), created_at`. `GeneratedImage` gains one new nullable FK, `generation_attempt_id`, and a `candidate_index` - N `GeneratedImage` rows per `GenerationAttempt`, exactly mirroring how N `GenerationReferenceSetImage` rows already belong to one `GenerationReferenceSet`. Quality modes map to candidate counts as the vision specifies (Fast=1, Balanced=3, Maximum Quality=5+), read from the Decision Engine's plan, not hardcoded in the Generation Engine itself.

### 13. Quality Engine

**Product Fidelity reuses `ImageValidationResult`/Stage 1 Identity Validation unchanged** - Product Lock v2 already designed this exact dimension, including the "compare against the same Reference Set used to generate" nuance and its known cross-angle limitation (§7 of that ADR). This ADR does not touch that schema.

The genuinely new dimensions don't fit inside `ImageValidationResult`'s existing shape, which is deliberately scoped to per-field product-identity checks - forcing them in would either bloat one artifact past its single responsibility (a pattern this codebase has consistently avoided: OCR/Fingerprint/MarketingAnalysis are already separate artifacts, not one mega-row) or require reopening an ADR that's already been reviewed twice. Proposed instead: a new `QualityAssessment` entity (per `GeneratedImage` candidate) that **references** the existing `ImageValidationResult` for the Product Fidelity dimension and adds JSON columns for the others:

- `creative_fidelity_json` - composition/layout/hierarchy scoring, informed by §8's Creative Intelligence facts. *(Revision #1)* Tightened per the new intent-preservation principle: this dimension must score fidelity to *creative intent* (does the region-tier plan from §8 still read as the same message/mood/hook?), never pixel- or environment-similarity to the original - a "premium modern kitchen" replacing "an average family kitchen" (§2's own motivating example) is a **pass**, not a penalized deviation, provided the context tier (kitchen) and every essential/important region are intact. Scoring against raw similarity would directly contradict "Creative Optimisation Rather Than Recreation" (the request's point 6).
- `photorealism_json` *(Revision #1 - replaces what the original draft called "Image Quality," which covered artefact/distortion detection but not the fuller photorealism bar now required by §2)*: realistic lighting, believable shadows, material accuracy, reflections, texture quality, perspective, object integrity, human anatomy, AI-artefact detection, image sharpness, and an overall photographic-realism judgment - the full checklist from the request, evaluated by a vision-provider call with its own dedicated schema, no Product Profile involved. Given photorealism is now a non-negotiable default (§2), this dimension is weighted heavily in the computed `accepted` decision below, not treated as a soft/optional signal.
- `text_quality_json` - only populated when `text_strategy=ai_rewrite` (§9); hook-preserved/readability/layout-fit scoring.
- One computed `overall_confidence_score` and `accepted: bool`, following this project's standing rule that pass/fail is always computed in code from structured sub-scores, never asked of the AI as a bare boolean (same discipline `image_validation_stage.py` already uses for `passed`).

Bundle products validate individually by construction - `QualityAssessment` rows key off the same `product_id`-per-appearance shape `ImageValidationResult` already uses, no new bundle-specific logic needed *for validation itself* (generation is the part that's actually bundle-constrained - see §17's conflict list).

### 14. Automatic Retry Loop

Decision Engine → Generation Engine → Quality Engine, chained via `GenerationAttempt.retry_of_generation_attempt_id`, until `QualityAssessment.accepted` or a configured retry limit is hit. **This must remain an explicitly user-triggered operation, never part of the automatic `/analyze` pipeline** - every candidate is a real paid provider call, and this project has an established, deliberate rule that real-cost operations sit outside `SLIDESHOW_STAGE_PIPELINE`'s automatic execution (`image_generation_stage`/`image_validation_stage` are already excluded from the pipeline for exactly this reason). A retry loop that can silently spend 5+ paid calls per slide must never be one `POST /analyze` away from firing - it needs its own explicit "Generate Creative" action, with the quality mode (and its implied cost) visible to the user before they trigger it.

### 15. Rendering Engine

Background image (accepted `GeneratedImage` candidate) + rendered `TextAsset`s (§9, when `text_strategy != no_text`) → one composited, upload-ready output. New `FinalOutput` entity (distinct from `GeneratedImage` - the raw model output vs. the composited final artifact are different things with different lifecycles): `id, generation_attempt_id, generated_image_id, file_path, text_assets_json (what was actually rendered), created_at`. This needs genuinely new infrastructure this codebase has no precedent for - a server-side text-rendering/compositing service (font selection/matching, dynamic sizing and wrapping to fit the original layout, stroke/shadow styling matching the source creative) - and **should get its own feasibility spike before implementation**, the same "investigate before build" discipline Phase 5.4 already established for TikTok Shop: matching an arbitrary creative's original typography closely enough to look native, not pasted-on, is a real design problem, not a rendering-library integration checkbox.

### 16. Long-term architecture - an opinion, not just the proposed diagram

The requested straight-line pipeline (Project → Evidence → Product Intelligence → Creative Intelligence → Text Intelligence → Decision → Generation → Quality → Rendering → Output) reads well as a diagram but doesn't match how these subsystems actually depend on each other, and building it as a literal one-way pipeline would misrepresent three real relationships:

1. **Evidence Engine isn't a stage that finishes** - it's continuously accumulating (§2, Evidence First), so it shouldn't be drawn as step 1 of N; it's more like a substrate every other subsystem reads from at any time, including after generation has already started (a user adding a sharper reference image mid-session should improve the *next* attempt without restarting the whole pipeline).
2. **Product Intelligence, Creative Intelligence, and Text Intelligence don't depend on each other** - they each read Evidence independently and produce independent facts (what the product looks like; why the creative works; what the text says and how it's styled). Drawing them as a straight chain implies a false ordering dependency; they should run in parallel.
3. **Quality Engine's output must flow backward, not just forward to Rendering** - the whole point of an adaptive Decision Engine (§11) is that a failed attempt informs the *next* Decision, not just triggers a blind repeat. A one-way arrow to Rendering only represents the success path.

**Proposed shape instead - a layered/hub model, not a pipeline:**

- **Foundation layer** (always-on, unordered): Evidence Engine, writing into Project's evidence store.
- **Intelligence layer** (parallel, each derived independently from Evidence): Product Intelligence, Scene Intelligence → Creative Intelligence (§8's tightly-coupled pair - Scene Intelligence's region detection feeds Creative Intelligence's transform decisions, but neither depends on Product or Text Intelligence), Text Intelligence.
- **Orchestration core** (a closed loop, not a chain): Decision Engine ⇄ Generation Engine ⇄ Quality Engine, reading from the Intelligence layer and Provider Capability Framework, looping on itself until acceptance or retry-limit.
- **Delivery layer**: Rendering Engine, consuming only the loop's accepted output plus Text Intelligence's rendering-scoped `TextAsset`s.

This is the same shape this codebase already uses at a smaller scale (compute-on-read assembly reading from several independently-updated sources, rather than a rigid pipeline) - scaling that proven pattern up is a stronger recommendation than adopting a new, unproven straight-pipeline shape for the whole platform.

### 17. ADR Review

**Overlaps with the Image Fidelity Mitigation Plan (Product Lock v2):**
- Product Intelligence (§6), Reference Selection/Library-vs-Set (§7), and Product Fidelity validation (§13's first dimension) are **fully specified there already** - this ADR references, does not re-derive, all three. Any future implementation work on these should cite Product Lock v2's sections, not this document's.
- `max_reference_images()` (Product Lock v2 §6) is subsumed into this ADR's broader `ProviderCapabilities` dataclass (§10) - Product Lock v2's sub-phase 9.3 should implement it as one field of that dataclass if this ADR is approved first, to avoid building the narrow version and then immediately widening it.

**Architectural conflicts, in order of how much they need resolving before any implementation:**
1. **Bundle-scene multi-product generation vs. the just-established single-product boundary** (Product Lock v2 §11's explicit non-goal) - the most significant open conflict. "Bundle products should be validated individually" (§13) is achievable without touching that boundary, since validation already keys off `product_id`-per-appearance. But if a bundle *scene* is meant to show multiple products in **one** generated image (the far more likely real intent for bundle marketing), that requires multi-product generation - directly reopening a boundary this session just finished re-confirming in Product Lock v2 Revision #2. **This needs an explicit decision from the user before any Quality Engine bundle work begins** - this ADR does not resolve it, and shouldn't try to inline that decision into a section about validation scoring.
2. **Project's role reversal** (§3) contradicts `project.py`'s own documented design rationale. Not fixing the docstring alongside the schema change would leave the codebase lying about its own architecture - a small but real risk if this section is implemented piecemeal.
3. **Text Intelligence/Rendering Engine scope vs. Product Lock v2's `branding_text` preservation** (§9) - resolved in this document by scoping Text Intelligence to marketing-overlay text only, but this boundary needs to be stated explicitly in whatever ADR eventually governs implementation, not left implicit - it's exactly the kind of distinction that's easy to blur once multiple people are touching the prompt compiler.
4. **"Populate Project automatically" vs. "resolution is never automatic"** (§5) - resolved here by scoping automation to slides/OCR/analysis and requiring confirmation for product identity, consistent with Listing resolution's existing precedent, but worth flagging as a place future implementers could accidentally regress the existing rule if they're not aware of it.
5. *(Revision #1)* **Scene Intelligence's "replaceable" tier vs. Product Lock v2's identity-fidelity work** - low risk, but worth naming: §8 already states the product region is always essential and never replaceable, precisely so Scene Intelligence's originality goal can't accidentally erode Product Lock v2's fidelity goal. Not a real conflict as designed, but a boundary worth keeping visible as more people implement against both ADRs.

**Recommended implementation order** (biased, per the standing 2026-07-22 directive, toward proving Autonomous Quality - the platform's actual novel capability - before investing in evidence-breadth, matching how Phase 8/Product Lock v2 were already prioritized ahead of Frontend consolidation):
1. **Finish Product Lock v2** (already in flight, closest to done) - this ADR's Product Intelligence and Reference Selection sections depend on it outright.
2. **Provider Capability Framework, scoped narrowly** (§10.1-10.2) - small, and unblocks the Decision Engine without speculative multi-provider work.
3. **Decision Engine + Generation Engine candidate counts + basic retry loop** (§11-§12, §14) - proves Autonomous Quality end-to-end using the *existing* single Product Fidelity dimension, before Creative/Photorealism/Text Quality exist. This is the same "prove the loop, then add capability" discipline the session's own standing directive already asks for.
4. **Photorealism dimension + `quality`/`style` provider settings** (§10.3, §13) - a comparatively small, well-grounded addition (the SDK parameters are already verified real) that raises the bar on the now-working loop before the harder dimensions.
5. **Scene Intelligence spike, then Creative Intelligence integration** (§8) - region-detection/importance-scoring accuracy needs proving with real vision-provider calls before any schema commitment, matching this project's own investigate-first discipline; once proven, feeds the Creative Fidelity dimension (§13) and the Decision Engine's creativity-level dial (§11).
6. **Project-as-aggregation-root + Evidence Engine unification** (§3-§4) - foundational, but the existing Slideshow-centric workflow keeps working throughout, so this doesn't block steps 2-5 and can land in parallel once someone's available for it.
7. **Text Intelligence + Rendering Engine** (§9, §15) - biggest, riskiest, most novel; needs its own feasibility spike (matching the rendering-fidelity problem named in §15) before any schema work.
8. **`DownieImportProvider`** (§5a) - genuinely low-risk given the existing `ImportProvider` extension point and now a concrete, evidence-based trigger mechanism (§5a's URL-scheme + destination-folder + poll-for-completion design), but not blocking anything else, so it's fine last or interleaved with 6-7 as capacity allows. Two small spikes gate it, in order: confirm the `downie://` URL scheme's real query-parameter grammar (a few minutes, one real download), then confirm TikTok itself doesn't block Downie the way it blocks generic scraping (§5b's anti-bot wall is a *different* system - Downie's own download mechanics were never tested by Phase 5.4 and need their own check). TikTok Shop product import (§5b) stays parked pending the user's own business decision, as it already was.

**Future ADRs this design implies:**
- *Provider Capability Framework & second image-generation provider* - its own ADR once a real second provider (Nano Banana Lite or otherwise) is actually being integrated, not before.
- *Scene Intelligence - region-detection feasibility spike* *(Revision #1)* - does a vision provider reliably segment a slide into the requested region taxonomy and produce useful five-tier importance scores against real creatives, before any `SceneAnalysis` schema is committed - the same "investigate, then decide" shape as every other spike in this project.
- *TikTok Slideshow Import via Downie 4 - implementation ADR* *(narrowed in Revision #2 - no longer a "what's even possible" feasibility spike, since Downie's automation surface is now fully documented; this future ADR covers the `DownieImportProvider` implementation itself plus the two remaining small spikes named in §17's implementation order)*, for §5a.
- *Text Intelligence & Rendering Engine* - its own design-only ADR once the feasibility spike (§15) has real findings to design against, given how much of this is unbuilt-anywhere-in-this-codebase.
- *Project as Aggregation Root - migration plan* - a dedicated schema/UX migration ADR (expand→backfill→switch-reads→contract, matching this project's standing migration discipline) once §3's role reversal is confirmed as intentional.

**Recommended improvements before any implementation begins:**
- Get an explicit answer on the bundle-scene multi-product-generation question (conflict 1) before scoping any Quality Engine bundle work - it changes the shape of Generation Engine, not just Quality Engine, if the answer is yes.
- State the marketing-overlay-text-only boundary (conflict 3) explicitly in whichever document ends up governing Text Intelligence implementation, not just here.
- Run the two small Downie spikes named in §5a (confirm the `downie://` URL-scheme parameter grammar; confirm TikTok doesn't block Downie's own download mechanics) before promising the Import Pipeline in any user-facing form - the same investigate-first discipline that already saved real effort on TikTok Shop, now scoped much narrower since the automation *mechanism* itself is already confirmed.
- Don't build the full N-provider Capability Framework speculatively (§10.4) - build `ProviderCapabilities` for OpenAI for real, and treat a second provider as real work only once it's actually being integrated.
- Decide Project's role reversal (§3) as an explicit yes/no before any schema PR touches it, and update `project.py`'s docstring in the same change if yes - don't let the code and the architecture doc disagree.
- *(Revision #1)* Run the Scene Intelligence feasibility spike before committing to the `SceneAnalysis`/`SceneRegion` schema (§8) - region-taxonomy detection and five-tier importance scoring is a real, unproven vision-analysis capability, not a safe schema-first bet.

### 18. Success criteria - traced to subsystems

Every bullet in the request's success-criteria list maps to a subsystem above: upload/TikTok-URL entry → Evidence Engine + Import Pipeline (§4-§5); optional product URLs → Evidence Engine's product-evidence path, reusing existing `ProductSourceAdapter`s (§4); text strategy choice → Text Intelligence (§9); automatic evidence analysis → the existing compute-on-read pipeline, extended (§2, §8's Scene Intelligence in particular); multiple candidates → Generation Engine (§12); automatic validation across fidelity dimensions (Product, Creative, Photorealism, and conditionally Text) → Quality Engine (§13); automatic retry → §14; highest-quality upload-ready output with minimal effort → Rendering Engine's `FinalOutput` (§15), gated by the whole closed loop in §16. Preserving intent while improving incidental detail (§2's fifth principle, added in Revision #1) is the mechanism behind "highest quality... with minimal effort," not a separate criterion - it's what makes the output better than a literal recreation rather than just a safe copy of it. No success-criterion bullet is left uncovered by this design - but per the implementation order above (§17), several of them (Text strategy, automatic retry, upload-ready rendering) are the *last* pieces to land, not the first, because they're the least proven and highest-novelty parts of the design.

---
