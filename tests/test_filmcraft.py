import os
import shutil
from fractions import Fraction
from pathlib import Path

import pytest

from openroughcut import filmcraft
from openroughcut.export import TimelineClip, to_xmeml
from openroughcut.media import MediaInfo


def test_caption_style_params():
    p = filmcraft.CaptionStyle(font="Anton", size=80, background=True).params()
    assert "size=80" in p and "font=Anton" in p and "background=true" in p and "anchor=bottom" in p


def test_missing_cli_has_clear_error(monkeypatch):
    monkeypatch.delenv("ORC_FILMCRAFT", raising=False)
    monkeypatch.setattr(shutil, "which", lambda name: None)
    with pytest.raises(filmcraft.FilmCraftError, match="filmcraft-cli not found"):
        filmcraft.find_cli()


@pytest.mark.skipif(not (os.environ.get("ORC_FILMCRAFT") or shutil.which("filmcraft-cli")),
                    reason="FilmCraft not installed")
def test_build_project_from_xml(tmp_path: Path):
    # media is offline on purpose: the import must still produce a sequence
    m = MediaInfo(str(tmp_path / "missing.mp4"), 10.0, Fraction(30), 1280, 720, True, 2)
    xml = tmp_path / "cut.xml"
    xml.write_text(to_xmeml([TimelineClip(m, 1, 3), TimelineClip(m, 5, 6)]), encoding="utf-8")
    srt = tmp_path / "cut.srt"
    srt.write_text("1\n00:00:00,500 --> 00:00:01,500\nHello\n", encoding="utf-8")
    info = filmcraft.build_project(xml, tmp_path / "cut.fcproj", srt)
    assert Path(info["project"]).exists()
    assert info["sequence"] is not None
    assert info["captions"] == 1
