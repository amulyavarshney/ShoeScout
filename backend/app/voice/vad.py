"""Energy-based server VAD with adaptive noise floor (MVP; swap for Silero/WebRTC VAD behind the same interface)."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class VADConfig:
    sample_rate: int = 16000
    frame_ms: int = 20
    start_threshold_db: float = 12.0   # dB above noise floor to count as speech
    noise_floor_init: float = 1e-4
    adapt_rate: float = 0.02


class EnergyVAD:
    def __init__(self, cfg: VADConfig | None = None) -> None:
        self.cfg = cfg or VADConfig()
        self.noise = self.cfg.noise_floor_init
        self._tail = b""

    @property
    def frame_bytes(self) -> int:
        return int(self.cfg.sample_rate * self.cfg.frame_ms / 1000) * 2

    def frames(self, pcm16: bytes) -> list[bool]:
        """Split incoming PCM into fixed frames; returns speech flags per frame."""
        buf = self._tail + pcm16
        n = len(buf) // self.frame_bytes
        flags: list[bool] = []
        for i in range(n):
            frame = buf[i * self.frame_bytes:(i + 1) * self.frame_bytes]
            flags.append(self.is_speech(frame))
        self._tail = buf[n * self.frame_bytes:]
        return flags

    def is_speech(self, frame: bytes) -> bool:
        x = np.frombuffer(frame, dtype=np.int16).astype(np.float32) / 32768.0
        if x.size == 0:
            return False
        energy = float(np.mean(x * x)) + 1e-10
        speech = 10 * np.log10(energy / self.noise) > self.cfg.start_threshold_db
        if not speech:
            self.noise = (1 - self.cfg.adapt_rate) * self.noise + self.cfg.adapt_rate * energy
        return bool(speech)

    def level(self, pcm16: bytes) -> float:
        x = np.frombuffer(pcm16[: len(pcm16) // 2 * 2], dtype=np.int16).astype(np.float32) / 32768.0
        return float(np.sqrt(np.mean(x * x))) if x.size else 0.0
