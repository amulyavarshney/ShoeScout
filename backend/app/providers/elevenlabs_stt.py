"""ElevenLabs Scribe v2 realtime STT over WebSocket (manual commit strategy driven by our server VAD)."""
from __future__ import annotations

import asyncio
import base64
import json
from typing import AsyncIterator

import websockets

from .base import ProviderError, TranscriptEvent

STT_WS = "wss://api.elevenlabs.io/v1/speech-to-text/realtime"
ERROR_TYPES = {"error", "auth_error", "quota_exceeded", "commit_throttled", "unaccepted_terms", "rate_limited", "queue_overflow",
               "resource_exhausted", "session_time_limit_exceeded", "input_error", "invalid_request", "chunk_size_exceeded",
               "insufficient_audio_activity", "transcriber_error"}


class ElevenLabsSTTProvider:
    name = "elevenlabs"

    def __init__(self, api_key: str, model: str = "scribe_v2_realtime", *, sample_rate: int = 16000, language: str | None = None) -> None:
        self._key = api_key
        self.model = model
        self.sample_rate = sample_rate
        self.language = language
        self._ws = None
        self._q: asyncio.Queue[TranscriptEvent | None] = asyncio.Queue()
        self._reader: asyncio.Task | None = None

    async def connect(self) -> None:
        params = f"model_id={self.model}&audio_format=pcm_{self.sample_rate}&commit_strategy=manual"
        if self.language and self.language != "auto":
            params += f"&language_code={self.language}"
        try:
            self._ws = await websockets.connect(f"{STT_WS}?{params}", additional_headers={"xi-api-key": self._key},
                                                max_size=8 * 1024 * 1024, open_timeout=10)
            first = json.loads(await asyncio.wait_for(self._ws.recv(), timeout=10))
        except Exception as e:  # noqa: BLE001
            raise ProviderError("STT_CONNECT", f"Could not connect to ElevenLabs STT: {type(e).__name__}", retryable=True) from e
        if first.get("message_type") != "session_started":
            raise ProviderError("STT_CONNECT", f"Unexpected STT handshake: {first.get('message_type')}")
        self._reader = asyncio.create_task(self._read_loop())

    async def _read_loop(self) -> None:
        try:
            async for raw in self._ws:
                msg = json.loads(raw)
                mt = msg.get("message_type")
                if mt == "partial_transcript":
                    await self._q.put(TranscriptEvent(kind="partial", text=msg.get("text", "")))
                elif mt == "committed_transcript":
                    await self._q.put(TranscriptEvent(kind="committed", text=msg.get("text", "")))
                elif mt in ERROR_TYPES:
                    await self._q.put(TranscriptEvent(kind="error", error=f"{mt}: {str(msg.get('error', ''))[:160]}"))
        except Exception as e:  # noqa: BLE001
            await self._q.put(TranscriptEvent(kind="error", error=f"STT connection closed: {type(e).__name__}"))
        finally:
            await self._q.put(None)

    async def send_audio(self, pcm16: bytes, *, commit: bool = False) -> None:
        if not self._ws:
            return
        await self._ws.send(json.dumps({"message_type": "input_audio_chunk", "audio_base_64": base64.b64encode(pcm16).decode(),
                                        "commit": commit, "sample_rate": self.sample_rate}))

    async def commit(self) -> None:
        await self.send_audio(b"", commit=True)

    async def events(self) -> AsyncIterator[TranscriptEvent]:
        while True:
            ev = await self._q.get()
            if ev is None:
                return
            yield ev

    async def close(self) -> None:
        if self._reader:
            self._reader.cancel()
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
        await self._q.put(None)
