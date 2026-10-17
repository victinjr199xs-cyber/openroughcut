"""Thin wrappers around ffmpeg / ffprobe."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import wave
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

import numpy as np

SAMPLE_RATE = 16000


class MediaError(RuntimeError):
    pass


def _tool(name: str) -> str:
    env = os.environ.get(f"ORC_{name.upper()}")
    if env:
        return env
    found = shutil.which(name)
    if not found:
        raise MediaError(f"{name} not found. Install FFmpeg or set ORC_{name.upper()} to its path.")
    return found


@dataclass
class MediaInfo:
    path: str
    duration: float
    fps: Fraction
    width: int | None
    height: int | None
    has_audio: bool
    audio_channels: int

    @property
    def timebase(self) -> int:
        """Integer timebase used by XML/EDL exports (24, 25, 30, 60...)."""
        return max(1, round(float(self.fps)))

    @property
    def ntsc(self) -> bool:
        return self.fps.denominator == 1001


def probe(path: str | Path) -> MediaInfo:
    out = subprocess.run(
        [_tool("ffprobe"), "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
        capture_output=True, text=True, encoding="utf-8",
    )
    if out.returncode != 0:
        raise MediaError(f"ffprobe failed for {path}: {out.stderr.strip()}")
    data = json.loads(out.stdout)
    video = next((s for s in data["streams"] if s.get("codec_type") == "video"), None)
    audio = next((s for s in data["streams"] if s.get("codec_type") == "audio"), None)
    fps = Fraction(30, 1)
    if video and video.get("avg_frame_rate") not in (None, "0/0"):
        fps = Fraction(video["avg_frame_rate"])
    return MediaInfo(
        path=str(Path(path).resolve()),
        duration=float(data["format"].get("duration", 0.0)),
        fps=fps,
        width=int(video["width"]) if video else None,
        height=int(video["height"]) if video else None,
        has_audio=audio is not None,
        audio_channels=int(audio.get("channels", 0)) if audio else 0,
    )


def extract_audio(src: str | Path, dst: str | Path, channel: int | None = None) -> Path:
    """Decode the first audio stream to 16 kHz mono 16-bit WAV.

    ``channel`` picks a single input channel (useful for podcasts recorded with
    one microphone per channel); by default all channels are mixed down.
    """
    dst = Path(dst)
    cmd = [_tool("ffmpeg"), "-y", "-v", "error", "-i", str(src), "-vn"]
    if channel is not None:
        cmd += ["-af", f"pan=mono|c0=c{channel}"]
    cmd += ["-ac", "1", "-ar", str(SAMPLE_RATE), "-c:a", "pcm_s16le", str(dst)]
    out = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if out.returncode != 0:
        raise MediaError(f"ffmpeg could not extract audio from {src}: {out.stderr.strip()}")
    return dst


def read_wav(path: str | Path) -> tuple[np.ndarray, int]:
    """Read a 16-bit PCM WAV into float32 samples in [-1, 1] (mono mixdown)."""
    with wave.open(str(path), "rb") as wf:
        rate = wf.getframerate()
        channels = wf.getnchannels()
        if wf.getsampwidth() != 2:
            raise MediaError("only 16-bit PCM WAV is supported")
        raw = wf.readframes(wf.getnframes())
    samples = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1)
    return samples, rate


def render_preview(src: str | Path, keep: list, dst: str | Path) -> Path:
    """Render the kept ranges into a single file with ffmpeg (re-encodes)."""
    from .timeline import ffmpeg_select_expr  # local import avoids a cycle

    info = probe(src)
    expr = ffmpeg_select_expr(keep)
    cmd = [_tool("ffmpeg"), "-y", "-v", "error", "-i", str(src)]
    filters = []
    maps = []
    if info.width:
        filters.append(f"[0:v]select='{expr}',setpts=N/FRAME_RATE/TB[v]")
        maps += ["-map", "[v]"]
    if info.has_audio:
        filters.append(f"[0:a]aselect='{expr}',asetpts=N/SR/TB[a]")
        maps += ["-map", "[a]"]
    cmd += ["-filter_complex", ";".join(filters), *maps, str(dst)]
    out = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if out.returncode != 0:
        raise MediaError(f"ffmpeg render failed: {out.stderr.strip()[-2000:]}")
    return Path(dst)
