import xml.etree.ElementTree as ET
from fractions import Fraction

import numpy as np
import pytest

from openroughcut.ai import build_request, cuts_from_decision
from openroughcut.captions import build_captions, remap, to_srt
from openroughcut.export import TimelineClip, path_url, timecode, to_edl, to_xmeml
from openroughcut.fillers import detect_fillers
from openroughcut.media import MediaInfo
from openroughcut.models import Cut, Range, Segment, Transcript, Word
from openroughcut.pipeline import parse_mic
from openroughcut.podcast import plan_shots, speaker_activity
from openroughcut.silence import detect_silences
from openroughcut.takes import detect_retakes, is_retake
from openroughcut.timeline import keep_ranges, merge_cuts, summarize

RATE = 16000


def tone(seconds, amp=0.3, freq=220):
    t = np.arange(int(seconds * RATE)) / RATE
    return (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def quiet(seconds):
    return (np.random.default_rng(0).normal(0, 0.0005, int(seconds * RATE))).astype(np.float32)


def words_transcript(spec, language="en"):
    """spec: list of (text, start, end); one segment per sentence-ending word."""
    words = [Word(t, s, e) for t, s, e in spec]
    return Transcript(language, words[-1].end + 0.5, [Segment(0, words[0].start, words[-1].end,
                                                               " ".join(w.text for w in words), words)])


def test_silence_detection_finds_gap_with_padding():
    audio = np.concatenate([tone(2), quiet(1.5), tone(2)])
    cuts = detect_silences(audio, RATE, min_silence=0.6, padding=0.15)
    assert len(cuts) == 1
    assert cuts[0].start == pytest.approx(2.15, abs=0.03)
    assert cuts[0].end == pytest.approx(3.35, abs=0.03)


def test_short_pauses_are_kept():
    audio = np.concatenate([tone(1), quiet(0.3), tone(1)])
    assert detect_silences(audio, RATE, min_silence=0.6) == []


def test_leading_and_trailing_silence_cut_fully():
    audio = np.concatenate([quiet(1), tone(1), quiet(1)])
    cuts = detect_silences(audio, RATE)
    assert cuts[0].start == 0.0
    assert cuts[-1].end == pytest.approx(3.0, abs=0.03)


def test_fillers_english_and_portuguese():
    t = words_transcript([(" So", 0, 0.3), (" um,", 0.5, 0.8), (" this", 1.0, 1.3), (" works.", 1.3, 1.8)])
    cuts = detect_fillers(t)
    assert len(cuts) == 1 and cuts[0].reason == "filler"
    assert 0.3 <= cuts[0].start <= 0.5 and 0.8 <= cuts[0].end <= 1.0

    pt = words_transcript([(" Então", 0, 0.4), (" hum", 0.5, 0.9), (" tipo", 1.0, 1.3), (" isso.", 1.4, 1.8)], "pt")
    assert [c.note for c in detect_fillers(pt)] == ['"hum"']
    assert len(detect_fillers(pt, extra=["tipo"])) == 2


def test_retake_detection_keeps_last_attempt():
    assert is_retake("today we are going to".split(), "today we are going to learn python".split())
    assert not is_retake("hello everyone".split(), "python is a language".split())
    spec = []
    t = 0.0
    for sentence in ["Today we are going to.", "Today we are going to learn Python.", "It is easy."]:
        for w in sentence.split():
            spec.append((" " + w, t, t + 0.3))
            t += 0.35
        t += 0.5
    cuts = detect_retakes(words_transcript(spec))
    assert len(cuts) == 1
    assert cuts[0].start == 0.0
    assert cuts[0].end == pytest.approx(spec[5][1])  # start of the good take


def test_merge_and_keep_ranges():
    cuts = [Cut(1, 2, "silence"), Cut(1.9, 3, "filler"), Cut(5, 5.1, "filler"), Cut(5.2, 6, "silence")]
    merged = merge_cuts(cuts)
    assert [(c.start, c.end) for c in merged] == [(1, 3), (5, 5.1), (5.2, 6)]
    assert merged[0].reason == "silence+filler"
    keep = keep_ranges(cuts, 10)
    # the 0.1s sliver between 5.1 and 5.2 is dropped
    assert [(r.start, r.end) for r in keep] == [(0, 1), (3, 5), (6, 10)]
    stats = summarize(cuts, 10, keep)
    assert stats["kept_seconds"] == 7 and stats["clips"] == 3


def test_caption_remap_and_srt():
    keep = [Range(0, 2), Range(4, 6)]
    assert remap(1, keep) == 1
    assert remap(3, keep) is None
    assert remap(5, keep) == 3
    t = words_transcript([(" Hello", 1.5, 1.9), (" cut", 2.5, 3.0), (" world.", 4.1, 4.6)])
    cards = build_captions(t, keep)
    assert [c.text for c in cards] == ["Hello world."]
    assert cards[0].start == pytest.approx(1.5) and cards[0].end == pytest.approx(2.6)
    assert "00:00:01,500 --> 00:00:02,600" in to_srt(cards)


def test_caption_word_limit():
    t = words_transcript([(f" w{i}", i * 0.3, i * 0.3 + 0.25) for i in range(7)])
    cards = build_captions(t, max_words=3, uppercase=True)
    assert [c.text for c in cards] == ["W0 W1 W2", "W3 W4 W5", "W6"]


def media(path="C:/v/clip one.mp4", fps=Fraction(30), dur=60.0):
    return MediaInfo(path=path, duration=dur, fps=fps, width=1920, height=1080, has_audio=True, audio_channels=2)


def test_xmeml_is_valid_and_frame_accurate():
    m = media()
    xml = to_xmeml([TimelineClip(m, 1.0, 2.0), TimelineClip(m, 5.0, 7.5)], name="test & demo")
    root = ET.fromstring(xml.split("\n", 2)[2])
    clips = root.findall("./sequence/media/video/track/clipitem")
    assert [(c.find("start").text, c.find("end").text, c.find("in").text, c.find("out").text) for c in clips] == [
        ("0", "30", "30", "60"), ("30", "105", "150", "225")]
    assert root.find("./sequence/duration").text == "105"
    # the media file is defined once and referenced afterwards
    assert len([f for f in root.iter("file") if f.find("pathurl") is not None]) == 1
    assert len(root.findall("./sequence/media/audio/track")) == 2
    assert path_url("C:\\v\\clip one.mp4") == "file://localhost/C%3A/v/clip%20one.mp4"


def test_xmeml_ntsc():
    m = media(fps=Fraction(30000, 1001))
    xml = to_xmeml([TimelineClip(m, 0, 10)])
    assert "<timebase>30</timebase><ntsc>TRUE</ntsc>" in xml
    assert "<out>300</out>" in xml  # 10s at 29.97 = 299.7 -> 300 frames


def test_edl():
    m = media()
    edl = to_edl([TimelineClip(m, 1.0, 2.0), TimelineClip(m, 3.0, 4.0)])
    assert "001  AX       AA/V  C        00:00:01:00 00:00:02:00 01:00:00:00 01:00:01:00" in edl
    assert "002  AX       AA/V  C        00:00:03:00 00:00:04:00 01:00:01:00 01:00:02:00" in edl
    assert timecode(30 * 3661 + 5, 30) == "01:01:01:05"


def test_podcast_switches_to_active_speaker():
    a = np.concatenate([tone(5), quiet(5), tone(5)])
    b = np.concatenate([quiet(5), tone(5, freq=330), quiet(5)])
    activity = speaker_activity([a, b], RATE)
    shots = plan_shots(activity, min_shot=2.0)
    assert [s.angle for s in shots] == [0, 1, 0]
    assert shots[1].start == pytest.approx(5.0, abs=0.6)


def test_parse_mic():
    assert parse_mic("C:\\rec\\mics.wav:1") == ("C:\\rec\\mics.wav", 1)
    assert parse_mic("C:\\rec\\host.wav") == ("C:\\rec\\host.wav", None)
    assert parse_mic("guest.wav") == ("guest.wav", None)


def test_ai_request_and_mapping_without_network():
    t = words_transcript([(" One", 0, 0.3), (" two.", 0.4, 0.8), (" Three", 1.0, 1.3), (" four.", 1.4, 1.8)])
    sentences, body = build_request(t, "keep it short")
    assert "[0] (0.0-0.8s) One two." in body and "keep it short" in body
    cuts = cuts_from_decision(sentences, [(0, "restart"), (99, "invented id")])
    assert len(cuts) == 1 and cuts[0].reason == "ai" and cuts[0].end == 1.0
