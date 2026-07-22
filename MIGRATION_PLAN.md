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
| 3 | Async execution boundary (3.1–3.5) | done |
| 4 | True multi-slide import | in progress |
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

---
