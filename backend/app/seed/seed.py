"""Idempotent seeding of demo catalog, stores, inventory, and fixture attributes."""
from __future__ import annotations

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import (EnrichedAttributes, EnrichmentJob, Inventory, Product, ProductImage, ProductVariant, Store,
                  utcnow)
from .demo_catalog import (PRODUCTS, STORES, content_hash, deterministic_quantity, fixture_attributes,
                           image_group_id, image_url, sku)


async def seed_demo(db: AsyncSession, *, force: bool = False) -> dict:
    existing = (await db.execute(select(func.count()).select_from(Product))).scalar_one()
    if existing and not force:
        return {"seeded": False, "reason": "catalog already present", "products": existing}
    if existing and force:
        for table in (Inventory, EnrichmentJob, EnrichedAttributes, ProductImage, ProductVariant, Product, Store):
            await db.execute(delete(table))
        await db.flush()

    stores = [Store(**s) for s in STORES]
    db.add_all(stores)
    await db.flush()

    n_variants = 0
    fixture = fixture_attributes()
    for p in PRODUCTS:
        product = Product(model_id=p.model_id, brand=p.brand, name=p.name, description=p.description,
                          category=p.category, base_price=p.price, currency="GBP")
        db.add(product)
        await db.flush()
        for cw in p.colorways:
            gid = image_group_id(p.model_id, cw.code)
            url = image_url(p.model_id, cw)
            db.add(ProductImage(image_group_id=gid, url=url, content_hash=content_hash(url), view_type="front", sort_order=0))
            if gid in fixture:
                f = fixture[gid]
                db.add(EnrichedAttributes(image_group_id=gid, primary_color=f["primary_color"],
                                          secondary_colors=f["secondary_colors"], style=f["style"], category=f["category"],
                                          tags=f["tags"], source=f["source"], evidence=f["evidence"],
                                          review_status=f["review_status"], model_version="fixture-v1",
                                          image_hash=content_hash(url), processed_at=utcnow()))
            for size in p.sizes:
                variant = ProductVariant(product_id=product.id, sku=sku(p.model_id, cw.code, size), colorway_code=cw.code,
                                         size=size, price=p.price, currency="GBP", image_group_id=gid, active=True)
                db.add(variant)
                await db.flush()
                n_variants += 1
                for store in stores:
                    qty = deterministic_quantity(variant.sku, store.name)
                    db.add(Inventory(variant_id=variant.id, store_id=store.id, quantity=qty, version=1))
    await db.commit()
    return {"seeded": True, "products": len(PRODUCTS), "variants": n_variants, "stores": len(stores)}
