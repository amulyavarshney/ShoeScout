from __future__ import annotations

import csv
import io
import json

from fastapi import APIRouter, Depends, File, Request, Response, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import analytics
from ..config import get_settings
from ..db import (AuditLog, EnrichedAttributes, EnrichmentJob, Inventory, Product, ProductImage, ProductVariant, Store,
                  get_db, utcnow)
from ..enrichment.worker import enqueue_changed
from ..providers.factory import build_llm, build_tts
from ..schemas import (LoginIn, ProviderKeyIn, ProviderStatus, ProviderTestOut, SettingsOut, SettingsPatch)
from ..search.index import get_search_backend
from ..security.auth import (admin_configured, clear_session, issue_session, read_session, require_admin, verify_login)
from ..seed.demo_catalog import content_hash
from ..seed.seed import seed_demo
from ..services_settings import (PROVIDERS, bump_version, delete_key, ensure_settings_row, load_effective_config,
                                 provider_status, store_key)
from .deps import http_error

router = APIRouter(prefix="/admin", tags=["admin"])


async def _audit(db: AsyncSession, actor: str, action: str, detail: dict | None = None) -> None:
    db.add(AuditLog(actor=actor, action=action, detail=detail or {}))
    await db.commit()


@router.get("/auth/status")
async def auth_status(request: Request):
    sess = read_session(request)
    return {"configured": admin_configured(), "authenticated": bool(sess), "username": sess.get("u") if sess else None,
            "csrf": sess.get("csrf") if sess else None}


@router.post("/login")
async def login(body: LoginIn, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    if not admin_configured():
        raise http_error(503, "ADMIN_NOT_CONFIGURED", "Set ADMIN_PASSWORD_HASH (or ADMIN_PASSWORD for local dev) on the server.")
    ip = request.client.host if request.client else "unknown"
    if not verify_login(body.username, body.password, ip):
        await _audit(db, body.username[:64], "login_failed", {"ip": ip})
        raise http_error(401, "INVALID_CREDENTIALS", "Invalid username or password")
    csrf = issue_session(response, body.username, secure=(request.url.scheme == "https" or get_settings().is_production))
    await _audit(db, body.username, "login", {"ip": ip})
    return {"authenticated": True, "username": body.username, "csrf": csrf}


@router.post("/logout")
async def logout(response: Response, admin=Depends(require_admin)):
    clear_session(response)
    return {"authenticated": False}


@router.get("/providers", response_model=list[ProviderStatus])
async def providers(db: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    return [ProviderStatus(**await provider_status(db, p)) for p in PROVIDERS]


@router.put("/providers/{provider}/key", response_model=ProviderStatus)
async def put_key(provider: str, body: ProviderKeyIn, db: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    if provider not in PROVIDERS:
        raise http_error(404, "UNKNOWN_PROVIDER", "Unknown provider")
    key = body.api_key.strip()
    if any(ch.isspace() for ch in key) or len(key) < 16:
        raise http_error(422, "INVALID_KEY_FORMAT", "That does not look like a valid API key")
    status = await store_key(db, provider, key)
    await _audit(db, admin["u"], "provider_key_set", {"provider": provider, "last4": status["last4"]})
    return ProviderStatus(**status)


@router.delete("/providers/{provider}/key", status_code=204)
async def remove_key(provider: str, db: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    if provider not in PROVIDERS:
        raise http_error(404, "UNKNOWN_PROVIDER", "Unknown provider")
    await delete_key(db, provider)
    await _audit(db, admin["u"], "provider_key_removed", {"provider": provider})
    return None


@router.post("/providers/{provider}/test", response_model=ProviderTestOut)
async def test_provider(provider: str, db: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    cfg = await load_effective_config(db)
    try:
        if provider == "openai":
            if not cfg.openai_key:
                return ProviderTestOut(ok=False, provider=provider, message="No OpenAI key configured", error_type="not_configured")
            from ..providers.openai_llm import OpenAILLMProvider
            r = await OpenAILLMProvider(cfg.openai_key, cfg.llm_model, timeout_s=cfg.provider_timeout_s).test_connection()
        elif provider == "elevenlabs":
            if not cfg.elevenlabs_key:
                return ProviderTestOut(ok=False, provider=provider, message="No ElevenLabs key configured", error_type="not_configured")
            from ..providers.elevenlabs_tts import ElevenLabsTTSProvider
            r = await ElevenLabsTTSProvider(cfg.elevenlabs_key, cfg.tts_model, output_format=cfg.tts_output_format, timeout_s=cfg.provider_timeout_s).test_connection()
            if r.get("ok") and not cfg.voice_id:
                r["message"] += "; no voice ID set (TTS will not speak until one is chosen)"
        else:
            raise http_error(404, "UNKNOWN_PROVIDER", "Unknown provider")
    except Exception as e:  # noqa: BLE001
        from ..security.secrets import redact
        return ProviderTestOut(ok=False, provider=provider, message=redact(f"{type(e).__name__}", [cfg.openai_key, cfg.elevenlabs_key]), error_type="exception")
    return ProviderTestOut(ok=bool(r.get("ok")), provider=provider, message=r.get("message", ""), error_type=r.get("error_type"), details=r.get("details", {}))


@router.get("/providers/elevenlabs/voices")
async def list_voices(db: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    cfg = await load_effective_config(db)
    if not cfg.elevenlabs_key:
        return {"voices": [], "reason": "not_configured"}
    from ..providers.elevenlabs_tts import ElevenLabsTTSProvider
    try:
        return {"voices": await ElevenLabsTTSProvider(cfg.elevenlabs_key, cfg.tts_model).list_voices()}
    except Exception as e:  # noqa: BLE001
        return {"voices": [], "reason": type(e).__name__}


@router.get("/settings", response_model=SettingsOut)
async def get_settings_(db: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    row = await ensure_settings_row(db)
    cfg = await load_effective_config(db)
    return SettingsOut(**{k: getattr(row, k) for k in SettingsOut.model_fields if k not in ("effective_mode",)}, effective_mode=cfg.effective_mode)


@router.patch("/settings", response_model=SettingsOut)
async def patch_settings(body: SettingsPatch, db: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    row = await ensure_settings_row(db)
    changes = body.model_dump(exclude_none=True)
    for k, v in changes.items():
        setattr(row, k, v)
    await bump_version(db)
    await db.commit()
    await _audit(db, admin["u"], "settings_updated", {"fields": list(changes)})
    cfg = await load_effective_config(db)
    return SettingsOut(**{k: getattr(row, k) for k in SettingsOut.model_fields if k not in ("effective_mode",)}, effective_mode=cfg.effective_mode)


@router.post("/settings/reset-defaults", response_model=SettingsOut)
async def reset_defaults(db: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    s = get_settings()
    row = await ensure_settings_row(db)
    row.llm_model, row.vision_model, row.stt_model, row.tts_model = s.default_llm_model, s.default_vision_model, s.default_stt_model, s.default_tts_model
    row.voice_id, row.silence_ms, row.language, row.tts_output_format = s.default_elevenlabs_voice_id, 750, "auto", "mp3_44100_128"
    await bump_version(db)
    await db.commit()
    cfg = await load_effective_config(db)
    return SettingsOut(**{k: getattr(row, k) for k in SettingsOut.model_fields if k not in ("effective_mode",)}, effective_mode=cfg.effective_mode)


@router.post("/catalog/seed-demo")
async def seed(force: bool = False, db: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    result = await seed_demo(db, force=force)
    n = await get_search_backend().rebuild(db)
    await _audit(db, admin["u"], "seed_demo", result)
    return {**result, "indexed_docs": n}


@router.post("/catalog/import")
async def import_catalog(file: UploadFile = File(...), db: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    """Import JSON (list of supplier records) or CSV (one row per variant). Upserts products/variants/images/stores/inventory."""
    raw = await file.read()
    if len(raw) > 10 * 1024 * 1024:
        raise http_error(413, "FILE_TOO_LARGE", "Max 10 MB")
    records: list[dict]
    errors: list[str] = []
    if file.filename and file.filename.lower().endswith(".csv"):
        rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
        by_model: dict[str, dict] = {}
        for i, r in enumerate(rows):
            mid = (r.get("model_id") or "").strip()
            if not mid:
                errors.append(f"row {i + 2}: missing model_id")
                continue
            rec = by_model.setdefault(mid, {"model_id": mid, "brand": r.get("brand", "Unknown"), "name": r.get("name", mid),
                                            "supplier_description": r.get("description", ""), "category": r.get("category"),
                                            "price": float(r.get("price") or 0), "image_urls": [], "variants": []})
            if r.get("image_url"):
                rec["image_urls"].append(r["image_url"])
            rec["variants"].append({"variant_id": r.get("sku") or f"{mid}-{r.get('colorway', 'STD')}-{r.get('size')}", "sku": r.get("sku"),
                                    "size": r.get("size"), "colorway": r.get("colorway", "STD"), "price": r.get("price")})
        records = list(by_model.values())
    else:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            raise http_error(422, "INVALID_JSON", f"Invalid JSON: {e.msg}")
        records = data if isinstance(data, list) else data.get("products", [])
        for s in (data.get("stores", []) if isinstance(data, dict) else []):
            existing = (await db.execute(select(Store).where(Store.name == s.get("name")))).scalar_one_or_none()
            if existing is None:
                db.add(Store(name=s["name"], address=s.get("address", ""), city=s.get("city", ""), postcode=s.get("postcode", ""),
                             latitude=float(s.get("latitude", 0)), longitude=float(s.get("longitude", 0))))
        await db.flush()
    upserted = 0
    for rec in records:
        mid = str(rec.get("model_id", "")).strip()
        if not mid:
            errors.append("record missing model_id")
            continue
        p = (await db.execute(select(Product).where(Product.model_id == mid))).scalar_one_or_none()
        if p is None:
            p = Product(model_id=mid, brand=str(rec.get("brand", "Unknown"))[:64], name=str(rec.get("name", mid))[:200],
                        description=str(rec.get("supplier_description") or rec.get("description") or "")[:4000],
                        category=rec.get("category"), base_price=float(rec.get("price") or 0), currency=rec.get("currency", "GBP"))
            db.add(p)
            await db.flush()
        else:
            p.name, p.brand = str(rec.get("name", p.name))[:200], str(rec.get("brand", p.brand))[:64]
            p.description = str(rec.get("supplier_description") or rec.get("description") or p.description)[:4000]
        for v in rec.get("variants", []):
            cw = str(v.get("colorway") or "STD")
            gid = f"{mid}-{cw}"
            sku_ = str(v.get("sku") or f"SKU-{mid}-{cw}-{v.get('size')}")
            size = str(v.get("size", "")).strip()
            if not size:
                errors.append(f"{mid}: variant without size skipped")
                continue
            var = (await db.execute(select(ProductVariant).where(ProductVariant.sku == sku_))).scalar_one_or_none()
            if var is None:
                var = ProductVariant(product_id=p.id, sku=sku_, colorway_code=cw, size=size, price=float(v.get("price") or p.base_price),
                                     currency=p.currency, image_group_id=gid)
                db.add(var)
                await db.flush()
            for st in v.get("stock", []):
                store = (await db.execute(select(Store).where(Store.name == st.get("store")))).scalar_one_or_none()
                if store:
                    inv = (await db.execute(select(Inventory).where(Inventory.variant_id == var.id, Inventory.store_id == store.id))).scalar_one_or_none()
                    if inv is None:
                        db.add(Inventory(variant_id=var.id, store_id=store.id, quantity=int(st.get("quantity", 0))))
                    else:
                        inv.quantity, inv.version = int(st.get("quantity", 0)), inv.version + 1
            for order, url in enumerate(rec.get("image_urls", [])):
                existing = (await db.execute(select(ProductImage).where(ProductImage.image_group_id == gid, ProductImage.url == url))).scalar_one_or_none()
                if existing is None:
                    db.add(ProductImage(image_group_id=gid, url=url, content_hash=content_hash(url), sort_order=order))
            upserted += 1
    await db.commit()
    n = await get_search_backend().rebuild(db)
    await _audit(db, admin["u"], "catalog_import", {"records": len(records), "errors": len(errors)})
    return {"records": len(records), "variants_upserted": upserted, "errors": errors[:50], "indexed_docs": n}


@router.post("/enrichment/run")
async def run_enrichment(force: bool = False, db: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    res = await enqueue_changed(db, force=force)
    await _audit(db, admin["u"], "enrichment_run", res)
    return res


@router.get("/enrichment/jobs")
async def enrichment_jobs(page: int = 1, limit: int = 50, status: str | None = None, db: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    limit = max(1, min(limit, 100))
    q = select(EnrichmentJob).order_by(EnrichmentJob.created_at.desc())
    if status:
        q = q.where(EnrichmentJob.status == status)
    jobs = (await db.execute(q.offset((page - 1) * limit).limit(limit))).scalars().all()
    attrs = {a.image_group_id: a for a in (await db.execute(select(EnrichedAttributes).where(EnrichedAttributes.image_group_id.in_([j.image_group_id for j in jobs])))).scalars()}
    counts = dict((await db.execute(select(EnrichmentJob.status, func.count()).group_by(EnrichmentJob.status))).all())
    return {"page": page, "counts": counts, "jobs": [{
        "id": j.id, "image_group_id": j.image_group_id, "status": j.status, "attempts": j.attempts, "error_code": j.error_code,
        "error_message": j.error_message, "created_at": j.created_at, "finished_at": j.finished_at, "model_version": j.model_version,
        "attributes": ({"primary_color": a.primary_color, "secondary_colors": a.secondary_colors, "source": a.source,
                        "review_status": a.review_status, "evidence": a.evidence} if (a := attrs.get(j.image_group_id)) else None)}
        for j in jobs]}


@router.post("/enrichment/jobs/{job_id}/retry")
async def retry_job(job_id: str, db: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    job = (await db.execute(select(EnrichmentJob).where(EnrichmentJob.id == job_id))).scalar_one_or_none()
    if not job:
        raise http_error(404, "JOB_NOT_FOUND", "Job not found")
    job.status, job.attempts, job.error_code, job.finished_at = "queued", 0, None, None
    await db.commit()
    from ..enrichment.worker import _wake
    _wake.set()
    return {"id": job.id, "status": job.status}


@router.get("/enrichment/review")
async def review_queue(db: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    rows = (await db.execute(select(EnrichedAttributes).where(EnrichedAttributes.review_status == "needs_review"))).scalars().all()
    return [{"image_group_id": a.image_group_id, "primary_color": a.primary_color, "secondary_colors": a.secondary_colors,
             "source": a.source, "evidence": a.evidence, "processed_at": a.processed_at} for a in rows]


@router.post("/enrichment/review/{image_group_id}")
async def review_decide(image_group_id: str, body: dict, db: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    a = (await db.execute(select(EnrichedAttributes).where(EnrichedAttributes.image_group_id == image_group_id))).scalar_one_or_none()
    if not a:
        raise http_error(404, "NOT_FOUND", "No attributes for that group")
    from ..search.normalize import norm_color
    color = norm_color(body.get("primary_color"))
    if not color:
        raise http_error(422, "INVALID_COLOR", "Unknown colour")
    a.primary_color, a.review_status, a.source, a.processed_at = color, "reviewed", "reviewed", utcnow()
    await db.commit()
    await get_search_backend().rebuild(db)
    await _audit(db, admin["u"], "attribute_reviewed", {"image_group_id": image_group_id, "primary_color": color})
    return {"image_group_id": image_group_id, "primary_color": color, "review_status": "reviewed"}


@router.get("/metrics/summary")
async def metrics(db: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    counts = {
        "products": (await db.execute(select(func.count()).select_from(Product))).scalar_one(),
        "variants": (await db.execute(select(func.count()).select_from(ProductVariant))).scalar_one(),
        "stores": (await db.execute(select(func.count()).select_from(Store))).scalar_one(),
        "needs_review": (await db.execute(select(func.count()).select_from(EnrichedAttributes).where(EnrichedAttributes.review_status == "needs_review"))).scalar_one(),
        "enrichment_jobs": dict((await db.execute(select(EnrichmentJob.status, func.count()).group_by(EnrichmentJob.status))).all()),
    }
    return {"catalog": counts, **analytics.summary()}
