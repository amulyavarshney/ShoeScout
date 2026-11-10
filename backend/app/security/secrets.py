"""AES-GCM encryption for provider credentials. Master key from server environment, never the DB."""
from __future__ import annotations

import base64
import hashlib
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from ..config import get_settings


def _aead() -> AESGCM:
    return AESGCM(get_settings().encryption_key())


def encrypt_secret(plaintext: str, *, aad: str) -> tuple[str, str]:
    nonce = os.urandom(12)
    ct = _aead().encrypt(nonce, plaintext.encode("utf-8"), aad.encode("utf-8"))
    return base64.b64encode(ct).decode(), base64.b64encode(nonce).decode()


def decrypt_secret(ciphertext_b64: str, nonce_b64: str, *, aad: str) -> str:
    pt = _aead().decrypt(base64.b64decode(nonce_b64), base64.b64decode(ciphertext_b64), aad.encode("utf-8"))
    return pt.decode("utf-8")


def fingerprint(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()[:16]


def mask(secret: str | None) -> str | None:
    if not secret:
        return None
    return secret[-4:] if len(secret) >= 8 else "****"


def redact(text: str, secrets: list[str | None]) -> str:
    """Remove any configured secret value from log/error text."""
    for s in secrets:
        if s and len(s) >= 8:
            text = text.replace(s, "[redacted]")
    return text
