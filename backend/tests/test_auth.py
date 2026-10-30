from __future__ import annotations

from fastapi.testclient import TestClient

SIGNUP = {
    "name": "Ramesh Gowda",
    "phone": "+91 98450 11223",
    "password": "secret123",
    "location": "Mandya",
    "role": "Farmer & Seller",
}


def test_signup_returns_token_and_profile(client: TestClient) -> None:
    response = client.post("/api/auth/signup", json=SIGNUP)
    assert response.status_code == 201, response.text

    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] > 0
    assert body["access_token"]
    assert body["user"]["name"] == "Ramesh Gowda"
    # Phone is normalized when stored.
    assert body["user"]["phone"] == "+919845011223"
    assert "password_hash" not in body["user"]


def test_signup_duplicate_phone_conflicts(client: TestClient) -> None:
    assert client.post("/api/auth/signup", json=SIGNUP).status_code == 201
    response = client.post("/api/auth/signup", json=SIGNUP)
    assert response.status_code == 409


def test_signup_rejects_short_password_and_bad_phone(client: TestClient) -> None:
    short_password = {**SIGNUP, "password": "123"}
    assert client.post("/api/auth/signup", json=short_password).status_code == 422

    bad_phone = {**SIGNUP, "phone": "abc"}
    assert client.post("/api/auth/signup", json=bad_phone).status_code == 422


def test_login_and_me(client: TestClient, auth_headers: dict[str, str]) -> None:
    login = client.post(
        "/api/auth/login",
        json={"phone": "+91 98450 11223", "password": "secret123"},
    )
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]

    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["location"] == "Mandya"

    anonymous = client.get("/api/auth/me")
    assert anonymous.status_code == 401


def test_login_wrong_password(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.post(
        "/api/auth/login",
        json={"phone": "+919845011223", "password": "not-the-password"},
    )
    assert response.status_code == 401


def test_update_profile(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.patch(
        "/api/auth/me",
        headers=auth_headers,
        json={"location": "Hubballi", "role": "Buyer / Trader"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["location"] == "Hubballi"
    assert response.json()["role"] == "Buyer / Trader"


def test_invalid_token_is_rejected(client: TestClient) -> None:
    response = client.get(
        "/api/auth/me", headers={"Authorization": "Bearer not-a-real-token"}
    )
    assert response.status_code == 401
