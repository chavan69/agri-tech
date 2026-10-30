"""AI Plant Doctor analysis endpoint."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from ..database import get_supabase
from ..dependencies import CurrentUser
from ..schemas import AnalysisResponse, AnalyzeRequest, DiagnosticReport, ScanOut
from ..services.plant_doctor import (
    PlantDoctorError,
    PlantDoctorUnavailable,
    analyze_leaf,
    decode_image_base64,
)
from ..utils import first_or_none

router = APIRouter(prefix="/plant-doctor", tags=["AI Plant Doctor"])


def _scan_row(report: DiagnosticReport, user_id: str, mime_type: str) -> dict:
    return {
        "user_id": user_id,
        "crop": report.crop,
        "status": report.status,
        "badge_color": report.badge_color,
        "diagnosis": report.diagnosis,
        "confidence": report.confidence,
        "prevention": report.prevention,
        "organic_cure": report.organic_cure,
        "chemical_cure": report.chemical_cure,
        "image_mime": mime_type,
    }


@router.post(
    "/analyze",
    response_model=AnalysisResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Analyze a leaf/plant image",
)
def analyze(payload: AnalyzeRequest, user: CurrentUser) -> AnalysisResponse:
    try:
        image_bytes = decode_image_base64(payload.image_base64, payload.mime_type)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc

    try:
        report = analyze_leaf(image_bytes, payload.mime_type)
    except PlantDoctorUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    except PlantDoctorError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc

    response = (
        get_supabase()
        .table("scans")
        .insert(_scan_row(report, user.id, payload.mime_type))
        .execute()
    )
    created = first_or_none(response.data)
    if created is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Scan result could not be saved.",
        )

    return AnalysisResponse(report=report, scan=ScanOut.model_validate(created))
