"""Core data types shared by every stage of the pipeline.

All times are in seconds (float) relative to the start of the source media.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class Word:
    text: str
    start: float
    end: float
    probability: float = 1.0


@dataclass
class Segment:
    """A sentence-like chunk of speech (as produced by the speech recognizer)."""

    id: int
    start: float
    end: float
    text: str
    words: list[Word] = field(default_factory=list)


@dataclass
class Transcript:
    language: str
    duration: float
    segments: list[Segment]

    @property
    def words(self) -> list[Word]:
        return [w for s in self.segments for w in s.words]

    def to_json(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(asdict(self), ensure_ascii=False, indent=1), encoding="utf-8")

    @classmethod
    def from_json(cls, path: str | Path) -> "Transcript":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        segments = [
            Segment(
                id=s["id"], start=s["start"], end=s["end"], text=s["text"],
                words=[Word(**w) for w in s.get("words", [])],
            )
            for s in data["segments"]
        ]
        return cls(language=data["language"], duration=data["duration"], segments=segments)


@dataclass
class Cut:
    """A range of the source that should be removed, and why."""

    start: float
    end: float
    reason: str  # "silence" | "filler" | "retake" | "ai" | ...
    note: str = ""

    @property
    def duration(self) -> float:
        return self.end - self.start


@dataclass
class Range:
    """A range of the source that is kept in the edit."""

    start: float
    end: float

    @property
    def duration(self) -> float:
        return self.end - self.start
