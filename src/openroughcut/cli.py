"""Command line interface: ``orc``."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__


def _cut(args) -> int:
    from .pipeline import CutOptions, rough_cut

    o = CutOptions(
        silence=not args.no_silence,
        fillers=not args.no_fillers,
        retakes=not args.no_retakes,
        ai=args.ai is not None,
        ai_instructions=args.ai or None,
        ai_model=args.ai_model,
        threshold_db=args.threshold,
        min_silence=args.min_silence,
        padding=args.padding,
        min_keep=args.min_keep,
        extra_fillers=[w for w in (args.filler_words or "").split(",") if w.strip()],
        whisper_model=args.model,
        language=args.language,
        captions=not args.no_captions,
        caption_max_chars=args.caption_chars,
        caption_max_words=args.caption_words,
        caption_uppercase=args.caption_upper,
        formats=tuple(f.strip() for f in args.formats.split(",")),
        render=args.render,
        filmcraft=args.filmcraft,
        filmcraft_export=args.filmcraft_export,
        burn_captions=not args.no_burn,
        loudness_lufs=None if args.lufs is None or args.lufs == 0 else args.lufs,
    )
    out_dir = Path(args.out_dir) if args.out_dir else Path(args.video).parent / "openroughcut"
    result = rough_cut(args.video, out_dir, o)
    s = result["stats"]
    print(f"\n{s['source_seconds']}s -> {s['kept_seconds']}s "
          f"(-{s['removed_percent']}%, {s['clips']} clips) {s['removed_by_reason']}")
    for kind, path in result["outputs"].items():
        print(f"  {kind:8} {path}")
    return 0


def _transcribe(args) -> int:
    from .media import extract_audio
    from .transcribe import transcribe
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        wav = extract_audio(args.video, Path(tmp) / "a.wav")
        t = transcribe(wav, model=args.model, language=args.language,
                       progress=lambda d, total: print(f"  {d:.0f}/{total:.0f}s", end="\r"))
    out = Path(args.output or Path(args.video).with_suffix(".transcript.json"))
    t.to_json(out)
    print(f"\n{len(t.segments)} segments, language={t.language} -> {out}")
    return 0


def _captions(args) -> int:
    from .captions import build_captions, to_srt, to_vtt
    from .models import Transcript

    t = Transcript.from_json(args.transcript)
    cards = build_captions(t, None, args.caption_chars, max_words=args.caption_words, uppercase=args.caption_upper)
    text = to_vtt(cards) if args.output.endswith(".vtt") else to_srt(cards)
    Path(args.output).write_text(text, encoding="utf-8")
    print(f"{len(cards)} captions -> {args.output}")
    return 0


def _podcast(args) -> int:
    from .pipeline import podcast_edit

    if len(args.mic) < 2:
        print("podcast mode needs at least two --mic sources (one per speaker)", file=sys.stderr)
        return 2
    if len(args.cam) not in (1, len(args.mic)):
        print("give one --cam per speaker (same order as --mic)", file=sys.stderr)
        return 2
    result = podcast_edit(args.cam, args.mic, args.output, wide=args.wide, audio=args.audio, min_shot=args.min_shot)
    if args.filmcraft:
        from . import filmcraft

        result["fcproj"] = filmcraft.build_project(args.output, Path(args.output).with_suffix(".fcproj"))["project"]
    print(json.dumps(result, indent=1))
    return 0


def _serve(args) -> int:
    from .server import serve

    serve(args.host, args.port)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="orc", description="OpenRoughCut - AI rough cuts for spoken-word video")
    p.add_argument("--version", action="version", version=f"openroughcut {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    def caption_opts(sp):
        sp.add_argument("--caption-chars", type=int, default=32, help="max characters per caption (default 32)")
        sp.add_argument("--caption-words", type=int, default=None, help="max words per caption, e.g. 3 for Reels style")
        sp.add_argument("--caption-upper", action="store_true", help="UPPERCASE captions")

    c = sub.add_parser("cut", help="make a rough cut of a recording")
    c.add_argument("video")
    c.add_argument("-o", "--out-dir", help="output folder (default: <video folder>/openroughcut)")
    c.add_argument("--no-silence", action="store_true", help="keep pauses")
    c.add_argument("--no-fillers", action="store_true", help="keep um/uh")
    c.add_argument("--no-retakes", action="store_true", help="keep repeated takes")
    c.add_argument("--ai", nargs="?", const="", metavar="INSTRUCTIONS",
                   help='Claude editorial pass, optionally with instructions, e.g. --ai "cut the intro small talk"')
    c.add_argument("--ai-model", default="claude-opus-5-5")
    c.add_argument("--threshold", type=float, default=30.0, help="silence = this many dB below speech (default 30)")
    c.add_argument("--min-silence", type=float, default=0.6, help="shortest pause to cut, seconds (default 0.6)")
    c.add_argument("--padding", type=float, default=0.15, help="air kept around speech, seconds (default 0.15)")
    c.add_argument("--min-keep", type=float, default=0.25, help="drop kept slivers shorter than this (default 0.25)")
    c.add_argument("--filler-words", help="extra filler words to cut, comma separated (e.g. 'like,tipo')")
    c.add_argument("--model", default="small", help="whisper model: tiny/base/small/medium/large-v3 (default small)")
    c.add_argument("--language", help="spoken language code, e.g. en, pt (auto-detected if omitted)")
    c.add_argument("--no-captions", action="store_true")
    c.add_argument("--formats", default="xml,edl,srt,json", help="any of xml,edl,srt,vtt,json")
    c.add_argument("--render", action="store_true", help="also render an MP4 preview with ffmpeg")
    fc = c.add_argument_group("FilmCraft (open-source editor)")
    fc.add_argument("--filmcraft", action="store_true", help="build an editable FilmCraft project (.fcproj)")
    fc.add_argument("--filmcraft-export", action="store_true",
                    help="build the project and render the final MP4 with FilmCraft")
    fc.add_argument("--no-burn", action="store_true", help="don't burn captions into the FilmCraft export")
    fc.add_argument("--lufs", type=float, default=-14.0, help="loudness target for the export, 0 = off (default -14)")
    caption_opts(c)
    c.set_defaults(func=_cut)

    t = sub.add_parser("transcribe", help="transcribe with word timestamps")
    t.add_argument("video")
    t.add_argument("-o", "--output")
    t.add_argument("--model", default="small")
    t.add_argument("--language")
    t.set_defaults(func=_transcribe)

    cp = sub.add_parser("captions", help="SRT/VTT from a transcript JSON (uncut timeline)")
    cp.add_argument("transcript")
    cp.add_argument("-o", "--output", required=True, help="file.srt or file.vtt")
    caption_opts(cp)
    cp.set_defaults(func=_captions)

    pc = sub.add_parser("podcast", help="multicam podcast: cut to whoever is talking")
    pc.add_argument("--cam", action="append", required=True, help="camera file, one per speaker, in --mic order")
    pc.add_argument("--mic", action="append", required=True, help="speaker audio: file or file:channel")
    pc.add_argument("--wide", help="optional wide shot for cross-talk and pauses")
    pc.add_argument("--audio", help="audio used in the sequence (default: first camera)")
    pc.add_argument("--min-shot", type=float, default=2.0, help="shortest shot, seconds (default 2)")
    pc.add_argument("-o", "--output", default="podcast.xml")
    pc.add_argument("--filmcraft", action="store_true", help="also build a FilmCraft project next to the XML")
    pc.set_defaults(func=_podcast)

    s = sub.add_parser("serve", help="local HTTP API used by the Premiere Pro panel")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8765)
    s.set_defaults(func=_serve)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (RuntimeError, FileNotFoundError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
