"""Application configuration loaded from environment variables / .env files."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    """Runtime settings for the AgriTech API.

    Values are read from (in order) real environment variables and the
    ``backend/.env`` / project-root ``.env`` files.
    """

    model_config = SettingsConfigDict(
        env_file=(BACKEND_DIR / ".env", PROJECT_DIR / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- App ---------------------------------------------------------------
    app_name: str = "02build AgriTech API"
    app_version: str = "1.0.0"
    environment: str = "development"
    api_prefix: str = "/api"
    serve_frontend: bool = True

    # --- Supabase ----------------------------------------------------------
    supabase_url: str = ""
    supabase_service_key: str = ""
    supabase_anon_key: str = ""
    # Optional direct Postgres connection string (used only by scripts/init_db.py)
    supabase_db_url: str = ""

    # --- Database selection ------------------------------------------------
    #   auto     -> Supabase when configured, otherwise local SQLite (dev only)
    #   supabase -> require Supabase; DB routes return 503 when it is missing
    #   local    -> always use the local SQLite development database
    database_mode: str = "auto"
    local_db_path: str = str(BACKEND_DIR / ".local" / "agritech.db")

    # --- Auth --------------------------------------------------------------
    jwt_secret: str = "dev-only-secret-change-me-before-prod!"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7  # 7 days

    # --- CORS --------------------------------------------------------------
    # Comma separated list of allowed origins, or "*" for any.
    cors_origins: str = "*"

    # --- AI Plant Doctor ---------------------------------------------------
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    gemini_timeout_seconds: int = 45
    plant_doctor_mock: bool = False
    max_image_bytes: int = 8 * 1024 * 1024  # 8 MB

    @property
    def cors_origin_list(self) -> list[str]:
        raw = self.cors_origins.strip()
        if not raw or raw == "*":
            return ["*"]
        return [origin.strip() for origin in raw.split(",") if origin.strip()]

    @property
    def supabase_configured(self) -> bool:
        return bool(self.supabase_url.strip() and self.supabase_service_key.strip())

    @property
    def resolved_database_mode(self) -> str:
        """Return ``"supabase"`` or ``"local"`` for the current configuration."""
        mode = (self.database_mode or "auto").strip().lower()
        if mode not in {"auto", "supabase", "local"}:
            raise RuntimeError(
                f"Invalid DATABASE_MODE={self.database_mode!r}. "
                "Use 'auto', 'supabase' or 'local'."
            )
        if mode == "auto":
            if self.supabase_configured:
                return "supabase"
            # Never silently fall back to a local file in production.
            return "local" if not self.is_production else "supabase"
        return mode

    @property
    def using_local_db(self) -> bool:
        return self.resolved_database_mode == "local"

    @property
    def plant_doctor_configured(self) -> bool:
        return bool(self.gemini_api_key.strip())

    @property
    def is_production(self) -> bool:
        return self.environment.strip().lower() in {"production", "prod"}

    @property
    def using_default_jwt_secret(self) -> bool:
        return self.jwt_secret == "dev-only-secret-change-me-before-prod!"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
