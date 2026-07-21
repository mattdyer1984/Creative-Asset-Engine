# Creative Asset Engine

Local application that analyses marketing images and produces a
**Creative Blueprint**: Product Lock Profile, Creative Fingerprint,
Marketing Analysis, OCR, and a provider-neutral Recreation Prompt.

Runs entirely on your own machine as a local web app (FastAPI backend +
React frontend, one process, opened in a browser). See
`docs/implementation-plan.md` (or the plan shared in chat) for the full
architecture.

## Status

**M7 — Creative Blueprint assembly + unified workflow.** The pipeline is
now an implementation detail: the UI presents one assembled Creative
Blueprint per creative (product spec, fingerprint, marketing analysis,
OCR, recreation prompt, all formatted - no raw JSON), not six separate
per-stage views. Each section has its own "rerun this part" action; a
top-level "Analyze / Re-run All" triggers the whole pipeline. A failure
in any one stage shows exactly what failed and why, both immediately
after triggering it and on any later visit - backed by
`last_failed_stage`/`last_failed_stage_error` on the Blueprint itself,
since a stage that fails a prerequisite check correctly creates no
`AnalysisRun`, so that information has nowhere else reliable to live.

**Requires an OpenAI API key to actually run analysis** — see
"Configuring an AI provider API key" below. Without one, Import/Products/
list/view still work; clicking Analyze will fail with a clear error.

### API endpoints so far

- `GET /api/projects`, `POST /api/projects`, `GET /api/projects/{id}`
- `POST /api/products`, `GET /api/products` (optional `?project_id=`), `GET /api/products/{id}`
- `GET /api/products/{id}/reference-images` — current reference image(s), if any
- `GET /api/products/{id}/reference-images/{id}/file` — serves a reference image
- `GET /api/products/{id}/lock-profile` — current Product Lock Profile, if any
- `POST /api/creatives/import` — multipart form: one or more `files`, optional `project_id`
- `GET /api/creatives` — optional `?project_id=` filter
- `GET /api/creatives/{id}`
- `GET /api/creatives/{id}/file` — serves the original image
- `POST /api/creatives/{id}/assign-product` — `{"product_id": "..."}` or `{"product_id": null}` to unassign
- `GET /api/creatives/{id}/blueprint` — the assembled Creative Blueprint (everything, in one call)
- `POST /api/creatives/{id}/analyze` — runs the full Stage pipeline (all 6 stages), returns the assembled Blueprint
- `POST /api/creatives/{id}/stages/{stage_name}/rerun` — reruns exactly one stage, returns the assembled Blueprint
- `GET /api/creatives/{id}/ocr-result` — the current OCR result, if any
- `GET /api/creatives/{id}/creative-fingerprint` — the current Creative Fingerprint, if any
- `GET /api/creatives/{id}/marketing-analysis` — the current Marketing Analysis, if any
- `GET /api/creatives/{id}/recreation-prompt` — the current Recreation Prompt, if any
- `GET /api/creatives/{id}/analysis-runs` — full history of every analysis attempt (traceability)

### Configuring an AI provider API key

The app looks up API keys via the macOS Keychain first, then falls back
to an environment variable — see `app/ai_providers/config.py`.

```bash
# Option A: macOS Keychain (the intended mechanism)
python3 -c "import keyring; keyring.set_password('creative-asset-engine', 'openai_api_key', 'sk-...')"

# Option B: environment variable (simpler for local dev/testing)
export OPENAI_API_KEY=sk-...
```

### Running the tests

```bash
cd backend
source .venv/bin/activate
pytest tests/ -v
```

Tests use a fake AI provider (`tests/fakes.py`) and a mocked OpenAI SDK
client (`tests/test_openai_adapter.py`) — no API key or network access
is required to run the suite.

## Running it

### Backend

```bash
cd backend
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head      # creates backend/data/creative_asset_engine.db
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

## Project layout

```
backend/
  app/
    main.py        # FastAPI entrypoint - API + serves built frontend
    config.py       # settings (DB path, storage dir)
    db.py           # SQLAlchemy engine/session
    storage.py       # local filesystem storage (storage/creatives/, storage/products/)
    orchestrator.py   # AnalysisOrchestrator - coordinates the Stage pipeline
    domain/          # plain domain objects (MarketingCreative)
    importers/        # ImportProvider interface + registry + LocalFileImporter
    ai_providers/       # AI capability interfaces + registry + OpenAI adapters
    stages/              # AnalysisStage interface + STAGE_PIPELINE (complete:
    │                      OCR, Product Isolation, Product Lock Profile,
    │                      Creative Fingerprint, Marketing Analysis,
    │                      Recreation Prompt)
    services/          # orchestration logic (creative_import,
    │                    creative_blueprint - assembles all 6 artifacts
    │                    into one response for the frontend)
    models/         # ORM models - full data model from plan §7 (Project,
    │                  Creative, CreativeBlueprint, AnalysisRun, OCRResult,
    │                  Product, ProductReferenceImage, ProductLockProfile,
    │                  CreativeFingerprint, MarketingAnalysis, RecreationPrompt)
    schemas.py       # Pydantic API request/response schemas
    routers/         # API endpoints, one module per resource (incl. products.py)
  alembic/          # schema migrations
  providers.yaml    # AI provider/model config (plan §4.2)
  tests/            # pytest suite - fakes.py provides test doubles
  data/              # SQLite DB + local file storage (gitignored)
frontend/
  src/
    App.tsx                     # top-level layout
    api.ts                        # typed API client
    components/
      ImportPanel.tsx             # file picker + optional project select
      CreativeGrid.tsx             # thumbnails, status badges, Analyze action,
      │                              "View Blueprint" button
      CreativeBlueprintModal.tsx    # the single assembled Creative Blueprint
      │                              view (plan §1, §11 M7) - formatted fields,
      │                              not raw JSON; per-section rerun actions
      ProductManager.tsx            # Products list + create form + analysis view
      ProductPicker.tsx              # per-creative new/existing product assignment
```
