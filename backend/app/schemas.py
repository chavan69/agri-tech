"""Pydantic request/response models for the AgriTech API."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .utils import normalize_phone

MarketMode = Literal["direct", "auction"]
MachineryType = Literal["available", "requirement"]
BadgeColor = Literal["green", "amber", "red"]


class APIModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


# ---------------------------------------------------------------------------
# Auth / users
# ---------------------------------------------------------------------------


class SignupRequest(APIModel):
    name: str = Field(min_length=2, max_length=120)
    phone: str
    password: str = Field(min_length=6, max_length=128)
    location: str = Field(default="Karnataka", max_length=160)
    role: str = Field(default="Farmer & Seller", max_length=80)

    @field_validator("phone")
    @classmethod
    def _check_phone(cls, value: str) -> str:
        return normalize_phone(value)

    @field_validator("name", "location", "role")
    @classmethod
    def _strip(cls, value: str) -> str:
        return value.strip()


class LoginRequest(APIModel):
    phone: str
    password: str = Field(min_length=1, max_length=128)

    @field_validator("phone")
    @classmethod
    def _check_phone(cls, value: str) -> str:
        return normalize_phone(value)


class UserOut(APIModel):
    id: str
    name: str
    phone: str
    location: str | None = None
    role: str | None = None
    created_at: datetime | None = None


class UserUpdate(APIModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    location: str | None = Field(default=None, max_length=160)
    role: str | None = Field(default=None, max_length=80)

    @field_validator("name", "location", "role")
    @classmethod
    def _strip(cls, value: str | None) -> str | None:
        return value.strip() if isinstance(value, str) else value


class TokenResponse(APIModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut


# ---------------------------------------------------------------------------
# Market listings & bids
# ---------------------------------------------------------------------------


class MarketListingIn(APIModel):
    name: str = Field(min_length=1, max_length=120)
    category: str = Field(default="Vegetables", max_length=60)
    mode: MarketMode = "direct"
    price: float = Field(gt=0, le=10_000_000)
    quantity: str = Field(default="100 kg", max_length=60)
    image: str | None = Field(default=None, max_length=2048)

    @field_validator("name", "category", "quantity")
    @classmethod
    def _strip(cls, value: str) -> str:
        return value.strip()


class MarketListingUpdate(APIModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    category: str | None = Field(default=None, max_length=60)
    mode: MarketMode | None = None
    price: float | None = Field(default=None, gt=0, le=10_000_000)
    quantity: str | None = Field(default=None, max_length=60)
    image: str | None = Field(default=None, max_length=2048)
    status: Literal["active", "sold", "closed"] | None = None


class MarketListingOut(APIModel):
    id: str
    name: str
    category: str | None = None
    mode: MarketMode = "direct"
    price: float | None = None
    current_bid: float | None = None
    quantity: str | None = None
    seller: str | None = None
    phone: str | None = None
    location: str | None = None
    image: str | None = None
    owner_id: str | None = None
    status: str = "active"
    created_at: datetime | None = None


class BidCreate(APIModel):
    amount: float = Field(gt=0, le=100_000_000)


class BidOut(APIModel):
    id: str
    listing_id: str
    bidder_id: str | None = None
    bidder_name: str | None = None
    amount: float
    created_at: datetime | None = None


# ---------------------------------------------------------------------------
# Machinery listings
# ---------------------------------------------------------------------------


class MachineryListingIn(APIModel):
    title: str = Field(min_length=1, max_length=140)
    type: MachineryType = "available"
    category: str = Field(default="Heavy Machinery", max_length=80)
    rate: str = Field(default="₹500 / hr", max_length=60)
    specs: str = Field(default="Verified", max_length=400)

    @field_validator("title", "category", "rate", "specs")
    @classmethod
    def _strip(cls, value: str) -> str:
        return value.strip()


class MachineryListingUpdate(APIModel):
    title: str | None = Field(default=None, min_length=1, max_length=140)
    type: MachineryType | None = None
    category: str | None = Field(default=None, max_length=80)
    rate: str | None = Field(default=None, max_length=60)
    specs: str | None = Field(default=None, max_length=400)
    status: Literal["active", "closed"] | None = None


class MachineryListingOut(APIModel):
    id: str
    title: str
    type: MachineryType = "available"
    category: str | None = None
    rate: str | None = None
    owner: str | None = None
    phone: str | None = None
    location: str | None = None
    specs: str | None = None
    owner_id: str | None = None
    status: str = "active"
    created_at: datetime | None = None


# ---------------------------------------------------------------------------
# Plant doctor & scans
# ---------------------------------------------------------------------------


class AnalyzeRequest(APIModel):
    """Accepts the frontend's camelCase payload and snake_case variants."""

    image_base64: str = Field(alias="imageBase64", min_length=16)
    mime_type: str = Field(default="image/jpeg", alias="mimeType", max_length=60)


class DiagnosticReport(APIModel):
    crop: str = "Unknown crop"
    status: str = "Healthy"
    badge_color: BadgeColor = Field(default="green", alias="badgeColor")
    diagnosis: str = "No diagnosis available."
    confidence: int | None = Field(default=None, ge=0, le=100)
    prevention: list[str] = Field(default_factory=list)
    organic_cure: str = Field(default="", alias="organicCure")
    chemical_cure: str = Field(default="", alias="chemicalCure")
    provider: str | None = None


class ScanOut(APIModel):
    id: str
    crop: str | None = None
    status: str | None = None
    badge_color: BadgeColor | None = None
    diagnosis: str | None = None
    confidence: int | None = None
    prevention: list[str] = Field(default_factory=list)
    organic_cure: str | None = None
    chemical_cure: str | None = None
    image_mime: str | None = None
    created_at: datetime | None = None


class AnalysisResponse(APIModel):
    report: DiagnosticReport
    scan: ScanOut
