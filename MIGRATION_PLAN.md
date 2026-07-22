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
| 5 | **Product Intelligence** (evidence model, listing import, canonical profile) | not started — see detailed section below |
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

**Status: direction confirmed by the user on 2026-07-22 (see the
resolved question at the end of this section); detailed sub-phase plan
below is ready for implementation to begin.**

**Problem.** `ProductLockProfile` is currently the only thing resembling
Product Intelligence, and it's a single AI-vision-derived blob: one
evidence source (crops from `slideshow.primary_slide`), no per-field
provenance, no confidence, wholesale-replaced on every regeneration
(`is_current` flips old→false). The goal is a canonical Product Profile
built by combining multiple evidence sources, each attribute individually
tagged with where it came from and how trustworthy that source is.

**Recommended shape, reusing existing patterns rather than inventing new
ones:**

- **New evidence artifact**: `ProductUrlImport` - same shape discipline
  as every other artifact (id/is_current/created_at), owned by
  `product_id`. Records what a product URL import produced: the source
  URL, fetch status, extracted title/brand, and whatever structured
  fields schema.org/OpenGraph/page-metadata parsing found.
  - **Not** forced through the existing `AnalysisRun` table - that model
    requires non-nullable `provider`/`model_name` (AI-call-specific); a
    URL fetch isn't an AI call. Worth a small, parallel, purpose-built
    traceability record instead (mirrors `AnalysisRun`'s shape: id,
    product_id, source_url, platform, status, error, created_at - just
    without the AI-specific fields).
- **`ProductSource` as the evidence-source concept** (user's term,
  2026-07-22): NOT a `Protocol`+registry with multiple pluggable
  marketplace adapters from day one (`app/importers/`'s `ImportProvider`
  pattern was the original inspiration, but building that indirection now
  - for exactly one real implementation - would itself be the premature
  abstraction the whole plan has avoided everywhere else). First
  iteration supports exactly two source types: manual product reference
  images (already exists - `ProductReferenceImage`/`ProductAppearance`,
  nothing new needed) and an optional product URL (new). The URL
  extractor is a single, platform-agnostic code path - schema.org
  JSON-LD + OpenGraph + page metadata, never a marketplace-specific
  scraper. Explicitly not building dedicated Shopify/Amazon/TikTok Shop
  integrations in this phase. `source_type` is stored as a plain string
  column, not a hardcoded enum requiring a migration to extend - so
  adding a real second source type later (a credentialed adapter) is
  additive data, not a schema change, without needing the registry
  ceremony built preemptively today.
- **Canonical profile as compute-on-read**: e.g. `assemble_product_profile
  (db, product) -> ProductProfile`, mirroring `assemble_slideshow_
  blueprint` exactly - merges every current evidence artifact for a
  product into a field-level `{value, source, confidence}` view at read
  time, not a new persisted/versioned entity. Keeps this additive;
  avoids a premature abstraction. Field-level provenance (not a flat
  merged blob) is what makes this generation-ready later - a future
  "compare generated image against the profile, score fidelity per
  field" step needs exactly this granularity, and nothing here would need
  redesigning to support it.
  - Merge/precedence logic (which source wins per field) lives in this
    new layer's own lookup table, not by changing `ProductLockProfile`'s
    existing schema - e.g. official listing wins for immutable physical
    facts (shape, dimensions, capacity, labels, branding, colors,
    packaging), slideshow evidence wins for what listings can't capture
    (camera angle, composition, lighting, marketing context).
- **Extend, don't replace, `ProductReferenceImage`**: it already has
  nullable `source_creative_id`/`source_slide_id` for exactly this
  "which provenance" pattern (Phase 2.3's transitional design). A new
  nullable `source_product_url_import_id` extends the same pattern for
  officially-sourced images rather than inventing a separate image
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

**Resolved (2026-07-22)**: asked which listing platform should get
first-class support beyond the schema.org/OpenGraph baseline. User's
answer, in full, confirming and sharpening the recommendation above:
build around a generic `ProductSource` abstraction rather than any
specific marketplace; first iteration supports manual reference images
(already exists) and an optional product URL only; when a URL is
supplied, extract whatever public product information is available
(schema.org/OpenGraph/JSON-LD, page metadata), download publicly
available listing images, and store the URL as an evidence source, not
a platform-specific implementation; explicitly do not build dedicated
Shopify/Amazon/TikTok Shop integrations yet; the architecture should
make adding dedicated adapters easy later without being built
preemptively now; the objective is not to integrate marketplaces, it's
to build the most accurate canonical Product Profile from any available
evidence. This is authoritative for the detailed sub-phase plan below.

## Phase 5: Product Intelligence — detailed sub-phase plan

**Problem** (same as above, restated for this section's self-
containment): build a canonical, multi-source Product Profile with
field-level provenance/confidence, without redoing any completed work.

### 5.1 — Additive schema: `ProductUrlImport` + `ProductReferenceImage` extension

- New model `ProductUrlImport`: `id, product_id (FK), is_current, source_url,
  fetch_status ("succeeded"|"partial"|"failed"), error (nullable),
  extracted_title (nullable), extracted_brand (nullable), structured_json
  (whatever schema.org/OG/page-metadata parsing found, in its own native
  shape - no attempt to remap into canonical fields at write time, see
  5.3), created_at`. Deliberately NOT built on `AnalysisArtifactMixin`
  (that mixin requires `analysis_run_id` -> `AnalysisRun`, which itself
  requires non-nullable `provider`/`model_name` - AI-call-specific,
  doesn't fit a URL fetch) - its own small, independent set of columns
  instead, `is_current` scoped to `product_id` following the same
  convention as every other artifact regardless.
- `ProductReferenceImage` gains a new nullable
  `source_product_url_import_id` FK (third provenance column, alongside
  the existing `source_creative_id`/`source_slide_id` - same pattern,
  same reasoning as Phase 2.3).
- Alembic migration (additive only, SQLite batch mode for the new FK
  column). New model-level tests only (round-trip, `is_current`
  scoping) - no behavior change to anything existing.
- **DB/schema changes**: two additive changes, no data migration needed
  (nothing existing maps to the new columns/table).
- **Rollback**: downgrade the migration; nothing else references the new
  table/column yet.
- **Expected commit size**: small (one new model file, one migration,
  one small test file).

### 5.2 — URL extraction service (backend only, no route yet)

- New dependencies: an HTTP client (`httpx` - already a transitive
  dependency via FastAPI's own stack, promote to a direct dependency)
  and an HTML parser for JSON-LD `<script type="application/ld+json">`
  blocks and OpenGraph `<meta property="og:...">` tags (`beautifulsoup4`
  - neither is in `requirements.txt` today, both need adding).
- `app/services/product_url_import.py`: `import_product_url(db,
  product_id, url) -> ProductUrlImport`. Fetches the URL with a sane
  timeout and response-size limit (this is fetching arbitrary
  user-supplied URLs - real abuse-surface even in a local single-user
  app, worth bounding regardless), parses schema.org JSON-LD first,
  falls back to OpenGraph/basic page metadata (`<title>`,
  `<meta name="description">`) if no JSON-LD found, downloads any
  discovered product images and persists them as `ProductReferenceImage`
  rows (`source_product_url_import_id` set, `isolation_method=
  "product_url"`) via a new small storage helper mirroring
  `save_product_reference_image`'s existing pattern. On any failure
  (unreachable, no parseable data, non-HTML response) creates a
  `ProductUrlImport` row with `fetch_status="failed"`/`error` set rather
  than raising - matching the established "the artifact records the
  attempt, including failures" discipline used everywhere else in this
  codebase.
- **Test strategy**: no real network calls in tests - mock the HTTP
  client/transport and feed it fixture HTML (a small local schema.org
  Product JSON-LD fixture, an OpenGraph-only fixture, a no-markup
  fixture, an unreachable-URL case, an oversized-response case). Live
  verification against a real, real-world product URL happens once in
  5.5, not repeated per-sub-phase.
- **API changes**: none yet - this is a service function, not a route.
- **Rollback**: revert the file; nothing calls it yet.
- **Expected commit size**: medium (new service + dependencies + fixture-based test suite).

### 5.3 — Canonical field vocabulary + merge service

- Define a small, explicit, documented canonical field set bridging both
  evidence sources' native vocabularies (e.g. vision-derived
  `colors.primary` and schema.org `color` both map to canonical
  `"color"`), plus a per-field classification: which fields are
  immutable/listing-preferred (shape, dimensions, capacity, labels,
  branding, colors, packaging) vs contextual/slideshow-preferred (camera
  angle, composition, lighting, marketing context) - this classification
  lives entirely in the new merge layer, no changes to
  `ProductLockProfile`'s existing schema.
- New Pydantic schema `ProductProfile` (`fields: dict[str,
  ProductProfileField]`, `ProductProfileField = {value, source_type,
  source_id, confidence}`).
- `app/services/product_profile.py`: `assemble_product_profile(db,
  product) -> ProductProfile` - reads the current `ProductLockProfile`
  and current `ProductUrlImport` for the product, maps each into
  canonical fields, resolves conflicts per the classification above.
  Compute-on-read, mirroring `assemble_slideshow_blueprint` - not a new
  persisted/versioned entity.
- **Known simplification, flagged rather than solved here**: the Product
  Lock Profile Stage doesn't emit per-field confidence today (facts
  only). Rather than blocking this sub-phase on prompt-engineering work
  to add it, start with a flat, documented default confidence per source
  type (e.g. vision evidence = 0.85, a successfully-parsed listing field
  = 0.98) - real per-field confidence from the vision model is a
  reasonable fast-follow, not a prerequisite for shipping field-level
  provenance at all.
- **Test strategy**: unit tests per merge scenario (listing-only,
  vision-only, both agreeing, both disagreeing - confirm the documented
  precedence wins, neither present - field absent from the profile, not
  a crash).
- **Rollback**: revert the file; nothing calls it yet.
- **Expected commit size**: medium (vocabulary/classification table +
  merge logic + a real test matrix).

### 5.4 — API surface

- `POST /api/products/{id}/url-import` - triggers 5.2's service. Runs
  synchronously (a deliberate, documented departure from Phase 3's
  "everything backgrounded" pattern - a single HTTP fetch + parse is a
  fundamentally different operation shape than a multi-provider AI
  pipeline; revisit if real-world latency proves otherwise, not assumed
  upfront).
- `GET /api/products/{id}/profile` - returns 5.3's assembled
  `ProductProfile`.
- New route-level tests for both (success, failure surfaced correctly,
  404 for unknown product).
- **Rollback**: revert the two routes independently; backend services
  underneath are unaffected either way.
- **Expected commit size**: small.

### 5.5 — Frontend: submit URL + view the profile with provenance

- `ProductManager.tsx`'s existing "View Analysis" panel gains a URL
  input + submit control, and a new profile view rendering each
  canonical field's value/source/confidence (replacing today's raw
  `<pre>{JSON.stringify(lockProfile.structured)}</pre>` dump for this
  purpose - `ProductLockProfile`'s own raw view can stay as a secondary/
  "raw evidence" detail if useful, but the primary view becomes the
  merged profile).
- Live-verify against a real product URL with genuine schema.org/OG
  markup (not fabricated) - same live-server discipline used for every
  other phase's frontend sub-phase.
- **Rollback**: revert; backend keeps working with a client that doesn't
  expose the new capability - degraded, not broken.
- **Expected commit size**: medium.

**Risks**: fetching arbitrary user-supplied URLs is new I/O surface for
this app (timeouts, oversized responses, malformed/hostile HTML,
SSRF-shaped concerns even in a local single-user context) - 5.2's own
bounds (timeout, size limit) are the mitigation, not deferred. Field
vocabulary/classification (5.3) is inherently a judgment call with room
to be wrong in ways that only show up with real product data - expect to
revisit the classification table as real profiles get built, not treat
it as final on first landing.

---
