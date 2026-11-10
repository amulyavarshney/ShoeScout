"""Session memory: structured preferences + bounded recent messages. In-memory with TTL; Redis optional."""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field

from ..config import get_settings
from ..schemas import Preferences

MAX_RECENT = 10


@dataclass
class Session:
    session_id: str
    preferences: Preferences = field(default_factory=Preferences)
    selected_variant_id: str | None = None
    last_results: list[dict] = field(default_factory=list)   # last shown cards (compact)
    recent_messages: list[dict] = field(default_factory=list)
    language: str = "en"
    location_token: str | None = None
    processed_turns: list[str] = field(default_factory=list)
    active_turn: str | None = None
    config_version: int | None = None
    created_at: float = field(default_factory=time.time)
    expires_at: float = 0.0

    def to_json(self) -> str:
        d = asdict(self)
        d["preferences"] = self.preferences.model_dump()
        return json.dumps(d)

    @classmethod
    def from_json(cls, raw: str) -> "Session":
        d = json.loads(raw)
        d["preferences"] = Preferences(**d.get("preferences", {}))
        return cls(**d)

    def add_message(self, role: str, text: str) -> None:
        self.recent_messages.append({"role": role, "text": text})
        self.recent_messages = self.recent_messages[-MAX_RECENT:]


class SessionStore:
    """In-memory store (default)."""

    def __init__(self) -> None:
        self._items: dict[str, Session] = {}

    async def create(self, session_id: str) -> Session:
        ttl = get_settings().session_ttl_seconds
        s = Session(session_id=session_id, expires_at=time.time() + ttl)
        self._items[session_id] = s
        return s

    async def get(self, session_id: str) -> Session | None:
        self._gc()
        s = self._items.get(session_id)
        if s and s.expires_at > time.time():
            return s
        return None

    async def save(self, session: Session) -> None:
        self._items[session.session_id] = session

    async def delete(self, session_id: str) -> None:
        self._items.pop(session_id, None)

    def _gc(self) -> None:
        now = time.time()
        for k in [k for k, v in self._items.items() if v.expires_at <= now]:
            del self._items[k]


class RedisSessionStore(SessionStore):
    def __init__(self, url: str) -> None:
        super().__init__()
        import redis.asyncio as redis
        self.r = redis.from_url(url, decode_responses=True)

    def _key(self, sid: str) -> str:
        return f"shoescout:session:{sid}"

    async def create(self, session_id: str) -> Session:
        s = await super().create(session_id)
        await self.save(s)
        return s

    async def get(self, session_id: str) -> Session | None:
        raw = await self.r.get(self._key(session_id))
        return Session.from_json(raw) if raw else None

    async def save(self, session: Session) -> None:
        ttl = max(1, int(session.expires_at - time.time()))
        await self.r.set(self._key(session.session_id), session.to_json(), ex=ttl)

    async def delete(self, session_id: str) -> None:
        await self.r.delete(self._key(session_id))


_store: SessionStore | None = None


def get_session_store() -> SessionStore:
    global _store
    if _store is None:
        url = get_settings().redis_url
        _store = RedisSessionStore(url) if url else SessionStore()
    return _store


def merge_preferences(current: Preferences, update: dict) -> Preferences:
    """Validated merge: explicit values override; None leaves existing values untouched."""
    data = current.model_dump()
    for k, v in update.items():
        if k in data and v is not None:
            data[k] = v
    return Preferences(**data)
