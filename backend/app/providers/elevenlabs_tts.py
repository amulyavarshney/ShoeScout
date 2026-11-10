"""ElevenLabs streaming TTS over HTTP (chunked) + account/voice helpers."""
from __future__ import annotations

from typing import AsyncIterator

import httpx

from .base import AudioChunk, ProviderError

EL_BASE = "https://api.elevenlabs.io"
FORMAT_INFO = {"mp3_44100_128": ("mp3", 44100), "mp3_22050_32": ("mp3", 22050), "mp3_44100_64": ("mp3", 44100),
               "pcm_16000": ("pcm_s16le", 16000), "pcm_24000": ("pcm_s16le", 24000), "pcm_22050": ("pcm_s16le", 22050)}
WS_INCOMPATIBLE_PREFIXES = ("eleven_v3", "eleven_v4")


class ElevenLabsTTSProvider:
    name = "elevenlabs"

    def __init__(self, api_key: str, model: str, *, output_format: str = "mp3_44100_128", timeout_s: int = 20) -> None:
        self._key = api_key
        self.model = model
        self.output_format = output_format if output_format in FORMAT_INFO else "mp3_44100_128"
        self.codec, self.sample_rate = FORMAT_INFO[self.output_format]
        self.timeout = timeout_s

    async def stream_audio(self, text: str, voice_id: str) -> AsyncIterator[AudioChunk]:
        if not voice_id:
            raise ProviderError("TTS_CONFIG", "No ElevenLabs voice ID configured")
        url = f"{EL_BASE}/v1/text-to-speech/{voice_id}/stream?output_format={self.output_format}"
        body = {"text": text, "model_id": self.model}
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(self.timeout, read=60)) as client:
                async with client.stream("POST", url, headers={"xi-api-key": self._key}, json=body) as r:
                    if r.status_code >= 400:
                        detail = (await r.aread())[:200].decode(errors="ignore")
                        code = "TTS_AUTH" if r.status_code == 401 else "TTS_ERROR"
                        raise ProviderError(code, f"ElevenLabs TTS error {r.status_code}: {detail}")
                    async for chunk in r.aiter_bytes(chunk_size=4096):
                        if chunk:
                            yield AudioChunk(data=chunk, codec=self.codec, sample_rate=self.sample_rate)
        except httpx.TimeoutException as e:
            raise ProviderError("TTS_TIMEOUT", "TTS timed out", retryable=True) from e
        except httpx.HTTPError as e:
            raise ProviderError("TTS_NETWORK", "TTS network error", retryable=True) from e

    async def test_connection(self) -> dict:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.get(f"{EL_BASE}/v1/user", headers={"xi-api-key": self._key})
            if r.status_code == 401:
                return {"ok": False, "error_type": "auth", "message": "API key rejected"}
            if r.status_code >= 400:
                return {"ok": False, "error_type": "http", "message": f"HTTP {r.status_code}"}
            user = r.json()
            details = {"tier": user.get("subscription", {}).get("tier"),
                       "ws_compatible_tts_model": not self.model.startswith(WS_INCOMPATIBLE_PREFIXES)}
            m = await client.get(f"{EL_BASE}/v1/models", headers={"xi-api-key": self._key})
            if m.status_code == 200:
                ids = {x.get("model_id") for x in m.json()}
                details["tts_model_known"] = self.model in ids
                if self.model not in ids:
                    return {"ok": False, "error_type": "model_not_found", "message": f"TTS model '{self.model}' not in account model list", "details": details}
            return {"ok": True, "message": "Connected", "details": details}

    async def list_voices(self) -> list[dict]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.get(f"{EL_BASE}/v2/voices?page_size=50", headers={"xi-api-key": self._key})
        if r.status_code >= 400:
            raise ProviderError("TTS_ERROR", f"Could not list voices: HTTP {r.status_code}")
        return [{"voice_id": v["voice_id"], "name": v.get("name"), "category": v.get("category"), "preview_url": v.get("preview_url")}
                for v in r.json().get("voices", [])]
