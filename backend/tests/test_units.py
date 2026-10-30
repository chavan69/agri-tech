from __future__ import annotations

import base64

import pytest

from app.schemas import DiagnosticReport
from app.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.services.plant_doctor import (
    build_report,
    decode_image_base64,
)
from app.utils import normalize_phone, sanitize_search_term


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("+91 98450 11223", "+919845011223"),
        ("9845011223", "9845011223"),
        ("(98450)-11223", "9845011223"),
        ("0091 98450 11223", "+919845011223"),
    ],
)
def test_normalize_phone(raw: str, expected: str) -> None:
    assert normalize_phone(raw) == expected


@pytest.mark.parametrize("raw", ["", "abc", "12", "+0 1234567", "1234567890123456"])
def test_normalize_phone_rejects_invalid(raw: str) -> None:
    with pytest.raises(ValueError):
        normalize_phone(raw)


def test_sanitize_search_term() -> None:
    assert sanitize_search_term("to,m(ato)%") == "tomato"


def test_password_hash_roundtrip() -> None:
    hashed = hash_password("secret123")
    assert hashed != "secret123"
    assert verify_password("secret123", hashed)
    assert not verify_password("wrong", hashed)
    assert not verify_password("secret123", "not-a-hash")


def test_password_supports_long_unicode() -> None:
    long_password = "🌾" * 100
    assert verify_password(long_password, hash_password(long_password))


def test_jwt_roundtrip_and_tampering() -> None:
    token, expires_in = create_access_token("user-123")
    assert expires_in > 0
    assert decode_access_token(token) == "user-123"
    assert decode_access_token(token + "x") is None
    assert decode_access_token("garbage") is None


def test_build_report_coerces_ai_output() -> None:
    report = build_report(
        {
            "crop": "Rice",
            "status": "Active Disease Detected",
            "diagnosis": "Blast - 88% confidence",
            "prevention": "Remove debris\nApply fungicide",
            "organicCure": "Pseudomonas spray",
        }
    )
    assert report.badge_color == "red"  # derived from status when missing
    assert report.confidence == 88  # parsed from the diagnosis text
    assert report.prevention == ["Remove debris", "Apply fungicide"]
    assert report.chemical_cure == ""
    assert report.provider == "gemini"


def test_build_report_rejects_invalid_badge() -> None:
    report = build_report({"crop": "Wheat", "badgeColor": "purple", "status": "Healthy"})
    assert report.badge_color == "green"


def test_decode_image_base64_handles_data_url() -> None:
    raw = b"\x89PNG\r\n\x1a\n" + b"0" * 20
    data_url = "data:image/png;base64," + base64.b64encode(raw).decode()
    assert decode_image_base64(data_url, "image/jpeg") == raw


def test_decode_image_base64_rejects_large_and_bad_input() -> None:
    with pytest.raises(ValueError):
        decode_image_base64("!!!!", "image/jpeg")
    with pytest.raises(ValueError):
        decode_image_base64(base64.b64encode(b"0" * 100).decode(), "image/jpeg", max_bytes=10)
    with pytest.raises(ValueError):
        decode_image_base64(base64.b64encode(b"0" * 10).decode(), "text/plain")


def test_diagnostic_report_serializes_camel_case() -> None:
    report = DiagnosticReport(
        crop="Tomato",
        organic_cure="Neem",
        chemical_cure="Mancozeb",
        badge_color="green",
    )
    payload = report.model_dump(by_alias=True)
    assert payload["organicCure"] == "Neem"
    assert payload["chemicalCure"] == "Mancozeb"
    assert payload["badgeColor"] == "green"
