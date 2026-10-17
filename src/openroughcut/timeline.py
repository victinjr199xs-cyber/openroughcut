"""Turn a list of cuts into the ranges that are kept."""

from __future__ import annotations

from .models import Cut, Range


def merge_cuts(cuts: list[Cut], gap: float = 0.05) -> list[Cut]:
    """Merge overlapping or nearly touching cuts, keeping every reason."""
    ordered = sorted((c for c in cuts if c.end > c.start), key=lambda c: c.start)
    merged: list[Cut] = []
    for c in ordered:
        if merged and c.start <= merged[-1].end + gap:
            last = merged[-1]
            reasons = last.reason.split("+")
            if c.reason not in reasons:
                reasons.append(c.reason)
            merged[-1] = Cut(last.start, max(last.end, c.end), "+".join(reasons),
                             "; ".join(n for n in (last.note, c.note) if n))
        else:
            merged.append(Cut(c.start, c.end, c.reason, c.note))
    return merged


def keep_ranges(cuts: list[Cut], duration: float, min_keep: float = 0.25) -> list[Range]:
    """Complement of ``cuts`` within [0, duration].

    Kept fragments shorter than ``min_keep`` seconds are dropped too: a 3-frame
    sliver between two cuts is almost always a glitch, not content.
    """
    keep: list[Range] = []
    pos = 0.0
    for c in merge_cuts(cuts):
        start, end = max(0.0, c.start), min(duration, c.end)
        if start > pos:
            keep.append(Range(round(pos, 3), round(start, 3)))
        pos = max(pos, end)
    if pos < duration:
        keep.append(Range(round(pos, 3), round(duration, 3)))
    return [r for r in keep if r.duration >= min_keep]


def summarize(cuts: list[Cut], duration: float, keep: list[Range]) -> dict:
    by_reason: dict[str, float] = {}
    for c in merge_cuts(cuts):
        by_reason[c.reason] = by_reason.get(c.reason, 0.0) + float(c.duration)
    kept = float(sum(r.duration for r in keep))
    duration = float(duration)
    return {
        "source_seconds": round(duration, 2),
        "kept_seconds": round(kept, 2),
        "removed_seconds": round(duration - kept, 2),
        "removed_percent": round(100 * (duration - kept) / duration, 1) if duration else 0.0,
        "removed_by_reason": {k: round(v, 2) for k, v in sorted(by_reason.items())},
        "clips": len(keep),
    }


def ffmpeg_select_expr(keep: list[Range]) -> str:
    return "+".join(f"between(t,{r.start:.3f},{r.end:.3f})" for r in keep) or "0"
