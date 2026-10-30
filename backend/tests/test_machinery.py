from __future__ import annotations

from fastapi.testclient import TestClient

MACHINE = {
    "title": "Mahindra 575 DI Tractor",
    "type": "available",
    "category": "Heavy Machinery",
    "rate": "₹850 / hour",
    "specs": "45 HP with driver",
}


def test_machinery_crud(client: TestClient, auth_headers: dict[str, str]) -> None:
    created = client.post("/api/machinery", json=MACHINE, headers=auth_headers)
    assert created.status_code == 201, created.text
    machine = created.json()
    assert machine["owner"] == "Ramesh Gowda"
    assert machine["location"] == "Mandya"

    listed = client.get("/api/machinery").json()
    assert len(listed) == 1

    updated = client.patch(
        f"/api/machinery/{machine['id']}",
        json={"rate": "₹900 / hour", "status": "closed"},
        headers=auth_headers,
    )
    assert updated.status_code == 200
    assert updated.json()["rate"] == "₹900 / hour"
    assert updated.json()["status"] == "closed"

    deleted = client.delete(f"/api/machinery/{machine['id']}", headers=auth_headers)
    assert deleted.status_code == 200
    assert client.get("/api/machinery").json() == []


def test_machinery_requires_auth(client: TestClient) -> None:
    assert client.post("/api/machinery", json=MACHINE).status_code == 401


def test_machinery_filters(client: TestClient, auth_headers: dict[str, str]) -> None:
    client.post("/api/machinery", json=MACHINE, headers=auth_headers)
    client.post(
        "/api/machinery",
        json={
            "title": "Labour team for harvest",
            "type": "requirement",
            "category": "Labour",
            "rate": "₹400 / day",
            "specs": "5 workers",
        },
        headers=auth_headers,
    )

    available = client.get("/api/machinery", params={"type": "available"}).json()
    assert [item["title"] for item in available] == ["Mahindra 575 DI Tractor"]

    search = client.get("/api/machinery", params={"search": "harvest"}).json()
    assert [item["title"] for item in search] == ["Labour team for harvest"]


def test_machinery_owner_check(client: TestClient, auth_headers: dict[str, str]) -> None:
    machine = client.post("/api/machinery", json=MACHINE, headers=auth_headers).json()

    signup = client.post(
        "/api/auth/signup",
        json={
            "name": "Suresh",
            "phone": "+919880133445",
            "password": "secret123",
        },
    )
    other = {"Authorization": f"Bearer {signup.json()['access_token']}"}

    response = client.delete(f"/api/machinery/{machine['id']}", headers=other)
    assert response.status_code == 403
