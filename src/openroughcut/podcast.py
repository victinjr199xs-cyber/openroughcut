"""Podcast mode: switch camera angles to whoever is talking.

Inputs are synchronized camera files (same start time) and one isolated audio
source per speaker (separate files, or channels of one file). The loudest
speaker over a short window gets the shot; a minimum shot length prevents
jittery cutting, and an optional wide shot covers cross-talk and long pauses.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .silence import rms_db


@dataclass
class Shot:
    start: float
    end: float
    angle: int  # index into the camera list; -1 means the wide shot


def speaker_activity(tracks: list[np.ndarray], rate: int, window: float = 0.1,
                     margin_db: float = 6.0) -> np.ndarray:
    """Per window: index of the dominant speaker, -2 for cross-talk, -1 for silence."""
    levels = [rms_db(t, rate, window) for t in tracks]
    n = min(len(lv) for lv in levels)
    stack = np.vstack([lv[:n] for lv in levels])
    # each mic is judged against its own loudness so gain differences don't matter
    floors = np.percentile(stack, 95, axis=1, keepdims=True) - 25.0
    active = stack > floors
    loudest = np.argmax(stack, axis=0)
    ordered = np.sort(stack, axis=0)
    second = ordered[-2] if len(tracks) > 1 else np.full(n, -120.0)
    result = np.where(active.any(axis=0), loudest, -1)
    crosstalk = (active.sum(axis=0) > 1) & (ordered[-1] - second < margin_db)
    result[crosstalk] = -2
    return result


def plan_shots(
    activity: np.ndarray,
    window: float = 0.1,
    min_shot: float = 2.0,
    smoothing: float = 0.8,
    wide: bool = False,
    wide_after: float = 4.0,
) -> list[Shot]:
    n = len(activity)
    if n == 0:
        return []
    smooth = max(1, int(smoothing / window))
    min_len = max(1, int(min_shot / window))
    wide_len = max(1, int(wide_after / window))

    # majority vote over a sliding window removes single-word interjections
    voted = activity.copy()
    for i in range(n):
        seg = activity[max(0, i - smooth // 2): i + smooth // 2 + 1]
        vals, counts = np.unique(seg, return_counts=True)
        voted[i] = vals[np.argmax(counts)]

    current = int(next((v for v in voted if v >= 0), 0))
    shots: list[Shot] = []
    start = 0
    quiet = 0
    for i, v in enumerate(voted):
        v = int(v)
        quiet = quiet + 1 if v < 0 else 0
        target = current
        if v >= 0:
            target = v
        elif wide and (v == -2 or quiet >= wide_len):
            target = -1
        if target != current and (i - start) >= min_len:
            shots.append(Shot(round(start * window, 3), round(i * window, 3), current))
            current, start = target, i
    shots.append(Shot(round(start * window, 3), round(n * window, 3), current))
    return shots
