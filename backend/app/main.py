"""
Application entrypoint.

Serves the JSON API under /api/* and the built frontend SPA (Vite's static
output) at /. Both run as a single local process (`uvicorn app.main:app`),
per the architecture plan (§2, §2.1) — no separate frontend dev server is
required to use the app, though one can still be run separately during
frontend development.
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.routers import creatives, products, projects

settings.ensure_directories()

app = FastAPI(title="Creative Asset Engine", version="0.1.0")

app.include_router(projects.router)
app.include_router(products.router)
app.include_router(creatives.router)


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
