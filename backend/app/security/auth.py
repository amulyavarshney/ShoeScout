"""Admin authentication: Argon2id password, HttpOnly signed session cookie, CSRF token, login rate limit."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from urllib.parse import urlparse

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Depends, HTTPException, Request, Response

from ..config import get_settings

COOKIE_NAME = "shoescout_admin"
CSRF_HEADER = "x-csrf-token"
SESSION_TTL = 8 * 3600
_ph = PasswordHasher()
_login_attempts: dict[str, list[float]] = {}
_runtime_hash: str | None = None


def hash_password(password: str) -> str:
    return _ph.hash(password)


def _auth_secret() -> bytes:
    s = get_settings()
    if s.admin_auth_secret:
        return s.admin_auth_secret.encode()
    if s.is_production:
        raise RuntimeError("ADMIN_AUTH_SECRET is required in production")
    return hashlib.sha256(b"dev-admin-secret|" + s.encryption_key()).digest()


def admin_configured() -> bool:
    s = get_settings()
    return bool(s.admin_password_hash or s.admin_password)


def _password_hash() -> str | None:
    global _runtime_hash
    s = get_settings()
    if s.admin_password_hash:
        return s.admin_password_hash
    if s.admin_password:
        if _runtime_hash is None:
            _runtime_hash = hash_password(s.admin_password)
        return _runtime_hash
    return None


def verify_login(username: str, password: str, client_ip: str) -> bool:
    now = time.time()
    if len(_login_attempts) > 10_000:
        for k in [k for k, v in _login_attempts.items() if not v or now - v[-1] > 300]:
            _login_attempts.pop(k, None)
    attempts = [t for t in _login_attempts.get(client_ip, []) if now - t < 300]
    if len(attempts) >= 10:
        raise HTTPException(status_code=429, detail={"code": "RATE_LIMITED", "message": "Too many login attempts; try later."})
    s = get_settings()
    h = _password_hash()
    ok = False
    if h and hmac.compare_digest(username, s.admin_username):
        try:
            ok = _ph.verify(h, password)
        except VerifyMismatchError:
            ok = False
    # Only failed attempts count toward the limit; a success clears the window.
    _login_attempts[client_ip] = [] if ok else attempts + [now]
    return ok


def _sign(payload: bytes) -> str:
    return base64.urlsafe_b64encode(hmac.new(_auth_secret(), payload, hashlib.sha256).digest()).decode().rstrip("=")


def _cookie_flags(secure: bool) -> tuple[bool, str]:
    """Pages on github.io calls the API on another site, so that cookie must be SameSite=None."""
    host = (urlparse(get_settings().frontend_origin).hostname or "").lower()
    if host not in {"", "localhost", "127.0.0.1"}:
        return True, "None"
    return secure, "Lax"


def _write_cookie(response: Response, value: str, max_age: int, *, secure: bool) -> None:
    cookie_secure, samesite = _cookie_flags(secure)
    parts = [f"{COOKIE_NAME}={value}", "HttpOnly", "Path=/", f"Max-Age={max_age}", f"SameSite={samesite}"]
    if cookie_secure:
        parts.append("Secure")
    if samesite == "None":
        parts.append("Partitioned")
    response.headers.append("set-cookie", "; ".join(parts))


def issue_session(response: Response, username: str, *, secure: bool) -> str:
    csrf = secrets.token_urlsafe(24)
    payload = json.dumps({"u": username, "exp": time.time() + SESSION_TTL, "csrf": csrf, "n": secrets.token_hex(8)}).encode()
    token = base64.urlsafe_b64encode(payload).decode().rstrip("=") + "." + _sign(payload)
    _write_cookie(response, token, SESSION_TTL, secure=secure)
    return csrf


def clear_session(response: Response) -> None:
    _write_cookie(response, "", 0, secure=get_settings().is_production)


def read_session(request: Request) -> dict | None:
    raw = request.cookies.get(COOKIE_NAME)
    if not raw or "." not in raw:
        return None
    b64, sig = raw.rsplit(".", 1)
    try:
        payload = base64.urlsafe_b64decode(b64 + "=" * (-len(b64) % 4))
    except Exception:
        return None
    if not hmac.compare_digest(_sign(payload), sig):
        return None
    data = json.loads(payload)
    if data.get("exp", 0) < time.time():
        return None
    return data


def require_admin(request: Request) -> dict:
    sess = read_session(request)
    if not sess:
        raise HTTPException(status_code=401, detail={"code": "UNAUTHORIZED", "message": "Admin login required"})
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        token = request.headers.get(CSRF_HEADER)
        if not token or not hmac.compare_digest(token, sess.get("csrf", "")):
            raise HTTPException(status_code=403, detail={"code": "CSRF_FAILED", "message": "Missing or invalid CSRF token"})
    return sess


AdminDep = Depends(require_admin)
