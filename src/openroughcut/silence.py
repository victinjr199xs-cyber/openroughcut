"""Energy-based silence detection.

The threshold is relative to the loudness of the recording itself, so the same
settings work for quiet and loud microphones: a window is "silent" when its RMS
level is ``threshold_db`` below the 95th-percentile loudness of the file.
"""

from __future__ import annotations

import numpy as np

from .models import Cut


def rms_db(samples: np.ndarray, rate: int, window: float = 0.02) -> np.ndarray:
    """RMS level in dBFS for consecutive windows of ``window`` seconds."""
    hop = max(1, int(rate * window))
    n = len(samples) // hop
    if n == 0:
        return np.full(1, -120.0)
    frames = samples[: n * hop].reshape(n, hop)
    rms = np.sqrt(np.mean(frames.astype(np.float64) ** 2, axis=1))
    return 20 * np.log10(np.maximum(rms, 1e-6))


def detect_silences(
    samples: np.ndarray,
    rate: int,
    threshold_db: float = 30.0,
    min_silence: float = 0.6,
    padding: float = 0.15,
    window: float = 0.02,
    absolute_floor_db: float = -60.0,
) -> list[Cut]:
    """Return removable silent ranges.

    ``padding`` seconds of the silence are kept on each side so cuts don't clip
    word onsets/tails and pacing stays natural.
    """
    levels = rms_db(samples, rate, window)
    reference = float(np.percentile(levels, 95))
    limit = max(reference - threshold_db, absolute_floor_db)
    silent = levels < limit

    cuts: list[Cut] = []
    duration = len(samples) / rate
    i = 0
    n = len(silent)
    while i < n:
        if not silent[i]:
            i += 1
            continue
        j = i
        while j < n and silent[j]:
            j += 1
        start, end = i * window, min(j * window, duration)
        if end - start >= min_silence:
            # keep a little air around speech, but trim fully at file edges
            s = start if i == 0 else start + padding
            e = end if j >= n else end - padding
            if e - s > 0.05:
                cuts.append(Cut(round(float(s), 3), round(float(e), 3), "silence", f"{end - start:.2f}s pause"))
        i = j
    return cuts
