"""E-market listings and live auction bids."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from ..database import get_supabase
from ..dependencies import CurrentUser, ensure_can_modify
from ..schemas import (
    BidCreate,
    BidOut,
    MarketListingIn,
    MarketListingOut,
    MarketListingUpdate,
    MarketMode,
)
from ..utils import first_or_none, sanitize_search_term

router = APIRouter(prefix="/market", tags=["E-Market"])

DEFAULT_IMAGE = (
    "https://images.unsplash.com/photo-1542838132-92c53300491e"
    "?auto=format&fit=crop&w=600&q=80"
)
_LISTING_COLUMNS = "*"


def _get_listing(listing_id: str) -> dict:
    response = (
        get_supabase()
        .table("market_listings")
        .select(_LISTING_COLUMNS)
        .eq("id", listing_id)
        .limit(1)
        .execute()
    )
    row = first_or_none(response.data)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Listing not found."
        )
    return row


@router.get("", response_model=list[MarketListingOut], summary="List market listings")
def list_listings(
    category: str | None = None,
    mode: MarketMode | None = None,
    search: str | None = None,
    owner_id: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 60,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[MarketListingOut]:
    query = (
        get_supabase()
        .table("market_listings")
        .select(_LISTING_COLUMNS)
        .order("created_at", desc=True)
        .range(offset, offset + limit - 1)
    )
    if category:
        query = query.eq("category", category)
    if mode:
        query = query.eq("mode", mode)
    if owner_id:
        query = query.eq("owner_id", owner_id)
    if search:
        term = sanitize_search_term(search)
        if term:
            pattern = f"%{term}%"
            query = query.or_(
                f"name.ilike.{pattern},seller.ilike.{pattern},location.ilike.{pattern}"
            )

    response = query.execute()
    return [MarketListingOut.model_validate(row) for row in response.data or []]


@router.get(
    "/{listing_id}", response_model=MarketListingOut, summary="Get a single listing"
)
def get_listing(listing_id: str) -> MarketListingOut:
    return MarketListingOut.model_validate(_get_listing(listing_id))


@router.post(
    "",
    response_model=MarketListingOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a market listing",
)
def create_listing(payload: MarketListingIn, user: CurrentUser) -> MarketListingOut:
    is_auction = payload.mode == "auction"
    row = {
        "name": payload.name,
        "category": payload.category,
        "mode": payload.mode,
        "price": payload.price,
        "current_bid": payload.price if is_auction else None,
        "quantity": payload.quantity,
        "seller": user.name,
        "phone": user.phone,
        "location": user.location or "Karnataka",
        "image": payload.image or DEFAULT_IMAGE,
        "owner_id": user.id,
    }

    response = get_supabase().table("market_listings").insert(row).execute()
    created = first_or_none(response.data)
    if created is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Listing could not be created.",
        )
    return MarketListingOut.model_validate(created)


@router.patch(
    "/{listing_id}", response_model=MarketListingOut, summary="Update your listing"
)
def update_listing(
    listing_id: str, payload: MarketListingUpdate, user: CurrentUser
) -> MarketListingOut:
    current = _get_listing(listing_id)
    ensure_can_modify(current, user)

    changes = payload.model_dump(exclude_none=True, exclude_unset=True)
    if not changes:
        return MarketListingOut.model_validate(current)

    if changes.get("mode") == "auction" and current.get("current_bid") is None:
        changes.setdefault("current_bid", changes.get("price", current.get("price")))

    response = (
        get_supabase()
        .table("market_listings")
        .update(changes)
        .eq("id", listing_id)
        .execute()
    )
    updated = first_or_none(response.data)
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Listing not found."
        )
    return MarketListingOut.model_validate(updated)


@router.delete("/{listing_id}", summary="Delete your listing")
def delete_listing(listing_id: str, user: CurrentUser) -> dict:
    current = _get_listing(listing_id)
    ensure_can_modify(current, user)

    get_supabase().table("market_listings").delete().eq("id", listing_id).execute()
    return {"success": True, "deleted_id": listing_id}


@router.post(
    "/{listing_id}/bid",
    response_model=BidOut,
    status_code=status.HTTP_201_CREATED,
    summary="Place a bid on an auction listing",
)
def place_bid(listing_id: str, payload: BidCreate, user: CurrentUser) -> BidOut:
    supabase = get_supabase()
    listing = _get_listing(listing_id)

    if listing.get("mode") != "auction":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Bids are only accepted on auction listings.",
        )
    if listing.get("status") != "active":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="This auction is closed."
        )

    current_bid = listing.get("current_bid")
    floor = current_bid if current_bid is not None else listing.get("price") or 0
    if payload.amount <= float(floor):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Bid must be higher than the current bid of ₹{float(floor):g}.",
        )

    # Optimistic concurrency: only apply the bid if nobody else changed it.
    update_query = (
        supabase.table("market_listings")
        .update({"current_bid": payload.amount})
        .eq("id", listing_id)
    )
    if current_bid is None:
        update_query = update_query.is_("current_bid", "null")
    else:
        update_query = update_query.eq("current_bid", current_bid)

    updated = update_query.execute()
    if not updated.data:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Another bid was placed first. Refresh and try again.",
        )

    bid_row = {
        "listing_id": listing_id,
        "bidder_id": user.id,
        "bidder_name": user.name,
        "amount": payload.amount,
    }
    response = supabase.table("bids").insert(bid_row).execute()
    created = first_or_none(response.data)
    if created is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Bid could not be saved.",
        )
    return BidOut.model_validate(created)


@router.get(
    "/{listing_id}/bids",
    response_model=list[BidOut],
    summary="List bids for an auction listing",
)
def list_bids(listing_id: str) -> list[BidOut]:
    _get_listing(listing_id)
    response = (
        get_supabase()
        .table("bids")
        .select("*")
        .eq("listing_id", listing_id)
        .order("amount", desc=True)
        .execute()
    )
    return [BidOut.model_validate(row) for row in response.data or []]
