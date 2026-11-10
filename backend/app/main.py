"""ShoeScout backend — FastAPI application."""
from __future__ import annotations

import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .api import admin, products, sessions
from .config import get_settings
from .db import get_sessionmaker, init_db
from .enrichment.worker import start_worker, stop_worker
from .search.index import get_search_backend
from .seed.seed import seed_demo
from .services_settings import ensure_settings_row
from .ws import voice_gateway

logging.basicConfig(level=logging.INFO, format='{"ts":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}')
log = logging.getLogger("shoescout")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    await init_db()
    async with get_sessionmaker()() as db:
        await ensure_settings_row(db)
        if settings.seed_on_startup:
            res = await seed_demo(db)
            if res.get("seeded"):
                log.info("seeded demo catalog: %s", res)
        n = await get_search_backend().rebuild(db)
        log.info("search index ready: %d docs (%s)", n, type(get_search_backend()).__name__)
    if settings.run_worker:
        start_worker()
    yield
    await stop_worker()


app = FastAPI(title="ShoeScout API", version="1.0.0", lifespan=lifespan, docs_url="/api/docs", openapi_url="/api/openapi.json")

settings = get_settings()
app.add_middleware(CORSMiddleware, allow_origins=sorted({settings.frontend_origin, "http://localhost:3000", "http://127.0.0.1:3000"}),
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("Cache-Control", "no-store")
    return response


@app.exception_handler(HTTPException)
async def http_exc(request: Request, exc: HTTPException):
    detail = exc.detail if isinstance(exc.detail, dict) else {"code": "HTTP_ERROR", "message": str(exc.detail)}
    detail.setdefault("request_id", str(uuid.uuid4()))
    return JSONResponse(status_code=exc.status_code, content={"error": detail})


@app.exception_handler(RequestValidationError)
async def validation_exc(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=422, content={"error": {"code": "VALIDATION_ERROR", "message": "Invalid request",
                                                            "request_id": str(uuid.uuid4()), "details": exc.errors()[:10]}})


@app.exception_handler(Exception)
async def unhandled_exc(request: Request, exc: Exception):
    rid = str(uuid.uuid4())
    log.exception("unhandled error request_id=%s", rid)
    return JSONResponse(status_code=500, content={"error": {"code": "INTERNAL_ERROR", "message": "Something went wrong", "request_id": rid}})


app.include_router(sessions.router, prefix="/api/v1")
app.include_router(products.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")
app.include_router(voice_gateway.router)


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}
