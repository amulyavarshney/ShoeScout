"""Application configuration (environment-driven)."""
from __future__ import annotations

import base64
import os
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), env_file_encoding="utf-8", extra="ignore")

    app_env: str = Field(default="development", alias="APP_ENV")
    database_url: str = Field(default="sqlite+aiosqlite:///./shoescout.db", alias="DATABASE_URL")
    redis_url: str | None = Field(default=None, alias="REDIS_URL")
    elasticsearch_url: str | None = Field(default=None, alias="ELASTICSEARCH_URL")
    frontend_origin: str = Field(default="http://localhost:3000", alias="FRONTEND_ORIGIN")
    backend_base_url: str = Field(default="http://localhost:8000", alias="BACKEND_BASE_URL")

    # Server-side provider key fallbacks (Settings-stored keys override these).
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    elevenlabs_api_key: str | None = Field(default=None, alias="ELEVENLABS_API_KEY")

    credentials_encryption_key_b64: str | None = Field(default=None, alias="CREDENTIALS_ENCRYPTION_KEY_B64")
    admin_auth_secret: str | None = Field(default=None, alias="ADMIN_AUTH_SECRET")
    admin_username: str = Field(default="admin", alias="ADMIN_USERNAME")
    # Argon2id hash of the admin password. Generate with: python -m scripts.hash_password <password>
    admin_password_hash: str | None = Field(default=None, alias="ADMIN_PASSWORD_HASH")
    # Development convenience: plaintext password, hashed at startup. Never set in production.
    admin_password: str | None = Field(default=None, alias="ADMIN_PASSWORD")

    default_llm_model: str = Field(default="gpt-4.1-mini", alias="DEFAULT_LLM_MODEL")
    default_vision_model: str = Field(default="gpt-4.1-mini", alias="DEFAULT_VISION_MODEL")
    default_stt_model: str = Field(default="scribe_v2_realtime", alias="DEFAULT_STT_MODEL")
    default_tts_model: str = Field(default="eleven_flash_v2_5", alias="DEFAULT_TTS_MODEL")
    default_elevenlabs_voice_id: str = Field(default="", alias="DEFAULT_ELEVENLABS_VOICE_ID")
    default_currency: str = Field(default="GBP", alias="DEFAULT_CURRENCY")
    mock_mode: bool = Field(default=True, alias="MOCK_MODE")
    seed_on_startup: bool = Field(default=True, alias="SEED_ON_STARTUP")
    run_worker: bool = Field(default=True, alias="RUN_WORKER")  # false when a dedicated worker process runs
    session_ttl_seconds: int = Field(default=24 * 3600, alias="SESSION_TTL_SECONDS")
    location_token_ttl_seconds: int = Field(default=3600, alias="LOCATION_TOKEN_TTL_SECONDS")

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() in {"production", "prod"}

    def encryption_key(self) -> bytes:
        """32-byte AES-GCM master key. In development a stable local key is derived if unset."""
        if self.credentials_encryption_key_b64:
            raw = base64.b64decode(self.credentials_encryption_key_b64)
            if len(raw) != 32:
                raise ValueError("CREDENTIALS_ENCRYPTION_KEY_B64 must decode to exactly 32 bytes")
            return raw
        if self.is_production:
            raise RuntimeError("CREDENTIALS_ENCRYPTION_KEY_B64 is required in production")
        # Development fallback: persist a generated key next to the database so restarts keep working.
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".dev_master_key")
        if os.path.exists(path):
            with open(path, "rb") as fh:
                return fh.read()
        key = os.urandom(32)
        with open(path, "wb") as fh:
            fh.write(key)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
        return key


@lru_cache
def get_settings() -> Settings:
    return Settings()
