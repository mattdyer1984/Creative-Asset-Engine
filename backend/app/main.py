"""
Application entrypoint.

Serves the JSON API under /api/* and the built frontend SPA (Vite's static
output) at /. Both run as a single local process (`uvicorn app.main:app`),
per the architecture plan (§2, §2.1) — no separate frontend dev server is
required to use the app, though one can still be run separately during
frontend development.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.ai_providers import registry as ai_provider_registry
from app.config import settings
from app.routers import products, projects, slideshows

settings.ensure_directories()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Explicit, documented trigger point for AIProviderRegistry
    # construction (see app/ai_providers/registry.py's module __getattr__)
    # - app startup, not merely importing some module that happens to
    # import it. Discarded: every Stage still gets the same cached
    # instance via its own `from app.ai_providers.registry import
    # default_registry`, this call just guarantees construction (and any
    # providers.yaml error) surfaces here rather than being left to
    # whichever import happens to touch it first.
    _ = ai_provider_registry.default_registry
    yield


app = FastAPI(title="Creative Asset Engine", version="0.1.0", lifespan=lifespan)

app.include_router(projects.router)
app.include_router(products.router)
app.include_router(slideshows.router)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


# Serve the built frontend (frontend/dist) as static files at the root.
# html=True makes it fall back to index.html for client-side routing.
FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"

if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="frontend")
else:
    @app.get("/")
    def frontend_not_built() -> dict[str, str]:
        return {
            "message": (
                "Frontend build not found. Run `npm run build` in the "
                "frontend/ directory, or use the frontend dev server "
                "during development."
            )
        }
