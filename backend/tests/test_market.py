from __future__ import annotations

from fastapi.testclient import TestClient

LISTING = {
    "name": "Organic Onions",
    "category": "Vegetables",
    "mode": "direct",
    "price": 30,
    "quantity": "500 kg",
}


def _second_user(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/auth/signup",
        json={
            "name": "Basavaraj Patil",
            "phone": "+919731244556",
            "password": "secret123",
            "location": "Raichur",
        },
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_create_list_and_delete_listing(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    created = client.post("/api/market", json=LISTING, headers=auth_headers)
    assert created.status_code == 201, created.text
    listing = created.json()
    assert listing["seller"] == "Ramesh Gowda"
    assert listing["phone"] == "+919845011223"
    assert listing["location"] == "Mandya"
    assert listing["mode"] == "direct"
    assert listing["current_bid"] is None

    listing_id = listing["id"]
    fetched = client.get(f"/api/market/{listing_id}")
    assert fetched.status_code == 200

    listing_response = client.get("/api/market")
    assert listing_response.status_code == 200
    assert len(listing_response.json()) == 1

    deleted = client.delete(f"/api/market/{listing_id}", headers=auth_headers)
    assert deleted.status_code == 200
    assert client.get("/api/market").json() == []


def test_market_requires_auth(client: TestClient) -> None:
    assert client.post("/api/market", json=LISTING).status_code == 401


def test_listing_validation(client: TestClient, auth_headers: dict[str, str]) -> None:
    bad_price = {**LISTING, "price": -5}
    assert client.post("/api/market", json=bad_price, headers=auth_headers).status_code == 422

    bad_mode = {**LISTING, "mode": "barter"}
    assert client.post("/api/market", json=bad_mode, headers=auth_headers).status_code == 422


def test_only_owner_can_delete(client: TestClient, auth_headers: dict[str, str]) -> None:
    created = client.post("/api/market", json=LISTING, headers=auth_headers).json()
    other_headers = _second_user(client)

    forbidden = client.delete(f"/api/market/{created['id']}", headers=other_headers)
    assert forbidden.status_code == 403

    assert client.delete(f"/api/market/{created['id']}", headers=auth_headers).status_code == 200


def test_search_and_category_filters(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    client.post("/api/market", json=LISTING, headers=auth_headers)
    client.post(
        "/api/market",
        json={**LISTING, "name": "Alphonso Mangoes", "category": "Fruits"},
        headers=auth_headers,
    )

    fruits = client.get("/api/market", params={"category": "Fruits"}).json()
    assert [item["name"] for item in fruits] == ["Alphonso Mangoes"]

    search = client.get("/api/market", params={"search": "onion"}).json()
    assert [item["name"] for item in search] == ["Organic Onions"]


def test_auction_bid_flow(client: TestClient, auth_headers: dict[str, str]) -> None:
    auction = client.post(
        "/api/market",
        json={**LISTING, "mode": "auction", "price": 32},
        headers=auth_headers,
    ).json()
    assert auction["current_bid"] == 32

    url = f"/api/market/{auction['id']}/bid"

    low = client.post(url, json={"amount": 30}, headers=auth_headers)
    assert low.status_code == 400

    first = client.post(url, json={"amount": 35}, headers=auth_headers)
    assert first.status_code == 201, first.text
    assert first.json()["amount"] == 35

    other_headers = _second_user(client)
    second = client.post(url, json={"amount": 40}, headers=other_headers)
    assert second.status_code == 201
    assert second.json()["bidder_name"] == "Basavaraj Patil"

    listing = client.get(f"/api/market/{auction['id']}").json()
    assert listing["current_bid"] == 40

    bids = client.get(f"{url}s").json()
    assert [bid["amount"] for bid in bids] == [40, 35]

    # Bidding on a direct listing is rejected.
    direct = client.post("/api/market", json=LISTING, headers=auth_headers).json()
    response = client.post(
        f"/api/market/{direct['id']}/bid", json={"amount": 10}, headers=auth_headers
    )
    assert response.status_code == 400


def test_bid_requires_auth(client: TestClient, auth_headers: dict[str, str]) -> None:
    auction = client.post(
        "/api/market",
        json={**LISTING, "mode": "auction", "price": 32},
        headers=auth_headers,
    ).json()
    response = client.post(f"/api/market/{auction['id']}/bid", json={"amount": 35})
    assert response.status_code == 401


def test_missing_listing_returns_404(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    assert client.get("/api/market/does-not-exist").status_code == 404
    response = client.delete("/api/market/does-not-exist", headers=auth_headers)
    assert response.status_code == 404
