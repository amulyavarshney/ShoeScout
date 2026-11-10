"""App-owned WebSocket protocol: audio in, STT/agent/TTS events out. Provider wire formats never reach the browser."""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from urllib.parse import urlparse

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from .. import analytics
from ..agent.controller import AgentController, DuplicateTurn
from ..agent.state import get_session_store
from ..config import get_settings
from ..db import get_sessionmaker
from ..providers.base import ProviderError
from ..providers.factory import build_llm, build_stt, build_tts
from ..services_settings import load_effective_config
from ..voice.audio_formats import resample_pcm16
from ..voice.turn_detector import TurnDetector, TurnDetectorConfig
from ..voice.vad import EnergyVAD, VADConfig

log = logging.getLogger("shoescout.ws")
router = APIRouter()
STT_RATE = 16000
MAX_AUDIO_QUEUE = 200  # frames; drop oldest under backpressure


def _origin_ok(ws: WebSocket) -> bool:
    origin = ws.headers.get("origin")
    if not origin:
        return True  # non-browser clients (tests); cookies/tokens still gate sessions
    allowed = {get_settings().frontend_origin.rstrip("/")}
    allowed |= {"http://localhost:3000", "http://127.0.0.1:3000"}
    return origin.rstrip("/") in allowed or urlparse(origin).hostname in ("localhost", "127.0.0.1")


class VoiceConnection:
    def __init__(self, ws: WebSocket, session_id: str) -> None:
        self.ws = ws
        self.session_id = session_id
        self.sample_rate = STT_RATE
        self.turn_id: str | None = None
        self.turn_generation = 0
        self.stt = None
        self.vad = EnergyVAD(VADConfig(sample_rate=STT_RATE))
        self.detector = TurnDetector()
        self.transcript_partial = ""
        self.final_transcript: asyncio.Future | None = None
        self.turn_task: asyncio.Task | None = None
        self.stt_task: asyncio.Task | None = None
        self.speaking_turn: str | None = None
        self.cancel_tts = asyncio.Event()
        self.closed = False
        self.auto_endpoint = True
        self.mode = "mock"
        self.speech_end_at: float | None = None

    async def send(self, payload: dict) -> None:
        if self.closed:
            return
        try:
            await self.ws.send_text(json.dumps(payload, default=str))
        except Exception:
            self.closed = True

    async def send_bytes(self, data: bytes) -> None:
        if self.closed:
            return
        try:
            await self.ws.send_bytes(data)
        except Exception:
            self.closed = True

    # ---- lifecycle ----
    async def start(self, msg: dict) -> None:
        self.sample_rate = int(msg.get("sample_rate") or STT_RATE)
        if msg.get("audio_format", "pcm_s16le") != "pcm_s16le":
            await self.send({"type": "error", "code": "UNSUPPORTED_FORMAT", "message": "Only pcm_s16le is supported"})
            return
        async with get_sessionmaker()() as db:
            cfg = await load_effective_config(db)
        self.cfg = cfg
        self.mode = "live" if cfg.voice_live else "mock"
        self.detector = TurnDetector(TurnDetectorConfig(silence_ms=cfg.silence_ms))
        self.auto_endpoint = bool(msg.get("auto_endpoint", True))
        if cfg.voice_live:
            try:
                self.stt = build_stt(cfg)
                await self.stt.connect()
                self.stt_task = asyncio.create_task(self._stt_reader())
            except ProviderError as e:
                self.stt = None
                await self.send({"type": "error", "code": e.code, "message": "Speech recognition is unavailable; please type your request."})
        await self.send({"type": "session.ready", "session_id": self.session_id, "mode": self.mode,
                         "server_stt": self.stt is not None, "server_tts": cfg.voice_live and bool(cfg.voice_id),
                         "silence_ms": cfg.silence_ms})

    async def _stt_reader(self) -> None:
        assert self.stt is not None
        async for ev in self.stt.events():
            if ev.kind == "partial":
                if ev.text and ev.text != self.transcript_partial and self.turn_id:
                    self.transcript_partial = ev.text
                    await self.send({"type": "stt.partial", "turn_id": self.turn_id, "text": ev.text})
            elif ev.kind == "committed":
                if self.final_transcript and not self.final_transcript.done():
                    self.final_transcript.set_result(ev.text)
            elif ev.kind == "error":
                log.warning("stt error: %s", ev.error)
                if self.final_transcript and not self.final_transcript.done():
                    self.final_transcript.set_exception(ProviderError("STT_UNAVAILABLE", ev.error or "stt error"))
                else:
                    await self.send({"type": "error", "turn_id": self.turn_id, "code": "STT_UNAVAILABLE",
                                     "message": "Speech recognition failed. Please try again or type your request."})

    async def audio_start(self, msg: dict) -> None:
        if self.speaking_turn:
            self.cancel_tts.set()  # barge-in: stop stale playback
        self.turn_id = msg.get("turn_id") or str(uuid.uuid4())
        self.turn_generation += 1
        self.transcript_partial = ""
        self.detector.reset()
        self.final_transcript = asyncio.get_event_loop().create_future()
        if self.stt is None:
            await self.send({"type": "error", "turn_id": self.turn_id, "code": "STT_UNAVAILABLE",
                             "message": "Server speech recognition is not configured. Demo mode uses your browser's speech recognition or typed input."})
            return
        await self.send({"type": "agent.state", "turn_id": self.turn_id, "state": "listening"})

    async def audio_frame(self, data: bytes) -> None:
        if not self.turn_id or self.stt is None or self.final_transcript is None or self.final_transcript.done():
            return
        pcm = resample_pcm16(data, self.sample_rate, STT_RATE) if self.sample_rate != STT_RATE else data
        await self.stt.send_audio(pcm)
        self._level_tick = getattr(self, "_level_tick", 0) + 1
        if self._level_tick % 5 == 0:
            await self.send({"type": "audio.level", "turn_id": self.turn_id, "level": round(self.vad.level(pcm), 3)})
        if not self.auto_endpoint:
            return
        for is_speech in self.vad.frames(pcm):
            ev = self.detector.feed(is_speech)
            if ev is None:
                continue
            if ev.kind == "speech_start":
                await self.send({"type": "vad.speech_start", "turn_id": self.turn_id})
            elif ev.kind in ("endpoint", "max_utterance"):
                await self._finalize(reason=ev.kind)
                break
            elif ev.kind == "no_speech":
                await self.send({"type": "vad.no_speech", "turn_id": self.turn_id, "message": "I didn't hear anything."})

    async def audio_end(self, msg: dict) -> None:
        """Client explicitly ended (push-to-talk)."""
        if self.turn_id and self.final_transcript and not self.final_transcript.done():
            await self._finalize(reason="client")

    async def _finalize(self, *, reason: str) -> None:
        if not self.turn_id or self.stt is None or self.final_transcript is None or self.final_transcript.done():
            return
        turn_id, gen = self.turn_id, self.turn_generation
        self.speech_end_at = time.perf_counter()
        await self.send({"type": "agent.state", "turn_id": turn_id, "state": "finalizing", "reason": reason})
        await self.stt.commit()
        try:
            text = await asyncio.wait_for(asyncio.shield(self.final_transcript), timeout=6)
        except asyncio.TimeoutError:
            text = self.transcript_partial
        except ProviderError as e:
            await self.send({"type": "error", "turn_id": turn_id, "code": e.code, "message": "Transcription failed. Please try again or type your request."})
            return
        if gen != self.turn_generation:
            return  # stale
        text = (text or "").strip()
        await self.send({"type": "stt.final", "turn_id": turn_id, "text": text})
        if not text:
            await self.send({"type": "agent.state", "turn_id": turn_id, "state": "listening"})
            self.detector.reset()
            return
        self.turn_task = asyncio.create_task(self.run_turn(turn_id, text))

    async def text_turn(self, msg: dict) -> None:
        text = str(msg.get("text", "")).strip()[:1000]
        turn_id = msg.get("turn_id") or str(uuid.uuid4())
        if not text:
            return
        if self.speaking_turn:
            self.cancel_tts.set()
        self.turn_id = turn_id
        self.turn_generation += 1
        self.turn_task = asyncio.create_task(self.run_turn(turn_id, text, speak=bool(msg.get("speak", True))))

    async def run_turn(self, turn_id: str, text: str, *, speak: bool = True) -> None:
        gen = self.turn_generation
        store = get_session_store()
        session = await store.get(self.session_id)
        if session is None:
            await self.send({"type": "error", "turn_id": turn_id, "code": "SESSION_NOT_FOUND", "message": "Session expired; please reload."})
            return
        async with get_sessionmaker()() as db:
            cfg = await load_effective_config(db)
            controller = AgentController(db, cfg, build_llm(cfg))
            t0 = time.perf_counter()
            try:
                outcome = await controller.handle_turn(session, turn_id, text, emit=self.send)
            except DuplicateTurn:
                return
            await store.save(session)
            await analytics.track(db, "transcript_finalized", session_id=self.session_id, turn_id=turn_id,
                                  latency_ms=round((time.perf_counter() - t0) * 1000))
        if gen != self.turn_generation:
            return
        await self.send({"type": "agent.message", "turn_id": turn_id, "text": outcome.message, "state": outcome.state,
                         "preferences": session.preferences.model_dump(), "selected_variant_id": session.selected_variant_id,
                         "is_demo": not cfg.llm_live})
        if speak:
            await self.speak(turn_id, outcome.message, cfg)
        await self.send({"type": "turn.complete", "turn_id": turn_id})

    async def speak(self, turn_id: str, text: str, cfg) -> None:
        tts = build_tts(cfg)
        if tts.name == "mock" or not cfg.voice_id:
            await self.send({"type": "tts.unavailable", "turn_id": turn_id, "reason": "mock" if tts.name == "mock" else "no_voice_id"})
            return
        self.speaking_turn = turn_id
        self.cancel_tts.clear()
        await self.send({"type": "agent.state", "turn_id": turn_id, "state": "speaking"})
        await self.send({"type": "tts.start", "turn_id": turn_id, "codec": tts.codec, "sample_rate": tts.sample_rate})
        first = None
        try:
            async for chunk in tts.stream_audio(text, cfg.voice_id):
                if self.cancel_tts.is_set() or self.closed:
                    break
                if first is None:
                    first = time.perf_counter()
                    if self.speech_end_at:
                        analytics.record_latency("speech_end_to_first_audio", round((first - self.speech_end_at) * 1000))
                await self.send_bytes(chunk.data)
        except ProviderError as e:
            await self.send({"type": "error", "turn_id": turn_id, "code": e.code, "message": "Speech playback is unavailable; the answer is shown as text."})
        finally:
            self.speaking_turn = None
            await self.send({"type": "tts.end", "turn_id": turn_id, "cancelled": self.cancel_tts.is_set()})

    async def cancel(self, msg: dict) -> None:
        self.cancel_tts.set()
        self.turn_generation += 1
        if self.turn_task and not self.turn_task.done():
            self.turn_task.cancel()
        await self.send({"type": "turn.cancelled", "turn_id": msg.get("turn_id")})
        await self.send({"type": "agent.state", "turn_id": msg.get("turn_id"), "state": "listening"})

    async def close(self) -> None:
        self.closed = True
        self.cancel_tts.set()
        for t in (self.turn_task, self.stt_task):
            if t and not t.done():
                t.cancel()
        if self.stt:
            await self.stt.close()


@router.websocket("/ws/voice")
async def voice_ws(ws: WebSocket):
    # Accept first so the browser receives an application close code (a pre-accept close surfaces as 403/1006).
    await ws.accept()
    if not _origin_ok(ws):
        await ws.send_text(json.dumps({"type": "error", "code": "ORIGIN_FORBIDDEN", "message": "Origin not allowed"}))
        await ws.close(code=4403)
        return
    session_id = ws.query_params.get("session_id")
    if not session_id or await get_session_store().get(session_id) is None:
        await ws.send_text(json.dumps({"type": "error", "code": "SESSION_NOT_FOUND", "message": "Session expired; starting a new one."}))
        await ws.close(code=4401)
        return
    conn = VoiceConnection(ws, session_id)
    try:
        while True:
            msg = await ws.receive()
            if msg.get("type") == "websocket.disconnect":
                break
            if msg.get("bytes") is not None:
                await conn.audio_frame(msg["bytes"])
                continue
            try:
                data = json.loads(msg.get("text") or "{}")
            except json.JSONDecodeError:
                await conn.send({"type": "error", "code": "BAD_FRAME", "message": "Invalid JSON"})
                continue
            t = data.get("type")
            if t == "session.start":
                await conn.start(data)
            elif t == "audio.start":
                await conn.audio_start(data)
            elif t == "audio.end":
                await conn.audio_end(data)
            elif t == "text.turn":
                await conn.text_turn(data)
            elif t == "turn.cancel":
                await conn.cancel(data)
            elif t == "session.stop":
                break
            elif t == "ping":
                await conn.send({"type": "pong"})
    except WebSocketDisconnect:
        pass
    finally:
        await conn.close()
