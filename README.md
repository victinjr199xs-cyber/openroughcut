# OpenRoughCut

**Open-source AI rough cuts for talking-head videos, tutorials and podcasts.**

Record, run one command, and open an editable sequence in Premiere Pro, DaVinci Resolve or
Final Cut, with the dead air, "um"s and failed takes already gone, plus captions that match
the edited timeline. Everything runs on your computer. The optional Claude pass sends only
transcript text, never audio or video.

```
$ orc cut sample.mp4 --language en --model base --render
silence: 5 pauses
retakes (heuristic): 1 sentences

28.6s -> 16.54s (-42.2%, 5 clips) {'retake+silence': 3.3, 'silence': 8.61}
  xml      sample.roughcut.xml   <- File > Import in Premiere / Resolve
  edl      sample.roughcut.edl
  srt      sample.roughcut.srt   <- captions already synced to the cut
  json     sample.cuts.json      <- every cut with its reason
  preview  sample.roughcut.mp4
```

*(Real output on the test clip made by `scripts/make_sample.ps1`.)*

## Features

| | |
|---|---|
| **Silence removal** | Loudness-relative detection, so it works with quiet or loud microphones. Keeps a little air around speech so pacing stays natural. |
| **Filler-word removal** | Removes "um", "uh" and similar sounds in English, Portuguese, Spanish, French, German and Italian, and you can add your own words (`--filler-words "like,tipo"`). |
| **Repeated / bad take removal** | Finds sentences you restarted or repeated and keeps the last attempt. Runs offline and costs nothing. |
| **Claude editorial pass** *(optional)* | `--ai "cut the small talk before the intro"` tells Claude what you want, and it picks the sentences to drop by meaning, not by waveform. |
| **Captions** | SRT/VTT from local Whisper with word timestamps, in 99 languages, remapped to the edited timeline. `--caption-words 3 --caption-upper` gives Reels-style cards. |
| **Podcast multicam** | `orc podcast` switches camera angles to whoever is talking, with a minimum shot length and an optional wide shot for cross-talk. |
| **Non-destructive** | Outputs FCP7 XML/EDL that point at your original media. Every cut stays editable and nothing is re-encoded unless you ask for `--render`. |
| **Premiere Pro panel** *(experimental)* | A UXP panel that sends the clip to the local engine and imports the result. |

## Install

Requirements: Python 3.10+ and [FFmpeg](https://ffmpeg.org/download.html) on your `PATH` (or set
`ORC_FFMPEG` / `ORC_FFPROBE` to the executables).

```bash
pip install "openroughcut[all] @ git+https://github.com/victinjr199xs-cyber/openroughcut"
```

Extras: `transcribe` (faster-whisper, needed for fillers/retakes/captions), `ai` (Claude), `all`.
Silence removal alone needs only the base install.

## Usage

```bash
# full rough cut (silences + fillers + retakes + captions)
orc cut recording.mp4

# only silences, more aggressive, render an MP4 preview too
orc cut recording.mp4 --no-fillers --no-retakes --min-silence 0.4 --render

# Portuguese, bigger Whisper model, punchy 3-word uppercase captions
orc cut gravacao.mov --language pt --model medium --caption-words 3 --caption-upper

# let Claude decide which takes to keep, with instructions
export ANTHROPIC_API_KEY=...        # or: ant auth login
orc cut vlog.mp4 --ai "keep only the final version of the intro; remove the sponsor read"

# podcast: one camera + one mic per speaker, optional wide shot
orc podcast --cam host.mp4 --mic host.wav --cam guest.mp4 --mic guest.wav --wide wide.mp4 -o podcast.xml
#   two mics on one file? use --mic recorder.wav:0 --mic recorder.wav:1

# transcript / captions only
orc transcribe talk.mp4 -o talk.json
orc captions talk.json -o talk.srt
```

Then in **Premiere Pro**: *File > Import* the `.xml`, which creates a new sequence. In **DaVinci
Resolve**: *File > Import > Timeline*. Drop the `.srt` on a caption track.

### Tuning

| Option | Default | Effect |
|---|---|---|
| `--threshold` | 30 dB | How far below speech level counts as silence. Lower means more aggressive. |
| `--min-silence` | 0.6 s | Shortest pause that gets cut. |
| `--padding` | 0.15 s | Air kept before and after speech. |
| `--model` | small | Whisper size: `tiny`, `base`, `small`, `medium`, `large-v3`. Bigger is more accurate but slower. |

`*.cuts.json` lists every cut with its reason, so you can review the decisions or build your own tooling.

## Premiere Pro panel (experimental)

1. Run the engine: `orc serve` (listens on `127.0.0.1:8765` only).
2. In Adobe **UXP Developer Tool**: *Add plugin*, then pick `premiere-panel/manifest.json` and click *Load*.
3. In Premiere Pro, open *Window > UXP Plugins > OpenRoughCut*, choose a recording and click *Rough cut*.

The panel requires Premiere Pro 25.6+ (UXP). It has not been tested against every Premiere build, so if
auto-import fails it shows the file paths for a manual import. Reports and PRs are welcome.

## How it works

```
media ──ffmpeg──▶ 16 kHz audio ──▶ silence detector (RMS vs. 95th percentile loudness)
                       └──▶ faster-whisper (word timestamps, disfluency prompt, VAD)
                                 ├──▶ filler detector
                                 ├──▶ retake detector (sentence similarity, keep last)
                                 └──▶ Claude pass (structured output: sentence ids to drop)
cuts ──merge──▶ keep ranges ──▶ FCP7 XML · EDL · SRT/VTT (remapped) · JSON · MP4 preview
```

Whisper normally "cleans up" transcripts and drops hesitations, so OpenRoughCut primes it with a
disfluent prompt per language to keep the "um"s it needs to find.

## Development

```bash
git clone https://github.com/victinjr199xs-cyber/openroughcut && cd openroughcut
python -m venv .venv && . .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[all,dev]"
pytest
powershell -File scripts/make_sample.ps1       # Windows: builds a TTS test video
```

Roadmap ideas: AI auto-reframe to vertical (face tracking), animated caption templates (MOGRT/ASS),
B-roll suggestions, speaker diarization for single-mic podcasts, a native timeline-editing panel.
See [docs/inspiration.md](docs/inspiration.md).

## Disclaimer

OpenRoughCut is an independent project. It is not affiliated with, endorsed by or derived from the
code of Adobe, Blackmagic Design, Apple, or any commercial auto-editing plugin. Product names are
trademarks of their owners.

---

### Português (resumo)

Ferramenta open source que faz o **primeiro corte** de vídeos falados: remove silêncios, "é…", "hum"
e takes repetidos, gera legendas sincronizadas com o corte e exporta uma sequência editável (XML) para
Premiere Pro / DaVinci Resolve. Roda localmente. O passe com o Claude é opcional e envia só o texto
da transcrição. Exemplo: `orc cut gravacao.mp4 --language pt`.

MIT License.
