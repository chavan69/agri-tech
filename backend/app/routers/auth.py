"""Authentication and profile endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from ..database import get_supabase
from ..dependencies import CurrentUser
from ..schemas import (
    LoginRequest,
    SignupRequest,
    TokenResponse,
    UserOut,
    UserUpdate,
)
from ..security import create_access_token, hash_password, verify_password
from ..utils import first_or_none

router = APIRouter(prefix="/auth", tags=["Authentication"])

_USER_COLUMNS = "id,name,phone,location,role,created_at"


def _token_response(user: UserOut) -> TokenResponse:
    token, expires_in = create_access_token(user.id)
    return TokenResponse(access_token=token, expires_in=expires_in, user=user)


@router.post(
    "/signup",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an account",
)
def signup(payload: SignupRequest) -> TokenResponse:
    supabase = get_supabase()

    existing = (
        supabase.table("users").select("id").eq("phone", payload.phone).limit(1).execute()
    )
    if existing.data:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this phone number already exists.",
        )

    row = {
        "name": payload.name,
        "phone": payload.phone,
        "password_hash": hash_password(payload.password),
        "location": payload.location,
        "role": payload.role,
    }
    inserted = supabase.table("users").insert(row).execute()
    created = first_or_none(inserted.data)
    if created is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Account could not be created. Please try again.",
        )

    user = UserOut.model_validate(created)
    return _token_response(user)


@router.post("/login", response_model=TokenResponse, summary="Log in with phone and password")
def login(payload: LoginRequest) -> TokenResponse:
    supabase = get_supabase()

    response = (
        supabase.table("users")
        .select(f"{_USER_COLUMNS},password_hash")
        .eq("phone", payload.phone)
        .limit(1)
        .execute()
    )
    row = first_or_none(response.data)
    if row is None or not verify_password(payload.password, row.get("password_hash") or ""):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid phone number or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return _token_response(UserOut.model_validate(row))


@router.get("/me", response_model=UserOut, summary="Current user profile")
def me(user: CurrentUser) -> UserOut:
    return user


@router.patch("/me", response_model=UserOut, summary="Update current user profile")
def update_me(payload: UserUpdate, user: CurrentUser) -> UserOut:
    changes = payload.model_dump(exclude_none=True, exclude_unset=True)
    if not changes:
        return user

    response = (
        get_supabase().table("users").update(changes).eq("id", user.id).execute()
    )
    updated = first_or_none(response.data)
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User account not found."
        )
    return UserOut.model_validate(updated)
