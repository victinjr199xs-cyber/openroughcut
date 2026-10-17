"""High-level operations shared by the CLI and the local server."""

from __future__ import annotations

import json
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import captions as cap
from .export import TimelineClip, to_edl, to_xmeml
from .fillers import detect_fillers
from .media import extract_audio, probe, read_wav, render_preview
from .models import Cut, Transcript
from .podcast import plan_shots, speaker_activity
from .silence import detect_silences
from .takes import detect_retakes
from .timeline import keep_ranges, merge_cuts, summarize


@dataclass
class CutOptions:
    silence: bool = True
    fillers: bool = True
    retakes: bool = True
    ai: bool = False
    ai_instructions: str | None = None
    ai_model: str = "claude-opus-5-5"
    threshold_db: float = 30.0
    min_silence: float = 0.6
    padding: float = 0.15
    min_keep: float = 0.25
    extra_fillers: list[str] = field(default_factory=list)
    whisper_model: str = "small"
    language: str | None = None
    captions: bool = True
    caption_max_chars: int = 32
    caption_max_words: int | None = None
    caption_uppercase: bool = False
    formats: tuple[str, ...] = ("xml", "edl", "srt", "json")
    render: bool = False


def needs_transcript(o: CutOptions) -> bool:
    return o.fillers or o.retakes or o.ai or o.captions


def load_or_transcribe(video: Path, out_dir: Path, o: CutOptions, log=print) -> Transcript:
    cache = out_dir / f"{video.stem}.transcript.json"
    if cache.exists():
        log(f"using cached transcript {cache}")
        return Transcript.from_json(cache)
    from .transcribe import transcribe

    with tempfile.TemporaryDirectory() as tmp:
        wav = extract_audio(video, Path(tmp) / "audio.wav")
        log(f"transcribing with whisper '{o.whisper_model}' (first run downloads the model)...")
        t = transcribe(wav, model=o.whisper_model, language=o.language,
                       progress=lambda done, total: log(f"  {done:.0f}/{total:.0f}s", end="\r"))
    log("")
    t.to_json(cache)
    return t


def rough_cut(video: str | Path, out_dir: str | Path, o: CutOptions, log=print,
              transcript: Transcript | None = None) -> dict:
    video, out_dir = Path(video), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    info = probe(video)
    if not info.has_audio:
        raise RuntimeError("the input has no audio track, nothing to analyse")

    cuts: list[Cut] = []
    if o.silence:
        with tempfile.TemporaryDirectory() as tmp:
            samples, rate = read_wav(extract_audio(video, Path(tmp) / "audio.wav"))
        cuts += detect_silences(samples, rate, o.threshold_db, o.min_silence, o.padding)
        log(f"silence: {sum(1 for c in cuts if c.reason == 'silence')} pauses")

    if transcript is None and needs_transcript(o):
        transcript = load_or_transcribe(video, out_dir, o, log)
    notes = ""
    if transcript is not None:
        if o.fillers:
            f = detect_fillers(transcript, o.extra_fillers)
            log(f"fillers: {len(f)} words")
            cuts += f
        if o.retakes:
            r = detect_retakes(transcript)
            log(f"retakes (heuristic): {len(r)} sentences")
            cuts += r
        if o.ai:
            from .ai import ai_cuts

            log(f"asking {o.ai_model} for an editorial pass...")
            a, notes = ai_cuts(transcript, o.ai_instructions, model=o.ai_model)
            log(f"ai: {len(a)} sentences. {notes}")
            cuts += a

    keep = keep_ranges(cuts, info.duration, o.min_keep)
    stats = summarize(cuts, info.duration, keep)
    clips = [TimelineClip(info, r.start, r.end) for r in keep]
    stem = video.stem
    outputs: dict[str, str] = {}

    if "xml" in o.formats:
        p = out_dir / f"{stem}.roughcut.xml"
        p.write_text(to_xmeml(clips, name=f"{stem} - rough cut"), encoding="utf-8")
        outputs["xml"] = str(p)
    if "edl" in o.formats:
        p = out_dir / f"{stem}.roughcut.edl"
        p.write_text(to_edl(clips, title=f"{stem} rough cut"), encoding="utf-8")
        outputs["edl"] = str(p)
    if transcript is not None and o.captions and ("srt" in o.formats or "vtt" in o.formats):
        cards = cap.build_captions(transcript, keep, o.caption_max_chars, max_words=o.caption_max_words,
                                   uppercase=o.caption_uppercase)
        if "srt" in o.formats:
            p = out_dir / f"{stem}.roughcut.srt"
            p.write_text(cap.to_srt(cards), encoding="utf-8")
            outputs["srt"] = str(p)
        if "vtt" in o.formats:
            p = out_dir / f"{stem}.roughcut.vtt"
            p.write_text(cap.to_vtt(cards), encoding="utf-8")
            outputs["vtt"] = str(p)
    if "json" in o.formats:
        p = out_dir / f"{stem}.cuts.json"
        p.write_text(json.dumps({
            "source": info.path, "stats": stats, "ai_notes": notes,
            "cuts": [asdict(c) for c in merge_cuts(cuts)],
            "keep": [asdict(r) for r in keep],
        }, ensure_ascii=False, indent=1), encoding="utf-8")
        outputs["json"] = str(p)
    if o.render:
        log("rendering preview with ffmpeg...")
        outputs["preview"] = str(render_preview(video, keep, out_dir / f"{stem}.roughcut.mp4"))

    return {"stats": stats, "outputs": outputs, "ai_notes": notes}


def parse_mic(spec: str) -> tuple[str, int | None]:
    """``"mics.wav:1"`` -> ("mics.wav", 1); a bare path (even ``C:\\x.wav``) -> (path, None)."""
    head, sep, tail = spec.rpartition(":")
    if sep and tail.isdigit() and len(head) > 1:
        return head, int(tail)
    return spec, None


def podcast_edit(cameras: list[str], mics: list[str], out: str | Path, wide: str | None = None,
                 audio: str | None = None, min_shot: float = 2.0, log=print) -> dict:
    """Build a multicam sequence. ``mics`` are files, or ``file:channel`` entries."""
    cam_info = [probe(c) for c in cameras]
    wide_info = probe(wide) if wide else None
    tracks = []
    with tempfile.TemporaryDirectory() as tmp:
        for i, m in enumerate(mics):
            path, ch = parse_mic(m)
            wav = extract_audio(path, Path(tmp) / f"mic{i}.wav", ch)
            samples, rate = read_wav(wav)
            tracks.append(samples)
    activity = speaker_activity(tracks, rate)
    shots = plan_shots(activity, min_shot=min_shot, wide=wide is not None)
    duration = min(i.duration for i in cam_info + ([wide_info] if wide_info else []))
    video = []
    for s in shots:
        if s.start >= duration:
            break
        media = wide_info if s.angle == -1 else cam_info[min(s.angle, len(cam_info) - 1)]
        video.append(TimelineClip(media, s.start, min(s.end, duration)))
    audio_info = probe(audio) if audio else cam_info[0]
    audio_clips = [TimelineClip(audio_info, 0.0, min(duration, audio_info.duration))]
    Path(out).write_text(to_xmeml(video, audio_clips, name="Podcast multicam", seq_info=cam_info[0]),
                         encoding="utf-8")
    counts: dict[str, int] = {}
    for s in shots:
        key = "wide" if s.angle == -1 else f"cam{s.angle + 1}"
        counts[key] = counts.get(key, 0) + 1
    log(f"{len(shots)} shots: {counts}")
    return {"shots": len(shots), "by_angle": counts, "output": str(out)}
