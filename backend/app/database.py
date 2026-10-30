"""Database client access (Supabase, or the local SQLite development store).

The API talks to Supabase's PostgREST endpoint with the *service role* key so
that it can manage rows on behalf of authenticated users. The service role key
must never be shipped to the browser.

When Supabase is not configured yet, development runs use a local SQLite file
that exposes the same query-builder surface (see :mod:`app.local_db`), so the
frontend works end to end without any cloud credentials. Set ``DATABASE_MODE``
to ``supabase`` to disable the fallback.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from supabase import create_client

from .config import settings


class DatabaseNotConfigured(RuntimeError):
    """Raised when Supabase credentials are missing from the environment."""


def database_info() -> dict[str, Any]:
    """Describe the database the API will use (never includes secrets)."""
    mode = settings.resolved_database_mode
    if mode == "local":
        return {
            "provider": "local-sqlite",
            "mode": mode,
            "configured": True,
            "path": settings.local_db_path,
        }
    return {
        "provider": "supabase",
        "mode": mode,
        "configured": settings.supabase_configured,
        "url": settings.supabase_url.strip().rstrip("/") or None,
    }


@lru_cache(maxsize=1)
def get_supabase() -> Any:
    """Return the configured database client (cached for the process)."""
    if settings.resolved_database_mode == "local":
        from .local_db import LocalSupabase

        return LocalSupabase(settings.local_db_path)

    if not settings.supabase_configured:
        raise DatabaseNotConfigured(
            "Supabase is not configured. Set SUPABASE_URL and "
            "SUPABASE_SERVICE_KEY in backend/.env (see backend/.env.example), "
            "or use DATABASE_MODE=local for offline development."
        )

    return create_client(
        settings.supabase_url.strip().rstrip("/"),
        settings.supabase_service_key.strip(),
    )
