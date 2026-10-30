from __future__ import annotations

import os
import tempfile
from pathlib import Path

os.environ.setdefault("ENVIRONMENT", "test")
# Keep the suite deterministic even when backend/.env has real credentials:
# never call Supabase or Gemini during tests.
os.environ["DATABASE_MODE"] = "local"
os.environ["SUPABASE_URL"] = ""
os.environ["SUPABASE_SERVICE_KEY"] = ""
os.environ["GEMINI_API_KEY"] = ""
# Never write the local development database into the repository during tests.
os.environ.setdefault(
    "LOCAL_DB_PATH",
    str(Path(tempfile.mkdtemp(prefix="agritech-test-")) / "agritech.db"),
)

import pytest
from fastapi.testclient import TestClient

from app import dependencies as dependencies_module
from app import main as main_module
from app.config import settings
from app.routers import auth, machinery, market, plant_doctor, scans
from tests.fake_supabase import FakeSupabase

PATCHED_MODULES = (
    dependencies_module,
    main_module,
    auth,
    market,
    machinery,
    plant_doctor,
    scans,
)


@pytest.fixture()
def fake_db() -> FakeSupabase:
    return FakeSupabase()


@pytest.fixture()
def client(fake_db: FakeSupabase, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    for module in PATCHED_MODULES:
        monkeypatch.setattr(module, "get_supabase", lambda: fake_db)

    monkeypatch.setattr(settings, "serve_frontend", False)

    with TestClient(main_module.app) as test_client:
        yield test_client


@pytest.fixture()
def auth_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/auth/signup",
        json={
            "name": "Ramesh Gowda",
            "phone": "+91 98450 11223",
            "password": "secret123",
            "location": "Mandya",
            "role": "Farmer & Seller",
        },
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}
