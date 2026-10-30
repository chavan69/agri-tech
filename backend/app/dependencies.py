"""FastAPI dependencies (auth, current user)."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .database import get_supabase
from .schemas import UserOut
from .security import decode_access_token
from .utils import first_or_none

bearer_scheme = HTTPBearer(
    auto_error=False,
    description="JWT returned by /api/auth/login or /api/auth/signup",
)

_USER_COLUMNS = "id,name,phone,location,role,created_at"


def _unauthorized(detail: str = "Not authenticated.") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> UserOut:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _unauthorized("Missing bearer token.")

    user_id = decode_access_token(credentials.credentials)
    if user_id is None:
        raise _unauthorized("Invalid or expired token.")

    response = (
        get_supabase()
        .table("users")
        .select(_USER_COLUMNS)
        .eq("id", user_id)
        .limit(1)
        .execute()
    )
    row = first_or_none(response.data)
    if row is None:
        raise _unauthorized("User account no longer exists.")

    return UserOut.model_validate(row)


CurrentUser = Annotated[UserOut, Depends(get_current_user)]


def ensure_can_modify(row: dict, user: UserOut) -> None:
    """Allow the owner of a row to modify it.

    Rows created before accounts existed (seed/demo data) have no owner and may
    be managed by any signed-in user.
    """
    owner_id = row.get("owner_id")
    if owner_id is not None and owner_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only modify your own listings.",
        )
