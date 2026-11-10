"""Anonymised analytics + in-memory stage metrics (p50/p95)."""
from __future__ import annotations

import logging
import statistics
from collections import defaultdict, deque

from sqlalchemy.ext.asyncio import AsyncSession

from .db import AnalyticsEvent

log = logging.getLogger("shoescout.analytics")
_latencies: dict[str, deque[int]] = defaultdict(lambda: deque(maxlen=500))
_counters: dict[str, int] = defaultdict(int)


def record_latency(stage: str, ms: int) -> None:
    _latencies[stage].append(ms)


def incr(name: str, n: int = 1) -> None:
    _counters[name] += n


def summary() -> dict:
    stages = {}
    for k, v in _latencies.items():
        if v:
            s = sorted(v)
            stages[k] = {"count": len(s), "p50": s[len(s) // 2], "p95": s[min(len(s) - 1, int(len(s) * 0.95))],
                         "mean": round(statistics.fmean(s))}
    return {"stages": stages, "counters": dict(_counters)}


async def track(db: AsyncSession, event_type: str, *, session_id: str | None = None, turn_id: str | None = None,
                latency_ms: int | None = None, meta: dict | None = None) -> None:
    incr(event_type)
    if latency_ms is not None:
        record_latency(event_type, latency_ms)
    try:
        db.add(AnalyticsEvent(session_id=session_id, event_type=event_type, turn_id=turn_id, latency_ms=latency_ms, meta=meta or {}))
        await db.commit()
    except Exception as e:  # noqa: BLE001
        log.debug("analytics write failed: %s", e)
