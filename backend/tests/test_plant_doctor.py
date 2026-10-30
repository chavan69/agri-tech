from __future__ import annotations

import base64

import pytest
from fastapi.testclient import TestClient

from app.routers import plant_doctor as plant_doctor_router
from app.schemas import DiagnosticReport

# Minimal payload that passes base64/size validation; the AI call is mocked.
IMAGE_BASE64 = base64.b64encode(b"\xff\xd8\xff\xe0" + b"\x00" * 64).decode()
REPORT = DiagnosticReport(
    crop="Tomato",
    status="Active Disease Detected",
    badge_color="red",
    diagnosis="Early Blight",
    confidence=96,
    prevention=["Remove infected leaves", "Avoid overhead watering", "Rotate crops"],
    organic_cure="Neem oil spray every 7 days.",
    chemical_cure="Mancozeb 2 g/L, repeat after 10 days.",
    provider="gemini",
)


def _mock_analyze(monkeypatch) -> None:
    monkeypatch.setattr(
        plant_doctor_router, "analyze_leaf", lambda _bytes, _mime: REPORT
    )


def test_analyze_saves_scan(
    client: TestClient, auth_headers: dict[str, str], monkeypatch
) -> None:
    _mock_analyze(monkeypatch)

    response = client.post(
        "/api/plant-doctor/analyze",
        json={"imageBase64": IMAGE_BASE64, "mimeType": "image/jpeg"},
        headers=auth_headers,
    )
    assert response.status_code == 201, response.text

    body = response.json()
    # The frontend expects camelCase keys in the report.
    assert body["report"]["badgeColor"] == "red"
    assert body["report"]["organicCure"].startswith("Neem oil")
    assert body["report"]["prevention"][0] == "Remove infected leaves"
    assert body["report"]["confidence"] == 96

    scan = body["scan"]
    assert scan["crop"] == "Tomato"
    assert scan["badge_color"] == "red"
    assert scan["prevention"][2] == "Rotate crops"

    history = client.get("/api/scans", headers=auth_headers)
    assert history.status_code == 200
    assert len(history.json()) == 1


def test_analyze_requires_auth(client: TestClient) -> None:
    response = client.post(
        "/api/plant-doctor/analyze",
        json={"imageBase64": IMAGE_BASE64, "mimeType": "image/jpeg"},
    )
    assert response.status_code == 401


def test_analyze_rejects_bad_image(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    response = client.post(
        "/api/plant-doctor/analyze",
        json={"imageBase64": "not-valid-base64!!", "mimeType": "image/jpeg"},
        headers=auth_headers,
    )
    assert response.status_code == 400

    wrong_type = client.post(
        "/api/plant-doctor/analyze",
        json={"imageBase64": IMAGE_BASE64, "mimeType": "application/pdf"},
        headers=auth_headers,
    )
    assert wrong_type.status_code == 400


def test_analyze_without_gemini_key_returns_503(
    client: TestClient, auth_headers: dict[str, str], monkeypatch
) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "gemini_api_key", "")
    monkeypatch.setattr(settings, "plant_doctor_mock", False)

    response = client.post(
        "/api/plant-doctor/analyze",
        json={"imageBase64": IMAGE_BASE64, "mimeType": "image/jpeg"},
        headers=auth_headers,
    )
    assert response.status_code == 503


def test_blocked_gemini_key_error_is_actionable(monkeypatch) -> None:
    import google.genai as genai

    from app.config import settings
    from app.services.plant_doctor import PlantDoctorUnavailable, analyze_leaf

    class _Blocked(Exception):
        status_code = 403

        def __str__(self) -> str:
            return (
                "403 PERMISSION_DENIED: API_KEY_SERVICE_BLOCKED - Requests to "
                "generativelanguage.googleapis.com are blocked "
                "(consumer: projects/1234567890)."
            )

    class _FakeModels:
        def generate_content(self, **_kwargs):
            raise _Blocked()

    class _FakeClient:
        def __init__(self, **_kwargs) -> None:
            self.models = _FakeModels()

    monkeypatch.setattr(settings, "gemini_api_key", "fake-key")
    monkeypatch.setattr(settings, "plant_doctor_mock", False)
    monkeypatch.setattr(genai, "Client", _FakeClient)

    with pytest.raises(PlantDoctorUnavailable) as excinfo:
        analyze_leaf(b"\xff\xd8\xff\xe0", "image/jpeg")

    message = str(excinfo.value)
    assert "disabled" in message
    assert "aistudio.google.com/apikey" in message
    assert "project=1234567890" in message


def test_scan_history_is_per_user(
    client: TestClient, auth_headers: dict[str, str], monkeypatch
) -> None:
    _mock_analyze(monkeypatch)
    created = client.post(
        "/api/plant-doctor/analyze",
        json={"imageBase64": IMAGE_BASE64, "mimeType": "image/jpeg"},
        headers=auth_headers,
    ).json()
    scan_id = created["scan"]["id"]

    signup = client.post(
        "/api/auth/signup",
        json={"name": "Other Farmer", "phone": "+919611255667", "password": "secret123"},
    )
    other = {"Authorization": f"Bearer {signup.json()['access_token']}"}
    assert client.get("/api/scans", headers=other).json() == []
    assert client.get(f"/api/scans/{scan_id}", headers=other).status_code == 404

    assert client.get(f"/api/scans/{scan_id}", headers=auth_headers).status_code == 200

    deleted = client.delete(f"/api/scans/{scan_id}", headers=auth_headers)
    assert deleted.status_code == 200
    assert client.get("/api/scans", headers=auth_headers).json() == []
