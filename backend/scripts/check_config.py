"""Check that the backend configuration is complete before starting the API.

Usage (from anywhere)::

    python backend/scripts/check_config.py
    python backend/scripts/check_config.py --require-supabase
    python backend/scripts/check_config.py --check-gemini

Without ``--require-supabase`` the script exits 0 when the API can serve using
the local SQLite development database (DATABASE_MODE=auto and no Supabase
credentials). Secret values are never printed - only a masked fingerprint.
``--check-gemini`` makes one network call to confirm the key can reach Gemini.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent

# Make ``app`` importable when the script is run directly.
sys.path.insert(0, str(BACKEND_DIR))

from app.config import settings  # noqa: E402

OK = "  OK   "
MISSING = " MISSING"
WARN = " WARN  "
INFO = " INFO  "


def mask(value: str) -> str:
    value = value.strip()
    if not value:
        return "(empty)"
    if len(value) <= 10:
        return "*" * len(value)
    return f"{value[:6]}...{value[-4:]} (len={len(value)})"


def report(label: str, value: str, required: bool, hint: str) -> bool:
    present = bool(value.strip())
    status = OK if present else (MISSING if required else WARN)
    print(f"[{status}] {label:<22} {mask(value)}")
    if not present:
        print(f"           -> {hint}")
    return present


def check_gemini() -> bool:
    """Confirm the key is valid and the Gemini API is enabled for its project."""
    key = settings.gemini_api_key.strip()
    if not key:
        print("[ FAIL  ] Gemini API key is empty - nothing to check.")
        return False

    try:
        from google import genai

        client = genai.Client(api_key=key)
        models = list(client.models.list())
    except Exception as exc:  # noqa: BLE001 - report, never crash
        message = str(exc)
        project_match = re.search(r"projects/(\d+)", message)
        project = project_match.group(1) if project_match else None
        print(f"[ FAIL  ] Gemini API check failed: {message[:300]}")
        print("           -> Enable the Gemini API (Generative Language API) for the key's project:")
        print(
            "              https://console.cloud.google.com/apis/library/"
            "generativelanguage.googleapis.com"
            + (f"?project={project}" if project else "")
        )
        print("           -> Or create a fresh key: https://aistudio.google.com/apikey")
        return False

    print(f"[{OK}] Gemini API key   reachable ({len(models)} models available)")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Check the AgriTech backend configuration.")
    parser.add_argument(
        "--require-supabase",
        action="store_true",
        help="Fail unless SUPABASE_URL and SUPABASE_SERVICE_KEY are set "
        "(use before deploying).",
    )
    parser.add_argument(
        "--check-gemini",
        action="store_true",
        help="Make one network call to verify GEMINI_API_KEY and the Gemini API.",
    )
    args = parser.parse_args()

    try:
        mode = settings.resolved_database_mode
    except RuntimeError as exc:
        print(f"[ FAIL  ] {exc}")
        return 1

    supabase_required = args.require_supabase or mode == "supabase"

    print(f"Config file:   {BACKEND_DIR / '.env'}")
    print(f"Database mode: {settings.database_mode} -> {mode}")
    if mode == "local":
        print(f"Local file:    {settings.local_db_path}")
    print()

    url_ok = report(
        "SUPABASE_URL",
        settings.supabase_url,
        required=supabase_required,
        hint="Supabase Dashboard -> Project Settings -> API -> Project URL "
        "(https://<ref>.supabase.co)",
    )
    key_ok = report(
        "SUPABASE_SERVICE_KEY",
        settings.supabase_service_key,
        required=supabase_required,
        hint="Project Settings -> API -> service_role key (or the new sb_secret_... key)",
    )
    report(
        "SUPABASE_DB_URL",
        settings.supabase_db_url,
        required=False,
        hint="Only needed by scripts/init_db.py: Database -> Connection string -> URI",
    )
    report(
        "GEMINI_API_KEY",
        settings.gemini_api_key,
        required=False,
        hint="Needed for real AI diagnoses, or set PLANT_DOCTOR_MOCK=true",
    )

    if args.check_gemini:
        print()
        if not check_gemini():
            return 1

    print()
    problems: list[str] = []

    url = settings.supabase_url.strip()
    if url and not url.startswith("https://"):
        problems.append("SUPABASE_URL must start with https://")
    if url and not url.rstrip("/").endswith(".supabase.co"):
        problems.append(
            "SUPABASE_URL usually ends with .supabase.co - double-check it is the Project URL"
        )

    key = settings.supabase_service_key.strip()
    if key and not (key.startswith("eyJ") or key.startswith("sb_secret_")):
        problems.append(
            "SUPABASE_SERVICE_KEY looks wrong (expected eyJ... or sb_secret_...); "
            "the anon/publishable key will not work"
        )

    db_url = settings.supabase_db_url.strip()
    if db_url and not db_url.startswith(("postgresql://", "postgres://")):
        problems.append("SUPABASE_DB_URL must start with postgresql:// or postgres://")

    if settings.jwt_secret.startswith("dev-only-secret"):
        problems.append("JWT_SECRET is still the development default")

    for problem in problems:
        print(f"[ WARN  ] {problem}")

    print()
    if url_ok and key_ok:
        print("Supabase configuration looks complete. Start the server with:")
        print("  python backend/run.py")
        if not db_url:
            print("Tables not created yet? Set SUPABASE_DB_URL, then run scripts/init_db.py.")
        return 0

    if mode == "local" and not args.require_supabase:
        print("Supabase is not configured, so the API will use the local SQLite")
        print("development database. The app is fully usable right now:")
        print("  python backend/run.py")
        print()
        print("Data is stored in:")
        print(f"  {settings.local_db_path}")
        print("Delete that file to reset the demo database.")
        print()
        print("Move to Supabase whenever you are ready:")
        print("  1. Create a free project at https://supabase.com/dashboard")
        print("  2. Fill SUPABASE_URL and SUPABASE_SERVICE_KEY in backend/.env")
        print("  3. Fill SUPABASE_DB_URL and run: python backend/scripts/init_db.py")
        return 0

    print("API configuration is INCOMPLETE for Supabase mode.")
    print("Database routes will return HTTP 503 until SUPABASE_URL and")
    print("SUPABASE_SERVICE_KEY are filled in backend/.env.")
    print()
    print("Steps:")
    print("  1. Create a free project at https://supabase.com/dashboard")
    print("  2. Copy the Project URL and service_role (or sb_secret_) key into backend/.env")
    print("  3. Copy the Postgres URI into SUPABASE_DB_URL (for the schema script)")
    print("  4. Run: python backend/scripts/init_db.py")
    print("  5. Run: python backend/run.py")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
