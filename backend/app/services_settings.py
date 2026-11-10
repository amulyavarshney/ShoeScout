"""Effective provider configuration: Settings-stored values override environment; versioned for safe invalidation."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import get_settings
from .db import ProviderCredential, ProviderSettings, utcnow
from .security.secrets import decrypt_secret, encrypt_secret, fingerprint, mask

PROVIDERS = ("openai", "elevenlabs")


@dataclass(frozen=True)
class EffectiveConfig:
    config_version: int
    mock_mode_requested: bool
    openai_key: str | None
    elevenlabs_key: str | None
    openai_source: str
    elevenlabs_source: str
    llm_model: str
    vision_model: str
    stt_model: str
    tts_model: str
    voice_id: str
    tts_output_format: str
    silence_ms: int
    language: str
    provider_timeout_s: int
    currency: str
    updated_at: datetime | None

    @property
    def llm_live(self) -> bool:
        return not self.mock_mode_requested and bool(self.openai_key)

    @property
    def voice_live(self) -> bool:
        return not self.mock_mode_requested and bool(self.elevenlabs_key)

    @property
    def effective_mode(self) -> str:
        return "live" if self.llm_live else "mock"


async def ensure_settings_row(db: AsyncSession) -> ProviderSettings:
    row = (await db.execute(select(ProviderSettings).where(ProviderSettings.id == 1))).scalar_one_or_none()
    if row is None:
        s = get_settings()
        row = ProviderSettings(id=1, llm_model=s.default_llm_model, vision_model=s.default_vision_model,
                               stt_model=s.default_stt_model, tts_model=s.default_tts_model,
                               voice_id=s.default_elevenlabs_voice_id, mock_mode=s.mock_mode, currency=s.default_currency)
        db.add(row)
        await db.commit()
    return row


async def _stored_key(db: AsyncSession, provider: str) -> tuple[str | None, ProviderCredential | None]:
    cred = (await db.execute(select(ProviderCredential).where(ProviderCredential.provider == provider))).scalar_one_or_none()
    if not cred:
        return None, None
    try:
        return decrypt_secret(cred.ciphertext, cred.nonce, aad=provider), cred
    except Exception:
        return None, cred


async def load_effective_config(db: AsyncSession) -> EffectiveConfig:
    row = await ensure_settings_row(db)
    env = get_settings()
    oa, _ = await _stored_key(db, "openai")
    el, _ = await _stored_key(db, "elevenlabs")
    return EffectiveConfig(
        config_version=row.config_version, mock_mode_requested=row.mock_mode,
        openai_key=oa or env.openai_api_key or None, elevenlabs_key=el or env.elevenlabs_api_key or None,
        openai_source="settings" if oa else ("environment" if env.openai_api_key else "none"),
        elevenlabs_source="settings" if el else ("environment" if env.elevenlabs_api_key else "none"),
        llm_model=row.llm_model, vision_model=row.vision_model, stt_model=row.stt_model, tts_model=row.tts_model,
        voice_id=row.voice_id, tts_output_format=row.tts_output_format, silence_ms=row.silence_ms, language=row.language,
        provider_timeout_s=row.provider_timeout_s, currency=row.currency, updated_at=row.updated_at)


async def provider_status(db: AsyncSession, provider: str) -> dict:
    key, cred = await _stored_key(db, provider)
    env = get_settings()
    env_key = env.openai_api_key if provider == "openai" else env.elevenlabs_api_key
    if key:
        return {"provider": provider, "configured": True, "source": "settings", "last4": cred.last4 if cred else None,
                "updated_at": cred.updated_at if cred else None}
    if cred and not key:
        return {"provider": provider, "configured": False, "source": "settings", "last4": cred.last4,
                "updated_at": cred.updated_at, "validation_status": "failed"}
    if env_key:
        return {"provider": provider, "configured": True, "source": "environment", "last4": mask(env_key), "updated_at": None}
    return {"provider": provider, "configured": False, "source": "none", "last4": None, "updated_at": None}


async def store_key(db: AsyncSession, provider: str, api_key: str) -> dict:
    ct, nonce = encrypt_secret(api_key, aad=provider)
    cred = (await db.execute(select(ProviderCredential).where(ProviderCredential.provider == provider))).scalar_one_or_none()
    if cred is None:
        cred = ProviderCredential(provider=provider, ciphertext=ct, nonce=nonce, key_fingerprint=fingerprint(api_key), last4=api_key[-4:])
        db.add(cred)
    else:
        cred.ciphertext, cred.nonce, cred.key_fingerprint, cred.last4 = ct, nonce, fingerprint(api_key), api_key[-4:]
        cred.updated_at = utcnow()
    await bump_version(db)
    await db.commit()
    return await provider_status(db, provider)


async def delete_key(db: AsyncSession, provider: str) -> None:
    cred = (await db.execute(select(ProviderCredential).where(ProviderCredential.provider == provider))).scalar_one_or_none()
    if cred:
        await db.delete(cred)
    await bump_version(db)
    await db.commit()


async def bump_version(db: AsyncSession) -> int:
    row = await ensure_settings_row(db)
    row.config_version += 1
    row.updated_at = utcnow()
    await db.flush()
    return row.config_version
