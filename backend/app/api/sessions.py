from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from .. import analytics
from ..agent.controller import AgentController, DuplicateTurn
from ..agent.state import get_session_store
from ..db import get_db
from ..inventory.location import geocode, location_store
from ..providers.factory import build_llm
from ..schemas import (LocationConsent, LocationToken, MessageIn, MessageOut, Preferences, SessionCreate, SessionOut)
from ..services_settings import load_effective_config
from .deps import http_error, load_session_or_404

router = APIRouter(tags=["sessions"])
_session_rate: dict[str, list[float]] = {}


def _rate_limit(ip: str, limit: int = 60, window: int = 60) -> None:
    now = time.time()
    if len(_session_rate) > 10_000:  # bound memory: drop idle clients
        for k in [k for k, v in _session_rate.items() if not v or now - v[-1] > window]:
            _session_rate.pop(k, None)
    hits = [t for t in _session_rate.get(ip, []) if now - t < window]
    if len(hits) >= limit:
        raise http_error(429, "RATE_LIMITED", "Too many requests; slow down.")
    _session_rate[ip] = hits + [now]


@router.post("/sessions", response_model=SessionOut)
async def create_session(request: Request, body: SessionCreate | None = None, db: AsyncSession = Depends(get_db)):
    _rate_limit(request.client.host if request.client else "unknown", limit=30)
    cfg = await load_effective_config(db)
    s = await get_session_store().create(str(uuid.uuid4()))
    if body and body.locale:
        s.language = body.locale[:8]
    await get_session_store().save(s)
    await analytics.track(db, "session_started", session_id=s.session_id)
    return SessionOut(session_id=s.session_id, expires_at=datetime.fromtimestamp(s.expires_at, tz=timezone.utc),
                      mode=cfg.effective_mode,
                      capabilities={"server_stt": cfg.voice_live, "server_tts": cfg.voice_live and bool(cfg.voice_id),
                                    "llm": "openai" if cfg.llm_live else "mock", "currency": cfg.currency,
                                    "silence_ms": cfg.silence_ms})


@router.post("/sessions/{session_id}/messages", response_model=MessageOut)
async def post_message(session_id: str, body: MessageIn, request: Request, db: AsyncSession = Depends(get_db)):
    _rate_limit(request.client.host if request.client else "unknown")
    session = await load_session_or_404(session_id)
    cfg = await load_effective_config(db)
    controller = AgentController(db, cfg, build_llm(cfg))
    t0 = time.perf_counter()
    try:
        outcome = await controller.handle_turn(session, body.turn_id, body.text)
    except DuplicateTurn:
        raise http_error(409, "DUPLICATE_TURN", "This turn was already processed")
    await get_session_store().save(session)
    await analytics.track(db, "query_submitted", session_id=session_id, turn_id=body.turn_id,
                          latency_ms=round((time.perf_counter() - t0) * 1000), meta={"mode": cfg.effective_mode, "products": len(outcome.products)})
    return MessageOut(turn_id=body.turn_id, message=outcome.message, products=outcome.products, stores=outcome.stores,
                      preferences=session.preferences, selected_variant_id=session.selected_variant_id, state=outcome.state,
                      relaxed_constraints=outcome.relaxed_constraints, is_demo=not cfg.llm_live)


@router.get("/sessions/{session_id}")
async def get_session(session_id: str):
    s = await load_session_or_404(session_id)
    return {"session_id": s.session_id, "preferences": s.preferences, "selected_variant_id": s.selected_variant_id,
            "recent_messages": s.recent_messages, "location_known": bool(location_store.resolve(s.location_token))}


@router.post("/sessions/{session_id}/select")
async def select_variant(session_id: str, body: dict):
    s = await load_session_or_404(session_id)
    vid = body.get("variant_id")
    if not isinstance(vid, str) or len(vid) > 64:
        raise http_error(400, "INVALID_VARIANT", "variant_id required")
    s.selected_variant_id = vid
    await get_session_store().save(s)
    return {"selected_variant_id": vid}


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(session_id: str, db: AsyncSession = Depends(get_db)):
    await get_session_store().delete(session_id)
    await analytics.track(db, "session_ended", session_id=session_id)
    return None


@router.post("/sessions/{session_id}/location/consent", response_model=LocationToken)
async def location_consent(session_id: str, body: LocationConsent):
    s = await load_session_or_404(session_id)
    if body.latitude is not None and body.longitude is not None:
        token, exp = location_store.issue(body.latitude, body.longitude, "your location")
        label = "your location"
    else:
        geo = geocode(body.postcode, body.city)
        if not geo:
            raise http_error(422, "LOCATION_UNRESOLVED", "Could not resolve that postcode or city (demo geocoder covers major UK cities).")
        token, exp = location_store.issue(geo[0], geo[1], geo[2])
        label = geo[2]
    s.location_token = token
    await get_session_store().save(s)
    return LocationToken(location_token=token, expires_at=datetime.fromtimestamp(exp, tz=timezone.utc), label=label)


@router.post("/location/consent", response_model=LocationToken)
async def location_consent_anonymous(body: LocationConsent):
    if body.latitude is not None and body.longitude is not None:
        token, exp = location_store.issue(body.latitude, body.longitude, "your location")
        return LocationToken(location_token=token, expires_at=datetime.fromtimestamp(exp, tz=timezone.utc), label="your location")
    geo = geocode(body.postcode, body.city)
    if not geo:
        raise http_error(422, "LOCATION_UNRESOLVED", "Could not resolve that postcode or city.")
    token, exp = location_store.issue(geo[0], geo[1], geo[2])
    return LocationToken(location_token=token, expires_at=datetime.fromtimestamp(exp, tz=timezone.utc), label=geo[2])


@router.get("/config/public")
async def public_config(db: AsyncSession = Depends(get_db)):
    """Non-secret runtime info for the storefront."""
    cfg = await load_effective_config(db)
    return {"mode": cfg.effective_mode, "server_stt": cfg.voice_live, "server_tts": cfg.voice_live and bool(cfg.voice_id),
            "currency": cfg.currency, "silence_ms": cfg.silence_ms, "demo_data": True}
