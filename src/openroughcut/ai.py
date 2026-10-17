"""Claude-powered editing pass ("tell the AI what you want cut").

Sends the numbered sentences of the transcript (text + timestamps only, never
audio or video) to Claude and asks which ones to remove. Requires the ``ai``
extra and an Anthropic credential (``ANTHROPIC_API_KEY`` or ``ant auth login``).
"""

from __future__ import annotations

from typing import Literal

from .models import Cut, Segment, Transcript
from .takes import split_sentences

DEFAULT_MODEL = "claude-opus-5-5"

SYSTEM_PROMPT = """You are an experienced video editor making the first rough cut of a \
spoken-word recording (talking head, tutorial, vlog or podcast). You receive the \
transcript as numbered sentences with timestamps.

Your job is to choose which sentences to REMOVE so the remaining sentences, played \
in order, form a clean, coherent take:
- When the speaker repeats or restarts a sentence, keep the best (usually the last \
complete) attempt and remove the others.
- Remove abandoned fragments, stutters, false starts, off-topic asides to the crew \
("wait, let me redo that", "is it recording?") and obvious mistakes they correct later.
- Never remove content that is only said once and belongs to the message.
- Follow the editor's instructions below when they are given; they override these defaults.

Prefer keeping over removing when unsure: a human will review every cut."""


def _require_sdk():
    try:
        import anthropic
        from pydantic import BaseModel, Field
    except ImportError as e:  # pragma: no cover - optional extra
        raise RuntimeError("The AI pass needs: pip install 'openroughcut[ai]'") from e
    return anthropic, BaseModel, Field


def format_sentences(sentences: list[Segment]) -> str:
    return "\n".join(f"[{s.id}] ({s.start:.1f}-{s.end:.1f}s) {s.text}" for s in sentences)


def build_request(transcript: Transcript, instructions: str | None) -> tuple[list[Segment], str]:
    sentences = split_sentences(transcript)
    body = (
        f"Language: {transcript.language}\n"
        f"Editor's instructions: {instructions.strip() if instructions else '(none, use your judgement)'}\n\n"
        f"Transcript:\n{format_sentences(sentences)}"
    )
    return sentences, body


def cuts_from_decision(sentences: list[Segment], removals: list[tuple[int, str]]) -> list[Cut]:
    by_id = {s.id: (i, s) for i, s in enumerate(sentences)}
    cuts = []
    for sid, reason in removals:
        if sid not in by_id:
            continue  # ignore ids the model invented
        i, s = by_id[sid]
        end = sentences[i + 1].start if i + 1 < len(sentences) else s.end
        cuts.append(Cut(round(s.start, 3), round(end, 3), "ai", reason))
    return cuts


def ai_cuts(
    transcript: Transcript,
    instructions: str | None = None,
    model: str = DEFAULT_MODEL,
    effort: Literal["low", "medium", "high", "xhigh", "max"] = "medium",
) -> tuple[list[Cut], str]:
    """Return (cuts, editor_notes) chosen by Claude."""
    anthropic, BaseModel, Field = _require_sdk()

    class Removal(BaseModel):
        id: int = Field(description="Sentence number to remove")
        reason: str = Field(description="Short reason, e.g. 'restart of sentence 12'")

    class EditDecision(BaseModel):
        remove: list[Removal]
        notes: str = Field(description="One or two sentences for the editor about the cut")

    sentences, body = build_request(transcript, instructions)
    if not sentences:
        return [], "empty transcript"

    client = anthropic.Anthropic()
    # Server-side fallback: if a safety classifier declines, the API retries on
    # a fallback model inside the same call instead of failing the edit.
    response = client.beta.messages.parse(
        model=model,
        max_tokens=16000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": body}],
        output_config={"effort": effort},
        output_format=EditDecision,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
    )
    if response.stop_reason == "refusal":
        raise RuntimeError("Claude declined to process this transcript.")
    if response.stop_reason == "max_tokens" or response.parsed_output is None:
        raise RuntimeError("Claude's answer was incomplete; try a shorter recording or a lower effort.")
    decision = response.parsed_output
    cuts = cuts_from_decision(sentences, [(r.id, r.reason) for r in decision.remove])
    return cuts, decision.notes
