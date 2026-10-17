"""Timeline exports.

* ``xmeml`` - Final Cut Pro 7 XML. Premiere Pro (File > Import), DaVinci
  Resolve and Final Cut Pro (via conversion) open it as an editable sequence
  whose clips still point at the original media, so every cut can be adjusted.
* ``edl`` - CMX3600 EDL, the lowest common denominator.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from urllib.parse import quote
from xml.sax.saxutils import escape

from .media import MediaInfo


@dataclass
class TimelineClip:
    """One piece of source media placed on the timeline."""

    media: MediaInfo
    src_in: float
    src_out: float


def frames(seconds: float, fps: Fraction) -> int:
    return int(round(seconds * fps))


def path_url(path: str) -> str:
    # Windows drive paths are kept as given, so XML made on any OS can point at them
    p = path if re.match(r"^[A-Za-z]:[\\/]", path) else os.path.abspath(path)
    p = p.replace("\\", "/")
    if not p.startswith("/"):
        p = "/" + p  # Windows drive letter
    return "file://localhost" + quote(p, safe="/")


def _rate(info: MediaInfo) -> str:
    return f"<rate><timebase>{info.timebase}</timebase><ntsc>{'TRUE' if info.ntsc else 'FALSE'}</ntsc></rate>"


class _Ids:
    def __init__(self):
        self.files: dict[str, str] = {}
        self.clip = 0

    def file_id(self, path: str) -> tuple[str, bool]:
        """Return (id, first_time). Full <file> must be written the first time only."""
        if path in self.files:
            return self.files[path], False
        self.files[path] = f"file-{len(self.files) + 1}"
        return self.files[path], True

    def next_clip(self) -> str:
        self.clip += 1
        return f"clipitem-{self.clip}"


def _file_xml(info: MediaInfo, fid: str, full: bool) -> str:
    if not full:
        return f'<file id="{fid}"/>'
    fps = info.fps
    video = ""
    if info.width:
        video = (f"<video><samplecharacteristics>{_rate(info)}<width>{info.width}</width>"
                 f"<height>{info.height}</height></samplecharacteristics></video>")
    audio = ""
    if info.has_audio:
        audio = ("<audio><samplecharacteristics><depth>16</depth><samplerate>48000</samplerate>"
                 f"</samplecharacteristics><channelcount>{info.audio_channels or 2}</channelcount></audio>")
    return (f'<file id="{fid}"><name>{escape(Path(info.path).name)}</name>'
            f"<pathurl>{escape(path_url(info.path))}</pathurl>{_rate(info)}"
            f"<duration>{frames(info.duration, fps)}</duration><media>{video}{audio}</media></file>")


def to_xmeml(
    video: list[TimelineClip],
    audio: list[TimelineClip] | None = None,
    name: str = "OpenRoughCut",
    seq_info: MediaInfo | None = None,
) -> str:
    """Build an FCP7 XML sequence.

    ``video`` clips are laid back to back on V1. ``audio`` defaults to the same
    clips (linked A/V); pass a separate list for e.g. a podcast where the
    picture switches cameras but the sound stays on the mixed track.
    """
    linked = audio is None
    audio = video if audio is None else audio
    ref = seq_info or (video[0].media if video else audio[0].media)
    fps = ref.fps
    ids = _Ids()

    def place(clips: list[TimelineClip]):
        pos, out = 0, []
        for c in clips:
            fin, fout = frames(c.src_in, c.media.fps), frames(c.src_out, c.media.fps)
            out.append((c, pos, pos + (fout - fin), fin, fout))
            pos += fout - fin
        return out, pos

    vplaced, vlen = place(video)
    aplaced, alen = place(audio)
    channels = min(2, max((c.media.audio_channels for c in audio), default=0) or 2)
    vids = [ids.next_clip() for _ in vplaced]
    aids = [[ids.next_clip() for _ in aplaced] for _ in range(channels)]

    def links(k: int) -> str:
        if not linked:
            return ""
        parts = [f"<link><linkclipref>{vids[k]}</linkclipref><mediatype>video</mediatype>"
                 f"<trackindex>1</trackindex><clipindex>{k + 1}</clipindex></link>"]
        for ch in range(channels):
            parts.append(f"<link><linkclipref>{aids[ch][k]}</linkclipref><mediatype>audio</mediatype>"
                         f"<trackindex>{ch + 1}</trackindex><clipindex>{k + 1}</clipindex></link>")
        return "".join(parts)

    def clipitem(cid, c: TimelineClip, start, end, fin, fout, extra="") -> str:
        fid, full = ids.file_id(c.media.path)
        return (f'<clipitem id="{cid}"><name>{escape(Path(c.media.path).name)}</name><enabled>TRUE</enabled>'
                f"<duration>{frames(c.media.duration, c.media.fps)}</duration>{_rate(c.media)}"
                f"<start>{start}</start><end>{end}</end><in>{fin}</in><out>{fout}</out>"
                f"{_file_xml(c.media, fid, full)}{extra}</clipitem>")

    vtrack = "".join(clipitem(vids[k], *p, links(k)) for k, p in enumerate(vplaced))
    atracks = []
    for ch in range(channels):
        items = "".join(
            clipitem(aids[ch][k], *p,
                     f"<sourcetrack><mediatype>audio</mediatype><trackindex>{ch + 1}</trackindex></sourcetrack>"
                     + links(k))
            for k, p in enumerate(aplaced)
        )
        atracks.append(f"<track><outputchannelindex>{ch + 1}</outputchannelindex>{items}</track>")

    fmt = ""
    if ref.width:
        fmt = (f"<format><samplecharacteristics>{_rate(ref)}<width>{ref.width}</width>"
               f"<height>{ref.height}</height><pixelaspectratio>square</pixelaspectratio>"
               "</samplecharacteristics></format>")
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE xmeml>\n<xmeml version="4">'
        f'<sequence id="sequence-1"><name>{escape(name)}</name><duration>{max(vlen, alen)}</duration>'
        f"{_rate(ref)}<media><video>{fmt}<track>{vtrack}</track></video>"
        f"<audio><numOutputChannels>{channels}</numOutputChannels>{''.join(atracks)}</audio>"
        "</media></sequence></xmeml>\n"
    )


def timecode(frame: int, timebase: int) -> str:
    s, f = divmod(frame, timebase)
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}:{f:02d}"


def to_edl(clips: list[TimelineClip], title: str = "OpenRoughCut", record_start_hour: int = 1) -> str:
    tb = clips[0].media.timebase if clips else 30
    lines = [f"TITLE: {title}", "FCM: NON-DROP FRAME", ""]
    rec = record_start_hour * 3600 * tb
    for n, c in enumerate(clips, 1):
        fin, fout = frames(c.src_in, c.media.fps), frames(c.src_out, c.media.fps)
        length = fout - fin
        lines.append(f"{n:03d}  AX       AA/V  C        {timecode(fin, tb)} {timecode(fout, tb)} "
                     f"{timecode(rec, tb)} {timecode(rec + length, tb)}")
        lines.append(f"* FROM CLIP NAME: {Path(c.media.path).name}")
        lines.append("")
        rec += length
    return "\n".join(lines)
