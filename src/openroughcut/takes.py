"""Heuristic detection of repeated / abandoned takes.

Creators who record talking-head video usually repeat a sentence until they
get it right. The last attempt is normally the good one, so for each sentence
we look ahead a few sentences: if a later sentence starts the same way (or is
a near-duplicate), the earlier one is a failed take and gets cut.

This runs offline and costs nothing. ``ai.py`` offers a smarter, Claude-based
pass that also understands meaning and the user's instructions.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from .fillers import normalize
from .models import Cut, Segment, Transcript


def _tokens(text: str) -> list[str]:
    return [t for t in (normalize(w) for w in re.split(r"\s+", text)) if t]


def similarity(a: list[str], b: list[str]) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b, autojunk=False).ratio()


def is_retake(earlier: list[str], later: list[str], threshold: float = 0.6, prefix_words: int = 4) -> bool:
    """True if ``earlier`` looks like a failed attempt at ``later``."""
    if len(earlier) < 2 or len(later) < 2:
        return False
    # 1) the earlier attempt is a (near) duplicate of the later one
    if similarity(earlier, later) >= threshold:
        return True
    # 2) the earlier attempt starts like the later one and was abandoned
    k = min(prefix_words, len(earlier), len(later))
    if k >= 3 and similarity(earlier[:k], later[:k]) >= 0.75 and len(earlier) <= len(later) + 2:
        return True
    return False


def split_sentences(transcript: Transcript) -> list[Segment]:
    """Split recognizer segments at sentence punctuation using word timestamps."""
    out: list[Segment] = []
    for seg in transcript.segments:
        if not seg.words:
            out.append(seg)
            continue
        current = []
        for w in seg.words:
            current.append(w)
            if re.search(r"[.!?…]$", w.text.strip()):
                out.append(_mk(len(out), current))
                current = []
        if current:
            out.append(_mk(len(out), current))
    return out


def _mk(idx: int, words) -> Segment:
    return Segment(id=idx, start=words[0].start, end=words[-1].end,
                   text="".join(w.text for w in words).strip(), words=list(words))


def detect_retakes(transcript: Transcript, lookahead: int = 3, threshold: float = 0.6) -> list[Cut]:
    sentences = split_sentences(transcript)
    toks = [_tokens(s.text) for s in sentences]
    cuts: list[Cut] = []
    for i, sent in enumerate(sentences):
        for j in range(i + 1, min(len(sentences), i + 1 + lookahead)):
            if is_retake(toks[i], toks[j], threshold):
                end = sentences[i + 1].start if i + 1 < len(sentences) else sent.end
                cuts.append(Cut(round(sent.start, 3), round(end, 3), "retake",
                                f'repeated later: "{sent.text[:60]}"'))
                break
    return cuts
