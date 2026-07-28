# Creative Asset Engine

Local application that reproduces a TikTok Shop slideshow so that every
regenerated image reads as **original** — the same story and the same
product, with subtly varied composition (backgrounds, colours, text
position) — in order to pass TikTok's unoriginal-content filters. It
ingests the source slides, understands each slide both individually and
as part of the slideshow's narrative, and drives a provider-independent
transformation pipeline that produces a fresh generation for each slide
while preserving the narrative across the set.

Runs entirely on your own machine (FastAPI backend + React frontend, one
process, opened in a browser). `MIGRATION_PLAN.md` and the documents
under `docs/` hold the full architecture and decision history.

## Status

The transformation pipeline is **frozen and provider-independent**:

```
Analysis → Plan Builder → TransformationPlan → Ownership → Attention
        → GenerationSpecification → provider prompt adapter
        → Generation → Validation
```

Everything upstream of the provider prompt adapter is provider-agnostic
plain data; turning a `GenerationSpecification` into a concrete provider
request is each adapter's own job. Recent work has been a deterministic,
evidence-led remediation programme across that pipeline — subject,
product presence, geometry, canvas, ownership, manifest, and
multi-product handling — governed by two principles: **consume, don't
reconstruct** (a stage passes an authoritative signal forward rather
than re-deriving it) and **record provenance at the moment it occurs**.
It is backed by a 57-test deterministic transformation suite that runs
with **no provider calls**, plus the two upstream capability additions
described below.

**Requires provider API keys to actually generate** — an OpenAI key, and
a Google key used for both Gemini analysis and Nano Banana image
generation. See "Configuring an AI provider API key". Without keys,
import and inspection still work; generation fails with a clear error.

## Recent capability work

**Source dimensions captured at ingestion (Task 1).** Every slide's
original pixel width and height are measured and persisted at the
earliest ingestion boundary — `app/services/image_dimensions.py` does
the measuring; `source_width`, `source_height`,
`dimension_measurement_source`, and `dimension_measured_at` on the slide
record the result — so downstream canvas/aspect decisions consume a
recorded fact instead of re-measuring a file that may since have moved
or been rewritten. A four-way persisted-state classifier distinguishes
*not-attempted* / *measured* / *file-missing* / *malformed*, and
`app/services/backfill_source_dimensions.py` fills existing rows
idempotently and resumably (recorded failures are skipped unless you
explicitly opt into retrying them). The read surface prefers the
persisted value, falling back to the file only when nothing was ever
recorded.

**Per-slide multi-product isolation (Task 2).** A slide that features
several distinct products no longer aborts isolation. Each distinct
product is isolated with its own product-targeted prompt and keeps its
own reference images; a product the targeted call cannot find has only
*its own* appearance retracted, not the whole slide. The product
isolation provider interface gained an optional `raw_sink` audit
out-dict (alongside the existing `usage_sink`) so the targeting prompt
can be validated against real vision calls with a full trail of what was
asked and what came back — see "Validating targeted isolation (paid)".

Still open upstream: spatial text→product linkage (Task 3), so
multi-product slides can bind each piece of overlay text to the specific
product it belongs to.

## Configuring an AI provider API key

`app/ai_providers/config.py`'s `get_api_key()` resolves credentials in
order: the macOS Keychain first (service `creative-asset-engine`,
account `<provider>_api_key`), then a `<PROVIDER>_API_KEY` environment
variable. `backend/.env.example` documents the variable names — note
that nothing in the codebase calls `load_dotenv()`, so a `.env` file is
inert unless your shell actually exports its contents; prefer the
Keychain locally and real environment variables in CI.

```bash
# Option A: macOS Keychain (the intended mechanism for local dev)
python3 -c "import keyring; keyring.set_password('creative-asset-engine', 'openai_api_key', 'sk-...')"
python3 -c "import keyring; keyring.set_password('creative-asset-engine', 'nano_banana_api_key', '...')"

# Option B: environment variables (for CI / controlled deployments)
export OPENAI_API_KEY=sk-...
export NANO_BANANA_API_KEY=...
```

**Google's two model families share one credential by design.** Gemini
(analysis) and Nano Banana (image generation) both resolve through
`get_api_key("nano_banana")` — `gemini_adapter.py` calls it explicitly.
There is no separate `gemini` key; rotating the Nano Banana credential
rotates Gemini at the same time.

## Running it

### Backend

```bash
cd backend
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head      # creates/updates backend/data/creative_asset_engine.db
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### Frontend

For production (served by the backend, single process/port):

```bash
cd frontend
npm install
npm run build              # outputs frontend/dist, served by FastAPI at /
```

Then open **http://127.0.0.1:8000**.

For frontend development with hot reload (proxies `/api/*` to the backend
above, which must also be running):

```bash
cd frontend
npm run dev                # opens on its own port, e.g. 5173
```

## Running the tests

The deterministic suites need **no API key and no network** — they use a
fake AI provider (`tests/fakes.py`) and portable analysis snapshots, so
they never make a real provider call.

```bash
cd backend
. .venv/bin/activate

pytest tests/transformation/ -q              # 57-test frozen transformation suite
pytest tests/test_source_dimensions.py -q    # Task 1: source-dimension capture + backfill
pytest tests/test_slide_product_isolation_stage.py -q   # Task 2: multi-product isolation
pytest tests/ -q                             # everything
```

### Validating targeted isolation (paid)

`run_targeting_validation.py` checks that the product-targeted isolation
prompt actually **discriminates** between the distinct products on a real
multi-product creative, rather than latching onto the single most
visually salient product regardless of which one was requested. It makes
real, paid vision calls, so it lives outside the deterministic suite and
is run by hand in the backend venv (the one with the OpenAI key
available).

```bash
cd backend
. .venv/bin/activate
python run_targeting_validation.py \
    --image data/<real_multiproduct_creative>.jpg \
    --present "Product A exact name" "Product B exact name" \
    --absent  "A product NOT in this image" \
    --repeats 3
```

It measures cross-target region overlap (high overlap between two
different targets == not discriminating), stability across repeats, and
that an absent target returns nothing; classifies each product as
`correct` / `latched_other` / `wrong_region` / `no_product`; and writes
a full audit trail (`target`, the model's verbatim response, parsed
boxes, confidence/notes for every call) to a timestamped JSON. Optional
`--truth truth.json` (name → box in 0–1 fractions) additionally asserts
each returned box covers the right product.

**Run discipline:** this is Check 1, and it is lightweight — iterate on
the targeted prompt here using its metrics and audit trail if it fails,
rather than re-running the full end-to-end stage. Only once Check 1
passes on a real multi-product creative, run the end-to-end stage
confirmation exactly once (`run_slideshow_e2e.py --no-generate`, with the
products assigned to one slide).

## Packaging a shareable archive

```bash
./scripts/package_release.sh [output-directory]   # defaults to the repo's parent
```

Builds the file list from `git ls-files` — an **allowlist of tracked
files**, so anything gitignored (`.env`, `backend/data/`, `.venv`,
`node_modules`, generated `gen_out*` folders) is excluded by
construction rather than by remembering to name it. Staging happens in a
temp directory, the archive is written outside the repo, and
`scripts/verify_archive.py` independently re-checks both the staging
directory and the finished archive.

### What the secret scanner does and does not guarantee

`scripts/verify_archive.py` is **deliberately narrower than
[gitleaks](https://github.com/gitleaks/gitleaks)**. Do not treat a clean
run as equivalent to a clean gitleaks run.

**It does detect:**

- Forbidden *paths*, regardless of content — `.env`, `.env.local`,
  `*.db`/`*.sqlite`, `*.bak`, `backend/data/`, `.venv/`, `node_modules/`,
  `.git/`, `__pycache__/`, nested `.zip`, `settings.local.json`.
- Specific credential *shapes* in file contents, in any file, whatever
  it is named — Google `AIza…` and `AQ.…` keys, OpenAI `sk-…`/`sk-proj-…`,
  Anthropic `sk-ant-…`, AWS `AKIA…`, PEM private-key blocks, and
  `api_key`/`secret`/`token`/`password` assigned a value of 24+ chars.
- It never echoes a matched value — a scanner that prints what it found
  has leaked it again.

**It does not detect:**

- Credential formats not in the list above (Stripe, Slack, GitHub PATs,
  JWTs, database connection strings, SSH keys, `.pem`/`.p12` files by
  extension, and any provider whose key format isn't enumerated).
- High-entropy strings generically — there is **no entropy analysis**,
  which is one of gitleaks' main strengths.
- Secrets in files over 2 MB, or in any file that is not valid UTF-8
  (binaries, images, archives) — those are path-checked only.
- Anything in **git history** — it inspects the working tree/archive
  only. `git log -S` or gitleaks is still the tool for history.
- Base64/encoded, split, or otherwise obfuscated secrets.

**Why not just use gitleaks:** it is not assumed to be installed, and
silently downloading and executing a release binary is not an acceptable
default. If you install gitleaks, `package_release.sh` detects it
automatically and runs it as an **additional** layer — this scanner is a
dependency-free floor, not a replacement.

## Project layout

```
backend/
  app/
    main.py               # FastAPI entrypoint — API + serves the built frontend
    config.py             # Settings (CAE_-prefixed env; DB path, storage dir, data_dir)
    db.py                 # SQLAlchemy engine/session
    ai_providers/         # provider-agnostic capability interfaces + registry +
    │                       OpenAI / Gemini / Nano Banana adapters + config.py
    slideshow_stages/     # per-slide analysis pipeline + orchestrator
    │                       (incl. product_isolation_stage.py — Task 2)
    transformation/       # the frozen pipeline: plan, plan_builder, ownership,
    │                       attention, generation_spec, generation_request,
    │                       post_validator, adapters/ (provider prompt adapters)
    services/             # image_dimensions.py, backfill_source_dimensions.py,
    │                       slideshow_import.py, and other orchestration logic
    models/               # SQLAlchemy ORM models
    routers/              # API endpoints, one module per resource
  alembic/                # schema migrations
  providers.yaml          # AI provider/model config (which provider backs each capability)
  run_targeting_validation.py   # paid Check-1 targeting validator (Task 2)
  run_slideshow_e2e.py          # end-to-end slideshow run (needs keys)
  tests/
    transformation/       # the 57-test deterministic transformation suite
    fixtures/             # portable analysis snapshots for replay (no DB)
    fakes.py              # AI provider test doubles
  data/                   # SQLite DB + local file storage (gitignored)
frontend/
  src/                    # React app (typed api.ts client, components)
```
