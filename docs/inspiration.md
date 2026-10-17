# Inspiration and scope

OpenRoughCut was started after reviewing the public marketing site of a commercial Premiere Pro
auto-editing plugin. The review was done on 2026-10-17 with [REA](https://github.com/morluto/rea)
(`inspect-web-page` and `analyze-web-bundle` on the public page). It looked at the advertised
feature set only.

What the analysis showed:

- The site is a Next.js marketing page (27 JavaScript chunks). It exposes no editing API: the product
  itself is a desktop plugin, so its implementation was not inspected or used.
- The publicly described workflow is: open a plugin inside Premiere Pro, optionally type an
  instruction for an LLM, and get a rough cut that removes silences, filler words, repeated or bad takes,
  with auto captions, multicam podcast switching and auto-reframe.

OpenRoughCut implements that idea independently, from scratch, as open source, using standard
techniques: energy-based silence detection, Whisper word timestamps, sequence similarity for retakes,
an optional Claude structured-output pass, and FCP7 XML/EDL interchange.

## Feature map

| Idea | Status in OpenRoughCut |
|---|---|
| Silence removal | ✅ `orc cut` |
| Filler-word removal | ✅ multi-language list + custom words |
| Repeated / bad take removal | ✅ heuristic, plus ✅ Claude pass |
| Instruction-driven LLM edit | ✅ `--ai "..."` |
| Auto captions (many languages) | ✅ SRT/VTT, remapped to the cut |
| Caption style templates | ⏳ roadmap (ASS / MOGRT) |
| Podcast multicam switching | ✅ `orc podcast` (one mic per speaker) |
| Auto reframe to vertical | ⏳ roadmap |
| In-editor panel | 🧪 experimental UXP panel |
| B-roll / music / SFX libraries | out of scope (content libraries, not software) |
