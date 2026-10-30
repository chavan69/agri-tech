"""Saved plant-doctor scan history for the signed-in user."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from ..database import get_supabase
from ..dependencies import CurrentUser
from ..schemas import ScanOut
from ..utils import first_or_none

router = APIRouter(prefix="/scans", tags=["AI Plant Doctor"])


@router.get("", response_model=list[ScanOut], summary="Your scan history")
def list_scans(
    user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[ScanOut]:
    response = (
        get_supabase()
        .table("scans")
        .select("*")
        .eq("user_id", user.id)
        .order("created_at", desc=True)
        .range(offset, offset + limit - 1)
        .execute()
    )
    return [ScanOut.model_validate(row) for row in response.data or []]


@router.get("/{scan_id}", response_model=ScanOut, summary="Get a saved scan")
def get_scan(scan_id: str, user: CurrentUser) -> ScanOut:
    response = (
        get_supabase()
        .table("scans")
        .select("*")
        .eq("id", scan_id)
        .eq("user_id", user.id)
        .limit(1)
        .execute()
    )
    row = first_or_none(response.data)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scan not found.")
    return ScanOut.model_validate(row)


@router.delete("/{scan_id}", summary="Delete a saved scan")
def delete_scan(scan_id: str, user: CurrentUser) -> dict:
    response = (
        get_supabase()
        .table("scans")
        .delete()
        .eq("id", scan_id)
        .eq("user_id", user.id)
        .execute()
    )
    if not response.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scan not found.")
    return {"success": True, "deleted_id": scan_id}
