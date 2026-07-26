# Production deployment checklist

Written so that somebody who has not worked on this system can deploy it.
Each item states what to do, how to verify it, and what happens if you skip
it.

**Three items currently BLOCK production.** They are marked ⛔ and listed
again in §11.

---

## 1. Deployment prerequisites

| Requirement | Check |
|---|---|
| Python 3.13 | `python3 --version` |
| A writable data directory | `CAE_DATA_DIR` (see §4) |
| Node 20+ (frontend build only) | `node --version` |
| Outbound HTTPS to the providers | see §3 |

```bash
cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

SQLite is the database. It is a file inside `CAE_DATA_DIR`; nothing external
is required.

## 2. ⛔ Font assets

**Blocks production.** Rendering currently resolves macOS-only system fonts.
Output that depends on which machine drew it makes benchmark scores
incomparable and recreations non-reproducible.

```bash
python scripts/fetch_fonts.py            # install the OFL/Apache set
python scripts/fetch_fonts.py --verify   # confirm every face and its checksum
```

Verify:

```bash
backend/.venv/bin/python -c "from app.services.typography import assert_fonts_are_portable; assert_fonts_are_portable(); print('fonts OK')"
```

This **must** pass before serving traffic. It refuses if any token resolves
only to a host face. To use your own licensed faces, put them in a directory
named per `VENDORED_FACES` and set `CAE_FONT_ROOT`.

*Current state: the mechanism, the gate and the pinned installer are done;
the twelve font files are not yet installed.*

## 3. Provider credentials

Resolved from the macOS Keychain first, then `<PROVIDER>_API_KEY`
environment variables. **Never commit a key, and never put one in
`providers.yaml`.**

| Provider | Used for | Notes |
|---|---|---|
| `openai` | product isolation, vision analysis, text/prompt generation | required |
| `nano_banana` | image generation **and Gemini** | one shared Google credential by design |
| `gemini` | — | not configured separately; `gemini_adapter` deliberately uses `nano_banana` |

Verify (prints presence only, never a value):

```bash
backend/.venv/bin/python -c "
from app.ai_providers.config import get_api_key
for p in ('openai','nano_banana'):
    try: get_api_key(p); print(f'{p}: present')
    except RuntimeError: print(f'{p}: MISSING')"
```

## 4. Configuration

Every setting is prefixed `CAE_`. **An unrecognised `CAE_` variable raises at
startup** — an override that silently does nothing is worse than one that
fails.

| Variable | Default | Meaning |
|---|---|---|
| `CAE_DATA_DIR` | `backend/data` | database, storage, generation logs |
| `CAE_FONT_ROOT` | `backend/assets/fonts` | bundled font faces |
| `CAE_TYPOGRAPHY_RENDERER_ENABLED` | `false` | ownership-aware rendering (§8) |
| `CAE_SEQUENTIAL_STAGES` | `false` | disable concurrent stages (§8) |

`CAE_DATABASE_URL` **does not exist**. Use `CAE_DATA_DIR`.

## 5. ⛔ Spend configuration

**Blocks production.** The daily cap is disabled because the image model has
no published rate configured, and enabling the cap with unpriced work would
refuse most work rather than silently under-count.

Configure in `backend/providers.yaml`:

```yaml
spend_limits:
  daily_usd: 25.00          # soft: in-flight work finishes, the next unit is refused
  unknown_cost_ceilings_usd:
    nano_banana:
      image_generation: 0.30   # YOUR conservative upper bound, not an inferred price
```

Operator tooling (never makes a provider call):

```bash
python scripts/spend.py today
python scripts/spend.py forecast --slides 3 --hard-stop 2.00
```

`daily_usd` is a **soft** cap; `--hard-stop` is **absolute** and refuses a run
before anything is spent. Unpriced work is refused unless explicitly allowed.

*Current state: `gemini-pro-latest` (Creative Fingerprint) and the image
model are unpriced, so cost reporting says "incomplete" rather than
under-reporting. Set official rates or a ceiling before enabling the cap.*

## 6. Benchmark version

Record which suite any score was measured against — a score without one is
not comparable to anything.

```bash
cat backend/tests/benchmarks/VERSION      # currently 1
```

Governance: `docs/BENCHMARK_GOVERNANCE.md`. Two fixtures are disputed and
awaiting adjudication (`docs/benchmark_review/BENCHMARK_REVIEW_001.md`);
neither has been changed.

## 7. Migration status

```bash
python scripts/migrate.py --status                 # current head
python scripts/migrate.py --live                   # apply (takes a backup first)
```

**Never call `alembic` directly against a live database.** `scripts/migrate.py`
refuses a live DB without `--live`, takes a WAL-safe backup, and runs an
integrity check afterwards.

Verify after migrating:

```bash
sqlite3 "$CAE_DATA_DIR/creative_asset_engine.db" "pragma integrity_check; select version_num from alembic_version;"
```

Every migration on this branch has a tested `downgrade()`.

## 8. Feature flags

| Flag | Default | Turn it on when |
|---|---|---|
| `CAE_TYPOGRAPHY_RENDERER_ENABLED` | **off** | fonts are portable (§2) and you have validated rendering on your own creatives |
| `CAE_SEQUENTIAL_STAGES` | off (i.e. concurrent) | you need to rule out concurrency during an incident |

Concurrent execution is on by default and measured at **−27.3%** wall clock
with no accuracy change. The sequential path remains fully tested.

## 9. Rollback

| Situation | Action |
|---|---|
| Rendering looks wrong | `CAE_TYPOGRAPHY_RENDERER_ENABLED=false` — the previous path is untouched |
| Suspected concurrency issue | `CAE_SEQUENTIAL_STAGES=1` |
| Bad deploy | `git revert <sha>`; each work package is one revertible commit |
| Bad migration | `python scripts/migrate.py --live --downgrade -1`; restore the backup it took |
| Runaway spend | lower `daily_usd`, or remove the `unknown_cost_ceilings_usd` entry so unpriced work fails closed |

Flags are the first line of rollback in every case — none needs a database
intervention.

## 10. Monitoring

Cost reporting reads `provider_calls` **exclusively**. A stage that skipped
it would be invisible to spend.

| Signal | Where | Watch for |
|---|---|---|
| Spend | `GET /api/costs/daily`, `scripts/spend.py today` | rising `calls_with_untrusted_cost` — cost is under-reported |
| Stage failures | `analysis_runs.status = 'failed'` | a stage failing consistently is usually a schema or provider change |
| Latency | `AnalysisRun.provider_call_ms` | **not** `duration_ms` for concurrent stages — see below |
| Unpriced calls | `provider_calls.cost_status = 'unknown'` | any growth means cost figures are drifting from reality |
| Validation status | `validation_status` on contract / ownership / profile | `failed` or `needs_review` trending up |

**Known instrumentation defect:** OCR, Creative Fingerprint, Scene
Intelligence and Composition Contract open their `AnalysisRun` after
concurrent provider work completes, so `duration_ms` records 2–11 ms of
bookkeeping against 14–26 s of real work. Use `provider_call_ms`. Fixing this
is a tracked recommendation.

## 11. Release validation

**Run before every release.** Mocked tests are not sufficient: Phase F's two
structured-output defects failed half the benchmark suite at 100% against the
real provider while over a thousand mocked tests passed.

```bash
backend/.venv/bin/python -m pytest backend/tests -q          # ~1145 tests, no provider
cd frontend && npx tsc --noEmit && npx oxlint src

python scripts/release_validation.py --i-understand-this-spends-money
```

The real-provider check runs one designed-typography case — deliberately, so
that every response schema including the typography one is exercised. A
caption case would skip the schema that actually failed.

Measured: **~51 s, $0.14, 8/8 checks passing.** Exit 0 pass, 1 fail, 2
refused before spending.

## 12. ⛔ What still blocks production

| # | Blocker | Why | Owner |
|---|---|---|---|
| 1 | **Fonts not installed** (§2) | rendering is macOS-only; needs a network-connected run of `fetch_fonts.py` | engineering |
| 2 | **Image model unpriced** (§5) | the spend cap cannot be enabled, so there is no cost ceiling | needs official pricing |
| 3 | **Generation unvalidated** | Product Lock, reference conditioning, generation and cleanup have never run against a benchmark; design approved in `docs/PRODUCT_BENCHMARK_DESIGN.md` | engineering |

None is architectural. Analysis, ownership, enforcement and rendering are
validated end to end; the gap is the product and generation path.
