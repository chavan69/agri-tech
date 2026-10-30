from __future__ import annotations

from fastapi.testclient import TestClient


def test_health_reports_local_database_by_default(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200

    body = response.json()
    assert body["database"]["provider"] == "local-sqlite"
    assert body["database"]["configured"] is True
    assert body["database"]["reachable"] is True
    assert body["status"] == "ok"


def test_health_is_degraded_in_supabase_mode_without_credentials(
    client: TestClient, monkeypatch
) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "database_mode", "supabase")

    body = client.get("/api/health").json()
    assert body["database"]["provider"] == "supabase"
    assert body["database"]["configured"] is False
    assert body["status"] == "degraded"


def test_openapi_schema_is_generated(client: TestClient) -> None:
    response = client.get("/openapi.json")
    assert response.status_code == 200

    paths = response.json()["paths"]
    for path in (
        "/api/auth/signup",
        "/api/auth/login",
        "/api/auth/me",
        "/api/market",
        "/api/market/{listing_id}/bid",
        "/api/machinery",
        "/api/plant-doctor/analyze",
        "/api/scans",
    ):
        assert path in paths


def test_frontend_is_served(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "02build AgriTech" in response.text

    script = client.get("/script.js")
    assert script.status_code == 200
    assert "API_BASE" in script.text


def test_database_endpoints_return_503_without_config(
    client: TestClient, monkeypatch
) -> None:
    # The fixture normally replaces the Supabase client; restore the real
    # behaviour of a missing configuration for this test.
    from app.database import DatabaseNotConfigured

    from app.routers import market

    def raise_not_configured():
        raise DatabaseNotConfigured("Supabase is not configured for this test.")

    monkeypatch.setattr(market, "get_supabase", raise_not_configured)

    response = client.get("/api/market")
    assert response.status_code == 503
    assert "not configured" in response.json()["detail"].lower()
