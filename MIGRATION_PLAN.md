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

1. **Product Intelligence** - a canonical Product Profile, built by
   combining evidence from multiple sources (official listing, Shopify/
   Amazon/TikTok Shop pages, official images, user-uploaded references,
   creator slideshows, future generated images), each attribute tagged
   with its source and a confidence score. An official Product URL, when
   supplied, becomes authoritative for immutable physical facts (shape,
   dimensions, capacity, labels, branding, official colors, packaging);
   slideshows continue to supply what listings can't (camera angle,
   composition, lighting, marketing context, persuasion, emotional
   positioning). These complement rather than compete.
2. **Creative Intelligence** - understanding why a slideshow sells a
   product. This is what Phases 2-4 already built (Slideshow/Slide,
   OCR, Creative Fingerprint, Marketing Analysis, Recreation Prompt).
3. **Generation Engine** (future, not started) - generate an original
   slideshow that preserves the marketing strategy while remaining
   visually original. Explicitly out of scope for now, but Product
   Intelligence is being designed so the eventual validation loop
   (generate → analyze → compare against the canonical Product Profile →
   measure fidelity → regenerate if below threshold) doesn't require a
   second architectural redesign later.

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
| 8 | Frontend consolidation *(was Phase 7)* | not started — Product Intelligence's own minimal UI ships inside Phase 5 itself (same discipline as Phases 3-4: backend+frontend as one working slice), not deferred here |
| 9 | PerformanceRecord (additive) *(was Phase 8)* | **explicitly out of scope for autonomous work — plan only if/when revisited, no implementation without direct review** |
| 10 | Pattern v0 (trivial candidate capture) *(was Phase 9)* | **same as 9** |
| 11 | Pattern curation lifecycle + ContextEfficacy + search *(was Phase 10)* | **same as 9** — now understood to sit above both Product and Creative Intelligence, not just Creative |
| — | **Generation Engine** | future, unnumbered — depends on Phase 5's canonical Product Profile existing; explicitly not started

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
