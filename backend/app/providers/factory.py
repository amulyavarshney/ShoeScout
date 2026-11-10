"""Build providers for a validated config version. Cached per version so a key change invalidates clients."""
from __future__ import annotations

from ..services_settings import EffectiveConfig
from .mock import MockLLMProvider, MockSTTProvider, MockTTSProvider, MockVisionProvider

_llm_cache: dict[int, object] = {}


def build_llm(cfg: EffectiveConfig):
    if cfg.llm_live:
        if cfg.config_version not in _llm_cache:
            from .openai_llm import OpenAILLMProvider
            _llm_cache.clear()
            _llm_cache[cfg.config_version] = OpenAILLMProvider(cfg.openai_key, cfg.llm_model, timeout_s=cfg.provider_timeout_s)
        return _llm_cache[cfg.config_version]
    return MockLLMProvider()


def build_vision(cfg: EffectiveConfig):
    if not cfg.mock_mode_requested and cfg.openai_key:
        from .openai_vision import OpenAIVisionProvider
        return OpenAIVisionProvider(cfg.openai_key, cfg.vision_model, timeout_s=max(cfg.provider_timeout_s, 30))
    return MockVisionProvider()


def build_stt(cfg: EffectiveConfig):
    if cfg.voice_live:
        from .elevenlabs_stt import ElevenLabsSTTProvider
        return ElevenLabsSTTProvider(cfg.elevenlabs_key, cfg.stt_model, language=cfg.language)
    return MockSTTProvider()


def build_tts(cfg: EffectiveConfig):
    if cfg.voice_live:
        from .elevenlabs_tts import ElevenLabsTTSProvider
        return ElevenLabsTTSProvider(cfg.elevenlabs_key, cfg.tts_model, output_format=cfg.tts_output_format, timeout_s=cfg.provider_timeout_s)
    return MockTTSProvider()
