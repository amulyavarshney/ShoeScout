"""Endpointing state machine. Pure logic (no I/O) so it is unit-testable with synthetic frame streams."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class TurnState(str, Enum):
    LISTENING = "listening"
    IN_SPEECH = "in_speech"
    POSSIBLE_END = "possible_end"
    FINALIZING = "finalizing"


@dataclass
class TurnDetectorConfig:
    frame_ms: int = 20
    silence_ms: int = 750          # endpoint threshold
    min_speech_ms: int = 200       # reject clicks
    no_speech_timeout_ms: int = 10000
    max_utterance_ms: int = 20000


@dataclass
class TurnEvent:
    kind: str   # speech_start | endpoint | no_speech | max_utterance
    speech_ms: int = 0


@dataclass
class TurnDetector:
    cfg: TurnDetectorConfig = field(default_factory=TurnDetectorConfig)
    state: TurnState = TurnState.LISTENING
    speech_ms: int = 0
    silence_ms: int = 0
    idle_ms: int = 0
    generation: int = 0

    def reset(self) -> None:
        self.state = TurnState.LISTENING
        self.speech_ms = self.silence_ms = self.idle_ms = 0
        self.generation += 1

    def feed(self, is_speech: bool) -> TurnEvent | None:
        f = self.cfg.frame_ms
        if self.state == TurnState.FINALIZING:
            return None
        if self.state == TurnState.LISTENING:
            if is_speech:
                self.speech_ms = f
                self.silence_ms = 0
                self.state = TurnState.IN_SPEECH
                return TurnEvent("speech_start")
            self.idle_ms += f
            if self.idle_ms >= self.cfg.no_speech_timeout_ms:
                self.idle_ms = 0
                return TurnEvent("no_speech")
            return None
        if is_speech:
            self.speech_ms += f + self.silence_ms  # pauses inside speech count toward utterance length
            self.silence_ms = 0
            self.state = TurnState.IN_SPEECH
            if self.speech_ms >= self.cfg.max_utterance_ms:
                self.state = TurnState.FINALIZING
                return TurnEvent("max_utterance", self.speech_ms)
            return None
        # silence frame while in speech / possible end
        self.silence_ms += f
        self.state = TurnState.POSSIBLE_END
        if self.silence_ms >= self.cfg.silence_ms:
            if self.speech_ms < self.cfg.min_speech_ms:
                self.reset()
                return None  # too short: noise, keep listening (no event)
            self.state = TurnState.FINALIZING
            return TurnEvent("endpoint", self.speech_ms)
        return None
