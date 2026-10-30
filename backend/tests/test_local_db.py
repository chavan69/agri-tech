from __future__ import annotations

import base64

import pytest
from fastapi.testclient import TestClient
from postgrest.exceptions import APIError

from app import dependencies as dependencies_module
from app import main as main_module
from app.config import settings
from app.local_db import LocalSupabase
from app.routers import auth, machinery, market, plant_doctor, scans

PATCHED_MODULES = (
    dependencies_module,
    main_module,
    auth,
    market,
    machinery,
    plant_doctor,
    scans,
)

IMAGE_BASE64 = base64.b64encode(b"\xff\xd8\xff\xe0" + b"\x00" * 64).decode()


@pytest.fixture()
def local_db(tmp_path) -> LocalSupabase:
    return LocalSupabase(tmp_path / "agritech.db")


@pytest.fixture()
def local_client(local_db: LocalSupabase, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    for module in PATCHED_MODULES:
        monkeypatch.setattr(module, "get_supabase", lambda: local_db)
    monkeypatch.setattr(settings, "serve_frontend", False)
    monkeypatch.setattr(settings, "plant_doctor_mock", True)

    with TestClient(main_module.app) as test_client:
        yield test_client


def _signup(client: TestClient, name: str, phone: str) -> dict[str, str]:
    response = client.post(
        "/api/auth/signup",
        json={
            "name": name,
            "phone": phone,
            "password": "secret123",
            "location": "Mandya",
            "role": "Farmer & Seller",
        },
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_seed_data_filters_and_projection(local_db: LocalSupabase) -> None:
    rows = local_db.table("market_listings").select("*").execute().data
    assert len(rows) == 2

    auctions = (
        local_db.table("market_listings")
        .select("*")
        .eq("mode", "auction")
        .execute()
        .data
    )
    assert [row["name"] for row in auctions] == ["Organic Roma Tomatoes"]

    search = (
        local_db.table("market_listings")
        .select("name")
        .or_("name.ilike.%rice%,seller.ilike.%nobody%")
        .execute()
        .data
    )
    assert search == [{"name": "Premium Sona Masoori Rice"}]

    newest_first = (
        local_db.table("market_listings").select("name").order("created_at", desc=True).execute().data
    )
    assert newest_first[0]["name"] == "Premium Sona Masoori Rice"


def test_duplicate_phone_raises_postgrest_conflict(local_db: LocalSupabase) -> None:
    local_db.table("users").insert(
        {"name": "A", "phone": "+919999000011", "password_hash": "x"}
    ).execute()

    with pytest.raises(APIError) as excinfo:
        local_db.table("users").insert(
            {"name": "B", "phone": "+919999000011", "password_hash": "y"}
        ).execute()

    assert excinfo.value.code == "23505"


def test_data_survives_a_restart(tmp_path) -> None:
    path = tmp_path / "persistent.db"
    first = LocalSupabase(path)
    first.table("users").insert(
        {"name": "Persisted", "phone": "+919999000022", "password_hash": "x"}
    ).execute()

    second = LocalSupabase(path)
    rows = second.table("users").select("*").eq("phone", "+919999000022").execute().data
    assert rows and rows[0]["name"] == "Persisted"
    # Seeding is idempotent.
    assert len(second.table("market_listings").select("id").execute().data) == 2


def test_full_api_flow_on_local_database(local_client: TestClient) -> None:
    owner = _signup(local_client, "Ramesh Gowda", "+91 98450 11223")
    bidder = _signup(local_client, "Basavaraj Patil", "+91 97312 44556")

    listing = local_client.post(
        "/api/market",
        headers=owner,
        json={
            "name": "Fresh Tomatoes",
            "category": "Vegetables",
            "mode": "auction",
            "price": 100,
            "quantity": "50 kg",
        },
    )
    assert listing.status_code == 201, listing.text
    listing_id = listing.json()["id"]
    assert listing.json()["current_bid"] == 100

    bid = local_client.post(
        f"/api/market/{listing_id}/bid", headers=bidder, json={"amount": 150}
    )
    assert bid.status_code == 201, bid.text
    assert bid.json()["amount"] == 150

    too_low = local_client.post(
        f"/api/market/{listing_id}/bid", headers=bidder, json={"amount": 120}
    )
    assert too_low.status_code == 400

    bids = local_client.get(f"/api/market/{listing_id}/bids")
    assert bids.status_code == 200
    assert [row["amount"] for row in bids.json()] == [150.0]

    machinery = local_client.post(
        "/api/machinery",
        headers=owner,
        json={"title": "Rotavator", "type": "available", "rate": "500 / hour"},
    )
    assert machinery.status_code == 201, machinery.text

    analysis = local_client.post(
        "/api/plant-doctor/analyze",
        headers=owner,
        json={"imageBase64": IMAGE_BASE64, "mimeType": "image/jpeg"},
    )
    assert analysis.status_code == 201, analysis.text
    assert analysis.json()["report"]["provider"] == "mock"

    history = local_client.get("/api/scans", headers=owner)
    assert history.status_code == 200
    assert len(history.json()) == 1
    scan_id = history.json()[0]["id"]

    deleted_scan = local_client.delete(f"/api/scans/{scan_id}", headers=owner)
    assert deleted_scan.status_code == 200

    profile = local_client.get("/api/auth/me", headers=owner)
    assert profile.status_code == 200
    assert profile.json()["phone"] == "+919845011223"

    deleted_listing = local_client.delete(f"/api/market/{listing_id}", headers=owner)
    assert deleted_listing.status_code == 200
    # Bids cascade with the listing.
    assert local_client.get(f"/api/market/{listing_id}/bids").status_code == 404
