"""Gemini powered leaf/plant image analysis."""

from __future__ import annotations

import base64
import binascii
import json
import re

from ..config import settings
from ..schemas import DiagnosticReport

ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}
_DATA_URL_RE = re.compile(r"^data:([\w/+.-]+);base64,", re.IGNORECASE)
_WHITESPACE_RE = re.compile(r"\s+")
_FENCE_RE = re.compile(r"^```(?:json)?|```$", re.MULTILINE)
_CONFIDENCE_RE = re.compile(r"(\d{1,3})\s*%")

PROMPT = """You are an expert AI Plant Pathologist and Agronomist. Analyze this plant/leaf image carefully.
Provide your response strictly in valid JSON format (no markdown code blocks, just raw JSON) with the following exact keys:
- "crop": Name of the crop or plant detected.
- "status": One of "Healthy", "Pre-Disease Warning", or "Active Disease Detected".
- "badgeColor": "green", "amber", or "red".
- "diagnosis": Name of the disease or deficiency (e.g. "Early Blight").
- "confidence": Integer 0-100 representing your confidence in the diagnosis.
- "prevention": An array of 3 bullet point strings detailing immediate field action or pre-disease preventive steps.
- "organicCure": Description of organic remedy/bio-pesticide.
- "chemicalCure": Recommended chemical treatment with exact dosage guidelines.
If the image does not contain a plant or leaf, set "crop" to "Not a plant", "status" to "Healthy",
"badgeColor" to "green" and explain in "diagnosis" that no plant was detected."""

MOCK_REPORT = DiagnosticReport(
    crop="Demo crop",
    status="Pre-Disease Warning",
    badge_color="amber",
    diagnosis="Demo analysis - Gemini API key is not configured",
    confidence=0,
    prevention=[
        "Set GEMINI_API_KEY in backend/.env to enable real AI diagnostics.",
        "Inspect both sides of the leaves for spots, mildew or discoloration.",
        "Keep the field well drained and avoid overhead irrigation.",
    ],
    organic_cure="Neem oil spray (5 ml/L) applied early morning every 7 days.",
    chemical_cure="Consult your local agri-extension officer before applying any chemical.",
    provider="mock",
)


class PlantDoctorUnavailable(RuntimeError):
    """AI provider is not configured."""


class PlantDoctorError(RuntimeError):
    """AI provider call or response parsing failed."""


def decode_image_base64(raw: str, mime_type: str, max_bytes: int | None = None) -> bytes:
    """Decode a base64 string or data URL into bytes, validating size and type."""
    limit = max_bytes or settings.max_image_bytes
    payload = (raw or "").strip()

    match = _DATA_URL_RE.match(payload)
    if match:
        detected_type = match.group(1).lower()
        if mime_type in {"", "image/jpeg"}:
            mime_type = detected_type
        payload = payload[match.end():]

    if mime_type not in ALLOWED_MIME_TYPES:
        raise ValueError(
            "Unsupported image type. Use JPEG, PNG, WEBP, HEIC or HEIF."
        )

    payload = _WHITESPACE_RE.sub("", payload)
    try:
        data = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("Image is not valid base64 data.") from exc

    if not data:
        raise ValueError("Image is empty.")
    if len(data) > limit:
        raise ValueError(f"Image is too large. Maximum size is {limit // (1024 * 1024)} MB.")

    return data


def _extract_json(text: str) -> dict:
    cleaned = _FENCE_RE.sub("", (text or "").strip()).strip()
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start == -1 or end <= start:
            raise PlantDoctorError("AI returned an unexpected response format.") from None
        try:
            parsed = json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError as exc:
            raise PlantDoctorError("AI returned invalid JSON.") from exc

    if not isinstance(parsed, dict):
        raise PlantDoctorError("AI returned an unexpected response format.")
    return parsed


def _as_text(value: object, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text or default


def _as_confidence(value: object, diagnosis: str) -> int | None:
    if value is not None:
        try:
            return max(0, min(100, int(float(value))))
        except (TypeError, ValueError):
            pass
    match = _CONFIDENCE_RE.search(diagnosis)
    if match:
        return max(0, min(100, int(match.group(1))))
    return None


def _as_prevention(value: object) -> list[str]:
    if isinstance(value, str):
        candidates = re.split(r"[\r\n]+|(?:^|\s)[-*•]\s*", value)
    elif isinstance(value, (list, tuple)):
        candidates = value
    else:
        candidates = []

    steps: list[str] = []
    for item in candidates:
        text = _as_text(item)
        if text:
            steps.append(text[:400])
    return steps[:6]


def build_report(data: dict, provider: str = "gemini") -> DiagnosticReport:
    """Coerce a (possibly partial) AI payload into a validated report."""
    diagnosis = _as_text(data.get("diagnosis"), "No diagnosis available.")
    status = _as_text(data.get("status"), "Healthy")
    badge = _as_text(data.get("badgeColor") or data.get("badge_color")).lower()

    if badge not in {"green", "amber", "red"}:
        lowered = status.lower()
        badge = "red" if "disease" in lowered else "amber" if "warning" in lowered else "green"

    prevention = _as_prevention(data.get("prevention"))
    if not prevention:
        prevention = ["Monitor the crop and consult a local agronomist for a closer inspection."]

    return DiagnosticReport(
        crop=_as_text(data.get("crop"), "Unknown crop")[:120],
        status=status[:80],
        badge_color=badge,  # type: ignore[arg-type]
        diagnosis=diagnosis[:400],
        confidence=_as_confidence(data.get("confidence"), diagnosis),
        prevention=prevention,
        organic_cure=_as_text(data.get("organicCure") or data.get("organic_cure"))[:1200],
        chemical_cure=_as_text(data.get("chemicalCure") or data.get("chemical_cure"))[:1200],
        provider=provider,
    )


def analyze_leaf(image_bytes: bytes, mime_type: str) -> DiagnosticReport:
    """Run the vision model and return a validated diagnostic report."""
    if not settings.plant_doctor_configured:
        if settings.plant_doctor_mock:
            return MOCK_REPORT
        raise PlantDoctorUnavailable(
            "AI Plant Doctor is not configured. Set GEMINI_API_KEY in backend/.env "
            "or enable PLANT_DOCTOR_MOCK=true for demo responses."
        )

    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:  # pragma: no cover - dependency is in requirements
        raise PlantDoctorUnavailable(
            "google-genai is not installed. Run 'pip install -r requirements.txt'."
        ) from exc

    client = genai.Client(
        api_key=settings.gemini_api_key,
        http_options=types.HttpOptions(timeout=settings.gemini_timeout_seconds * 1000),
    )

    try:
        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                PROMPT,
            ],
        )
    except Exception as exc:  # noqa: BLE001 - surfaced as a 502/503 to the client
        status_code = getattr(exc, "status_code", None) or getattr(exc, "code", None)
        message = str(exc)
        project_match = re.search(r"projects/(\d+)", message)
        project = project_match.group(1) if project_match else None
        enable_url = (
            "https://console.cloud.google.com/apis/library/"
            "generativelanguage.googleapis.com"
            + (f"?project={project}" if project else "")
        )

        if status_code == 403 and (
            "API_KEY_SERVICE_BLOCKED" in message or "SERVICE_DISABLED" in message
        ):
            raise PlantDoctorUnavailable(
                "Google blocked this Gemini API key because the Gemini API "
                "(Generative Language API) is disabled for its Google Cloud "
                f"project{f' ({project})' if project else ''}. Enable it at "
                f"{enable_url} - wait 2-5 minutes - or create a fresh key at "
                "https://aistudio.google.com/apikey, then restart the server."
            ) from exc

        if status_code in {400, 401, 403} and "API_KEY" in message.upper():
            raise PlantDoctorUnavailable(
                "Gemini rejected the API key. Check GEMINI_API_KEY in backend/.env, "
                "or create a new key at https://aistudio.google.com/apikey."
            ) from exc

        raise PlantDoctorError(f"AI provider request failed: {exc}") from exc

    text = getattr(response, "text", None) or ""
    if not text.strip():
        raise PlantDoctorError("AI provider returned an empty response.")

    return build_report(_extract_json(text), provider="gemini")
