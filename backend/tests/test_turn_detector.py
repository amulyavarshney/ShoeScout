from app.voice.turn_detector import TurnDetector, TurnDetectorConfig, TurnState
from app.voice.vad import EnergyVAD, VADConfig
import numpy as np


def frames(speech_ms: int, silence_ms: int, frame_ms: int = 20):
    return [True] * (speech_ms // frame_ms) + [False] * (silence_ms // frame_ms)


def run(det, flags):
    events = []
    for f in flags:
        ev = det.feed(f)
        if ev:
            events.append(ev.kind)
    return events


def test_short_pause_does_not_finalize():
    det = TurnDetector(TurnDetectorConfig(silence_ms=750))
    # T10: 300 ms pause mid-sentence, then speech continues, then a real endpoint
    events = run(det, frames(600, 300) + frames(500, 800))
    assert events == ["speech_start", "endpoint"]


def test_silence_800ms_commits_once():
    det = TurnDetector(TurnDetectorConfig(silence_ms=750))
    events = run(det, frames(800, 800) + [False] * 50)
    assert events.count("endpoint") == 1  # T11
    assert det.state == TurnState.FINALIZING


def test_click_rejected_by_min_speech():
    det = TurnDetector(TurnDetectorConfig(silence_ms=750, min_speech_ms=200))
    events = run(det, frames(60, 1000))
    assert "endpoint" not in events
    assert det.state == TurnState.LISTENING


def test_no_speech_timeout():
    det = TurnDetector(TurnDetectorConfig(no_speech_timeout_ms=1000))
    events = run(det, [False] * 60)
    assert "no_speech" in events


def test_max_utterance():
    det = TurnDetector(TurnDetectorConfig(max_utterance_ms=2000))
    events = run(det, [True] * 150)
    assert events[-1] == "max_utterance"


def test_energy_vad_detects_tone_over_silence():
    vad = EnergyVAD(VADConfig())
    sr = 16000
    silence = (np.random.default_rng(0).normal(0, 20, sr // 5)).astype(np.int16).tobytes()  # 200 ms of low noise
    for _ in range(5):
        vad.frames(silence)
    t = np.arange(sr // 5) / sr
    tone = (np.sin(2 * np.pi * 220 * t) * 8000).astype(np.int16).tobytes()
    flags = vad.frames(tone)
    assert sum(flags) >= len(flags) * 0.8
