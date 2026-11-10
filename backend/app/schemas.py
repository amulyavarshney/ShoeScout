"""Pydantic API schemas (shared by HTTP + WebSocket)."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ErrorBody(BaseModel):
    code: str
    message: str
    request_id: str | None = None


class ErrorEnvelope(BaseModel):
    error: ErrorBody


class ProductCard(BaseModel):
    product_id: str
    variant_id: str
    model_id: str
    name: str
    brand: str
    primary_color: str | None = None
    color_confidence: Literal["verified", "unverified", "unknown"] = "unknown"
    category: str | None = None
    price: float
    currency: str
    image_url: str | None = None
    available_sizes: list[str] = Field(default_factory=list)
    in_stock: bool = False
    stock_status: Literal["in_stock", "out_of_stock", "unknown"] = "unknown"
    stock_checked_at: datetime | None = None
    store_count: int = 0
    image_group_id: str
    is_alternative: bool = False
    relaxed: list[str] = Field(default_factory=list)


class StoreAvailability(BaseModel):
    store_id: str
    name: str
    address: str
    city: str
    postcode: str
    size: str | None = None
    quantity_status: Literal["in_stock", "low_stock", "out_of_stock", "unknown"]
    quantity: int | None = None
    distance_km: float | None = None
    updated_at: datetime | None = None


class AvailabilityResponse(BaseModel):
    variant_id: str | None
    model_id: str | None
    size: str | None
    stores: list[StoreAvailability]
    stock_checked_at: datetime | None
    inventory_status: Literal["ok", "unavailable"] = "ok"
    location_known: bool = False
    available_sizes: list[str] = Field(default_factory=list)


class Preferences(BaseModel):
    brand: str | None = None
    model: str | None = None
    color: str | None = None
    category: str | None = None
    size: str | None = None
    max_price: float | None = None
    use_case: str | None = None


class SessionCreate(BaseModel):
    locale: str | None = None


class SessionOut(BaseModel):
    session_id: str
    expires_at: datetime
    mode: Literal["mock", "live"]
    capabilities: dict


class MessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=1000)
    turn_id: str = Field(min_length=1, max_length=64)


class MessageOut(BaseModel):
    turn_id: str
    message: str
    products: list[ProductCard]
    stores: list[StoreAvailability] | None = None
    preferences: Preferences
    selected_variant_id: str | None = None
    state: Literal["complete", "error", "needs_clarification"]
    relaxed_constraints: list[str] = Field(default_factory=list)
    is_demo: bool = False


class LocationConsent(BaseModel):
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    postcode: str | None = Field(default=None, max_length=16)
    city: str | None = Field(default=None, max_length=80)


class LocationToken(BaseModel):
    location_token: str
    expires_at: datetime
    label: str


class ProductDetail(BaseModel):
    product_id: str
    model_id: str
    brand: str
    name: str
    description: str
    category: str | None
    base_price: float
    currency: str
    colorways: list[dict]


# ---- Admin ----
class ProviderStatus(BaseModel):
    provider: Literal["openai", "elevenlabs"]
    configured: bool
    source: Literal["settings", "environment", "none"]
    last4: str | None = None
    updated_at: datetime | None = None
    validation_status: Literal["unknown", "ok", "failed"] = "unknown"


class ProviderKeyIn(BaseModel):
    api_key: str = Field(min_length=8, max_length=512)


class ProviderTestOut(BaseModel):
    ok: bool
    provider: str
    message: str
    error_type: str | None = None
    details: dict = Field(default_factory=dict)


class SettingsOut(BaseModel):
    llm_model: str
    vision_model: str
    stt_model: str
    tts_model: str
    voice_id: str
    tts_output_format: str
    silence_ms: int
    language: str
    provider_timeout_s: int
    mock_mode: bool
    currency: str
    config_version: int
    updated_at: datetime | None
    effective_mode: Literal["mock", "live"]


class SettingsPatch(BaseModel):
    llm_model: str | None = Field(default=None, max_length=64)
    vision_model: str | None = Field(default=None, max_length=64)
    stt_model: str | None = Field(default=None, max_length=64)
    tts_model: str | None = Field(default=None, max_length=64)
    voice_id: str | None = Field(default=None, max_length=64)
    tts_output_format: str | None = Field(default=None, max_length=32)
    silence_ms: int | None = Field(default=None, ge=200, le=3000)
    language: str | None = Field(default=None, max_length=16)
    provider_timeout_s: int | None = Field(default=None, ge=3, le=120)
    mock_mode: bool | None = None
    currency: str | None = Field(default=None, min_length=3, max_length=3)


class LoginIn(BaseModel):
    username: str = Field(max_length=64)
    password: str = Field(max_length=256)
