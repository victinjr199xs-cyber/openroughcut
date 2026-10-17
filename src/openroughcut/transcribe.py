"""Speech-to-text with word timestamps via faster-whisper (runs locally)."""

from __future__ import annotations

from pathlib import Path

from .models import Segment, Transcript, Word

# Whisper is trained to write "clean" transcripts and silently drops "um"/"uh".
# Priming it with a disfluent prompt makes it keep them, which filler removal
# depends on.
DISFLUENT_PROMPTS = {
    "en": "Umm, let me think like, hmm... Okay, uh, here's what I'm, like, thinking.",
    "pt": "É... então, hum, deixa eu ver, ãh... tá, é, eu acho que, hum, é isso.",
    "es": "Eh... bueno, mmm, déjame pensar, este... vale, eh, creo que, mmm, sí.",
    "fr": "Euh... bon, hum, laisse-moi réfléchir, euh... voilà, euh, je pense que.",
    "de": "Äh... also, ähm, lass mich überlegen, äh... ja, ähm, ich glaube.",
    "it": "Ehm... allora, eh, fammi pensare, ehm... ecco, eh, credo che.",
}


def transcribe(
    audio_path: str | Path,
    model: str = "small",
    language: str | None = None,
    device: str = "auto",
    compute_type: str = "int8",
    keep_fillers: bool = True,
    progress=None,
) -> Transcript:
    try:
        from faster_whisper import WhisperModel
    except ImportError as e:  # pragma: no cover - depends on optional extra
        raise RuntimeError(
            "Transcription needs faster-whisper: pip install 'openroughcut[transcribe]'"
        ) from e

    from .media import SAMPLE_RATE, read_wav

    samples, rate = read_wav(audio_path)
    if rate != SAMPLE_RATE:
        raise ValueError(f"expected {SAMPLE_RATE} Hz audio, got {rate} Hz (use media.extract_audio)")

    whisper = WhisperModel(model, device=device, compute_type=compute_type)
    prompt = DISFLUENT_PROMPTS.get((language or "en")[:2]) if keep_fillers else None
    # decoded samples are passed directly so faster-whisper never needs PyAV
    raw_segments, info = whisper.transcribe(
        samples,
        language=language,
        word_timestamps=True,
        # Without VAD, long pauses make Whisper stop early and drop the rest of
        # the recording. Generous padding keeps short hesitations like "um".
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 500, "speech_pad_ms": 200},
        initial_prompt=prompt,
        condition_on_previous_text=False,
    )
    segments: list[Segment] = []
    for seg in raw_segments:
        words = [
            Word(text=w.word, start=round(w.start, 3), end=round(w.end, 3), probability=round(w.probability, 3))
            for w in (seg.words or [])
        ]
        segments.append(Segment(id=len(segments), start=round(seg.start, 3), end=round(seg.end, 3),
                                text=seg.text.strip(), words=words))
        if progress:
            progress(seg.end, info.duration)
    return Transcript(language=info.language, duration=round(info.duration, 3), segments=segments)
