"""Audio format helpers."""
from __future__ import annotations

import numpy as np

SUPPORTED_INPUT = {"pcm_s16le"}


def resample_pcm16(pcm: bytes, src_rate: int, dst_rate: int) -> bytes:
    if src_rate == dst_rate:
        return pcm
    x = np.frombuffer(pcm[: len(pcm) // 2 * 2], dtype=np.int16).astype(np.float32)
    if x.size == 0:
        return b""
    n_out = int(round(x.size * dst_rate / src_rate))
    idx = np.linspace(0, x.size - 1, n_out)
    y = np.interp(idx, np.arange(x.size), x)
    return np.clip(y, -32768, 32767).astype(np.int16).tobytes()
