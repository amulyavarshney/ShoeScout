from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import EnrichedAttributes, Product, ProductImage, ProductVariant, get_db
from ..inventory.location import location_store
from ..inventory.service import InventoryService, InventoryUnavailable
from ..schemas import AvailabilityResponse, ProductDetail, StoreAvailability
from ..search.router import SearchRequest, search_products
from .deps import http_error

router = APIRouter(tags=["products"])


@router.get("/products/search")
async def product_search(brand: str | None = None, color: str | None = None, model: str | None = None, category: str | None = None,
                         size: str | None = None, max_price: float | None = Query(default=None, ge=0), q: str | None = None,
                         limit: int = Query(default=5, ge=1, le=5), sort: str = "relevance", db: AsyncSession = Depends(get_db)):
    res = await search_products(db, SearchRequest(brand=brand, model=model, color=color, category=category, size=size,
                                                  max_price=max_price, use_case=q, sort=sort if sort in ("relevance", "price_asc", "price_desc") else "relevance", limit=limit))
    return {"products": res.products, "relaxed_constraints": res.relaxed_constraints, "route": res.route,
            "inventory_status": res.inventory_status, "next_cursor": None}


@router.get("/products/{product_id}", response_model=ProductDetail)
async def product_detail(product_id: str, db: AsyncSession = Depends(get_db)):
    p = (await db.execute(select(Product).where((Product.id == product_id) | (Product.model_id == product_id)))).scalar_one_or_none()
    if not p:
        raise http_error(404, "PRODUCT_NOT_FOUND", "Product not found")
    variants = (await db.execute(select(ProductVariant).where(ProductVariant.product_id == p.id, ProductVariant.active == True))).scalars().all()  # noqa: E712
    groups: dict[str, list[ProductVariant]] = {}
    for v in variants:
        groups.setdefault(v.image_group_id, []).append(v)
    attrs = {a.image_group_id: a for a in (await db.execute(select(EnrichedAttributes).where(EnrichedAttributes.image_group_id.in_(list(groups))))).scalars()}
    images: dict[str, list[str]] = {}
    for img in (await db.execute(select(ProductImage).where(ProductImage.image_group_id.in_(list(groups))).order_by(ProductImage.sort_order))).scalars():
        images.setdefault(img.image_group_id, []).append(img.url)
    inv = InventoryService(db)
    try:
        stock = await inv.batch_stock([v.id for v in variants])
        inventory_status = "ok"
    except InventoryUnavailable:
        stock, inventory_status = {}, "unavailable"
    colorways = []
    for gid, vs in groups.items():
        a = attrs.get(gid)
        colorways.append({
            "image_group_id": gid, "colorway_code": vs[0].colorway_code, "images": images.get(gid, []),
            "primary_color": a.primary_color if a else None,
            "color_confidence": "verified" if a and a.review_status == "approved" and a.primary_color else ("unverified" if a and a.primary_color else "unknown"),
            "secondary_colors": a.secondary_colors if a else [], "style": a.style if a else None, "tags": a.tags if a else [],
            "attribute_source": a.source if a else None, "review_status": a.review_status if a else None,
            "price": min(v.price for v in vs), "currency": vs[0].currency,
            "variants": [{"variant_id": v.id, "sku": v.sku, "size": v.size, "price": v.price,
                          "stock_status": ("unknown" if inventory_status != "ok" else ("in_stock" if v.id in stock else "out_of_stock")),
                          "store_count": len(set(stock[v.id].store_ids)) if v.id in stock else 0}
                         for v in sorted(vs, key=lambda x: float(x.size))],
        })
    return ProductDetail(product_id=p.id, model_id=p.model_id, brand=p.brand, name=p.name, description=p.description,
                         category=p.category, base_price=p.base_price, currency=p.currency, colorways=colorways)


@router.get("/variants/{variant_id}/availability", response_model=AvailabilityResponse)
async def variant_availability(variant_id: str, size: str | None = None, location_token: str | None = None, db: AsyncSession = Depends(get_db)):
    v = (await db.execute(select(ProductVariant).where(ProductVariant.id == variant_id))).scalar_one_or_none()
    if not v:
        raise http_error(404, "VARIANT_NOT_FOUND", "Variant not found")
    if size and size != v.size:
        sib = (await db.execute(select(ProductVariant).where(ProductVariant.image_group_id == v.image_group_id, ProductVariant.size == size))).scalar_one_or_none()
        if not sib:
            return AvailabilityResponse(variant_id=None, model_id=None, size=size, stores=[], stock_checked_at=None, available_sizes=[])
        v = sib
    loc = location_store.resolve(location_token)
    inv = InventoryService(db)
    try:
        stores, checked = await inv.store_availability(v.id, location=(loc.lat, loc.lon) if loc else None)
    except InventoryUnavailable:
        return AvailabilityResponse(variant_id=v.id, model_id=None, size=v.size, stores=[], stock_checked_at=None, inventory_status="unavailable")
    p = (await db.execute(select(Product).where(Product.id == v.product_id))).scalar_one()
    sibs = (await db.execute(select(ProductVariant.id).where(ProductVariant.image_group_id == v.image_group_id))).scalars().all()
    stock = await inv.batch_stock(list(sibs))
    return AvailabilityResponse(variant_id=v.id, model_id=p.model_id, size=v.size,
                                stores=[StoreAvailability(**{**s, "size": v.size}) for s in stores], stock_checked_at=checked,
                                location_known=bool(loc), available_sizes=sorted({s.size for s in stock.values()}, key=float))
