"""Authoritative inventory reads. Stock key = (variant_id, store_id). Failures return UNKNOWN, never in_stock."""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import Inventory, ProductVariant, Store, utcnow


class InventoryUnavailable(Exception):
    pass


@dataclass
class VariantStock:
    variant_id: str
    size: str
    total_quantity: int
    store_ids: list[str]


@dataclass
class StockSummary:
    """Stock summary for a colorway group: which sizes are in stock, across how many stores."""
    image_group_id: str
    available_sizes: list[str]
    store_count: int
    best_variant_id: str | None
    checked_at: datetime


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


class InventoryService:
    def __init__(self, db: AsyncSession, *, fail: bool = False) -> None:
        self.db = db
        self.fail = fail  # test hook: simulate inventory outage

    async def batch_stock(self, variant_ids: list[str]) -> dict[str, VariantStock]:
        """One batched query for all candidate variants. Returns only variants with positive stock."""
        if self.fail:
            raise InventoryUnavailable("inventory backend unavailable")
        if not variant_ids:
            return {}
        rows = (await self.db.execute(
            select(Inventory.variant_id, Inventory.store_id, Inventory.quantity, ProductVariant.size)
            .join(ProductVariant, ProductVariant.id == Inventory.variant_id)
            .where(Inventory.variant_id.in_(variant_ids), Inventory.quantity > 0)
        )).all()
        out: dict[str, VariantStock] = {}
        for variant_id, store_id, qty, size in rows:
            vs = out.setdefault(variant_id, VariantStock(variant_id=variant_id, size=size, total_quantity=0, store_ids=[]))
            vs.total_quantity += qty
            vs.store_ids.append(store_id)
        return out

    async def summarize_groups(self, groups: dict[str, list[str]], *, size: str | None) -> dict[str, StockSummary]:
        """groups: image_group_id -> variant_ids. Returns summaries only for groups with in-stock variants
        (respecting the requested size if provided)."""
        all_ids = [vid for ids in groups.values() for vid in ids]
        stock = await self.batch_stock(all_ids)
        now = utcnow()
        out: dict[str, StockSummary] = {}
        for gid, ids in groups.items():
            in_stock = [stock[v] for v in ids if v in stock]
            if size:
                in_stock = [s for s in in_stock if s.size == size]
            if not in_stock:
                continue
            sizes = sorted({s.size for s in in_stock}, key=lambda x: float(x))
            stores = {sid for s in in_stock for sid in s.store_ids}
            best = in_stock[0]
            if size:
                best = next(s for s in in_stock if s.size == size)
            out[gid] = StockSummary(image_group_id=gid, available_sizes=sizes, store_count=len(stores),
                                    best_variant_id=best.variant_id, checked_at=now)
        return out

    async def store_availability(self, variant_id: str, *, location: tuple[float, float] | None) -> tuple[list[dict], datetime]:
        if self.fail:
            raise InventoryUnavailable("inventory backend unavailable")
        rows = (await self.db.execute(
            select(Store, Inventory.quantity, Inventory.updated_at)
            .join(Inventory, Inventory.store_id == Store.id)
            .where(Inventory.variant_id == variant_id, Store.active == True)  # noqa: E712
        )).all()
        out = []
        for store, qty, updated_at in rows:
            d = {"store_id": store.id, "name": store.name, "address": store.address, "city": store.city,
                 "postcode": store.postcode, "quantity": qty, "updated_at": updated_at,
                 "quantity_status": "in_stock" if qty > 2 else "low_stock" if qty > 0 else "out_of_stock",
                 "distance_km": None}
            if location:
                d["distance_km"] = round(haversine_km(location[0], location[1], store.latitude, store.longitude), 1)
            out.append(d)
        stocked = [s for s in out if s["quantity"] > 0]
        if location:
            stocked.sort(key=lambda s: s["distance_km"])
        else:
            stocked.sort(key=lambda s: s["name"])
        return stocked, utcnow()
