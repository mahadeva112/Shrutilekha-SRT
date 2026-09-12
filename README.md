# Srutilekha

Transcribe a DaVinci Resolve timeline and import the result back as a styled
SRT subtitle track. Built for Indic-language footage: the output is pinned to a
single script, so code-switched English is transliterated into that script
instead of splitting the line across two fonts.

Transcription uses the [ElevenLabs Scribe](https://elevenlabs.io) API. Cue
splitting, timing, styling and placement all run locally.

![The Srutilekha main window](docs/main-window.png)

## Contents

- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Usage](#usage)
- [Updating](#updating)
- [Configuration](#configuration)
- [Transliteration](#transliteration)
- [Project structure](#project-structure)
- [Troubleshooting](#troubleshooting)

## Features

- **Timeline-aware transcription.** Reads the clips on the selected audio
  track, transcribes only the region each clip uses, and remaps words back onto
  timeline positions — cuts, gaps and correction clips from other source files
  all land correctly.
- **Single-script output.** Pinning a language forces Scribe to write that
  language's script; a transliteration pass catches Latin tokens that slip
  through (`fast food` → `फास्ट-फूड`). Auto-detect is also available.
- **Linguistic cue splitting.** Boundaries are scored on punctuation (including
  the danda `।`/`॥` and Urdu `۔`/`؟`), silence width measured relative to the
  speaker's own rate, and the grammar on both sides. No cue opens with a
  phrase-completing word (है, ছিল, ஆகும், ఉంది, ಇದೆ, ഉണ്ട്, છે, ਹੈ, ଅଛି, ہے, or a
  standalone postposition). Max characters, lines, duration, word count and
  reading speed (cps) are all enforced.
- **Dedicated subtitle track.** Cues are imported onto a new subtitle track with
  per-speaker colouring. Existing subtitle tracks are never modified.
- **Cached re-splitting.** Scribe results are cached per (audio, model,
  language, diarize). Changing split settings re-runs only local cue building —
  no second API call.
- **Trimmed uploads.** Only the region the timeline uses is sent to Scribe,
  padded, merged and cached per window. Requires `ffmpeg` on `PATH`; without it
  the full source file is uploaded.
- **Review step.** Optionally stop on an editable cue list before anything
  touches the timeline, with a waveform, per-cue reading-speed bars, and
  out-of-budget cues flagged. The waveform requires `ffmpeg`.
- **Undo.** Removes the subtitle track the last run created, and only that
  track.
- **Sync Existing.** Re-aligns an existing SRT's text against the audio without
  changing the words. Reports a failure rather than guessing when too little of
  the text can be matched.

## Requirements

| | |
| --- | --- |
| OS | Windows (the Resolve-side script is cross-platform; setup and UI are Windows-first) |
| DaVinci Resolve | 21.x recommended; 21.0 and earlier supported via the Lua script |
| Python | 3.10+ with `tkinter` |
| API key | [ElevenLabs](https://elevenlabs.io) |
| Optional | `ffmpeg` on `PATH` — enables trimmed uploads and the review waveform |

## Installation

```bash
setup.bat
```

Setup verifies Python, installs `elevenlabs` and `truststore` with `--user`,
records the project path in `%USERPROFILE%\.audio_to_srt_path`, copies
`audio_to_srt.py` into Resolve's per-user `Fusion\Scripts\Utility` folder as
`Srutilekha.py`, and prompts for your API key (stored in `.env`).

No administrator rights are required. On networks that inspect HTTPS, setup
falls back to exporting the Windows certificate store to a PEM for pip.

Launch from Resolve: **Workspace → Scripts → Srutilekha**.

> **Note**
> Resolve 21.1 runs menu scripts in a Lua sandbox without the `io` table, so
> the Lua entry point cannot run there. Setup removes any `Srutilekha.lua` left
> by an earlier install. [audio_to_srt.lua](audio_to_srt.lua) remains in the
> repository for Resolve 21.0 and earlier.

## Usage

1. Set timeline in/out points if you only want part of the timeline.
2. Launch the script from **Workspace → Scripts → Srutilekha**.
3. Configure the run — all settings are on one page, in two columns:

   | Column | Controls |
   | --- | --- |
   | **Source** | Audio track, language, reference script, punctuation, separate speakers |
   | **Timing** | Max characters, lines per cue, max/min length, reading speed, max words, review-first, presets |

4. Drag inside the live preview to set caption height in frame.
5. Click **Generate captions**. The window becomes the progress view.

### Frame presets

The preview switches between **Reel** (9:16) and **HD** (16:9) and opens on the
timeline's actual shape. Caption size is a share of frame *height* and all
positions are frame-relative, so the default placement differs:

| Frame | Height above bottom | Rationale |
| --- | --- | --- |
| HD | `0.10` | Broadcast lower third, inside the title-safe margin |
| Reel | `0.28` | Clears the caption, handle and action-button overlays used by Instagram, TikTok and Shorts |

The chosen fraction is converted against timeline height and sent as
`srt_posy`. A manually dragged value is preserved across frame switches. If
Resolve reports no resolution, `srt_posy` is omitted and the script's built-in
`posY` (620) applies.

## Updating

Setup is a one-time step. On each launch the window checks GitHub for a newer
release on a background thread. The chip at the right of the title bar shows the
result:

| Chip | Meaning |
| --- | --- |
| `v1.0.0` | Up to date. Click to re-check. |
| `Checking…` | A manual check is in flight (startup checks are silent). |
| **Update** | A release is available. Click for release notes and to install. |
| `Restart to finish` | Installed. Close the window and relaunch the script. |

Offline or rate-limited checks fail silently and report as up to date.

Installing downloads and validates the branch archive, backs up the current
version to `.update-backup\` (last three kept), writes the new files, and
re-deploys `Srutilekha.py` into Resolve's `Scripts\Utility` folder. A failed or
truncated download leaves the installation untouched. `.env`,
`subtitle_style.json`, `.cache/`, `presets/` and `logs/` are never replaced.

If the window will not open, run the updater directly:

```bash
python updater.py --install
```

### Publishing a release

`version.json` is the single source of truth — `updater.VERSION` reads it.

```json
{ "version": "1.1.0", "released": "2026-08-02", "notes": ["What changed."] }
```

Bump `version` and push to `main`. Clients see it within about five minutes
(raw-file CDN cache). Add `"min_version": "1.1.0"` to make the update mandatory
— use this when a release changes the handshake format between the
Resolve-side script and the loader.

Pushing without bumping `version.json` still reaches clients: the check also
compares the branch head against the commit each install recorded, and offers
the update with commit subjects in place of release notes.

## Configuration

Cue styling is not exposed as a form. Font is selected per cue from the script
it is written in; point size, outline, drop shadow and colour come from the
`defaults` block in [audio_to_srt.py](audio_to_srt.py). Caption height is set by
dragging inside the preview.

| Setting | Where |
| --- | --- |
| API key | `.env` (written by setup) |
| Cue style defaults | `defaults` block in [audio_to_srt.py](audio_to_srt.py) |
| Saved split settings | `presets/` (Save/Load in the UI) |
| Language override | `ELEVENLABS_LANGUAGE` env var — ISO 639-1/639-3 code, or `auto` |

Presets saved by earlier builds still load; keys describing the removed Text+
path are ignored.

Generated at runtime and gitignored: `.env`, `.cache/`, `logs/`, `presets/`,
`.update-backup/`, `.update_state.json`.

## Transliteration

With a language pinned, Scribe writes most spoken English in the target script,
but regularly leaves tokens in Latin (`neurological`, `coffee`). Those would
stay Latin on screen and, being script-neutral, could not be assigned the right
font — so every Latin run is transliterated.

Spellings are derived from *pronunciations* (the CMU Pronouncing Dictionary)
rather than letters, because English spelling does not predict English
pronunciation: letter-based rules give `नेउरोलोगिकाल`, pronunciation-based rules
give `न्यूरोलॉजिकल`. Hindi convention also consults the spelling for reduced
vowels (`फेस्टिवल`, `मार्केट`), so both are used.

Coverage:

| Script | Source |
| --- | --- |
| Devanagari (Hindi, Marathi, Nepali, Sanskrit) | Own dictionary and phonetic table |
| Bengali (Bengali, Assamese) | Own dictionary and phonetic table |
| Gurmukhi, Gujarati, Odia, Tamil, Telugu, Kannada, Malayalam | Devanagari's, mapped by codepoint offset with per-script corrections in `languages/scripts.py` |
| Urdu | Not supported — Perso-Arabic shares no layout with the Indic blocks. Latin tokens are left as-is. |

Per-script corrections cover the cases the offset alone gets wrong: Tamil folds
the voiced and aspirated series onto the plain stop (`bread` → `ப்ரேட்`);
candra-O is written `ā` in Punjabi, Tamil, Telugu and Kannada, long `ō` in
Malayalam, and omitted in Odia; the Dravidian scripts and Odia need the
word-final vowel-killer restored (72% of the dictionary); Punjabi writes
clusters without a visible halant (`ਸਕੂਲ`, `ਡਾਕਟਰ`).

The dictionary reaches conventional spelling for roughly four words in five.
Irregular words are listed in a hand-verified exception table that overrides
the engine. Anything in neither — names, invented words — falls back to
letter-based rules in `transcribe.py`, which are rough but always land in the
target script.

Nothing in this path runs at transcription time: no API call, no key, no
third-party package — just a data file loaded lazily on the first Latin word.

## Project structure

| File | Role |
| --- | --- |
| [audio_to_srt.py](audio_to_srt.py) | Runs inside Resolve. Reads tracks and clip ranges, drives the UI and worker, imports and styles the SRT, owns Undo and Sync. Installed as `Srutilekha.py`. |
| [audio_to_srt.lua](audio_to_srt.lua) | Lua equivalent for Resolve 21.0 and earlier. Not installed by setup. |
| [loader.pyw](loader.pyw) | Tkinter UI — settings form, live preview, cue review/editor, progress. |
| [transcribe.py](transcribe.py) | Worker. Calls Scribe, normalizes and transliterates, builds cues, writes the SRT and `.cap` sidecar. |
| [dialog.py](dialog.py) | Dark-themed alert/pick/input dialogs used by the Lua script. |
| [updater.py](updater.py) | Version check and in-place install. Standard library only. |
| `version.json` | Published release metadata. Read over HTTPS by every install. |
| `data/translit_*.json.gz` | Generated English→Devanagari/Bengali pronunciation spellings. |
| `languages/` | Per-language phonetic tables and per-script corrections. |

## Troubleshooting

- **Changes to `audio_to_srt.py` have no effect.** Resolve runs the copy in its
  Scripts folder (`Srutilekha.py`), not the repository file. Re-run `setup.bat`
  after editing that file. All other Python files are read live.
- **A run fails silently inside Resolve.** Check `logs/audio_to_srt.log` first.
- **The menu entry does nothing on Resolve 21.1.** A stale `Srutilekha.lua` is
  present; re-run `setup.bat` to remove it. Lua errors appear only in
  `Support\logs\ResolveDebug.txt`.

### Running the worker standalone

```bash
python transcribe.py <audio> <out.srt> [max_chars] [max_lines] [max_secs]
```
