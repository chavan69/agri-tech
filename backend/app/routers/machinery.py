"""Machinery & labour rental listings."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from ..database import get_supabase
from ..dependencies import CurrentUser, ensure_can_modify
from ..schemas import (
    MachineryListingIn,
    MachineryListingOut,
    MachineryListingUpdate,
    MachineryType,
)
from ..utils import first_or_none, sanitize_search_term

router = APIRouter(prefix="/machinery", tags=["Machinery & Labour"])


def _get_listing(listing_id: str) -> dict:
    response = (
        get_supabase()
        .table("machinery_listings")
        .select("*")
        .eq("id", listing_id)
        .limit(1)
        .execute()
    )
    row = first_or_none(response.data)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Machinery listing not found."
        )
    return row


@router.get("", response_model=list[MachineryListingOut], summary="List machinery")
def list_listings(
    type: MachineryType | None = None,
    category: str | None = None,
    search: str | None = None,
    owner_id: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 60,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[MachineryListingOut]:
    query = (
        get_supabase()
        .table("machinery_listings")
        .select("*")
        .order("created_at", desc=True)
        .range(offset, offset + limit - 1)
    )
    if type:
        query = query.eq("type", type)
    if category:
        query = query.eq("category", category)
    if owner_id:
        query = query.eq("owner_id", owner_id)
    if search:
        term = sanitize_search_term(search)
        if term:
            pattern = f"%{term}%"
            query = query.or_(
                f"title.ilike.{pattern},specs.ilike.{pattern},location.ilike.{pattern}"
            )

    response = query.execute()
    return [MachineryListingOut.model_validate(row) for row in response.data or []]


@router.get(
    "/{listing_id}", response_model=MachineryListingOut, summary="Get a machinery listing"
)
def get_listing(listing_id: str) -> MachineryListingOut:
    return MachineryListingOut.model_validate(_get_listing(listing_id))


@router.post(
    "",
    response_model=MachineryListingOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a machinery listing",
)
def create_listing(
    payload: MachineryListingIn, user: CurrentUser
) -> MachineryListingOut:
    row = {
        "title": payload.title,
        "type": payload.type,
        "category": payload.category,
        "rate": payload.rate,
        "owner": user.name,
        "phone": user.phone,
        "location": user.location or "Karnataka",
        "specs": payload.specs,
        "owner_id": user.id,
    }
    response = get_supabase().table("machinery_listings").insert(row).execute()
    created = first_or_none(response.data)
    if created is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Machinery listing could not be created.",
        )
    return MachineryListingOut.model_validate(created)


@router.patch(
    "/{listing_id}", response_model=MachineryListingOut, summary="Update your machinery listing"
)
def update_listing(
    listing_id: str, payload: MachineryListingUpdate, user: CurrentUser
) -> MachineryListingOut:
    current = _get_listing(listing_id)
    ensure_can_modify(current, user)

    changes = payload.model_dump(exclude_none=True, exclude_unset=True)
    if not changes:
        return MachineryListingOut.model_validate(current)

    response = (
        get_supabase()
        .table("machinery_listings")
        .update(changes)
        .eq("id", listing_id)
        .execute()
    )
    updated = first_or_none(response.data)
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Machinery listing not found.",
        )
    return MachineryListingOut.model_validate(updated)


@router.delete("/{listing_id}", summary="Delete your machinery listing")
def delete_listing(listing_id: str, user: CurrentUser) -> dict:
    current = _get_listing(listing_id)
    ensure_can_modify(current, user)

    get_supabase().table("machinery_listings").delete().eq("id", listing_id).execute()
    return {"success": True, "deleted_id": listing_id}
