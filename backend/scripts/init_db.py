"""Apply the Supabase SQL schema (and optional seed data) to a Postgres database.

Usage (from the backend/ directory):

    python scripts/init_db.py
    python scripts/init_db.py --no-seed
    python scripts/init_db.py --url "postgresql://postgres:...@db.xxx.supabase.co:5432/postgres"

The connection string is read from --url, then SUPABASE_DB_URL, then
DATABASE_URL (backend/.env is loaded automatically).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
SQL_DIR = BACKEND_DIR / "sql"

# Make ``app`` importable when the script is run directly.
sys.path.insert(0, str(BACKEND_DIR))

from app.config import settings  # noqa: E402


def _ensure_ssl(url: str) -> str:
    if "sslmode=" in url:
        return url
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}sslmode=require"


def apply_sql(url: str, include_seed: bool) -> None:
    try:
        import psycopg
    except ImportError:
        raise SystemExit(
            "psycopg is required. Install it with: pip install -r requirements.txt"
        )

    files = sorted(SQL_DIR.glob("*.sql"))
    if not include_seed:
        files = [path for path in files if "seed" not in path.name]

    if not files:
        raise SystemExit(f"No SQL files found in {SQL_DIR}")

    print("Connecting to Postgres...")
    with psycopg.connect(_ensure_ssl(url), connect_timeout=20) as connection:
        with connection.cursor() as cursor:
            for path in files:
                print(f"  applying {path.name} ...", end=" ")
                cursor.execute(path.read_text(encoding="utf-8"))
                print("ok")
        connection.commit()

    print("Done. Supabase schema is ready.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply the AgriTech Supabase schema.")
    parser.add_argument("--url", help="Postgres connection string (overrides env vars)")
    parser.add_argument("--no-seed", action="store_true", help="Skip 002_seed.sql")
    args = parser.parse_args()

    url = args.url or settings.supabase_db_url or ""
    if not url.strip():
        raise SystemExit(
            "No database URL found. Set SUPABASE_DB_URL in backend/.env or pass --url.\n"
            "Get it from Supabase: Project Settings -> Database -> Connection string -> URI."
        )

    apply_sql(url.strip(), include_seed=not args.no_seed)


if __name__ == "__main__":
    main()
