from __future__ import annotations

import uuid

from fastapi import HTTPException

from ..agent.state import Session, get_session_store


def http_error(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message, "request_id": str(uuid.uuid4())})


async def load_session_or_404(session_id: str) -> Session:
    s = await get_session_store().get(session_id)
    if not s:
        raise http_error(404, "SESSION_NOT_FOUND", "Session not found or expired")
    return s
