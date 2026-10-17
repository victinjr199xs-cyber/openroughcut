"""Caption generation (SRT / WebVTT) aligned to the edited timeline."""

from __future__ import annotations

from dataclasses import dataclass

from .models import Range, Transcript, Word


@dataclass
class Caption:
    start: float
    end: float
    text: str


def remap(t: float, keep: list[Range]) -> float | None:
    """Map a source time to the edited timeline, or None if it was cut."""
    offset = 0.0
    for r in keep:
        if t < r.start:
            return None
        if t <= r.end:
            return offset + (t - r.start)
        offset += r.duration
    return None


def build_captions(
    transcript: Transcript,
    keep: list[Range] | None = None,
    max_chars: int = 32,
    max_duration: float = 3.0,
    max_words: int | None = None,
    uppercase: bool = False,
) -> list[Caption]:
    """Group words into short caption cards.

    Short cards (``max_words=3``) give the punchy social-media style; the
    defaults produce regular single-line subtitles.
    """
    words: list[Word] = []
    for w in transcript.words:
        if keep is None:
            words.append(w)
            continue
        s, e = remap(w.start, keep), remap(w.end, keep)
        if s is None and e is None:
            continue  # the word was cut out
        if s is None or e is None:
            mid = remap((w.start + w.end) / 2, keep)
            if mid is None:
                continue
            s = mid if s is None else s
            e = mid + 0.05 if e is None else e
        words.append(Word(w.text, s, max(e, s + 0.05), w.probability))

    captions: list[Caption] = []
    current: list[Word] = []

    def flush():
        if current:
            text = " ".join(w.text.strip() for w in current).strip()
            captions.append(Caption(current[0].start, current[-1].end, text.upper() if uppercase else text))
            current.clear()

    for w in words:
        if current:
            candidate = " ".join(x.text.strip() for x in current + [w])
            too_long = len(candidate) > max_chars
            too_slow = w.end - current[0].start > max_duration
            too_many = max_words is not None and len(current) >= max_words
            gap = w.start - current[-1].end > 0.7
            if too_long or too_slow or too_many or gap:
                flush()
        current.append(w)
        if w.text.strip()[-1:] in ".!?":
            flush()
    flush()

    # never overlap: end each card when the next one starts
    for a, b in zip(captions, captions[1:]):
        a.end = min(a.end, b.start)
    return [c for c in captions if c.text]


def _ts(t: float, sep: str) -> str:
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def to_srt(captions: list[Caption]) -> str:
    return "\n".join(f"{i}\n{_ts(c.start, ',')} --> {_ts(c.end, ',')}\n{c.text}\n"
                     for i, c in enumerate(captions, 1))


def to_vtt(captions: list[Caption]) -> str:
    return "WEBVTT\n\n" + "\n".join(f"{_ts(c.start, '.')} --> {_ts(c.end, '.')}\n{c.text}\n" for c in captions)
