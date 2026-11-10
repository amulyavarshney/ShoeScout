"""Offline enrichment: idempotent on (image_group_id, image_hash, model_version); retry with backoff; dead-letter."""
from __future__ import annotations

import asyncio
import logging
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import EnrichedAttributes, EnrichmentJob, Product, ProductImage, ProductVariant, get_sessionmaker, utcnow
from ..providers.factory import build_vision
from ..search.index import get_search_backend
from ..search.normalize import norm_category, norm_color
from ..services_settings import load_effective_config

log = logging.getLogger("shoescout.enrichment")
MAX_ATTEMPTS = 3
ALLOWED_IMAGE_HOSTS = {"localhost", "127.0.0.1"}  # plus relative /demo paths; extend with approved CDN hosts
_worker_task: asyncio.Task | None = None
_wake = asyncio.Event()


def image_allowed(url: str) -> bool:
    if url.startswith("/"):
        return True
    host = (urlparse(url).hostname or "").lower()
    return host in ALLOWED_IMAGE_HOSTS or host.endswith(".amazonaws.com") or host.endswith(".cloudfront.net")


def group_hash(images: list[ProductImage]) -> str:
    import hashlib
    return hashlib.sha256("|".join(sorted(i.content_hash for i in images)).encode()).hexdigest()[:32]


async def enqueue_changed(db: AsyncSession, *, force: bool = False) -> dict:
    """Queue a job for every image group whose hash/model_version is not yet enriched (or all, if force)."""
    cfg = await load_effective_config(db)
    vision = build_vision(cfg)
    images = (await db.execute(select(ProductImage))).scalars().all()
    groups: dict[str, list[ProductImage]] = {}
    for img in images:
        groups.setdefault(img.image_group_id, []).append(img)
    attrs = {a.image_group_id: a for a in (await db.execute(select(EnrichedAttributes))).scalars()}
    existing_jobs = {(j.image_group_id, j.image_hash, j.model_version) for j in (await db.execute(select(EnrichmentJob))).scalars()}
    queued = 0
    for gid, imgs in groups.items():
        h = group_hash(imgs)
        a = attrs.get(gid)
        unchanged = a is not None and a.image_hash == h and a.model_version == vision.model_version
        if unchanged and not force:
            continue
        if (gid, h, vision.model_version) in existing_jobs and not force:
            continue
        db.add(EnrichmentJob(image_group_id=gid, image_hash=h, model_version=vision.model_version, status="queued"))
        queued += 1
    await db.commit()
    _wake.set()
    return {"queued": queued, "groups": len(groups), "model_version": vision.model_version}


def validate_attributes(raw: dict, supplier_description: str, previous: EnrichedAttributes | None) -> tuple[dict, str, dict]:
    """Normalise vocabulary; detect supplier/vision disagreement; never silently overwrite."""
    color = norm_color(raw.get("primary_color")) if raw.get("primary_color") not in (None, "unknown") else None
    supplier_colors = [c for c in ("red", "blue", "navy", "black", "white", "grey", "gray", "green", "burgundy", "brown", "tan",
                                   "orange", "pink", "yellow", "purple", "cherry red") if c in supplier_description.lower()]
    supplier_color = norm_color(supplier_colors[0]) if supplier_colors else None
    review = "approved"
    evidence = {"vision_color": raw.get("primary_color"), "supplier_color": supplier_color}
    if supplier_color and color and supplier_color != color:
        review = "needs_review"
        evidence["note"] = "supplier/vision disagreement; supplier label preserved"
        primary = supplier_color
        secondary = sorted(set([color] + [norm_color(c) for c in raw.get("secondary_colors", []) if norm_color(c)]))
    else:
        primary = supplier_color or color
        secondary = [c for c in (norm_color(x) for x in raw.get("secondary_colors", [])) if c and c != primary]
        if primary is None:
            review = "needs_review"
    attrs = {"primary_color": primary, "secondary_colors": secondary, "style": raw.get("style") if raw.get("style") != "unknown" else None,
             "category": norm_category(raw.get("category")) if raw.get("category") not in (None, "unknown") else None,
             "tags": [t for t in raw.get("tags", []) if isinstance(t, str)][:20]}
    return attrs, review, evidence


async def process_job(db: AsyncSession, job: EnrichmentJob) -> None:
    cfg = await load_effective_config(db)
    vision = build_vision(cfg)
    job.status, job.attempts = "running", job.attempts + 1
    await db.commit()
    try:
        images = (await db.execute(select(ProductImage).where(ProductImage.image_group_id == job.image_group_id))).scalars().all()
        variant = (await db.execute(select(ProductVariant).where(ProductVariant.image_group_id == job.image_group_id))).scalars().first()
        product = (await db.execute(select(Product).where(Product.id == variant.product_id))).scalar_one() if variant else None
        urls = [i.url for i in images]
        bad = [u for u in urls if not image_allowed(u)]
        if bad:
            raise RuntimeError("IMAGE_HOST_NOT_ALLOWED")
        raw = await vision.extract_attributes(urls, product.description if product else "")
        prev = (await db.execute(select(EnrichedAttributes).where(EnrichedAttributes.image_group_id == job.image_group_id))).scalar_one_or_none()
        attrs, review, evidence = validate_attributes(raw, product.description if product else "", prev)
        source = "vision" if vision.name != "mock" else "fixture"
        if prev is None:
            prev = EnrichedAttributes(image_group_id=job.image_group_id)
            db.add(prev)
        elif prev.review_status == "reviewed":
            review = "reviewed"  # human decision wins
            attrs = {k: getattr(prev, k) for k in attrs}
        for k, v in attrs.items():
            setattr(prev, k, v)
        prev.source, prev.review_status, prev.evidence = source, review, evidence
        prev.model_version, prev.image_hash, prev.processed_at = job.model_version, job.image_hash, utcnow()
        job.status, job.finished_at, job.error_code, job.error_message = "done", utcnow(), None, None
        await db.commit()
    except Exception as e:  # noqa: BLE001
        msg = str(e)[:300]
        code = msg.split(":")[0][:64] if msg else type(e).__name__
        job.error_code, job.error_message = code, msg
        job.status = "dead" if job.attempts >= MAX_ATTEMPTS else "failed"
        if job.status == "dead":
            job.finished_at = utcnow()
        await db.commit()
        log.warning("enrichment job %s failed (%s): %s", job.id, job.status, code)


async def run_pending(limit: int = 50) -> int:
    processed = 0
    async with get_sessionmaker()() as db:
        jobs = (await db.execute(select(EnrichmentJob).where(EnrichmentJob.status.in_(["queued", "failed"]))
                                 .order_by(EnrichmentJob.created_at).limit(limit))).scalars().all()
        for job in jobs:
            if job.status == "failed":
                await asyncio.sleep(min(8.0, 0.5 * (2 ** job.attempts)))  # exponential backoff
            await process_job(db, job)
            processed += 1
        if processed:
            await get_search_backend().rebuild(db)
    return processed


async def worker_loop() -> None:
    while True:
        try:
            n = await run_pending()
            if n == 0:
                _wake.clear()
                try:
                    await asyncio.wait_for(_wake.wait(), timeout=15)
                except asyncio.TimeoutError:
                    pass
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            log.exception("worker loop error: %s", e)
            await asyncio.sleep(2)


def start_worker() -> None:
    global _worker_task
    if _worker_task is None or _worker_task.done():
        _worker_task = asyncio.create_task(worker_loop())


async def stop_worker() -> None:
    global _worker_task
    if _worker_task:
        _worker_task.cancel()
        try:
            await _worker_task
        except (asyncio.CancelledError, Exception):
            pass
        _worker_task = None
