"""Srutilekha caption window entry point.

Launched for every caption run: by the tray helper and the Resolve 21.1+
bridge (resolve_bridge.py), by the Studio-only Python launcher
(audio_to_srt.py), and by the Lua launcher for Resolve 21.0 and earlier. It
opens the WebView2 caption studio (web_studio.py, pages in ui/), which shows
the form, runs the worker with progress, offers the review editor, and
exchanges the selection/args/done/result/ack files with Resolve's side.

Flow:
  1. Read --prompt file (track items + defaults). 2. Show the form. On submit,
     write --selection so the Resolve-side script can build clip ranges and
     write the worker args file.
  3. Wait for --args-file, run transcribe.py hidden, show its progress.
  4. Write the exit code to --done and close.

Args:
  --prompt    JSON  {"items":[...], "defaults":{"settings":"15,1,1","punct":0}}
  --selection JSON  {"chosen":..., "settings":..., "punct": 0|1}
  --args-file path to the worker args file the Resolve-side script writes
  --done      sentinel file: written with exit code when finished
  --log       transcribe.py stdout log file
  --python    interpreter to run the worker
  --script    transcribe.py path
"""

import argparse
import json
import os
import sys
from app_runtime import frozen, data_dir

# Self-update. Guarded because an install updated from a build that predates
# updater.py will not have the file yet — the window must still open, just
# without the update chip.
try:
    if frozen():
        import release_updater as updater
    else:
        import updater
except Exception:
    updater = None


def _enable_dpi_awareness():
    from dpi import enable
    enable()


_enable_dpi_awareness()

# Languages offered in the form. Order matters: the first is the default.
# The code (ISO 639-3) is passed to ElevenLabs as language_code, which forces
# the whole transcript into that language's script — for Hindi that means
# Devanagari for every word, including spoken English.
# "Auto-detect" is the exception: its "auto" sentinel makes transcribe.py omit
# language_code entirely, so Scribe identifies whatever is spoken (any
# language, not just the ones listed here) at the cost of the script guarantee.
AUTO_LANGUAGE = "Auto-detect"
# Assamese belongs here on the engine's own terms: transcribe.py already maps
# "asm" to the Bengali script block, carries its own conjunction and
# postposition lists for the cue splitter, and normalises both "as" and "asm" —
# it was reachable by every path except this dropdown. Odia sat in exactly the
# same position, and for longer: the Odia block is in _SCRIPT_RANGES, the cue
# splitter has its function-word tables, SUBTITLE_SCRIPTS below resolves it a
# font, the Resolve-side font mapper knows the "orya" tag and the segmentation
# tests run an Odia sentence — the dropdown was the one place it was missing,
# so the whole of it was unreachable. "ori" is both the code ElevenLabs' own
# language list uses for Odia and the key transcribe.py's function-word tables
# are already written against.
_LANGUAGE_CODES = {
    "Assamese": "asm", "Bengali": "ben", "English": "eng", "Gujarati": "guj",
    "Hindi": "hin", "Kannada": "kan", "Malayalam": "mal", "Marathi": "mar",
    "Nepali": "nep", "Odia": "ori", "Punjabi": "pan", "Tamil": "tam",
    "Telugu": "tel",
}
# Alphabetical, built from the map rather than typed out again, so a language
# added above cannot end up in the list without a code or out of order.
# Auto-detect is pinned first: it is the default and not a language, and sorting
# it in among the A's would bury it.
LANGUAGES = (AUTO_LANGUAGE,) + tuple(sorted(_LANGUAGE_CODES))
LANGUAGE_CODES = dict(_LANGUAGE_CODES)
LANGUAGE_CODES[AUTO_LANGUAGE] = "auto"

# ── Frame formats ───────────────────────────────────────────────────────────
# The preview used to be 9:16 and nothing else, which is right for a reel and
# wrong for a talk cut in HD: caption size is a share of frame *height*, so the
# same number is a very different caption in the two frames, and a preview in
# the wrong shape quietly misreports both size and placement.
#
# `srt_posy` is where subtitles sit, as a fraction of frame height measured up
# from the bottom — the same convention the Resolve-side script uses when it
# converts the fraction to the subtitle item's posY. The two defaults are the
# professional placements, and they differ because the frames differ:
#
#   HD    0.10  — the broadcast lower third. Text bottom sits just inside the
#                 title-safe margin, which is where a viewer expects subtitles.
#   Reel  0.28  — has to clear the platform's own furniture. Instagram, TikTok
#                 and Shorts all park the caption, handle and action buttons
#                 across roughly the bottom fifth of the frame, so subtitles
#                 sitting at 0.10 land underneath them.
FRAME_FORMATS = {
    "Reel": {"aspect": 9.0 / 16.0, "label": "9:16", "srt_posy": 0.28},
    "HD":   {"aspect": 16.0 / 9.0, "label": "16:9", "srt_posy": 0.10},
}
FRAME_ORDER = ("Reel", "HD")          # Reel first: it is the default
DEFAULT_FRAME = "Reel"

# Fallback caption fonts, used only if system font detection fails. The Font
# picker normally lists every installed font family (font_families()).
# "Auto (by language)" keeps the script-aware behaviour (Devanagari -> Vesper
# Libre, Bengali -> Noto Serif Bengali); any other choice forces that font.
CAPTION_FONTS = (
    "Auto (by language)",
    "Vesper Libre",
    "Noto Serif Bengali",
    "Noto Sans Devanagari",
    "Mukta",
    "Hind",
    "Poppins",
    "Montserrat",
    "Arial",
    "Helvetica Neue Bold",
    "Anton",
)

# Font weight/style applied on top of the family. "Auto" keeps the default;
# anything else drives the subtitle item's bold/italic properties.
FONT_STYLES = ("Auto", "Regular", "Light", "Medium", "SemiBold",
               "Bold", "Black", "Italic", "Bold Italic")


def font_families():
    """Every installed font family, sorted; vertical (@) faces left out.

    The same list Windows gives any font picker: EnumFontFamiliesExW with
    DEFAULT_CHARSET and no face name names every family in every script, once
    per character set, so the set below folds the repeats."""
    if sys.platform != "win32":
        return []
    import ctypes
    from ctypes import wintypes

    class LOGFONTW(ctypes.Structure):
        _fields_ = [("lfHeight", wintypes.LONG), ("lfWidth", wintypes.LONG),
                    ("lfEscapement", wintypes.LONG), ("lfOrientation", wintypes.LONG),
                    ("lfWeight", wintypes.LONG), ("lfItalic", wintypes.BYTE),
                    ("lfUnderline", wintypes.BYTE), ("lfStrikeOut", wintypes.BYTE),
                    ("lfCharSet", wintypes.BYTE), ("lfOutPrecision", wintypes.BYTE),
                    ("lfClipPrecision", wintypes.BYTE), ("lfQuality", wintypes.BYTE),
                    ("lfPitchAndFamily", wintypes.BYTE), ("lfFaceName", wintypes.WCHAR * 32)]

    callback_type = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.POINTER(LOGFONTW), ctypes.c_void_p,
                                       wintypes.DWORD, wintypes.LPARAM)
    found = set()

    def collect(logfont, _metrics, _kind, _param):
        found.add(logfont.contents.lfFaceName)
        return 1
    callback = callback_type(collect)
    user32, gdi32 = ctypes.WinDLL("user32"), ctypes.WinDLL("gdi32")
    user32.GetDC.argtypes, user32.GetDC.restype = [wintypes.HWND], wintypes.HDC
    user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    gdi32.EnumFontFamiliesExW.argtypes = [wintypes.HDC, ctypes.POINTER(LOGFONTW), callback_type,
                                          wintypes.LPARAM, wintypes.DWORD]
    hdc = user32.GetDC(None)
    try:
        logfont = LOGFONTW(lfCharSet=1)               # DEFAULT_CHARSET
        gdi32.EnumFontFamiliesExW(hdc, ctypes.byref(logfont), callback, 0, 0)
    finally:
        user32.ReleaseDC(None, hdc)
    return sorted(f for f in found if f and not f.startswith("@"))


# ── Subtitle fonts, one per script ──────────────────────────────────────────
# What a cue gets set in on the timeline. Before this, the Resolve-side script
# tested for Devanagari and sent everything else to a single default — which
# was a Bengali serif, so Tamil, Telugu, Kannada, Malayalam, Gujarati, Gurmukhi
# and Odia subtitles were all typeset in a font holding none of their glyphs
# and came out as empty boxes.
#
# Each entry is (script tag, human name, candidate families most preferred
# first). The tags match SCRIPT_RANGES in audio_to_srt.py. Candidates are lists
# because the right font is whatever is actually installed: the serif faces give
# the house look, and Nirmala UI closes every list because it is the Windows
# pan-Indic family and covers all nine scripts on its own.
SUBTITLE_SCRIPTS = (
    ("deva", "Devanagari", ("Vesper Libre", "Noto Serif Devanagari",
                            "Noto Sans Devanagari", "Mangal", "Nirmala UI")),
    ("beng", "Bengali / Assamese", ("Noto Serif Bengali", "Tiro Bangla",
                                    "Noto Sans Bengali", "Vrinda",
                                    "Nirmala UI")),
    ("guru", "Gurmukhi", ("Noto Serif Gurmukhi", "Noto Sans Gurmukhi",
                          "Raavi", "Nirmala UI")),
    ("gujr", "Gujarati", ("Noto Serif Gujarati", "Noto Sans Gujarati",
                          "Shruti", "Nirmala UI")),
    ("orya", "Odia", ("Noto Serif Oriya", "Noto Sans Oriya", "Kalinga",
                      "Nirmala UI")),
    ("taml", "Tamil", ("Noto Serif Tamil", "Noto Sans Tamil", "Latha",
                       "Nirmala UI")),
    ("telu", "Telugu", ("Noto Serif Telugu", "Noto Sans Telugu", "Gautami",
                        "Nirmala UI")),
    ("knda", "Kannada", ("Noto Serif Kannada", "Noto Sans Kannada", "Tunga",
                         "Nirmala UI")),
    ("mlym", "Malayalam", ("Noto Serif Malayalam", "Noto Sans Malayalam",
                           "Kartika", "Nirmala UI")),
)

_SCRIPT_FONTS = None


def resolve_subtitle_fonts():
    """{script tag: installed family} for every script we can serve.

    Resolved here rather than in the Resolve-side script because only this side
    can ask the system what is installed, and naming a font Resolve does not
    have just moves the empty boxes around. A tag whose every candidate is
    missing is left out entirely, so the Resolve-side script falls back to its
    default for it rather than setting a font that is not there.

    ``fontByScript`` in subtitle_style.json wins over the lists above when the
    family it names is installed — same idea as the rest of that file, which
    exists so the look can change without editing code.
    """
    global _SCRIPT_FONTS
    if _SCRIPT_FONTS is not None:
        return _SCRIPT_FONTS
    try:
        installed = set(font_families())
    except Exception:
        installed = set()

    overrides = {}
    try:
        path = os.path.join(data_dir(), "subtitle_style.json")
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f).get("fontByScript") or {}
        if isinstance(raw, dict):
            overrides = {str(k): str(v) for k, v in raw.items()}
    except Exception:
        overrides = {}

    out = {}
    for tag, _name, candidates in SUBTITLE_SCRIPTS:
        for family in (overrides.get(tag),) + tuple(candidates):
            if family and family in installed:
                out[tag] = family
                break
    _SCRIPT_FONTS = out
    return out


def encode_subtitle_fonts(fonts):
    """"deva=Vesper Libre|taml=Nirmala UI" for the selection file.

    Flat rather than a nested object: it dates from the Lua wrapper, which read
    the selection with string patterns rather than a parser. audio_to_srt.py
    parses the selection properly now, but the format is kept because the two
    halves ship separately and an older one must still be able to read this.
    Neither delimiter can occur in a font family name.
    """
    return "|".join("%s=%s" % (tag, fam) for tag, fam in sorted(fonts.items())
                    if fam and "|" not in fam and "=" not in fam)


def _run_web_studio(prompt, a):
    """Show the WebView2 caption studio for this run and return its outcome.

    None when WebView2 is not available on this PC."""
    import web_studio
    import web_ui
    if not web_ui.available():
        return None
    try:
        families = font_families()
    except Exception:
        families = []
    try:
        srt_fonts = encode_subtitle_fonts(resolve_subtitle_fonts())
    except Exception:
        srt_fonts = ""
    ctx = dict(languages=LANGUAGES, language_codes=LANGUAGE_CODES, frames=FRAME_FORMATS,
               default_frame=DEFAULT_FRAME, caption_fonts=CAPTION_FONTS,
               font_styles=FONT_STYLES, families=families, srt_fonts=srt_fonts,
               demo_captions=web_studio.DEMO_CAPTIONS, updater=updater, frozen=frozen(),
               run_id=a.run_id, run_marker=a.run_marker,
               paths=dict(selection=a.selection, args=a.args_file, done=a.done, log=a.log,
                          result=a.result, ack=a.ack, python=a.python, script=a.script))
    try:
        return web_studio.run(prompt, ctx)
    except Exception:
        import traceback
        return {"action": "failed", "details": traceback.format_exc()}


def _write(path, text):
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
    except Exception:
        pass


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--prompt",    required=True)
    p.add_argument("--selection", required=True)
    p.add_argument("--args-file", required=True)
    p.add_argument("--done",      required=True)
    p.add_argument("--log",       required=True)
    p.add_argument("--python",    required=True)
    p.add_argument("--script",    required=True)
    p.add_argument("--result",    required=True)
    p.add_argument("--ack",       required=True)
    # Optional so an older Resolve-side script still works: without them the
    # supersede watchdog simply stays off.
    p.add_argument("--run-id",     default=None)
    p.add_argument("--run-marker", default=None)
    a = p.parse_args()

    with open(a.prompt, "r", encoding="utf-8") as f:
        prompt = json.load(f)

    # The studio window runs the whole job: form, progress, review and the
    # Resolve handshake. Its outcome only decides how this process exits.
    web = _run_web_studio(prompt, a)
    if web is not None and web["action"] == "finished":
        sys.exit(web["code"])
    if web is not None and web["action"] == "superseded":
        _write(a.done, "130")
        sys.exit(130)
    # Cancelled, or the window could not open. Either way Resolve's side is
    # told the run is off (130, as for Cancel) before any notice is shown, so
    # it stops waiting and leaves the timeline untouched.
    _write(a.done, "130")
    _write(a.ack, "cancel")
    if web is None or web["action"] == "failed":
        import web_notice
        if web is None:
            web_notice.tell(web_notice.MISSING_RUNTIME)
        else:
            import notices
            web_notice.tell(dict(notices.describe("Could not start the Srutilekha window.\n" + web["details"]),
                                 kind="error", kicker="One more step", button="Got it"))
    sys.exit(130)


if __name__ == "__main__":
    main()
