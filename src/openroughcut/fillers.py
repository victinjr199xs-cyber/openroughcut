"""Filler-word detection from word-level timestamps."""

from __future__ import annotations

import re
import unicodedata

from .models import Cut, Transcript

# Only sounds that are (almost) never meaningful. Ambiguous words such as
# "like", "tipo" or "então" are opt-in via --filler-words because removing
# them blindly breaks sentences.
FILLERS: dict[str, set[str]] = {
    "en": {"um", "uh", "uhm", "umm", "uh-huh", "hmm", "mm", "er", "erm", "ah"},
    "pt": {"é", "ééé", "eh", "ehh", "hã", "hum", "hmm", "ã", "ãh", "ah", "uhm", "humm", "aham"},
    "es": {"eh", "em", "este", "mmm", "ehh", "ah", "hmm"},
    "fr": {"euh", "heu", "bah", "hum"},
    "de": {"äh", "ähm", "öhm", "hm", "hmm"},
    "it": {"ehm", "eh", "mmm", "uhm"},
}


def normalize(word: str) -> str:
    word = unicodedata.normalize("NFC", word.strip().lower())
    return re.sub(r"^[^\w]+|[^\w]+$", "", word)


def filler_set(language: str, extra: list[str] | None = None) -> set[str]:
    base = set(FILLERS.get(language[:2], set())) | FILLERS["en"]
    for w in extra or []:
        base.add(normalize(w))
    return base


def detect_fillers(
    transcript: Transcript,
    extra: list[str] | None = None,
    max_length: float = 1.5,
) -> list[Cut]:
    """Cut each filler word, extending into the gap to its neighbours.

    The cut stretches halfway into the gaps before/after the filler so that the
    pause that usually accompanies "um" disappears together with it.
    """
    fillers = filler_set(transcript.language, extra)
    words = transcript.words
    cuts: list[Cut] = []
    for i, w in enumerate(words):
        token = normalize(w.text)
        if not token or token not in fillers or (w.end - w.start) > max_length:
            continue
        prev_end = words[i - 1].end if i > 0 else max(0.0, w.start - 0.1)
        next_start = words[i + 1].start if i + 1 < len(words) else w.end + 0.1
        start = max(prev_end, w.start - (w.start - prev_end) / 2)
        end = min(next_start, w.end + (next_start - w.end) / 2)
        cuts.append(Cut(round(start, 3), round(end, 3), "filler", f'"{w.text.strip()}"'))
    return cuts
