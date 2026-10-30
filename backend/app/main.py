"""FastAPI application entry point."""

from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

# Allow both ``uvicorn app.main:app`` and ``python app/main.py``. When the file
# is executed as a script there is no parent package, so give it one (and make
# the ``app`` package importable) before the relative imports below run.
if __package__ in {None, ""}:  # pragma: no cover - only true for direct execution
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    __package__ = "app"

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from postgrest.exceptions import APIError

from . import __version__
from .config import PROJECT_DIR, settings
from .database import DatabaseNotConfigured, database_info, get_supabase
from .routers import auth, machinery, market, plant_doctor, scans

logging.basicConfig(
    level=logging.DEBUG if not settings.is_production else logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("agritech")


@asynccontextmanager
async def lifespan(_: FastAPI):
    mode = settings.resolved_database_mode

    if mode == "local":
        if settings.is_production:
            raise RuntimeError(
                "DATABASE_MODE resolves to 'local' but ENVIRONMENT=production. "
                "Set SUPABASE_URL and SUPABASE_SERVICE_KEY."
            )
        logger.warning(
            "Supabase is not configured; using the local SQLite development "
            "database at %s. Data will NOT be stored in Supabase.",
            settings.local_db_path,
        )
    elif not settings.supabase_configured:
        logger.warning(
            "Supabase is not configured. Set SUPABASE_URL and SUPABASE_SERVICE_KEY "
            "in backend/.env. API calls that need the database will return 503."
        )

    if settings.is_production and settings.using_default_jwt_secret:
        raise RuntimeError(
            "JWT_SECRET must be changed before running with ENVIRONMENT=production."
        )
    if not settings.plant_doctor_configured:
        if settings.plant_doctor_mock:
            logger.warning(
                "GEMINI_API_KEY is not set; AI Plant Doctor serves demo reports "
                "because PLANT_DOCTOR_MOCK=true."
            )
        else:
            logger.warning(
                "GEMINI_API_KEY is not set; AI Plant Doctor will return 503 unless "
                "PLANT_DOCTOR_MOCK=true."
            )
    yield


app = FastAPI(
    title=settings.app_name,
    version=__version__,
    description=(
        "Backend for the 02build AgriTech frontend: phone/password auth, "
        "e-market auctions, machinery rentals, and Gemini powered plant "
        "disease diagnosis. Data is stored in Supabase (Postgres)."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


@app.exception_handler(DatabaseNotConfigured)
async def database_not_configured_handler(
    _: Request, exc: DatabaseNotConfigured
) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.exception_handler(APIError)
async def postgrest_error_handler(_: Request, exc: APIError) -> JSONResponse:
    code = getattr(exc, "code", None)
    message = getattr(exc, "message", None) or str(exc)

    if code == "23505":
        return JSONResponse(
            status_code=409,
            content={"detail": "A record with these values already exists."},
        )
    if code in {"23503", "23514"}:
        return JSONResponse(
            status_code=400,
            content={"detail": "The request conflicts with the database schema."},
        )

    logger.exception("Supabase request failed: %s", message)
    detail = message if not settings.is_production else "Database request failed."
    return JSONResponse(status_code=500, content={"detail": detail})


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

app.include_router(auth.router, prefix=settings.api_prefix)
app.include_router(market.router, prefix=settings.api_prefix)
app.include_router(machinery.router, prefix=settings.api_prefix)
app.include_router(plant_doctor.router, prefix=settings.api_prefix)
app.include_router(scans.router, prefix=settings.api_prefix)


@app.get(f"{settings.api_prefix}/health", tags=["System"], summary="Service health")
def health() -> dict:
    info = database_info()
    db_reachable: bool | None = None
    db_error: str | None = None

    if info["configured"]:
        try:
            get_supabase().table("market_listings").select("id").limit(1).execute()
            db_reachable = True
        except DatabaseNotConfigured:
            db_reachable = False
            db_error = "Database is not configured."
        except Exception as exc:  # noqa: BLE001 - health must never raise
            db_reachable = False
            db_error = "Database is unreachable." if settings.is_production else str(exc)

    healthy = bool(db_reachable)
    return {
        "status": "ok" if healthy else "degraded",
        "version": __version__,
        "environment": settings.environment,
        "database": {
            **info,
            "reachable": db_reachable,
            "error": db_error,
        },
        "plant_doctor": {
            "configured": settings.plant_doctor_configured,
            "mock": settings.plant_doctor_mock,
            "model": settings.gemini_model,
        },
    }


# ---------------------------------------------------------------------------
# Optional: serve the static frontend from the same origin (default on)
# ---------------------------------------------------------------------------

_INDEX_FILE = PROJECT_DIR / "index.html"
_SCRIPT_FILE = PROJECT_DIR / "script.js"

if settings.serve_frontend and _INDEX_FILE.exists():

    @app.get("/", include_in_schema=False)
    def serve_index() -> FileResponse:
        return FileResponse(_INDEX_FILE, media_type="text/html")

    @app.get("/script.js", include_in_schema=False)
    def serve_frontend_script() -> FileResponse:
        return FileResponse(_SCRIPT_FILE, media_type="application/javascript")

else:

    @app.get("/", include_in_schema=False)
    def api_info() -> dict:
        return {
            "name": settings.app_name,
            "version": __version__,
            "docs": "/docs",
            "health": f"{settings.api_prefix}/health",
        }


if __name__ == "__main__":  # pragma: no cover - manual smoke run
    import uvicorn

    # Pass the app object (not an import string) so this works regardless of
    # the current working directory. Use ``python run.py`` for auto-reload.
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")
