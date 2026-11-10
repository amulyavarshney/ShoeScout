"""Async SQLAlchemy engine/session and ORM models."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import AsyncIterator

from sqlalchemy import (JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text,
                        UniqueConstraint)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from .config import get_settings


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class Product(Base):
    __tablename__ = "products"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    model_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    brand: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    base_price: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(3), default="GBP")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    variants: Mapped[list["ProductVariant"]] = relationship(back_populates="product", cascade="all, delete-orphan")


class ProductVariant(Base):
    __tablename__ = "product_variants"
    __table_args__ = (Index("ix_variants_product_size", "product_id", "size"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"), index=True)
    sku: Mapped[str] = mapped_column(String(64), unique=True)
    colorway_code: Mapped[str] = mapped_column(String(64))
    size: Mapped[str] = mapped_column(String(16))
    price: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(3), default="GBP")
    image_group_id: Mapped[str] = mapped_column(String(64), index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    product: Mapped[Product] = relationship(back_populates="variants")


class ProductImage(Base):
    __tablename__ = "product_images"
    __table_args__ = (Index("ix_images_group", "image_group_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    image_group_id: Mapped[str] = mapped_column(String(64))
    url: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64))
    view_type: Mapped[str] = mapped_column(String(32), default="front")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class EnrichedAttributes(Base):
    __tablename__ = "enriched_attributes"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    image_group_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    primary_color: Mapped[str | None] = mapped_column(String(32), nullable=True)
    secondary_colors: Mapped[list] = mapped_column(JSON, default=list)
    style: Mapped[str | None] = mapped_column(String(64), nullable=True)
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    source: Mapped[str] = mapped_column(String(16), default="supplier")  # supplier | vision | reviewed | fixture
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    review_status: Mapped[str] = mapped_column(String(16), default="approved")  # approved | needs_review | rejected
    model_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    image_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Store(Base):
    __tablename__ = "stores"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120))
    address: Mapped[str] = mapped_column(String(200))
    city: Mapped[str] = mapped_column(String(80))
    postcode: Mapped[str] = mapped_column(String(16))
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Inventory(Base):
    __tablename__ = "inventory"
    __table_args__ = (
        UniqueConstraint("variant_id", "store_id", name="ux_inventory_variant_store"),
        Index("ix_inventory_store_variant", "store_id", "variant_id"),
    )
    variant_id: Mapped[str] = mapped_column(ForeignKey("product_variants.id"), primary_key=True)
    store_id: Mapped[str] = mapped_column(ForeignKey("stores.id"), primary_key=True)
    quantity: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    version: Mapped[int] = mapped_column(Integer, default=1)


class EnrichmentJob(Base):
    __tablename__ = "enrichment_jobs"
    __table_args__ = (Index("ix_enrichment_jobs_status", "status", "created_at"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    image_group_id: Mapped[str] = mapped_column(String(64), index=True)
    image_hash: Mapped[str] = mapped_column(String(64))
    model_version: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="queued")  # queued | running | done | failed | dead
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ProviderCredential(Base):
    __tablename__ = "provider_credentials"
    provider: Mapped[str] = mapped_column(String(32), primary_key=True)
    ciphertext: Mapped[str] = mapped_column(Text)  # base64-encoded AES-GCM ciphertext
    nonce: Mapped[str] = mapped_column(String(64))
    key_fingerprint: Mapped[str] = mapped_column(String(64))
    last4: Mapped[str] = mapped_column(String(4))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class ProviderSettings(Base):
    __tablename__ = "provider_settings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    llm_model: Mapped[str] = mapped_column(String(64))
    vision_model: Mapped[str] = mapped_column(String(64))
    stt_model: Mapped[str] = mapped_column(String(64))
    tts_model: Mapped[str] = mapped_column(String(64))
    voice_id: Mapped[str] = mapped_column(String(64), default="")
    tts_output_format: Mapped[str] = mapped_column(String(32), default="mp3_44100_128")
    silence_ms: Mapped[int] = mapped_column(Integer, default=750)
    language: Mapped[str] = mapped_column(String(16), default="auto")
    provider_timeout_s: Mapped[int] = mapped_column(Integer, default=20)
    mock_mode: Mapped[bool] = mapped_column(Boolean, default=True)
    currency: Mapped[str] = mapped_column(String(3), default="GBP")
    config_version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class AnalyticsEvent(Base):
    __tablename__ = "analytics_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    session_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(48), index=True)
    turn_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    actor: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(64))
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


_engine = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_engine():
    global _engine, _sessionmaker
    if _engine is None:
        url = get_settings().database_url
        kwargs = {"future": True}
        if url.startswith("sqlite"):
            kwargs["connect_args"] = {"timeout": 30}
        _engine = create_async_engine(url, **kwargs)
        _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    get_engine()
    assert _sessionmaker is not None
    return _sessionmaker


async def get_db() -> AsyncIterator[AsyncSession]:
    async with get_sessionmaker()() as session:
        yield session


async def init_db() -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        if get_settings().database_url.startswith("sqlite"):
            from sqlalchemy import text
            await conn.execute(text("PRAGMA journal_mode=WAL"))
        await conn.run_sync(Base.metadata.create_all)


async def reset_engine_for_tests() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None
