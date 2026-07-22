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

## Phase list

| # | Phase | Status |
|---|-------|--------|
| 0 | Characterization safety net | done |
| 1 | Orthogonal reliability fixes (1.1–1.4) | done |
| 2 | Entity split: Creative → Slideshow + Slide (2.1–2.7) | done, reviewed |
| 2.8 | Drop legacy Creative/CreativeBlueprint schema | **gated — explicit approval required, do not implement** |
| 3 | Async execution boundary (3.1–3.5) | done |
| 4 | True multi-slide import (4.1–4.4) | done |
| 5 | **Product Intelligence** (evidence model, listing import, canonical profile) | done (5.1-5.7, live-verified — TikTok Shop deliberately unsupported, see 5.4) |
| 6 | Multi per-slide product detection *(was Phase 5)* | not started — demoted; now an enhancement to Product Intelligence's slideshow-evidence source, not a prerequisite for it |
| 7 | Narrative pass with dependency-aware staleness *(was Phase 6)* | not started — unaffected by the revision, pure Creative Intelligence |
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

### 6.2 — Product Isolation + Product Lock Profile stages: loop over every current appearance

- Both stages change from "get one current appearance, process that one
  product" to "get every current appearance, process each *distinct*
  product_id once" (dedupe if a slide somehow has two appearances for
  the same product - run isolation/profiling once per product, not once
  per appearance row).
- No schema change needed - each stage's artifacts (`ProductReferenceImage`,
  `ProductLockProfile`) are already scoped to `product_id`, not `slide_id`,
  so producing N sets of artifacts for N products on one slide already
  fits the existing model exactly.
- The zero-appearance case (today's "no product assigned" failure)
  stays unchanged - still correct.
- **Test strategy**: existing single-product tests must keep passing
  unchanged (looping over a 1-element list is behaviorally identical to
  today's single-item handling) - new tests specifically construct 2+
  current appearances via 6.1's new endpoint and confirm both products
  get isolated/profiled independently.
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
6.4+6.5 together, tested thoroughly, is the mitigation. Deduping by
product_id in 6.2 is a judgment call worth re-checking against real
multi-product usage once it exists - documented as a reasonable default,
not asserted as definitely correct forever.

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
