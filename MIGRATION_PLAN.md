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

## Phase list

| # | Phase | Status |
|---|-------|--------|
| 0 | Characterization safety net | done |
| 1 | Orthogonal reliability fixes (1.1–1.4) | done |
| 2 | Entity split: Creative → Slideshow + Slide (2.1–2.7) | done, reviewed |
| 2.8 | Drop legacy Creative/CreativeBlueprint schema | **gated — explicit approval required, do not implement** |
| 3 | Async execution boundary | in progress |
| 4 | True multi-slide import | not started |
| 5 | Optional multi per-slide product detection | not started |
| 6 | Narrative pass with dependency-aware staleness | not started |
| 7 | Frontend consolidation | not started |
| 8 | PerformanceRecord (additive) | **explicitly out of scope for autonomous work — plan only if/when revisited, no implementation without direct review** |
| 9 | Pattern v0 (trivial candidate capture) | **same as 8** |
| 10 | Pattern curation lifecycle + ContextEfficacy + search | **same as 8** |

## Standing authorization (granted 2026-07-21/22, user away for an
extended, unspecified period)

Permitted without further chat confirmation, for Phases 3–7 only:
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

**2026-07-22: user enabled the Claude Code app's "bypass permissions
mode"** (stops per-tool-call confirmation prompts) before stepping away
for an extended period. This does not change any of the boundaries
above — those are self-imposed, not enforced by the permission dialog,
and remain in force regardless of app-level permission mode.

## Open questions

_(none yet)_

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

---
