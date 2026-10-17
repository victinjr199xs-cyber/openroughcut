"""FilmCraft integration (open-source NLE, https://github.com/storytold/filmcraft).

Builds a ready-to-edit ``.fcproj`` from OpenRoughCut's outputs through the
headless ``filmcraft-cli``: imports the FCP7 XML sequence, adds the captions as
a styled caption track and can export the final video with burned-in captions.
No editor window is needed, so this also works as an all-local render path.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


class FilmCraftError(RuntimeError):
    pass


def find_cli() -> str:
    env = os.environ.get("ORC_FILMCRAFT")
    if env:
        return env
    found = shutil.which("filmcraft-cli")
    if not found:
        raise FilmCraftError("filmcraft-cli not found. Install FilmCraft and add it to PATH or set ORC_FILMCRAFT.")
    return found


def _run(args: list[str]) -> dict:
    out = subprocess.run([find_cli(), "--compact", *args], capture_output=True, text=True, encoding="utf-8")
    if out.returncode != 0:
        raise FilmCraftError(f"filmcraft-cli {' '.join(args[:3])} failed: {(out.stderr or out.stdout).strip()[-1500:]}")
    text = out.stdout.strip()
    if not text:
        return {}
    try:
        return json.loads(text.splitlines()[-1])
    except json.JSONDecodeError:
        return {"output": text}


@dataclass
class CaptionStyle:
    """Caption track look. ``size`` is in FilmCraft points at sequence resolution."""

    font: str | None = None
    size: float = 64
    color: str = "#ffffff"
    outline: float = 4
    outline_color: str = "#000000"
    background: bool = False
    anchor: str = "bottom"  # top | middle | bottom
    margin: float = 0.12  # fraction of frame height

    def params(self) -> list[str]:
        p = [f"size={self.size}", f"color={self.color}", f"outline={self.outline}",
             f"outlineColor={self.outline_color}", f"background={'true' if self.background else 'false'}",
             f"anchor={self.anchor}", f"margin={self.margin}"]
        if self.font:
            p.append(f"font={self.font}")
        return p


def build_project(
    xml: str | Path,
    project: str | Path,
    captions: str | Path | None = None,
    style: CaptionStyle | None = None,
) -> dict:
    """Create ``project`` (.fcproj) holding the rough-cut sequence and captions."""
    project = Path(project)
    if project.exists():
        project.unlink()  # importing into an old project would duplicate the sequence
    result = _run(["--save-as", str(project), "import", str(xml)])
    docs = result.get("documents") or [{}]
    offline = [m for d in docs for m in d.get("offlineMedia", [])]
    if result.get("errors"):
        raise FilmCraftError(f"FilmCraft could not import {xml}: {result['errors']}")
    info = {"project": str(project), "sequence": (result.get("sequences") or [None])[0], "offline_media": offline}
    if captions:
        cap = _run(["--project", str(project), "--save", "exec", "captions.import", f"path={captions}"])
        info["captions"] = cap.get("captions")
        track = cap.get("track")
        if track is not None:
            _run(["--project", str(project), "--save", "exec", "captions.setStyle", f"track={track}",
                  *(style or CaptionStyle()).params()])
    return info


def export(
    project: str | Path,
    output: str | Path,
    burn_captions: bool = True,
    loudness_lufs: float | None = -14.0,
    preset: str | None = None,
) -> dict:
    """Render the project's active sequence (H.264 MP4 unless ``preset`` says otherwise)."""
    params = [f"path={Path(output).resolve()}", f"burnCaptions={'true' if burn_captions else 'false'}", "wait=true"]
    params.append(f"preset={preset}" if preset else "format=h264")
    if loudness_lufs is not None:
        params.append(f"loudnessLufs={loudness_lufs}")
    result = _run(["--project", str(project), "exec", "file.exportMedia", *params])
    if result.get("offlineMedia"):
        raise FilmCraftError(f"media offline, export skipped: {result['offlineMedia']}")
    return result.get("result", result)
