"""Provider protocols and shared data types."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import AsyncIterator, Protocol


@dataclass
class ToolCall:
    call_id: str
    name: str
    arguments: dict
    raw_item: dict | None = None


@dataclass
class AgentRequest:
    system_prompt: str
    messages: list[dict]            # [{role, text}] history + current user message last
    tools: list[dict]
    tool_results: list[tuple[ToolCall, dict]] = field(default_factory=list)  # (call, result) pairs this turn
    previous_response_id: str | None = None
    model: str = ""
    context: dict = field(default_factory=dict)  # preferences / selected variant for mock NLU


@dataclass
class AgentResponse:
    text: str | None
    tool_calls: list[ToolCall]
    response_id: str | None = None
    raw_output: list[dict] = field(default_factory=list)

    @property
    def is_final(self) -> bool:
        return not self.tool_calls


@dataclass
class TranscriptEvent:
    kind: str   # partial | committed | error
    text: str = ""
    error: str | None = None


@dataclass
class AudioChunk:
    data: bytes
    codec: str = "mp3"
    sample_rate: int = 44100


class LLMProvider(Protocol):
    name: str
    async def respond(self, request: AgentRequest) -> AgentResponse: ...


class STTProvider(Protocol):
    name: str
    async def connect(self) -> None: ...
    async def send_audio(self, pcm16: bytes, *, commit: bool = False) -> None: ...
    async def commit(self) -> None: ...
    def events(self) -> AsyncIterator[TranscriptEvent]: ...
    async def close(self) -> None: ...


class TTSProvider(Protocol):
    name: str
    codec: str
    sample_rate: int
    def stream_audio(self, text: str, voice_id: str) -> AsyncIterator[AudioChunk]: ...


class VisionProvider(Protocol):
    name: str
    model_version: str
    async def extract_attributes(self, images: list[str], description: str) -> dict: ...


class ProviderError(Exception):
    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable
