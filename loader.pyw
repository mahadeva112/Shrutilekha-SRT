"""Srutilekha single-window UI: form + progress.

Launched by audio_to_srt.py via pythonw.exe. Renders one Tkinter window
that begins as a track / settings form and transitions in place to a
progress view once the user clicks Generate Subtitles.

Flow:
  1. Read --prompt file (track items + defaults). 2. Show form. On submit,
  write --selection file so the Resolve-side script can
     build clip ranges and write the worker args file.
  3. Wait for --args-file to appear, then spawn transcribe.py hidden,
     parse PROGRESS|pct|message lines, and animate the progress UI.
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
import math
import os
import queue
import re
import subprocess
import sys
import threading
import time
import unicodedata
import tkinter as tk
from tkinter import ttk, messagebox, font as tkfont

# Self-update. Guarded because an install updated from a build that predates
# updater.py will not have the file yet — the window must still open, just
# without the update chip.
try:
    import updater
except Exception:
    updater = None


def _enable_dpi_awareness():
    """Tell Windows this process handles its own scaling.

    Without this, an unaware process gets its whole window bitmap-scaled by
    Windows on any display that isn't at 100% scaling (125%/150%/etc. are the
    Windows default on most laptops and 4K monitors). That stretch happens
    AFTER Tk has already laid out and drawn every pixel-measured widget in
    this file, so the true window edge lands to the left of where Tk thinks
    it is — the rightmost content (our right-hand settings column) gets
    silently cut off. This must run before the first Tk() is created; it is
    called once at import time, below. No-op on non-Windows or on failure.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes
        # Per-Monitor v2 (Windows 10 1703+): best fidelity, matches whichever
        # monitor the window is actually on.
        #
        # NOTE: this call does not exist on shcore — it lives in user32 — so
        # this branch always raises and the process settles for
        # SYSTEM_DPI_AWARE below. That is currently load-bearing, not a typo
        # to fix in passing: under Per-Monitor v2 Tk is told the monitor's real
        # DPI, so its point-sized fonts grow (10pt goes from 17px to ~25px at
        # 150%) while the window stays pinned to the pixel literals in
        # App.__init__ (930x740, min 880x560) and every widget size in this
        # file. The layout overflows. Moving to Per-Monitor v2 means scaling
        # those constants by dpi/96 first — a separate change, and one that
        # has to be tested on a scaled display.
        ctypes.windll.shcore.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        return
    except Exception:
        pass
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)  # PROCESS_SYSTEM_DPI_AWARE
        return
    except Exception:
        pass
    try:
        import ctypes
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


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
    "Telugu": "tel", "Urdu": "urd",
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
# picker normally lists every installed font family (tkfont.families()).
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

TRANSPARENT_KEY = "#010203"  # sentinel color used for Toplevel transparency

CREATE_NO_WINDOW = 0x08000000

# ── Palette ───────────────────────────────────────────────────────────────
# Warm graphite ground with a single accent: subtitle yellow, the colour of
# the thing this tool actually produces. Editing suites stay neutral so the
# footage is the only saturated thing on screen — the accent is spent only on
# the primary action, the active tab and focus, never on decoration.
#
# Every widget in this file reads these names, so the whole window is themed
# from this block.
#
# The values are sampled from DaVinci Resolve itself, not chosen: this window
# opens inside Resolve, and a palette invented next to it reads as a foreign
# application no matter how well it is drawn. Three things about Resolve drove
# the whole set and are worth stating, because each is the opposite of the
# usual dark-UI instinct:
#
#   * It is light. Its main surface is #28282e — mid grey, not near-black.
#   * Its text is grey, not white: #8b8b8b in a list, #929292 in the menus.
#   * Its separators are DARKER than the surfaces they divide (#090909), so
#     depth reads as a cut rather than as a raised edge.
#
# Semantic colours (GOOD / BAD) are separate from both accents. SELECT is
# Resolve's own blue and carries every interactive state — a switch that is
# on, the group being edited, progress. ACCENT is kept for one thing only:
# subtitles. It is the colour of the caption in the preview, of the baseline
# being dragged, and of the button that makes them. Resolve uses no amber
# anywhere, which is exactly why it can be this window's signature.
BG_OUTER = "#17181a"        # void — Resolve's menu and toolbar ground
BG_BAR   = "#17181a"        # title bar and action bar — the same dark band,
#                             because in Resolve the chrome is darker than the
#                             panels, not raised above them
BG       = "#212126"        # ground — its secondary panel
BG_CARD  = "#28282e"        # panel — its main list surface
BG_PANEL2 = "#2d2f33"       # group-card header band (one step above the card)
BG_INPUT = "#1c1c21"        # field interiors (sunken, below the card)
BG_HOVER = "#35373d"        # raised — hover, secondary buttons
BG_TILE  = "#35373d"        # 28×28 icon tile bg
BORDER   = "#17171b"        # input hairline — darker than what it encloses
BORDER_TILE = "#3a3a3a"     # icon tile border
BORDER_CARD = "#17171b"     # outer card border
BORDER_BRIGHT = "#4a4a50"   # hover hairline
SHADOW   = "#090909"
FG       = "#d4d4d6"
FG_DIM   = "#9a9a9d"
FG_MUTE  = "#6e7176"
FG_LABEL = "#6e7176"
ACCENT       = "#e8c547"     # subtitle yellow — captions, baseline, Generate
ACCENT_DARK  = "#c9a62f"
ACCENT_HOVER = "#f2d264"
ACCENT_GLOW  = "#453a1c"     # solid stand-in for the amber glow halo
ACCENT_INK   = "#14150f"     # text/glyphs drawn ON an accent fill
SELECT       = "#007fe3"     # Resolve blue — on, selected, focused, running
SELECT_DARK  = "#0063b0"
SELECT_HOVER = "#2b96e8"
SELECT_GLOW  = "#12293d"
SELECT_INK   = "#ffffff"
DIVIDER  = "#1b1b1f"
DIVIDER_MID = "#35373d"
TRACK_OFF = "#3a3a40"
THUMB_OFF = "#8b8b8e"
GOOD     = "#4fae7a"         # within limits / stage complete
BAD      = "#e64b3d"         # over the reading-speed limit / failed

# Numeric fields hold values like 0.120 and 0.280 that change as you drag a
# slider. Proportional Segoe makes those digits jitter because its figures
# aren't tabular; Consolas is fixed-width and ships on every Windows install.
FONT_NUM = "Consolas"

# The UI face. Open Sans is the one Resolve itself uses — "Open Sans" is the
# only UI family named in BMDDavUI.dll, and measuring a clip name in a Resolve
# screenshot ("Manasarovar 6 Music.wav", 155px wide) puts it at Open Sans 10
# (152px) ahead of Segoe UI 10 (151px) and IBM Plex Sans 10 (150px).
#
# Note the size. Resolve's rows are 23px tall around ~13px text: the density
# comes from cutting the padding, not from shrinking the type. Text set
# smaller than this goes soft on a normal display, which is the opposite of
# what a settings form needs.
#
# Resolved once at startup against the families the machine actually reports,
# because Tk substitutes silently for a family it cannot find.
UI_FONT = "Segoe UI"
UI_FONT_CANDIDATES = ("Open Sans", "Segoe UI", "Tahoma")


def resolve_ui_font():
    """Pick the first UI face the machine actually has. Call once, with a root."""
    global UI_FONT
    try:
        have = set(tkfont.families())
    except Exception:
        return UI_FONT
    for family in UI_FONT_CANDIDATES:
        if family in have:
            UI_FONT = family
            break
    return UI_FONT

# Icon names rendered by IconCanvas (Canvas-drawn, font-independent)
ICO_MIC          = "mic"
ICO_VOLUME       = "volume"


def _steal_focus(win):
    try:
        import ctypes
        u32 = ctypes.windll.user32
        u32.SystemParametersInfoW(0x2001, 0, 0, 2)
        hwnd = int(win.winfo_id())
        u32.ShowWindow(hwnd, 9)
        u32.BringWindowToTop(hwnd)
        u32.SetForegroundWindow(hwnd)
        # Force HWND_TOPMOST via SetWindowPos — more reliable than tkinter's
        # -topmost attribute when overrideredirect is used on Windows.
        HWND_TOPMOST  = -1
        SWP_NOMOVE    = 0x0002
        SWP_NOSIZE    = 0x0001
        SWP_NOACTIVATE = 0x0010
        u32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                         SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)
    except Exception:
        pass


def _dwm_rounds_windows():
    """True where the compositor can round corners for us (Windows 11+)."""
    if sys.platform != "win32":
        return False
    try:
        return sys.getwindowsversion().build >= 22000
    except Exception:
        return False


DWM_ROUNDING = _dwm_rounds_windows()


def _win_hwnd(win):
    """The top-level HWND Windows actually manages for a Tk window.

    ``winfo_id()`` returns Tk's own child window. Passing that to DWM gets
    E_HANDLE and passing it to SetWindowRgn silently clips nothing, which is
    why both have to go through GA_ROOT (=2).
    """
    import ctypes
    return ctypes.windll.user32.GetAncestor(int(win.winfo_id()), 2)


def round_corners(win, radius=8, square=False):
    """Round a frameless window's corners. No-op off Windows, or on failure.

    Two implementations, because the good one only exists on Windows 11:

    * Build 22000+: DWMWA_WINDOW_CORNER_PREFERENCE. The compositor does the
      clipping, so the arc is antialiased and follows every resize by itself.
    * Older: SetWindowRgn with a round-rect region. Hard-edged — a region is a
      binary mask, there is no partial coverage — and sized in window
      coordinates, so the caller must re-apply it whenever the window resizes.

    ``square`` restores hard corners, for a maximized window: Windows unrounds
    its own maximized windows, and a rounded one shows slivers of desktop in
    the corners of what is meant to read as edge-to-edge.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes
        hwnd = _win_hwnd(win)
        if not hwnd:
            return
        if DWM_ROUNDING:
            # 33 = DWMWA_WINDOW_CORNER_PREFERENCE.
            # 1 = DONOTROUND, 2 = ROUND (the standard Windows 11 radius),
            # 3 = ROUNDSMALL. ROUND is what every other Win11 app uses, which
            # is the point — this window opens inside Resolve and should read
            # as part of the OS, not as a shape someone chose.
            pref = ctypes.c_int(1 if square else 2)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                ctypes.c_void_p(hwnd), 33,
                ctypes.byref(pref), ctypes.sizeof(pref))
            return
        if square:
            ctypes.windll.user32.SetWindowRgn(hwnd, 0, True)
            return
        win.update_idletasks()
        w, h = win.winfo_width(), win.winfo_height()
        if w <= 1 or h <= 1:
            return
        # CreateRoundRectRgn's last two arguments are the ellipse's full width
        # and height, not its radius — hence the doubling. Off-by-two here is
        # a corner that looks almost but not quite right.
        rgn = ctypes.windll.gdi32.CreateRoundRectRgn(
            0, 0, w + 1, h + 1, radius * 2, radius * 2)
        # Ownership of the region passes to the window; do not delete it.
        ctypes.windll.user32.SetWindowRgn(hwnd, rgn, True)
    except Exception:
        pass


def _keep_topmost(win):
    """Re-assert HWND_TOPMOST every 500 ms so the window stays above all apps."""
    try:
        import ctypes
        hwnd = int(win.winfo_id())
        ctypes.windll.user32.SetWindowPos(
            hwnd, -1, 0, 0, 0, 0, 0x0003)  # HWND_TOPMOST | SWP_NOMOVE | SWP_NOSIZE
    except Exception:
        pass
    try:
        win.after(500, lambda: _keep_topmost(win))
    except Exception:
        pass


_FONT_CACHE = {}


def _font(family=None, size=10, weight="normal", slant="roman"):
    """A tkfont.Font that is guaranteed to outlive the canvas items using it.

    A canvas text item stores only the *name* of its Tcl font, not the font
    itself. A tkfont.Font built as a local variable is garbage collected as
    soon as the function returns, and its __del__ runs `font delete` — leaving
    every canvas item that was drawn with it pointing at a font that no longer
    exists. Tk then crashes on the next redraw or when the widget is torn down.

    Only needed where the measured metrics are wanted (measure / linespace); a
    plain ("Segoe UI", 10) tuple is handled by Tk directly and is always safe.
    Don't use this for a font you intend to mutate — RoundedButton reconfigures
    its own weight and therefore keeps a private instance.
    """
    family = family or UI_FONT
    key = (family, size, weight, slant)
    f = _FONT_CACHE.get(key)
    if f is None:
        f = tkfont.Font(family=family, size=size, weight=weight, slant=slant)
        _FONT_CACHE[key] = f
    return f


def _round_rect(canvas, x1, y1, x2, y2, r, **kw):
    """Draw a rounded rectangle on a Canvas using a smoothed polygon."""
    r = min(r, (x2 - x1) // 2, (y2 - y1) // 2)
    pts = [
        x1 + r, y1, x2 - r, y1, x2, y1,
        x2, y1 + r, x2, y2 - r, x2, y2,
        x2 - r, y2, x1 + r, y2, x1, y2,
        x1, y2 - r, x1, y1 + r, x1, y1,
    ]
    return canvas.create_polygon(pts, smooth=True, **kw)


class IconCanvas(tk.Canvas):
    """Monochrome icon drawn directly on a Canvas — no icon-font dependency."""

    def __init__(self, parent, name, size=18, color="#7a85a0", bg_parent=BG):
        super().__init__(parent, width=size, height=size, bg=bg_parent,
                         highlightthickness=0, bd=0)
        self._name = name
        self._size = size
        self._color = color
        self._draw()

    def set_color(self, color):
        self._color = color
        self._draw()

    def configure(self, **kw):
        super().configure(**kw)
        if "bg" in kw or "background" in kw:
            self._draw()

    config = configure

    def _draw(self):
        self.delete("all")
        s = self._size
        c = self._color
        n = self._name
        if n == "mic":
            self._mic(s, c)
        elif n == "volume":
            self._volume(s, c)
        elif n == "chevron-down":
            self._chevron(s, c)
        elif n == "bullet":
            self._bullet(s, c)

    def _mic(self, s, c):
        w = s * 0.42
        x1, x2 = (s - w) / 2, (s + w) / 2
        y1, y2 = s * 0.10, s * 0.62
        _round_rect(self, x1, y1, x2, y2, w / 2, fill=c, outline=c)
        self.create_arc(s * 0.20, s * 0.45, s * 0.80, s * 0.80,
                        start=180, extent=180, style="arc",
                        outline=c, width=max(2, int(s * 0.10)))
        line_w = max(2, int(s * 0.10))
        self.create_line(s / 2, s * 0.78, s / 2, s * 0.92,
                         fill=c, width=line_w, capstyle="round")
        self.create_line(s * 0.34, s * 0.92, s * 0.66, s * 0.92,
                         fill=c, width=line_w, capstyle="round")

    def _volume(self, s, c):
        self.create_rectangle(s * 0.18, s * 0.40, s * 0.32, s * 0.60,
                              fill=c, outline=c)
        pts = [s * 0.32, s * 0.40, s * 0.50, s * 0.22,
               s * 0.50, s * 0.78, s * 0.32, s * 0.60]
        self.create_polygon(pts, fill=c, outline=c)
        wave_w = max(2, int(s * 0.10))
        self.create_arc(s * 0.50, s * 0.30, s * 0.72, s * 0.70,
                        start=-50, extent=100, style="arc",
                        outline=c, width=wave_w)
        self.create_arc(s * 0.58, s * 0.18, s * 0.90, s * 0.82,
                        start=-50, extent=100, style="arc",
                        outline=c, width=wave_w)

    def _chevron(self, s, c):
        line_w = max(2, int(s * 0.14))
        pad = s * 0.25
        mid = s / 2
        self.create_line(pad,     s * 0.40, mid, s * 0.65,
                         fill=c, width=line_w,
                         capstyle="round", joinstyle="round")
        self.create_line(s - pad, s * 0.40, mid, s * 0.65,
                         fill=c, width=line_w,
                         capstyle="round", joinstyle="round")

    def _bullet(self, s, c):
        r = s * 0.18
        cx = cy = s / 2
        self.create_oval(cx - r, cy - r, cx + r, cy + r, fill=c, outline=c)


class RoundedButton(tk.Canvas):
    """Flex-width rounded button with optional icon and filled/outline variant."""

    def __init__(self, parent, text, command, primary=False,
                 icon_name=None, bg_parent=BG, height=36, radius=6):
        self._font = tkfont.Font(family=UI_FONT, size=10,
                                 weight="bold" if primary else "normal")
        self._text = text
        self._icon = icon_name
        self._icon_size = 14
        self._primary = primary
        self._bg_parent = bg_parent
        self._H = height + 8   # extra space below for primary's glow halo
        self._R = radius
        self._command = command
        self._hover = False
        self._btn_h = height
        min_w = (self._font.measure(text)
                 + (self._icon_size + 8 if icon_name else 0)
                 + 28)
        super().__init__(parent, width=min_w, height=self._H,
                         bg=bg_parent, highlightthickness=0, bd=0,
                         cursor="hand2")
        self.bind("<Configure>", lambda e: self._draw())
        self.bind("<Enter>",     lambda e: self._set_hover(True))
        self.bind("<Leave>",     lambda e: self._set_hover(False))
        self.bind("<Button-1>",  lambda e: command())

    def _set_hover(self, on):
        self._hover = on
        self._draw()

    def set_primary(self, primary):
        """Switch filled/outline variant at runtime (used by segmented tabs)."""
        self._primary = primary
        self._font.configure(weight="bold" if primary else "normal")
        self._draw()

    def set_text(self, text):
        """Relabel the button at runtime (used when Generate/Sync toggles)."""
        self._text = text
        self._draw()

    def _draw(self):
        self.delete("all")
        w = max(self.winfo_width(), self.winfo_reqwidth())
        h = self._btn_h
        if self._primary:
            fill   = ACCENT_HOVER if self._hover else ACCENT
            border = fill
            tcol   = ACCENT_INK
            # Soft glow underneath (concentric blurred rounds)
            for off in range(5, 0, -1):
                col = _mix(self._bg_parent, ACCENT_GLOW, 0.25 - off * 0.03)
                _round_rect(self, off, off + 4, w - off, h + off + 4,
                            self._R + off, fill=col, outline=col)
            _round_rect(self, 0, 0, w, h, self._R, fill=border, outline=border)
            # Vertical ramp instead of a flat fill. Tk has no gradient brush,
            # so the face is drawn a scanline at a time and each line is inset
            # by the corner arc it crosses — which is what keeps the rounded
            # shape a flat fill would have given for free.
            self._ramp(1, 1, w - 1, h - 1, max(1, self._R - 1),
                       _mix(fill, "#ffffff", 0.16), _mix(fill, ACCENT_DARK, 0.55))
            # Top inner highlight
            self.create_line(self._R, 1, w - self._R, 1,
                             fill=_mix(fill, "#ffffff", 0.42))
        else:
            fill   = BG_HOVER if self._hover else BG
            border = BORDER_BRIGHT if self._hover else BORDER
            tcol   = FG_DIM
            _round_rect(self, 0, 0, w, h, self._R, fill=border, outline=border)
            _round_rect(self, 1, 1, w - 1, h - 1, max(1, self._R - 1),
                        fill=fill, outline=fill)

        cy = h // 2
        if self._icon:
            iw = self._icon_size
            tw = self._font.measure(self._text)
            gap = 8
            total = iw + gap + tw
            ix = (w - total) // 2
            self._draw_inline_icon(self._icon, ix, cy - iw // 2,
                                   iw, tcol, fill)
            self.create_text(ix + iw + gap, cy, anchor="w",
                             text=self._text, fill=tcol, font=self._font)
        else:
            self.create_text(w // 2, cy, text=self._text,
                             fill=tcol, font=self._font)

    def _ramp(self, x1, y1, x2, y2, r, top, bottom):
        """Fill a rounded rect with a vertical two-stop ramp, one line a row."""
        h = int(y2 - y1)
        if h <= 0:
            return
        for i in range(h):
            y = y1 + i
            dy = 0.0
            if i < r:
                dy = r - i
            elif i > h - r:
                dy = i - (h - r)
            inset = 0.0
            if dy > 0:
                inset = r - math.sqrt(max(0.0, r * r - dy * dy))
            col = _mix(top, bottom, i / float(max(1, h - 1)))
            self.create_line(x1 + inset, y, x2 - inset, y, fill=col)

    def _draw_inline_icon(self, name, x, y, s, color, bg):
        """Render a small IconCanvas-style glyph in-place on the button canvas."""
        if name == "mic":
            w = s * 0.42
            x1, x2 = x + (s - w) / 2, x + (s + w) / 2
            y1, y2 = y + s * 0.10, y + s * 0.62
            _round_rect(self, x1, y1, x2, y2, w / 2, fill=color, outline=color)
            lw = max(2, int(s * 0.10))
            self.create_arc(x + s * 0.20, y + s * 0.45,
                            x + s * 0.80, y + s * 0.80,
                            start=180, extent=180, style="arc",
                            outline=color, width=lw)
            self.create_line(x + s / 2, y + s * 0.78,
                             x + s / 2, y + s * 0.92,
                             fill=color, width=lw, capstyle="round")
            self.create_line(x + s * 0.34, y + s * 0.92,
                             x + s * 0.66, y + s * 0.92,
                             fill=color, width=lw, capstyle="round")


class RoundedField(tk.Canvas):
    """Rounded container holding a single child widget (Entry / Label row).

    Draws a hairline border + filled background and re-lays out on resize.
    The child is positioned via create_window with horizontal padding `padx`
    and centered vertically.
    """

    def __init__(self, parent, height=44, radius=4, padx=16,
                 bg_parent=BG, fill=BG_INPUT, border=BORDER):
        # width=80 rather than Tk's 378px Canvas default. Every field either
        # packs fill="x" or is given an explicit width, so the default is only
        # ever a *requested* size — but 378 asks for more than a setup column
        # has, and a card wider than its column is clipped, not widened.
        super().__init__(parent, height=height, width=80, bg=bg_parent,
                         highlightthickness=0, bd=0)
        self._h = height
        self._r = radius
        self._padx = padx
        self._fill = fill
        self._border = border
        self._child = None
        self._right_child = None  # optional right-side widget (e.g. chevron)
        self._child_win = None
        self._right_win = None
        self.bind("<Configure>", lambda e: self._redraw())

    def set_child(self, child, right_child=None):
        self._child = child
        self._right_child = right_child
        self._redraw()

    def set_border(self, color):
        self._border = color
        self._redraw()

    def set_fill(self, color):
        self._fill = color
        self._redraw()

    def set_height(self, height):
        """Re-height the field around a child whose size isn't known up front
        (a cue editor sized to the current lines-per-cue budget)."""
        height = int(height)
        if height == self._h:
            return
        self._h = height
        self.configure(height=height)
        self._redraw()

    def _redraw(self):
        self.delete("bg")
        w = self.winfo_width()
        h = self._h
        # Outer (border) rounded rect
        _round_rect(self, 0, 0, w, h, self._r,
                    fill=self._border, outline=self._border, tags=("bg",))
        # Inner fill
        _round_rect(self, 1, 1, w - 1, h - 1, max(1, self._r - 1),
                    fill=self._fill, outline=self._fill, tags=("bg",))
        # Keep background polygons below the hosted child widgets
        self.tag_lower("bg")

        # Place right child first so we can measure its width
        right_w = 0
        if self._right_child is not None:
            if self._right_win is None:
                self._right_win = self.create_window(
                    w - 6, h // 2, anchor="e", window=self._right_child)
            else:
                self.coords(self._right_win, w - 6, h // 2)
            self.update_idletasks()
            right_w = self._right_child.winfo_reqwidth() + 8

        if self._child is not None:
            child_w = max(10, w - self._padx * 2 - right_w)
            if self._child_win is None:
                self._child_win = self.create_window(
                    self._padx, h // 2, anchor="w",
                    window=self._child, width=child_w)
            else:
                self.coords(self._child_win, self._padx, h // 2)
                self.itemconfigure(self._child_win, width=child_w)


class PillEntry(RoundedField):
    """Rounded text input with a placeholder that never reaches the variable.

    The Entry is deliberately NOT bound to `textvariable` with Tk's own
    `textvariable=` option. Placeholder text is shown by inserting it into the
    Entry, and a bound variable would receive it as a real value — so an empty
    "Full path to the .srt…" field would read back as a path, and callers had
    to special-case the hint string ("Name…") to spot an empty box. Instead the
    two are synced by hand in `_push` / `_pull`, and `_push` refuses to run
    while the placeholder is on screen.
    """

    def __init__(self, parent, textvariable, placeholder="", bg_parent=BG,
                 height=40):
        super().__init__(parent, height=height, radius=4, padx=12,
                         bg_parent=bg_parent, fill=BG_INPUT, border=BORDER)
        self._focused = False
        self._var = textvariable
        self._placeholder = placeholder
        self._ph_shown = False
        self._pushing = False
        self.entry = tk.Entry(
            # width=8, not the Tk default of 20 characters. This field is
            # always packed fill="x", so its natural width never decides its
            # real one — but it does decide the requested width of the card
            # it sits in, and a card asking for more than its column has is
            # clipped rather than widened.
            self, width=8,
            bg=BG_INPUT, fg=FG, insertbackground=SELECT,
            relief="flat", bd=0, highlightthickness=0,
            font=(UI_FONT, 10),
        )
        self.set_child(self.entry)
        self.entry.bind("<FocusIn>",  lambda e: self._set_focus(True))
        self.entry.bind("<FocusOut>", lambda e: self._set_focus(False))
        self.entry.bind("<KeyRelease>", self._push)
        for seq in ("<<Paste>>", "<<Cut>>", "<<Clear>>"):
            self.entry.bind(seq, lambda e: self.after_idle(self._push))
        try:
            textvariable.trace_add("write", lambda *a: self._pull())
        except AttributeError:
            textvariable.trace("w", lambda *a: self._pull())
        self._pull()

    # ── variable ⇄ entry ─────────────────────────────────────────────────
    def _pull(self):
        """Variable changed elsewhere (preset load, reel style) → entry."""
        if self._pushing or not self.entry.winfo_exists():
            return
        val = self._var.get()
        self._ph_shown = False
        self.entry.configure(fg=FG)
        self.entry.delete(0, "end")
        if val:
            self.entry.insert(0, val)
        elif not self._focused:
            self._show_placeholder()

    def _push(self, _e=None):
        """Typing → variable. Never runs while the placeholder is showing."""
        if self._ph_shown:
            return
        self._pushing = True
        try:
            self._var.set(self.entry.get())
        finally:
            self._pushing = False

    # ── grey hint shown while the field is empty and unfocused ────────────
    def _show_placeholder(self):
        if not self._placeholder or self._var.get():
            return
        self.entry.delete(0, "end")
        self.entry.insert(0, self._placeholder)
        self.entry.configure(fg=FG_MUTE)
        self._ph_shown = True

    def _clear_placeholder(self):
        if self._ph_shown:
            self.entry.delete(0, "end")
            self.entry.configure(fg=FG)
            self._ph_shown = False

    def _set_focus(self, on):
        self._focused = on
        if on:
            self._clear_placeholder()
        elif not self.entry.get():
            self._show_placeholder()
        self._redraw()

    def focus(self):
        self.entry.focus()


class SmallInput(RoundedField):
    """Compact numeric input cell — same Fluent-style focus underline.

    Set in FONT_NUM rather than Segoe: these cells hold slider-linked values
    like 0.120, and fixed-width figures keep the digits from shifting sideways
    while you drag.
    """

    def __init__(self, parent, textvariable, unit=None, bg_parent=BG,
                 size=10, height=36):
        super().__init__(parent, height=height, radius=4, padx=10,
                         bg_parent=bg_parent, fill=BG_INPUT, border=BORDER)
        self._focused = False
        self._var = textvariable
        self.entry = tk.Entry(
            # Four digits is the widest value any of these cells holds.
            self, textvariable=textvariable, width=4,
            bg=BG_INPUT, fg=FG, insertbackground=SELECT,
            relief="flat", bd=0, highlightthickness=0,
            font=(FONT_NUM, size),
            justify="left",
        )
        # The unit rides in RoundedField's right-hand slot rather than being
        # baked into the value, so what the entry holds stays a bare number.
        unit_lbl = None
        if unit:
            unit_lbl = tk.Label(self, text=unit, bg=BG_INPUT, fg=FG_MUTE,
                                font=(UI_FONT, 8))
        self.set_child(self.entry, right_child=unit_lbl)
        self.entry.bind("<FocusIn>",  lambda e: self._set_focus(True))
        self.entry.bind("<FocusOut>", lambda e: self._set_focus(False))

    def _set_focus(self, on):
        self._focused = on
        self._redraw()

    def _redraw(self):
        super()._redraw()

    def focus(self):
        self.entry.focus()


class RowHandle:
    """Show/hide one settings row (and the hairline above it) in place.

    pack_forget loses a widget's position and re-packing appends it to the end
    of the container, so a row that came back would land at the bottom of its
    card. The sibling order is therefore snapshotted the first time the row is
    hidden — by then the card is fully built — and a restored row is packed
    `before` the first sibling that is still packed and was originally after it.

    Visibility is tracked here rather than read back from winfo_ismapped():
    every row of an inactive tab is unmapped, so asking Tk would report the
    whole Type tab as hidden whenever another tab is in front, and show() would
    re-pack — and reorder — rows nobody had hidden.
    """

    def __init__(self, container, row, divider=None, pack_opts=None):
        self._container = container
        self._row = row
        self._divider = divider
        # Rows fill the card's width and nothing else; a whole group card also
        # carries the gap to the card below it, which pack_forget would drop.
        self._opts = dict(pack_opts or {"fill": "x"})
        self._order = None
        self._visible = True

    def show(self):
        if self._visible:
            return
        self._visible = True
        after = self._order[self._order.index(self._row) + 1:] if self._order else []
        packed = set(self._container.pack_slaves())
        anchor = next((w for w in after
                       if w.winfo_exists() and w in packed), None)
        for w in (self._divider, self._row):
            if w is None:
                continue
            opts = dict(self._opts) if w is self._row else {"fill": "x"}
            if anchor is not None:
                opts["before"] = anchor
            w.pack(**opts)

    def hide(self):
        if not self._visible:
            return
        if self._order is None:
            self._order = list(self._container.pack_slaves())
        self._visible = False
        for w in (self._divider, self._row):
            if w is not None:
                w.pack_forget()

    def set_visible(self, on):
        self.show() if on else self.hide()

    @property
    def visible(self):
        return self._visible

    @staticmethod
    def tidy_dividers(container):
        """Drop a hairline that has become the first thing in the card.

        A divider means "there is a row above this one". Hiding the first row of
        a card promotes the second row's divider to the top, where it draws a
        stray line straight under the header band. Called after any visibility
        change, so whichever row is first has no rule above it.

        Only ever removes: show() re-packs a row's own divider, so a divider
        that stops being the leading one comes back on its own.
        """
        slaves = [w for w in container.pack_slaves() if w.winfo_exists()]
        for w in slaves:
            if not getattr(w, "_is_row_divider", False):
                break                     # first element is a real row: done
            w.pack_forget()


# Categories a combining mark falls into: Mn for the non-spacing signs (ु, ्,
# ঁ) and Mc for the spacing ones (ा, ी, ো). A caret is never allowed to stop on
# one of these — see CueText._snap_insert.
_MARK_CATEGORIES = ("Mn", "Mc")
# Every virama/halant in the scripts this tool targets. A consonant followed by
# one is joined to whatever comes next, so the position after the virama is
# inside a conjunct even though the next character is an ordinary letter.
_VIRAMAS = "्্੍્୍்్್്්"


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
    ("arab", "Urdu", ("Noto Naskh Arabic", "Urdu Typesetting", "Aldhabi",
                      "Segoe UI")),
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
        installed = set(tkfont.families())
    except Exception:
        installed = set()

    overrides = {}
    try:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "subtitle_style.json")
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


_CUE_FONT = None


def cue_font_family():
    """The family cue text is drawn in, resolved once against what is installed.

    Segoe UI carries no Indic glyphs at all. Asked to render a Devanagari or
    Bengali cue in it, Tk falls back glyph by glyph, and a fallback that happens
    per character cannot shape a cluster: the vowel sign gets separated from its
    consonant and drawn on its own dotted circle, so मिलता came out as मिलत◌ा.
    Every script this tool targets was affected — it is not a Hindi problem.

    Nirmala UI is Windows' pan-Indic UI font and covers all of Devanagari,
    Bengali/Assamese, Gujarati, Gurmukhi, Kannada, Malayalam, Odia, Tamil and
    Telugu in one family, so the whole cue is one run and shapes correctly.
    Resolved at first use rather than at import: tkfont.families() needs a live
    interpreter, and this module is imported before Tk starts.
    """
    global _CUE_FONT
    if _CUE_FONT is not None:
        return _CUE_FONT
    try:
        installed = set(tkfont.families())
    except Exception:
        installed = set()
    for family in ("Nirmala UI", "Nirmala Text", "Mangal", "Segoe UI"):
        if family in installed:
            _CUE_FONT = family
            break
    else:
        _CUE_FONT = "Segoe UI"
    return _CUE_FONT


class CueText(tk.Frame):
    """Multi-line cue editor for the review list.

    A cue is wrapped text, so with "Lines per cue" above 1 it holds real
    newline characters. The list used to edit it in a tk.Entry, which is
    single-line: the newline showed as an unselectable control glyph, the second
    line was invisible, and proofreading a two-line cue — the thing this tool
    mostly produces — was impossible. This is a tk.Text sized to the line
    budget, wrapping on words, with Return swallowed so a cue can never grow
    more lines than the budget allows. Return is not wasted, though: the review
    list registers ``on_return`` to break the cue in two at the caret, which is
    what pressing Enter mid-sentence means for a subtitle.

    Exposes just enough of the old Entry surface for the review code:
    ``.get()``, ``.on_change()`` and ``.words_before_cursor()``. Deliberately no
    StringVar: the widget IS the value, and a mirror variable is the kind of
    second source of truth that let hand edits get silently reverted.
    """

    def __init__(self, parent, text="", lines=1, bg_parent=BG_INPUT):
        super().__init__(parent, bg=bg_parent)
        self._lines = max(1, int(lines))
        self._cbs = []
        self._ret_cbs = []
        self._syncing = False
        self.text = tk.Text(
            self, height=self._lines, wrap="word", bg=bg_parent, fg=FG,
            insertbackground=SELECT, relief="flat", bd=0, highlightthickness=0,
            font=(cue_font_family(), 12), padx=0, pady=0, spacing1=1, spacing3=1,
            undo=True, maxundo=50,
        )
        self.text.pack(fill="both", expand=True)
        if text:
            self.text.insert("1.0", text)
        self.text.bind("<<Modified>>", self._on_modified)
        # Return would add a line the cue budget has no room for, so it never
        # reaches the text — it splits the cue at the caret instead (on_return).
        # Tab belongs to focus traversal, not to the text.
        self.text.bind("<Return>", self._on_return)
        self.text.bind("<KP_Enter>", self._on_return)
        self.text.bind("<Tab>", self._focus_next)

        # Keep the caret off the inside of a grapheme cluster. Tk positions the
        # insertion cursor between two characters, and in an Indic script the
        # vowel sign is its own character — so a caret "between" त and ा splits
        # the cluster, and the orphaned matra is drawn on a dotted circle:
        # मिलता became मिलत◌ा the moment the cue was clicked. It is not a font
        # problem (it happens identically in Segoe UI and Nirmala UI, and not at
        # all with no caret in either), so the fix is to stop the caret landing
        # there. Bound with add="+" and run from the idle queue so Tk's own
        # handler has already moved the insert mark by the time we adjust it.
        for seq in ("<Button-1>", "<ButtonRelease-1>", "<Right>", "<Home>",
                    "<End>", "<Up>", "<Down>", "<Control-Left>",
                    "<Control-Right>"):
            self.text.bind(seq, self._queue_snap, add="+")
        self.text.bind("<Left>", lambda e: self._queue_snap(e, forward=False),
                       add="+")

    # ── Grapheme-cluster-safe caret ──────────────────────────────────────
    def _queue_snap(self, _e=None, forward=True):
        try:
            self.text.after_idle(lambda: self._snap_insert(forward))
        except Exception:
            pass

    def _inside_cluster(self, idx):
        """True when ``idx`` sits between a base letter and its marks.

        Two ways that happens: the character at the caret is a combining mark,
        or the character just behind it is a virama, which joins the consonant
        before it to whatever follows.
        """
        t = self.text
        here = t.get(idx, "%s+1c" % idx)
        if here and unicodedata.category(here) in _MARK_CATEGORIES:
            return True
        prev = t.get("%s-1c" % idx, idx)
        return bool(prev) and prev in _VIRAMAS

    def _snap_insert(self, forward=True):
        """Move the caret to the nearest cluster boundary, if it is not on one.

        Travels the way the caret was already travelling, so Left out of a
        cluster keeps going left instead of being bounced back in.
        """
        t = self.text
        try:
            if not t.winfo_exists():
                return
            # Never fight a drag-selection: snapping mid-drag would fight the
            # user's own anchor.
            if t.tag_ranges("sel"):
                return
            idx = t.index("insert")
            if not self._inside_cluster(idx):
                return
            step = "+1c" if forward else "-1c"
            for _ in range(8):          # a cluster this long is already broken
                nxt = t.index("%s%s" % (idx, step))
                if nxt == idx:
                    break
                idx = nxt
                if not self._inside_cluster(idx):
                    break
            t.mark_set("insert", idx)
        except Exception:
            pass

    # ── Entry-ish surface ────────────────────────────────────────────────
    def get(self):
        return self.text.get("1.0", "end-1c")

    def on_change(self, callback):
        self._cbs.append(callback)

    def on_return(self, callback):
        """Run ``callback`` when Enter is pressed. The keystroke is still
        swallowed either way, so a failing callback cannot leave a stray newline
        in a cue that has no room for one."""
        self._ret_cbs.append(callback)

    def bind_all_widgets(self, seq, fn):
        """Bind on the frame and the Text, so a click anywhere in the cell
        selects the row (the Text covers the whole cell)."""
        for w in (self, self.text):
            w.bind(seq, fn, add="+")

    def words_before_cursor(self):
        """How many whitespace-separated words precede the insertion point —
        where a manual split should cut."""
        try:
            upto = self.text.get("1.0", "insert")
        except Exception:
            return 0
        return len(upto.split())

    def focus(self, at_start=False):
        self.text.focus_set()
        if at_start:
            # After a split the caret belongs at the head of the new second
            # half, so Enter can be pressed again to keep breaking it down.
            try:
                self.text.mark_set("insert", "1.0")
                self.text.see("insert")
            except Exception:
                pass

    # ── change plumbing ──────────────────────────────────────────────────
    def _on_return(self, _e=None):
        for cb in list(self._ret_cbs):
            try:
                cb()
            except Exception:
                pass
        return "break"

    def _on_modified(self, _e=None):
        # <<Modified>> only fires again after the flag is cleared, and clearing
        # it re-fires the event — hence the guard.
        if self._syncing:
            return
        self._syncing = True
        try:
            self.text.edit_modified(False)
        finally:
            self._syncing = False
        for cb in self._cbs:
            try:
                cb()
            except Exception:
                pass

    def _focus_next(self, _e=None):
        try:
            self.text.tk_focusNext().focus_set()
        except Exception:
            pass
        return "break"


class Dropdown(RoundedField):
    """Rounded dropdown trigger + canvas-rendered rounded menu with pill rows."""

    ROW_H   = 34
    ROW_GAP = 2
    PAD     = 6
    CARD_R  = 8
    PILL_R  = 6

    # How many rows the menu shows before it starts scrolling. A 16-language
    # list rendered in full is a column of text taller than the card that
    # opened it; four rows is enough to read the neighbours of the current
    # pick and still look like a control rather than a page.
    MAX_ROWS = 8
    SB_W     = 4        # scrollbar thumb width
    SB_GAP   = 5        # gutter between the rows and the thumb

    def __init__(self, parent, values, variable, on_pick=None, icon_name=None,
                 display_prefix="", bg_parent=BG, height=48, radius=12,
                 max_rows=None):
        super().__init__(parent, height=height, radius=radius, padx=10,
                         bg_parent=bg_parent, fill=BG_INPUT, border=BORDER)
        self.values = list(values)
        self.variable = variable
        self.on_pick = on_pick
        self.max_rows = max(1, int(max_rows or self.MAX_ROWS))
        self._popup = None
        self._shadow = None
        self._outside_bind = None

        body = tk.Frame(self, bg=BG_INPUT)
        if icon_name:
            self._icon = RoundedIconTile(body, icon_name=icon_name,
                                         size=28, radius=8,
                                         bg_parent=BG_INPUT)
            self._icon.configure(cursor="hand2")
            self._icon.pack(side="left", padx=(0, 10))
        else:
            self._icon = None
        # Trigger label. With a display_prefix the shown text is decorated
        # (e.g. "Auto-detect · Hindi") while `variable` still holds the raw
        # value ("Hindi") used everywhere else, including the menu rows.
        if display_prefix:
            self._disp = tk.StringVar()
            def _sync_disp(*_a, v=variable, pfx=display_prefix):
                self._disp.set(pfx + v.get())
            variable.trace_add("write", _sync_disp)
            _sync_disp()
            label_var = self._disp
        else:
            label_var = variable
        self._label = tk.Label(
            body, textvariable=label_var, bg=BG_INPUT, fg=FG,
            font=(UI_FONT, 10), anchor="w", cursor="hand2",
        )
        self._label.pack(side="left", fill="x", expand=True)
        self._body = body

        self._arrow = IconCanvas(self, "chevron-down", size=12, color=FG_MUTE,
                                 bg_parent=BG_INPUT)
        self._arrow.configure(cursor="hand2")
        self.set_child(body, right_child=self._arrow)

        click_targets = [self._label, self._arrow, self, body]
        if self._icon is not None:
            click_targets.append(self._icon)
        for w in click_targets:
            w.bind("<Button-1>", self._toggle)
        for w in (body, self._label, self._arrow):
            w.bind("<Enter>", lambda e: self._hover(True))
            w.bind("<Leave>", lambda e: self._hover(False))

    def _hover(self, on):
        if self._popup:
            return
        c = BG_HOVER if on else BG_INPUT
        self.set_fill(c)
        self._body.configure(bg=c)
        self._label.configure(bg=c)
        self._arrow.configure(bg=c)
        if self._icon is not None:
            self._icon.configure(bg=c)

    def _toggle(self, _e=None):
        if self._popup:
            self._close()
        else:
            self._open()

    def _open(self):
        self.update_idletasks()

        x = self.winfo_rootx()
        y = self.winfo_rooty() + self.winfo_height() + 4
        w = self.winfo_width()
        n = max(1, len(self.values))
        # Only `max_rows` rows are on screen at once; the rest are scrolled to.
        vis = min(n, self.max_rows)
        self._vis = vis
        self._n = n
        self._step = self.ROW_H + self.ROW_GAP
        self._max_top = n - vis                  # largest first-visible index
        h = self.PAD * 2 + vis * self.ROW_H + (vis - 1) * self.ROW_GAP

        # A long list (11 caption styles) opened from a field low in the window
        # ran straight off the bottom of the screen, with the last entries
        # unreachable. Flip above the field when there is more room up there,
        # and clamp to the screen either way.
        screen_h = self.winfo_screenheight()
        above = self.winfo_rooty() - 4 - h
        if y + h > screen_h and above > 0:
            y = above
        y = max(0, min(y, max(0, screen_h - h)))
        x = max(0, min(x, max(0, self.winfo_screenwidth() - w)))

        # ── Popup toplevel (rounded card, pill rows; no border, no shadow)
        self._popup = tk.Toplevel(self)
        self._popup.overrideredirect(True)
        try:
            self._popup.attributes("-topmost", True)
            self._popup.attributes("-transparentcolor", TRANSPARENT_KEY)
        except Exception:
            pass
        self._popup.configure(bg=TRANSPARENT_KEY)
        self._popup.geometry("%dx%d+%d+%d" % (w, h, x, y))

        c = tk.Canvas(self._popup, bg=TRANSPARENT_KEY,
                      highlightthickness=0, bd=0, width=w, height=h)
        c.pack(fill="both", expand=True)
        self._canvas = c
        self._menu_w = w
        self._menu_h = h

        # Card backdrop — flat fill, no visible border
        _round_rect(c, 0, 0, w, h, self.CARD_R,
                    fill=BG_INPUT, outline=BG_INPUT)

        # Open with the current pick in view, roughly centred in the window so
        # the neighbours above and below it are both readable.
        try:
            cur_i = self.values.index(self.variable.get())
        except ValueError:
            cur_i = 0
        self._top = max(0, min(self._max_top, cur_i - vis // 2))
        self._hl = cur_i
        self._render_rows()

        if self._max_top:
            c.bind("<MouseWheel>", self._on_wheel)
            self._popup.bind("<MouseWheel>", self._on_wheel)
            c.tag_bind("sbar", "<Button-1>", self._on_sb_press)
            c.tag_bind("sbar", "<B1-Motion>", self._on_sb_drag)

        c.configure(cursor="hand2")
        self._popup.bind("<Escape>", lambda e: self._close())
        self._popup.bind("<Up>", lambda e: self._move_hl(-1))
        self._popup.bind("<Down>", lambda e: self._move_hl(1))
        self._popup.bind("<Prior>", lambda e: self._move_hl(-self._vis))
        self._popup.bind("<Next>", lambda e: self._move_hl(self._vis))
        self._popup.bind("<Home>", lambda e: self._move_hl(-self._n))
        self._popup.bind("<End>", lambda e: self._move_hl(self._n))
        self._popup.bind("<Return>",
                         lambda e: self._pick(self.values[self._hl]))

        # Click-outside-to-close
        root = self.winfo_toplevel()
        self._outside_bind = root.bind("<Button-1>",
                                       self._maybe_close_outside, add="+")
        self._popup.focus_set()

    # ── Menu rendering ──────────────────────────────────────────────────────
    def _render_rows(self):
        """Draw the `_vis` rows starting at `_top`, plus the scroll thumb.

        Only the visible window is drawn, and scrolling snaps to whole rows,
        so nothing ever needs clipping: a half row bleeding into the card's
        6px padding would clip badly against the transparent rounded corners.
        """
        c = self._canvas
        if not c.winfo_exists():
            return
        c.delete("rows")
        w, h = self._menu_w, self._menu_h
        gutter = (self.SB_W + self.SB_GAP) if self._max_top else 0
        current = self.variable.get()
        row_font = (UI_FONT, 10)

        for slot in range(self._vis):
            i = self._top + slot
            v = self.values[i]
            ry1 = self.PAD + slot * self._step
            ry2 = ry1 + self.ROW_H
            rx1 = self.PAD
            rx2 = w - self.PAD - gutter
            is_cur = (v == current) or (i == self._hl)
            fill = BG_HOVER if is_cur else BG_INPUT
            tag = "row%d" % i
            rect = _round_rect(c, rx1, ry1, rx2, ry2, self.PILL_R,
                               fill=fill, outline=fill, tags=(tag, "rows"))
            c.create_text(rx1 + 16, (ry1 + ry2) // 2, anchor="w",
                          text=v, fill=FG, font=row_font, tags=(tag, "rows"))

            def on_enter(_e, r=rect):
                c.itemconfig(r, fill=BG_HOVER, outline=BG_HOVER)

            def on_leave(_e, r=rect, cur=is_cur):
                color = BG_HOVER if cur else BG_INPUT
                c.itemconfig(r, fill=color, outline=color)

            c.tag_bind(tag, "<Enter>", on_enter)
            c.tag_bind(tag, "<Leave>", on_leave)
            c.tag_bind(tag, "<Button-1>", lambda e, val=v: self._pick(val))

        if not self._max_top:
            return

        # Slim thumb in the right gutter, sized to the visible fraction.
        tx2 = w - self.PAD
        tx1 = tx2 - self.SB_W
        ty1, ty2 = self.PAD, h - self.PAD
        track = ty2 - ty1
        thumb = max(20, int(track * self._vis / float(self._n)))
        off = int((track - thumb) * self._top / float(self._max_top))
        _round_rect(c, tx1, ty1, tx2, ty2, self.SB_W // 2,
                    fill=TRACK_OFF, outline=TRACK_OFF, tags=("rows", "sbar"))
        _round_rect(c, tx1, ty1 + off, tx2, ty1 + off + thumb,
                    self.SB_W // 2, fill=FG_MUTE, outline=FG_MUTE,
                    tags=("rows", "sbar"))

    def _scroll_to(self, top):
        top = max(0, min(self._max_top, int(top)))
        if top != self._top:
            self._top = top
            self._render_rows()

    def _on_wheel(self, e):
        self._scroll_to(self._top - int(e.delta / 120))
        return "break"

    def _on_sb_press(self, e):
        self._scroll_from_y(e.y)
        return "break"

    def _on_sb_drag(self, e):
        self._scroll_from_y(e.y)
        return "break"

    def _scroll_from_y(self, y):
        """Map a y inside the scrollbar track to a first-visible index."""
        ty1, ty2 = self.PAD, self._menu_h - self.PAD
        track = max(1, ty2 - ty1)
        thumb = max(20, int(track * self._vis / float(self._n)))
        span = max(1, track - thumb)
        frac = (y - ty1 - thumb / 2.0) / span
        self._scroll_to(round(frac * self._max_top))

    def _move_hl(self, delta):
        """Keyboard nav: move the highlight and keep it inside the window."""
        if not self._popup:
            return "break"
        self._hl = max(0, min(self._n - 1, self._hl + delta))
        if self._hl < self._top:
            self._top = self._hl
        elif self._hl >= self._top + self._vis:
            self._top = self._hl - self._vis + 1
        self._top = max(0, min(self._max_top, self._top))
        self._render_rows()
        return "break"

    def _maybe_close_outside(self, event):
        if not self._popup:
            return
        wx = self._popup.winfo_rootx()
        wy = self._popup.winfo_rooty()
        ww = self._popup.winfo_width()
        wh = self._popup.winfo_height()
        if wx <= event.x_root < wx + ww and wy <= event.y_root < wy + wh:
            return
        sx = self.winfo_rootx()
        sy = self.winfo_rooty()
        sw = self.winfo_width()
        sh = self.winfo_height()
        if sx <= event.x_root < sx + sw and sy <= event.y_root < sy + sh:
            return
        self._close()

    def _pick(self, value):
        self.variable.set(value)
        self._close()
        if self.on_pick:
            self.on_pick(value)

    def _close(self):
        if self._popup:
            self._popup.destroy()
            self._popup = None
        if self._shadow:
            self._shadow.destroy()
            self._shadow = None
        if self._outside_bind is not None:
            try:
                self.winfo_toplevel().unbind("<Button-1>", self._outside_bind)
            except Exception:
                pass
            self._outside_bind = None
        self._hover(False)


class ToggleSwitch(tk.Canvas):
    """Compact iOS-style toggle bound to an IntVar."""

    W, H = 38, 20

    def __init__(self, parent, variable):
        super().__init__(parent, width=self.W, height=self.H, bg=BG,
                         highlightthickness=0, bd=0, cursor="hand2")
        self.variable = variable
        self._draw()
        self.bind("<Button-1>", self._toggle)
        try:
            variable.trace_add("write", lambda *a: self._draw())
        except AttributeError:  # Py3.5
            variable.trace("w", lambda *a: self._draw())

    def _rounded(self, x0, y0, x1, y1, r, fill):
        self.create_oval(x0, y0, x0 + 2 * r, y1, fill=fill, outline=fill)
        self.create_oval(x1 - 2 * r, y0, x1, y1, fill=fill, outline=fill)
        self.create_rectangle(x0 + r, y0, x1 - r, y1, fill=fill, outline=fill)

    def _draw(self):
        # The bound IntVar lives on App and outlives this canvas: once the form
        # is torn down for the progress/review screen, a later write to
        # punct/diarize/outline/shadow/review still fires this trace. Every
        # other var-driven widget here guards the same way (Slider,
        # ComfortMeter, ReelPreview); this one did not, and raised
        # TclError "invalid command name .!toggleswitch" out of the Tk callback.
        if not self.winfo_exists():
            return
        self.delete("all")
        on = bool(self.variable.get())
        track = SELECT if on else TRACK_OFF
        self._rounded(1, 2, self.W - 1, self.H - 2, (self.H - 4) // 2, track)
        kx = self.W - 16 if on else 4
        thumb = SELECT_INK if on else THUMB_OFF
        self.create_oval(kx, 3, kx + 14, self.H - 3,
                         fill=thumb, outline=thumb)

    def _toggle(self, _e=None):
        self.variable.set(0 if self.variable.get() else 1)


def _hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _rgb_to_hex(rgb):
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(c))) for c in rgb)


def _mix(c1, c2, t):
    """Linear blend c1→c2 at t∈[0,1]."""
    r1, g1, b1 = _hex_to_rgb(c1)
    r2, g2, b2 = _hex_to_rgb(c2)
    return _rgb_to_hex((r1 + (r2 - r1) * t,
                       g1 + (g2 - g1) * t,
                       b1 + (b2 - b1) * t))


class LogoTile(tk.Canvas):
    """The Srutilekha mark: two caption bars on a rounded gold tile.

    Same geometry as make_icon.py — a long line with a shorter one under it,
    the way a subtitle sits on a frame. Change one, change the other.

    It used to draw five shapes here (three waveform bars plus two caption
    lines) with a per-row gradient and a highlight line along the top edge.
    In a 22px title-bar tile none of that survives: every shape lands on one
    or two pixels, Tk's canvas does not antialias lines, and the result was a
    smudge. Two bars snapped to whole pixels on a flat tile stay legible.
    """

    # Fractions of the tile, mirroring BAR_H / GAP / TOP_W / BOTTOM_W in
    # make_icon.py. The gap must stay wider than the bars are thick or the
    # pair reads as one block; the length ratio stays near 2:1.
    BAR_H = 0.11
    GAP = 0.15
    TOP_W = 0.58
    BOTTOM_W = 0.30

    def __init__(self, parent, size=38, radius=10, bg_parent=BG):
        super().__init__(parent, width=size, height=size,
                         bg=bg_parent, highlightthickness=0, bd=0)
        self._size = size
        self._radius = radius
        self._draw()

    def _bar(self, cy, width):
        """A caption bar centred on cy, on integer pixel edges."""
        s = self._size
        h = max(2, int(round(s * self.BAR_H)))
        half_w = int(round(width / 2.0))
        cx = s // 2
        y = int(round(cy - h / 2.0))
        self.create_rectangle(cx - half_w, y, cx + half_w, y + h,
                              fill=ACCENT_INK, outline="")

    def _draw(self):
        self.delete("all")
        s = self._size
        _round_rect(self, 0, 0, s, s, self._radius, fill=ACCENT, outline="")
        cy = s / 2.0
        # The bars are drawn h pixels thick, so the centre-to-centre offset has
        # to clear h or the ideal fraction rounds down into a merged block at
        # the smallest sizes.
        h = max(2, int(round(s * self.BAR_H)))
        off = max(int(round(s * self.GAP)), h + 1)
        self._bar(cy - off, s * self.TOP_W)
        self._bar(cy + off, s * self.BOTTOM_W)


class RoundedIconTile(tk.Canvas):
    """28×28 rounded tile (bg + 1px border) hosting either a canvas icon
    or a short text label (e.g. 'Aa')."""

    def __init__(self, parent, icon_name=None, text=None,
                 size=28, radius=8, bg_parent=BG_INPUT,
                 fill=BG_TILE, border=BORDER_TILE,
                 icon_color=FG_DIM, text_color=FG_DIM,
                 text_font=(UI_FONT, 9, "bold")):
        super().__init__(parent, width=size, height=size, bg=bg_parent,
                         highlightthickness=0, bd=0)
        self._size = size
        self._radius = radius
        self._fill = fill
        self._border = border
        self._icon_name = icon_name
        self._text = text
        self._icon_color = icon_color
        self._text_color = text_color
        self._text_font = text_font
        self._draw()

    def set_parent_bg(self, color):
        self.configure(bg=color)

    def _draw(self):
        self.delete("all")
        s = self._size
        # Border
        _round_rect(self, 0, 0, s, s, self._radius,
                    fill=self._border, outline=self._border)
        # Inner fill
        _round_rect(self, 1, 1, s - 1, s - 1, max(1, self._radius - 1),
                    fill=self._fill, outline=self._fill)
        # Glyph
        if self._text:
            self.create_text(s / 2, s / 2 + 1, text=self._text,
                             fill=self._text_color, font=self._text_font)
        elif self._icon_name:
            self._draw_icon(self._icon_name)

    def _draw_icon(self, name):
        s = self._size
        c = self._icon_color
        gx = s / 2
        gy = s / 2
        if name == "volume":
            # speaker body
            self.create_rectangle(s * 0.30, s * 0.42,
                                  s * 0.40, s * 0.58,
                                  fill=c, outline=c)
            pts = [s * 0.40, s * 0.42, s * 0.52, s * 0.28,
                   s * 0.52, s * 0.72, s * 0.40, s * 0.58]
            self.create_polygon(pts, fill=c, outline=c)
            wave_w = max(1, int(s * 0.07))
            self.create_arc(s * 0.52, s * 0.34, s * 0.70, s * 0.66,
                            start=-50, extent=100, style="arc",
                            outline=c, width=wave_w)
            self.create_arc(s * 0.58, s * 0.26, s * 0.80, s * 0.74,
                            start=-50, extent=100, style="arc",
                            outline=c, width=wave_w)
        elif name == "mic":
            bw = s * 0.13
            bh = s * 0.18
            _round_rect(self, gx - bw, gy - bh, gx + bw, gy + bh, bw,
                        fill=c, outline=c)
            ar = s * 0.23
            lw = max(1, int(s * 0.07))
            self.create_arc(gx - ar, gy - ar * 0.30, gx + ar, gy + ar * 1.40,
                            start=200, extent=140, style="arc",
                            outline=c, width=lw)
            self.create_line(gx, gy + ar * 1.05, gx, gy + ar * 1.35,
                             fill=c, width=lw, capstyle="round")
            self.create_line(gx - ar * 0.50, gy + ar * 1.35,
                             gx + ar * 0.50, gy + ar * 1.35,
                             fill=c, width=lw, capstyle="round")


class GradientDivider(tk.Canvas):
    """1px horizontal line with fade-in/out at the edges."""

    def __init__(self, parent, height=1, bg_parent=BG,
                 mid_color=DIVIDER_MID, edge_color=BG):
        super().__init__(parent, height=height, bg=bg_parent,
                         highlightthickness=0, bd=0)
        self._h = height
        self._mid = mid_color
        self._edge = edge_color
        self.bind("<Configure>", lambda e: self._draw())

    def _draw(self):
        self.delete("all")
        w = max(self.winfo_width(), 2)
        steps = max(20, w)
        mid = w / 2
        for x in range(steps):
            xx = int(x * w / steps)
            t = 1.0 - abs(xx - mid) / mid
            t = max(0.0, min(1.0, t))
            col = _mix(self._edge, self._mid, t * t)
            self.create_line(xx, 0, xx + 1, 0, fill=col, width=self._h)


class TitleBarControls(tk.Frame):
    """Minimize / maximize / close buttons for the frameless window."""
    BTN_W, BTN_H = 46, 32

    def __init__(self, parent, on_minimize, on_maximize, on_close):
        super().__init__(parent, bg=BG, bd=0, highlightthickness=0)
        self._max_c = None
        for kind, cmd, is_close in [
            ("min",   on_minimize, False),
            ("max",   on_maximize, False),
            ("close", on_close,    True),
        ]:
            c = self._make_btn(kind, cmd, is_close)
            c.pack(side="left")
            if kind == "max":
                self._max_c = c

    def _make_btn(self, kind, cmd, is_close):
        hover_bg = "#c42b1c" if is_close else BG_HOVER
        c = tk.Canvas(self, width=self.BTN_W, height=self.BTN_H,
                      bg=BG, highlightthickness=0, bd=0, cursor="hand2")
        c._kind = kind
        c._maximized = False

        def draw(hover=False):
            c.delete("all")
            bg = hover_bg if hover else BG
            c.create_rectangle(0, 0, self.BTN_W, self.BTN_H, fill=bg, outline=bg)
            fg = "#ffffff" if hover else FG_DIM
            cx, cy = self.BTN_W // 2, self.BTN_H // 2
            if c._kind == "min":
                c.create_line(cx - 5, cy, cx + 5, cy,
                              fill=fg, width=1)
            elif c._kind == "max":
                if c._maximized:
                    # Restore: back square, then front square offset
                    c.create_rectangle(cx - 2, cy - 5, cx + 5, cy + 2,
                                       outline=fg, fill=bg, width=1)
                    c.create_rectangle(cx - 5, cy - 2, cx + 2, cy + 5,
                                       outline=fg, fill=bg, width=1)
                else:
                    c.create_rectangle(cx - 5, cy - 5, cx + 5, cy + 5,
                                       outline=fg, fill="", width=1)
            elif c._kind == "close":
                c.create_line(cx - 5, cy - 5, cx + 5, cy + 5,
                              fill=fg, width=1, capstyle="round")
                c.create_line(cx + 5, cy - 5, cx - 5, cy + 5,
                              fill=fg, width=1, capstyle="round")

        draw()
        c.bind("<Enter>",    lambda e: draw(True))
        c.bind("<Leave>",    lambda e: draw(False))
        c.bind("<Button-1>", lambda e: cmd())
        c._draw = draw
        return c

    def update_max_icon(self, maximized):
        if self._max_c:
            self._max_c._maximized = maximized
            self._max_c._draw()


class UpdatePill(tk.Canvas):
    """Title-bar control for the self-updater. Always present.

    It was previously created hidden and packed only when a check found a
    newer release, which meant that on an install that was already current —
    the normal case — the title bar showed nothing at all. There was then no
    way to tell "no update available" apart from "the updater is broken", and
    no way to ask it to look again. So the control is always mounted and
    carries the state instead:

      idle       "v1.0.0"     quiet outline. Click to check now.
      checking   "Checking…"  same outline, while the thread is out.
      available  "Update"     filled blue with a download arrow.
      done       "Restart"    after an install, until the window closes.

    Only ``available`` is loud. It is built exactly like a primary
    RoundedButton — same radius, same vertical ramp, same inner top highlight
    — but in Resolve blue rather than subtitle yellow. Two reasons for the
    colour: it must not compete with Generate, and hue separates them better
    than weight does, since amber in this window means subtitles and nothing
    else while blue already carries every interactive state. The other states
    borrow the secondary button's outline treatment so they read as chrome.
    """
    H = 24
    R = 6

    # Layout, left to right. Named because the width computation and the draw
    # have to agree — a mismatch shows up as text clipped by a corner arc.
    PAD_L, GLYPH, GAP, PAD_R = 11, 11, 7, 13

    LOUD = ("available",)          # states drawn as a filled blue button

    def __init__(self, parent, text, command, bg_parent=BG_CARD,
                 state="available"):
        self._font = _font(UI_FONT, 9, "bold")
        self._text = text
        self._state = state
        self._bg_parent = bg_parent
        self._hover = False
        self._measure()
        # Canvas is 8px taller than the button, which is drawn at the top of
        # it. That is RoundedButton's convention — it reserves the strip for
        # the primary variant's glow halo — and the Generate / Sync Existing
        # tabs share this bar. Sizing the canvas to the button instead centres
        # it 4px lower than they sit, which reads as a chip that missed the
        # row it belongs to.
        super().__init__(parent, width=self._bw, height=self.H + 8,
                         bg=bg_parent,
                         highlightthickness=0, bd=0, cursor="hand2")
        self.bind("<Enter>",    lambda e: self._set_hover(True))
        self.bind("<Leave>",    lambda e: self._set_hover(False))
        self.bind("<Button-1>", lambda e: command())
        self._draw()

    # ── state ───────────────────────────────────────────────────────────
    def _loud(self):
        return self._state in self.LOUD

    def _measure(self):
        """Width for the current text. The glyph only exists in a loud state,
        so it is only paid for there — otherwise the version label sits in a
        chip padded like a label, not like a button with a missing icon."""
        self._font.configure(weight="bold" if self._loud() else "normal")
        glyph = (self.GLYPH + self.GAP) if self._loud() else 0
        self._bw = (self.PAD_L + glyph + self._font.measure(self._text)
                    + self.PAD_R)

    def set_state(self, state, text):
        """Move to a new state and relabel. Resizes the canvas, because every
        state has a different width and Tk will not do that for a Canvas."""
        if (state, text) == (self._state, self._text):
            return
        self._state, self._text = state, text
        self._measure()
        try:
            self.configure(width=self._bw)
        except tk.TclError:
            return                       # widget already destroyed
        self._draw()

    def state(self):
        return self._state

    def _set_hover(self, on):
        self._hover = on
        self._draw()

    def _draw(self):
        self.delete("all")
        w, h, r = self._bw, self.H, self.R

        if self._loud():
            face = SELECT_HOVER if self._hover else SELECT
            _round_rect(self, 0, 0, w, h, r, fill=face, outline=face)
            # Vertical ramp, a scanline at a time, each line inset by the
            # corner arc it crosses. Tk has no gradient brush;
            # RoundedButton._ramp does the same for the primary button and
            # this matches it on purpose.
            self._ramp(1, 1, w - 1, h - 1, max(1, r - 1),
                       _mix(face, "#ffffff", 0.18),
                       _mix(face, SELECT_DARK, 0.60))
            # Inner top highlight: one bright line under the edge is what
            # makes a flat fill read as a raised surface rather than a
            # coloured rectangle.
            self.create_line(r, 1, w - r, 1, fill=_mix(face, "#ffffff", 0.45))
            self._arrow(self.PAD_L, h // 2, self.GLYPH, SELECT_INK)
            tx, tcol = self.PAD_L + self.GLYPH + self.GAP, SELECT_INK
        else:
            # Quiet, but still visibly a control. The outline is DIVIDER_MID
            # rather than the BORDER used on the cards: BORDER is #17171b and
            # the title bar is #17181a, so on this one surface that hairline
            # is invisible and the chip collapses into a stray grey word —
            # which is the whole complaint the resting state exists to answer.
            edge = BORDER_BRIGHT if self._hover else DIVIDER_MID
            fill = BG_HOVER if self._hover else self._bg_parent
            _round_rect(self, 0, 0, w, h, r, fill=edge, outline=edge)
            _round_rect(self, 1, 1, w - 1, h - 1, max(1, r - 1),
                        fill=fill, outline=fill)
            tx = self.PAD_L
            tcol = FG if self._hover else FG_DIM

        self.create_text(tx, h // 2, anchor="w", text=self._text,
                         font=self._font, fill=tcol)

    def _ramp(self, x1, y1, x2, y2, r, top, bottom):
        h = int(y2 - y1)
        if h <= 0:
            return
        for i in range(h):
            dy = 0.0
            if i < r:
                dy = r - i
            elif i > h - r:
                dy = i - (h - r)
            inset = r - math.sqrt(max(0.0, r * r - dy * dy)) if dy > 0 else 0.0
            col = _mix(top, bottom, i / float(max(1, h - 1)))
            self.create_line(x1 + inset, y1 + i, x2 - inset, y1 + i, fill=col)

    def _arrow(self, x, cy, s, color):
        """Download arrow: stem, chevron head, and a short tray under it.

        Half-pixel centres. A 2px line centred on a whole coordinate straddles
        two pixel columns and comes out 3px wide and grey at this size, which
        is exactly the softness that made the old chip look unfinished."""
        cx = x + s / 2.0 + 0.5
        top = cy - s / 2.0 - 0.5
        stem_end = top + s * 0.58
        self.create_line(cx, top, cx, stem_end,
                         fill=color, width=2, capstyle="round")
        for dx in (-s * 0.30, s * 0.30):
            self.create_line(cx + dx, stem_end - s * 0.30, cx, stem_end,
                             fill=color, width=2, capstyle="round")
        self.create_line(cx - s * 0.40, top + s,
                         cx + s * 0.40, top + s,
                         fill=color, width=2, capstyle="round")


class SlimScrollbar(tk.Canvas):
    """Thin rounded dark scrollbar that matches the UI (replaces the chunky
    native tk.Scrollbar). Drives a Canvas through its yview; the scrolled
    widget calls .set(first, last) via its yscrollcommand.

    With ``autohide`` it unpacks itself whenever the whole content fits, so a
    view that needs no scrolling shows no track at all and gets the width back.

    ``reserve`` is the same idea without giving the width back: the bar stays
    packed and only stops drawing. Reclaiming 14px is the right trade for a
    view whose height never changes, and the wrong one for the settings page —
    there, one task mode fits the window and the other does not, so the bar was
    appearing and disappearing as the task switched and shifting every control
    in both columns sideways by 7px. The gutter is spent either way; spending
    it always is what makes the switch not move."""

    # Hysteresis: show once >0.5% of the content is off-screen, hide only once
    # it fits to within 0.1%. The dead band stops the bar flickering when
    # reclaiming its width nudges the content height by a pixel.
    _AH_SHOW = 0.995
    _AH_HIDE = 0.999

    def __init__(self, parent, command, width=6, bg_parent=BG, autohide=True,
                 reserve=False):
        super().__init__(parent, width=width, bg=bg_parent,
                         highlightthickness=0, bd=0)
        self._command = command          # canvas.yview
        self._first, self._last = 0.0, 1.0
        self._barw = width               # NOT self._w — Tk uses that internally
        self._drag_dy = None
        self._hover = False
        self._autohide = autohide
        self._reserve = reserve
        self._pack_kw = None             # replayed when the bar comes back
        self._hidden = False
        self.bind("<Configure>", lambda e: self._draw())
        self.bind("<Button-1>", self._on_press)
        self.bind("<B1-Motion>", self._on_drag)
        self.bind("<Enter>", lambda e: self._draw(True))
        self.bind("<Leave>", lambda e: self._draw(False))

    def pack(self, **kw):
        # Remember how the caller wanted it packed; autohide re-packs with the
        # same options, and always after the scrolled widget, so the side/expand
        # geometry comes out identical.
        self._pack_kw = dict(kw)
        super().pack(**kw)
        self._hidden = False
        self._apply_autohide()

    def _apply_autohide(self):
        if not self._autohide or self._pack_kw is None:
            return
        frac = self._last - self._first
        if self._hidden:
            if frac < self._AH_SHOW:
                if not self._reserve:
                    super().pack(**self._pack_kw)
                self._hidden = False
        elif frac >= self._AH_HIDE:
            if not self._reserve:
                super().pack_forget()
            self._hidden = True

    def set(self, first, last):
        self._first, self._last = float(first), float(last)
        self._apply_autohide()
        if self._hidden:
            # Reserved but not needed: empty gutter, no track and no thumb.
            self.delete("all")
        else:
            self._draw()

    def _thumb_bounds(self):
        h = max(self.winfo_height(), 1)
        y0, y1 = self._first * h, self._last * h
        if y1 - y0 < 24:                 # keep the thumb grabbable
            mid = (y0 + y1) / 2
            y0, y1 = mid - 12, mid + 12
            y0 = max(0, min(y0, h - 24)); y1 = y0 + 24
        return y0, y1, h

    def _draw(self, hover=None):
        if hover is not None:
            self._hover = hover
        self.delete("all")
        w = self._barw
        y0, y1, _ = self._thumb_bounds()
        # faint track
        _round_rect(self, 2, 1, w - 2, self.winfo_height() - 1, (w - 4) / 2,
                    fill=BG_INPUT, outline=BG_INPUT)
        col = SELECT if self._hover else BORDER_BRIGHT
        _round_rect(self, 1, y0, w - 1, y1, (w - 2) / 2, fill=col, outline=col)

    def _on_press(self, e):
        y0, y1, h = self._thumb_bounds()
        if y0 <= e.y <= y1:
            self._drag_dy = e.y - y0
        else:
            self._command("moveto", max(0.0, min(1.0, e.y / max(h, 1))))
            self._drag_dy = None

    def _on_drag(self, e):
        h = max(self.winfo_height(), 1)
        base = e.y if self._drag_dy is None else (e.y - self._drag_dy)
        self._command("moveto", max(0.0, min(1.0, base / h)))


class Slider(tk.Canvas):
    """Rounded dark horizontal slider bound to a StringVar holding a number in
    [lo, hi]. Dragging updates the var (formatted with ``fmt``); an external
    change to the var (e.g. typing in a linked number box) redraws the thumb —
    two-way binding through the shared StringVar."""

    def __init__(self, parent, variable, lo, hi, fmt="%.3f", step=None,
                 height=30, bg_parent=BG):
        super().__init__(parent, height=height, bg=bg_parent,
                         highlightthickness=0, bd=0, cursor="hand2")
        self.var = variable
        self.lo, self.hi = float(lo), float(hi)
        self.fmt = fmt
        self.step = step
        self._th = 6          # track thickness
        self._r = 8           # thumb radius (grows by 1 while hovered/dragged)
        self._moat = 2        # bg-coloured gap punched around the thumb
        self._bgp = bg_parent
        self._hot = False     # hovered or mid-drag
        self._guard = False
        self.bind("<Configure>", lambda e: self._draw())
        self.bind("<Button-1>", self._press)
        self.bind("<B1-Motion>", self._set_from_x)
        self.bind("<ButtonRelease-1>", self._release)
        self.bind("<Enter>", lambda e: self._set_hot(True))
        self.bind("<Leave>", lambda e: self._set_hot(False))
        try:
            variable.trace_add("write", lambda *a: self._draw())
        except AttributeError:
            variable.trace("w", lambda *a: self._draw())

    def _value(self):
        try:
            return max(self.lo, min(self.hi, float(self.var.get())))
        except (ValueError, TypeError):
            return self.lo

    def _frac(self):
        span = self.hi - self.lo
        return (self._value() - self.lo) / span if span else 0.0

    def _bounds(self):
        w = max(self.winfo_width(), 1)
        # +1 for the hover growth, + the moat, so the thumb never clips at
        # either end of the travel.
        pad = self._r + 1 + self._moat
        return pad, w - pad

    def _draw(self):
        # The bound StringVar outlives this widget (it lives on App); once the
        # form is rebuilt the trace can still fire on a destroyed canvas.
        if self._guard or not self.winfo_exists():
            return
        self.delete("all")
        h = self.winfo_height()
        cy = h // 2
        x0, x1 = self._bounds()
        half = self._th // 2
        # Groove one step off the card rather than BG_INPUT: dark enough to read
        # as a channel, light enough not to need an outline. (Outlining it made
        # the empty half look like a second, empty input box next to the chip.)
        self._capsule(x0, x1, cy, half, TRACK_OFF)
        tx = x0 + self._frac() * (x1 - x0)
        if tx > x0 + 1:
            self._capsule(x0, tx, cy, half, SELECT)
        r = self._r + (1 if self._hot else 0)
        # The thumb sits ON the accent fill, so a same-colour thumb would melt
        # into it and a white one reads as a separate object stuck to the bar.
        # Punching the card colour out around it gives the fill a clean stop and
        # lets the thumb stay accent-coloured — one control, not two.
        m = r + self._moat
        self.create_oval(tx - m, cy - m, tx + m, cy + m,
                         fill=self._bgp, outline=self._bgp)
        self.create_oval(tx - r, cy - r, tx + r, cy + r,
                         fill=SELECT_HOVER if self._hot else SELECT,
                         outline=SELECT_DARK, width=1)

    def _capsule(self, x0, x1, cy, half, fill):
        """Horizontal pill with genuinely round caps.

        _round_rect's smoothed polygon degenerates into a square-ended slab at
        this thickness (6 px), so the caps are drawn as real circles instead."""
        x1 = max(x1, x0 + 2 * half)
        self.create_oval(x0, cy - half, x0 + 2 * half, cy + half,
                         fill=fill, outline=fill)
        self.create_oval(x1 - 2 * half, cy - half, x1, cy + half,
                         fill=fill, outline=fill)
        self.create_rectangle(x0 + half, cy - half, x1 - half, cy + half,
                              fill=fill, outline=fill)

    def _set_hot(self, on):
        if self._hot != on:
            self._hot = on
            self._draw()

    def _press(self, e):
        self._hot = True
        self._set_from_x(e)

    def _release(self, _e):
        # Pointer may have left the canvas mid-drag; only stay lit if it didn't.
        x, y = self.winfo_pointerxy()
        inside = (self.winfo_rootx() <= x < self.winfo_rootx() + self.winfo_width()
                  and self.winfo_rooty() <= y < self.winfo_rooty() + self.winfo_height())
        self._set_hot(inside)

    def _set_from_x(self, e):
        x0, x1 = self._bounds()
        f = max(0.0, min(1.0, (e.x - x0) / max(1, x1 - x0)))
        v = self.lo + f * (self.hi - self.lo)
        if self.step:
            v = round(v / self.step) * self.step
            v = max(self.lo, min(self.hi, v))
        # Avoid the trace bouncing back into a redraw mid-set.
        self._guard = True
        self.var.set(self.fmt % v)
        self._guard = False
        self._draw()


class ReelPreview(tk.Canvas):
    """Live reel/HD preview showing where the subtitle cue will land on the
    frame before it is imported onto the timeline.

    Bound to the subtitle height and point size (and, optionally, colour +
    outline/shadow toggles). Height follows the same bottom-origin convention
    the Resolve-side script converts to the subtitle item's ``posY``: 0 is the
    bottom of the frame, 1 the top. So what you see here is where the cue
    actually renders.

    It is also interactive: click or drag inside the frame to set the height."""

    SAMPLE = "Subtitle preview"

    def __init__(self, parent, srt_posy_var, srt_size_var,
                 color_var=None, outline_var=None, shadow_var=None,
                 safe_zone_var=None, width=170, bg_parent=BG,
                 aspect=9.0 / 16.0, srt_posy_default=None, frame_height=None):
        # `aspect` is width/height. The widget is laid out to a fixed area
        # rather than a fixed width, so switching between a reel and an HD
        # frame doesn't make the stage column jump: a 9:16 frame is tall and
        # narrow, a 16:9 frame short and wide, and both occupy the same box.
        self._pw_max = int(width)
        self._ph_max = int(round(self._pw_max * 16 / 9))
        self._aspect = float(aspect)
        self._pw, self._ph = self._fit(self._aspect)
        super().__init__(parent, width=self._pw, height=self._ph, bg=bg_parent,
                         highlightthickness=0, bd=0, cursor="crosshair")
        self.srt_posy_var = srt_posy_var
        self.srt_size_var = srt_size_var
        self.color_var = color_var
        self.outline_var = outline_var
        self.shadow_var = shadow_var
        self.safe_zone_var = safe_zone_var
        self._srt_posy_default = srt_posy_default or (lambda: 0.28)
        self._frame_height = frame_height or (lambda: None)
        self._pad = 7            # phone bezel thickness

        for v in (srt_posy_var, srt_size_var, color_var, outline_var,
                  shadow_var, safe_zone_var):
            if v is None:
                continue
            try:
                v.trace_add("write", lambda *a: self._draw())
            except AttributeError:
                v.trace("w", lambda *a: self._draw())

        self.bind("<Configure>", lambda e: self._draw())
        self.bind("<Button-1>", self._set_from_xy)
        self.bind("<B1-Motion>", self._set_from_xy)
        self._draw()

    def set_width(self, width):
        """Rescale to a new maximum width, keeping the current frame shape.

        Everything drawn here is derived from _screen(), which reads only _pw
        and _ph, so resizing is these two numbers plus a redraw.
        """
        w = max(120, int(width))
        if w == self._pw_max:
            return
        self._pw_max = w
        self._ph_max = int(round(w * 16 / 9))
        self._reshape()

    def _fit(self, aspect):
        """Largest (w, h) of the given aspect that fits the stage box."""
        w = self._pw_max
        h = int(round(w / aspect))
        if h > self._ph_max:
            h = self._ph_max
            w = int(round(h * aspect))
        return max(120, w), max(80, h)

    def set_aspect(self, aspect):
        """Switch between the reel and HD frames."""
        aspect = float(aspect)
        if abs(aspect - self._aspect) < 1e-6:
            return
        self._aspect = aspect
        self._reshape()

    def _reshape(self):
        self._pw, self._ph = self._fit(self._aspect)
        self.configure(width=self._pw, height=self._ph)
        self._draw()

    @property
    def is_portrait(self):
        return self._aspect < 1.0

    # ── geometry: the inner "screen" rectangle inside the bezel ────────────
    def _screen(self):
        # A phone needs a visible bezel; a 16:9 frame is a picture, not a
        # handset, so it gets a hairline instead.
        p = self._pad if self.is_portrait else 3
        return p, p, self._pw - p, self._ph - p

    def _fnum(self, var, default):
        try:
            return float(var.get())
        except (ValueError, TypeError, AttributeError):
            return default

    def _posy(self):
        """The chosen height, or this frame's professional default when the
        field is blank."""
        raw = (self.srt_posy_var.get() or "").strip() if self.srt_posy_var else ""
        try:
            py = float(raw) if raw else self._srt_posy_default()
        except ValueError:
            py = self._srt_posy_default()
        return max(0.0, min(1.0, py))

    def _set_from_xy(self, e):
        # A subtitle track is centred and has one placement number, so only the
        # vertical half of a drag means anything here.
        fx0, fy0, fx1, fy1 = self._screen()
        py = (fy1 - e.y) / max(1, fy1 - fy0)     # flip: bottom-left origin
        if self.srt_posy_var is not None:
            self.srt_posy_var.set("%.3f" % max(0.0, min(1.0, py)))
        self._draw()

    @staticmethod
    def _blend(fg, bg, a):
        """Blend hex colour fg over bg by alpha a (a=1 -> fg, a=0 -> bg)."""
        try:
            a = max(0.0, min(1.0, a))
            fr, fgn, fb = int(fg[1:3], 16), int(fg[3:5], 16), int(fg[5:7], 16)
            br, bgn, bb = int(bg[1:3], 16), int(bg[3:5], 16), int(bg[5:7], 16)
            r = int(fr * a + br * (1 - a))
            g = int(fgn * a + bgn * (1 - a))
            b = int(fb * a + bb * (1 - a))
            return "#%02x%02x%02x" % (r, g, b)
        except Exception:
            return fg

    def _draw(self):
        # The bound vars live on App and outlive this canvas across rebuilds.
        if not self.winfo_exists():
            return
        self.delete("all")
        w, h = self._pw, self._ph
        fx0, fy0, fx1, fy1 = self._screen()

        # Body + screen. The rounded phone shell is right for a reel and wrong
        # for a 16:9 cut, which gets a plain bezel instead.
        body_r, screen_r = (16, 11) if self.is_portrait else (7, 4)
        _round_rect(self, 1, 1, w - 1, h - 1, body_r,
                    fill=BG_TILE, outline=BORDER_BRIGHT)
        _round_rect(self, fx0, fy0, fx1, fy1, screen_r,
                    fill="#0a0c10", outline=BORDER)

        sw, sh = fx1 - fx0, fy1 - fy0

        # rule-of-thirds guides
        for i in (1, 2):
            gx = fx0 + sw * i / 3
            self.create_line(gx, fy0 + 4, gx, fy1 - 4, fill="#1c212b")
            gy = fy0 + sh * i / 3
            self.create_line(fx0 + 4, gy, fx1 - 4, gy, fill="#1c212b")
        # safe-area box (5% inset, dashed)
        mx, my = sw * 0.05, sh * 0.05
        self.create_rectangle(fx0 + mx, fy0 + my, fx1 - mx, fy1 - my,
                              outline="#2a3341", dash=(2, 3))

        # Viewfinder corner ticks. Purely framing — they mark the edge of the
        # deliverable frame, which the dashed safe area alone doesn't do once
        # the safe-zone overlay is switched off.
        tl = max(7.0, sw * 0.075)
        tw = 2
        tick = _mix("#2a3341", ACCENT, 0.35)
        for ox, oy, dx, dy in ((fx0, fy0, 1, 1), (fx1, fy0, -1, 1),
                               (fx0, fy1, 1, -1), (fx1, fy1, -1, -1)):
            self.create_line(ox, oy, ox + dx * tl, oy, fill=tick, width=tw)
            self.create_line(ox, oy, ox, oy + dy * tl, fill=tick, width=tw)

        # "Safe zone" overlay — but the thing being kept clear is not the same
        # in the two frames. On a reel it is the platform's own furniture
        # (Reels/Shorts/TikTok all park an action column on the right and a
        # caption/handle band across the bottom). On a 16:9 cut there is no
        # platform chrome; what matters is the broadcast title-safe box, which
        # is where a burned-in subtitle is expected to sit.
        if self.safe_zone_var is None or bool(int(self._fnum(self.safe_zone_var, 1))):
            ui = "#3a4453"
            if self.is_portrait:
                cxr = fx1 - sw * 0.11        # right-side action column
                r = max(3, sw * 0.045)
                for j, fy in enumerate((0.42, 0.55, 0.68, 0.80)):
                    yc = fy1 - sh * fy
                    self.create_oval(cxr - r, yc - r, cxr + r, yc + r,
                                     outline=ui, width=1)
                # bottom caption/handle band (kept clear on a pro layout)
                by = fy1 - sh * 0.16
                self.create_line(fx0 + mx, by, fx1 - sw * 0.20, by,
                                 fill=ui, dash=(1, 2))
                self.create_rectangle(fx0 + mx, by + 3, fx0 + sw * 0.44, by + 8,
                                      outline=ui, width=1)
            else:
                tx, ty = sw * 0.10, sh * 0.10      # 10% title-safe
                self.create_rectangle(fx0 + tx, fy0 + ty, fx1 - tx, fy1 - ty,
                                      outline=ui, dash=(1, 2))

        # A subtitle track has one placement: centred, at a height above the
        # bottom of the frame.
        px, py = 0.5, self._posy()
        cx_t = fx0 + px * sw
        cy_t = fy1 - py * sh

        # A subtitle track takes a point size against the real frame, so the
        # preview divides by the timeline height to know how big that is on
        # screen. With no resolution reported, fall back to 1080 rather than
        # draw nothing.
        pt = self._fnum(self.srt_size_var, 55.0) if self.srt_size_var else 55.0
        ts = pt / float(self._frame_height() or 1080)
        fontpx = int(round(ts * sh))
        fontpx = max(8, min(int(sh * 0.28), fontpx))
        col = (self.color_var.get().strip() if self.color_var else "") or "#ffffff"

        # Measured, then shrunk if the sample would overflow the frame width
        # (real captions scale to fit) so nothing is clipped.
        # Same family as the cue editor, and for the same reason: the sample IS
        # a caption, so in Segoe UI every Indic preview came out with its vowel
        # signs detached onto dotted circles. See cue_font_family().
        fam = cue_font_family()
        try:
            font = _font(fam, -fontpx, "bold")
            tw = font.measure(self.SAMPLE)
            th = font.metrics("linespace")
            avail = sw * 0.90
            if tw > avail and tw > 0:
                fontpx = max(7, int(fontpx * avail / tw))
                font = _font(fam, -fontpx, "bold")
                tw = font.measure(self.SAMPLE)
                th = font.metrics("linespace")
        except Exception:
            font = (fam, 9, "bold")
            tw, th = fontpx * 8, fontpx

        half_w, half_h = tw / 2 + 5, th / 2 + 3
        cx = max(fx0 + half_w, min(fx1 - half_w, cx_t))
        cy = max(fy0 + half_h, min(fy1 - half_h, cy_t))

        pill = "#11151c"
        outline_on = (not self.outline_var) or bool(int(self._fnum(self.outline_var, 1)))
        shadow_on = self.shadow_var and bool(int(self._fnum(self.shadow_var, 1)))
        ocol = "#000000"
        scol = "#000000"
        # Mirrors subtitle_style.json: a stroke one pixel out, and a shadow
        # offset slightly down-right and soft-edged. A dim core plus a fainter
        # halo one pixel further is as close to a blur as Tk text gets.
        sdx, sdy = 2, 3
        scol_core = self._blend(scol, pill, 0.42)
        scol_soft = self._blend(scol, pill, 0.18)

        # translucent-ish backing pill for legibility
        _round_rect(self, cx - half_w, cy - half_h, cx + half_w, cy + half_h,
                    5, fill=self._blend(pill, "#0a0c10", 1.0), outline="")

        if shadow_on:
            for hx, hy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                self.create_text(cx + sdx + hx, cy + sdy + hy, text=self.SAMPLE,
                                 font=font, fill=scol_soft)
            self.create_text(cx + sdx, cy + sdy, text=self.SAMPLE,
                             font=font, fill=scol_core)
        if outline_on:
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    if dx or dy:
                        self.create_text(cx + dx, cy + dy, text=self.SAMPLE,
                                         font=font, fill=ocol)
        self.create_text(cx, cy, text=self.SAMPLE, font=font, fill=col)

        # anchor dot + live height readout
        self.create_oval(cx - 2, cy - 2, cx + 2, cy + 2,
                         fill=ACCENT, outline="")
        self.create_text(fx0 + 5, fy1 - 7, text="Y %.2f" % py,
                         anchor="w", fill=FG_MUTE, font=(UI_FONT, 7))


class Tooltip:
    """Hover explanation, the way Resolve carries them.

    A hint used to sit under every label. That is friendlier to read once and
    dead weight every time after, and it is what made this form twice the
    height of anything around it: the explanations were roughly a third of the
    page. Here they are one hover away and cost no space at rest.

    Worth recording, because the comment on _wire_card_activity says the
    opposite and is wrong: <Enter>, <Motion> and <Leave> all arrive normally in
    this frameless always-on-top window. That was tested by walking the real
    cursor across a stand-in window and logging what fired. Whatever defeated
    the earlier hover experiment, it was not the window flags.
    """

    DELAY = 450          # ms of stillness before it appears
    MAX_W = 260

    def __init__(self, widget, text, app_root=None):
        self.widget = widget
        self.text = text
        self._root = app_root or widget
        self._tip = None
        self._after = None
        self.rebind()

    def rebind(self):
        """(Re)bind the whole subtree.

        Called again after the caller has filled the row's control slot, since
        those widgets do not exist yet when the row is built.
        """
        self._bind(self.widget)

    def _bind(self, w):
        if getattr(w, "_tooltip_bound", None) is self:
            return
        w._tooltip_bound = self
        w.bind("<Enter>", self._schedule, add="+")
        w.bind("<Leave>", self._hide, add="+")
        w.bind("<Button-1>", self._hide, add="+")
        for child in w.winfo_children():
            self._bind(child)

    def _schedule(self, _e=None):
        self._cancel()
        try:
            self._after = self.widget.after(self.DELAY, self._show)
        except tk.TclError:
            self._after = None

    def _cancel(self):
        if self._after is not None:
            try:
                self.widget.after_cancel(self._after)
            except tk.TclError:
                pass
            self._after = None

    def _show(self):
        self._after = None
        if self._tip is not None or not self.widget.winfo_exists():
            return
        try:
            x = self.widget.winfo_rootx() + 14
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        except tk.TclError:
            return
        tip = tk.Toplevel(self.widget)
        tip.overrideredirect(True)
        # The window it explains is always-on-top; a tooltip that is not would
        # open behind it and never be seen.
        try:
            tip.attributes("-topmost", True)
        except tk.TclError:
            pass
        tip.configure(bg=BORDER_BRIGHT)
        body = tk.Frame(tip, bg=BG_OUTER)
        body.pack(padx=1, pady=1)
        tk.Label(body, text=self.text, bg=BG_OUTER, fg=FG,
                 font=(UI_FONT, 9), justify="left", anchor="w",
                 wraplength=self.MAX_W).pack(padx=8, pady=(5, 6))
        tip.update_idletasks()
        # Keep it on screen when the row is near the right or bottom edge.
        sw = tip.winfo_screenwidth()
        sh = tip.winfo_screenheight()
        w, h = tip.winfo_reqwidth(), tip.winfo_reqheight()
        x = max(0, min(x, sw - w - 4))
        y = max(0, min(y, sh - h - 4))
        tip.geometry("+%d+%d" % (x, y))
        round_corners(tip, radius=6)
        self._tip = tip

    def _hide(self, _e=None):
        self._cancel()
        if self._tip is not None:
            try:
                self._tip.destroy()
            except tk.TclError:
                pass
            self._tip = None


class TrackedLabel(tk.Canvas):
    """Small-caps section label with real letter-spacing.

    Tk font objects expose family / size / weight / slant / underline and
    nothing else — there is no tracking option, which is why these headings
    used to be written with literal spaces ("S U B T I T L E"). A real space
    between every letter is a word break: it can't be tuned, it breaks text
    search, and a screen reader spells the heading out. Drawing each glyph at
    a computed x gives actual tracking instead.
    """

    def __init__(self, parent, text, tracking=1.7, color=FG_LABEL,
                 size=8, bold=True, bg_parent=BG, upper=True):
        self._font = _font(UI_FONT, size, "bold" if bold else "normal")
        self._text = text.upper() if upper else text
        self._tracking = tracking
        self._color = color
        self._w = int(sum(self._font.measure(c) + self._tracking
                          for c in self._text)) + 2
        self._h = self._font.metrics("linespace") + 2
        super().__init__(parent, width=self._w, height=self._h, bg=bg_parent,
                         highlightthickness=0, bd=0)
        self._draw()

    def _draw(self):
        self.delete("all")
        x = 1.0
        cy = self._h / 2
        for ch in self._text:
            self.create_text(x, cy, anchor="w", text=ch,
                             fill=self._color, font=self._font)
            x += self._font.measure(ch) + self._tracking


class LivePill(tk.Canvas):
    """Green 'live' dot + word, marking the preview as tracking the controls."""

    def __init__(self, parent, text="live", bg_parent=BG):
        f = _font(UI_FONT, 8)
        w = f.measure(text) + 26
        super().__init__(parent, width=w, height=18, bg=bg_parent,
                         highlightthickness=0, bd=0)
        self.create_oval(3, 6, 9, 12, fill=GOOD, outline="")
        self.create_text(14, 9, anchor="w", text=text, fill=GOOD, font=f)


class SegmentedControl(tk.Canvas):
    """A small pill of mutually exclusive choices, bound to a StringVar.

    Used for the two decisions that govern everything downstream — which output
    path is being built, and which frame it is being judged in. Both are picked
    far more often than they are read, and both have exactly two answers, so a
    dropdown would cost a click and hide the alternative.
    """

    H = 30
    PAD = 11          # horizontal padding inside one segment

    def __init__(self, parent, values, var, bg_parent=BG, on_change=None,
                 font_size=9):
        self._values = tuple(values)
        self._var = var
        self._on_change = on_change
        self._font = _font(UI_FONT, font_size)
        self._font_on = _font(UI_FONT, font_size, "bold")
        self._hover = None
        # NOT _w: Tk stores the widget's own Tcl path there.
        widths = [self._font_on.measure(v) + self.PAD * 2 for v in self._values]
        self._seg_w = [max(w, 46) for w in widths]
        super().__init__(parent, width=sum(self._seg_w) + 8, height=self.H,
                         bg=bg_parent, highlightthickness=0, bd=0,
                         cursor="hand2")
        self.bind("<Button-1>", self._click)
        self.bind("<Motion>", self._motion)
        self.bind("<Leave>", lambda e: self._set_hover(None))
        try:
            var.trace_add("write", lambda *a: self._draw())
        except AttributeError:
            var.trace("w", lambda *a: self._draw())
        self._draw()

    def _index_at(self, x):
        left = 4
        for i, w in enumerate(self._seg_w):
            if left <= x < left + w:
                return i
            left += w
        return None

    def _click(self, e):
        i = self._index_at(e.x)
        if i is None:
            return
        if self._var.get() != self._values[i]:
            self._var.set(self._values[i])
            if self._on_change:
                self._on_change(self._values[i])

    def _motion(self, e):
        self._set_hover(self._index_at(e.x))

    def _set_hover(self, i):
        if i != self._hover:
            self._hover = i
            self._draw()

    def _draw(self, *_a):
        self.delete("all")
        cur = self._var.get()
        _round_rect(self, 0, 0, sum(self._seg_w) + 8, self.H, 8,
                    fill=BG_INPUT, outline=BORDER)
        left = 4
        for i, (v, w) in enumerate(zip(self._values, self._seg_w)):
            on = (v == cur)
            if on:
                _round_rect(self, left, 3, left + w, self.H - 3, 6,
                            fill=SELECT, outline=SELECT)
            elif self._hover == i:
                _round_rect(self, left, 3, left + w, self.H - 3, 6,
                            fill=BG_HOVER, outline=BG_HOVER)
            self.create_text(left + w // 2, self.H // 2, text=v,
                             fill=SELECT_INK if on else
                                  (FG if self._hover == i else FG_DIM),
                             font=self._font_on if on else self._font)
            left += w


class RangeBar(tk.Canvas):
    """A hairline showing where a numeric setting sits between its limits.

    The split values are only meaningful against the range they are allowed —
    42 characters is generous, 42 is also nearly the cap — and a chip on its
    own cannot say which. Three pixels under the cell says it without adding
    a control to read.
    """

    def __init__(self, parent, variable, lo, hi, bg_parent=BG_CARD, height=3):
        # width=40: it is packed fill="x" under its cell, so what it asks for
        # only matters to the width the page reports needing.
        super().__init__(parent, bg=bg_parent, highlightthickness=0, bd=0,
                         width=40, height=height)
        self._var = variable
        self._lo = float(lo)
        self._hi = float(hi)
        self._h = height
        try:
            variable.trace_add("write", lambda *a: self._draw())
        except AttributeError:
            variable.trace("w", lambda *a: self._draw())
        self.bind("<Configure>", lambda e: self._draw())

    def _frac(self):
        # A half-typed or cleared box is a normal state while editing, not an
        # error: it reads as the bottom of the range until a number is back.
        try:
            v = float(str(self._var.get()).strip())
        except (ValueError, TypeError, tk.TclError):
            return 0.0
        span = self._hi - self._lo
        if span <= 0:
            return 0.0
        return max(0.0, min(1.0, (v - self._lo) / span))

    def _draw(self):
        if not self.winfo_exists():
            return
        w = max(self.winfo_width(), 2)
        h = self._h
        self.delete("all")
        _round_rect(self, 0, 0, w, h, h / 2.0,
                    fill=TRACK_OFF, outline=TRACK_OFF)
        fill_w = int(round(w * self._frac()))
        if fill_w >= h:
            _round_rect(self, 0, 0, fill_w, h, h / 2.0,
                        fill=SELECT_DARK, outline=SELECT_DARK)


class ComfortMeter(tk.Canvas):
    """Reads the timing numbers back as a judgement about legibility.

    Max characters, reading speed and minimum duration only mean anything in
    combination, and nothing in the form used to say whether the combination
    was sane — you found out once the cues were already on the timeline. The
    threshold is the usual subtitling one: comfortable to about 25 characters
    per second, readable to about 32, past that the tail of a line is gone
    before it can be read.
    """

    H = 78

    def __init__(self, parent, cps_var, chars_var, bg_parent=BG):
        # Packed fill="x" in the Timing column; see RoundedField on why the
        # Canvas default width is not left in place.
        super().__init__(parent, width=120, height=self.H, bg=bg_parent,
                         highlightthickness=0, bd=0)
        self.cps_var = cps_var
        self.chars_var = chars_var
        self.bind("<Configure>", lambda e: self._draw())
        for v in (cps_var, chars_var):
            try:
                v.trace_add("write", lambda *a: self._draw())
            except AttributeError:
                v.trace("w", lambda *a: self._draw())

    def _grade(self):
        try:
            cps = float(self.cps_var.get())
        except (TypeError, ValueError, tk.TclError):
            return ("—", FG_MUTE, 0.0,
                    "Reading speed isn't a number, so cues will be split on "
                    "character count alone.")
        if cps <= 0:
            return ("No limit", FG_DIM, 0.0,
                    "Cues split on character count alone. A dense line can "
                    "flash past before it can be read.")
        frac = min(1.0, cps / 40.0)
        if cps <= 17:
            return ("Very relaxed", GOOD, frac,
                    "Slow enough for anyone. Expect more cues than you need.")
        if cps <= 25:
            return ("Comfortable", GOOD, frac,
                    "A viewer has time to read every cue before it changes.")
        if cps <= 32:
            return ("Brisk", ACCENT, frac,
                    "Readable, but long lines will feel rushed on a phone.")
        return ("Too fast", BAD, frac,
                "Past about 32 characters a second the end of each line is "
                "gone before it can be read.")

    def _draw(self):
        if not self.winfo_exists():
            return
        self.delete("all")
        w = max(self.winfo_width(), 2)
        h = self.H
        _round_rect(self, 0, 0, w, h, 8, fill=DIVIDER, outline=DIVIDER)
        _round_rect(self, 1, 1, w - 1, h - 1, 7, fill=BG_CARD, outline=BG_CARD)

        verdict, col, frac, hint = self._grade()
        self.create_text(13, 15, anchor="w", text="Reading comfort",
                         fill=FG, font=(UI_FONT, 9, "bold"))
        self.create_text(w - 13, 15, anchor="e", text=verdict, fill=col,
                         font=(FONT_NUM, 9))
        by = 30
        _round_rect(self, 13, by, w - 13, by + 5, 2,
                    fill=BORDER, outline=BORDER)
        fw = 13 + frac * max(0, w - 26)
        if fw > 15:
            _round_rect(self, 13, by, fw, by + 5, 2, fill=col, outline=col)
        self.create_text(13, by + 13, anchor="nw", text=hint, fill=FG_MUTE,
                         font=(UI_FONT, 8), width=max(80, w - 26))


class WaveformStrip(tk.Canvas):
    """The audio the cues were cut from, drawn above the cue list.

    A timecode is a number; a pause is a shape. Judging whether a break lands
    on a breath or in the middle of a phrase was impossible from "0:05.47 →
    0:06.77" alone, and that is the one judgement the review screen exists to
    support.

    The envelope is the SAME one transcribe.py already computes for onset
    snapping (``_audio_envelope``), so this costs one ffmpeg decode and adds no
    dependency. ffmpeg is optional there and optional here: when it is missing
    the envelope is None, and the caller simply never packs the strip rather
    than showing an empty box that looks broken.

    Ticks along the bottom mark every cue boundary and a filled window marks
    the selected cue, which is what makes a mid-phrase break visible. Clicking
    seeks — the parent maps the time back to a cue and selects it.
    """

    H = 68
    BAR_STEP = 3                 # 2px bar + 1px gap
    PAD = 6                      # inset from the rounded edge

    def __init__(self, parent, on_seek=None, bg_parent=BG):
        super().__init__(parent, height=self.H, bg=bg_parent,
                         highlightthickness=0, bd=0, cursor="hand2")
        self._env = None
        self._hop = 0.005
        self._dur = 0.0
        self._bounds = ()
        self._span = None
        self._on_seek = on_seek
        self.bind("<Configure>", lambda e: self._draw())
        self.bind("<Button-1>", self._click)
        self.bind("<B1-Motion>", self._click)

    def set_audio(self, env, hop, dur=0.0):
        self._env = env or None
        self._hop = max(0.001, hop)
        # The envelope's own length is authoritative for the media, but the cue
        # list can end past it when readability extended the last cue.
        self._dur = max(dur, len(self._env) * self._hop if self._env else 0.0)
        self._draw()

    def set_cues(self, bounds, span=None):
        """``bounds``: (start, end) per cue. ``span``: the selected cue."""
        self._bounds = tuple(bounds)
        self._span = span
        self._draw()

    def has_audio(self):
        return bool(self._env)

    def _x(self, t, w):
        if self._dur <= 0:
            return self.PAD
        frac = max(0.0, min(t, self._dur)) / self._dur
        return self.PAD + frac * max(1, w - self.PAD * 2)

    def _click(self, e):
        if self._dur <= 0 or self._on_seek is None:
            return
        w = max(self.winfo_width(), 2)
        frac = (e.x - self.PAD) / max(1.0, w - self.PAD * 2)
        self._on_seek(max(0.0, min(1.0, frac)) * self._dur)

    def _draw(self):
        if not self.winfo_exists():
            return
        self.delete("all")
        w = max(self.winfo_width(), 2)
        h = self.H
        _round_rect(self, 0, 0, w, h, 8, fill=DIVIDER, outline=DIVIDER)
        _round_rect(self, 1, 1, w - 1, h - 1, 7,
                    fill=BG_INPUT, outline=BG_INPUT)
        env = self._env
        if not env or self._dur <= 0:
            return

        x0 = self.PAD
        x1 = max(x0 + 1, w - self.PAD)
        tick_y = h - 9                     # boundary ticks live below the bars
        sx0 = sx1 = None
        if self._span:
            sx0 = self._x(self._span[0], w)
            sx1 = max(sx0 + 2, self._x(self._span[1], w))
            _round_rect(self, sx0, 4, sx1, tick_y - 3, 3,
                        fill=SELECT_GLOW, outline="")

        mid = (tick_y + 4) / 2.0
        half = (tick_y - 4) / 2.0 - 1
        n = max(1, int((x1 - x0) // self.BAR_STEP))
        per = len(env) / float(n)
        for i in range(n):
            lo = int(i * per)
            hi = max(lo + 1, int((i + 1) * per))
            if lo >= len(env):
                break
            pk = max(env[lo:hi])
            bh = max(1.0, pk * half)
            bx = x0 + i * self.BAR_STEP
            inside = sx0 is not None and sx0 - 1 <= bx <= sx1
            self.create_rectangle(bx, mid - bh, bx + 2, mid + bh,
                                  fill=ACCENT if inside else "#39404a",
                                  outline="")
        if sx0 is not None:
            # Re-draw the window edge on top: the bars are painted over it.
            _round_rect(self, sx0, 4, sx1, tick_y - 3, 3,
                        fill="", outline=SELECT_DARK)

        # One tick per boundary. Ticks that fall on the selected cue's own
        # edges are brightened, so the window reads as bounded by real cuts.
        for s, e in self._bounds:
            for t in (s, e):
                bx = self._x(t, w)
                hot = (self._span is not None
                       and abs(t - self._span[0]) < 1e-6
                       or self._span is not None
                       and abs(t - self._span[1]) < 1e-6)
                self.create_line(bx, tick_y, bx, h - 3,
                                 fill=SELECT if hot else BORDER_BRIGHT)


class CueMeter(tk.Canvas):
    """One cue's reading speed, as a bar and its number.

    The CPS limit used to be a single line of sidebar prose, which meant a cue
    at 37 CPS looked exactly like a cue at 14 — the list was flat and every row
    claimed equal attention. The bar is the fraction of the limit used, clipped
    at full and turning BAD once past it, so the rows that need work are
    findable without reading any of them.
    """

    # Stacked rather than side-by-side: the meter now lives in a fixed column
    # down the right of every card, so all of them line up and the list can be
    # scanned vertically for the bars that are long or red. A horizontal
    # bar-then-number sat wherever the timecode above it happened to end.
    W, H = 62, 30
    BAR_W = 62

    def __init__(self, parent, cps, limit, bg_parent=BG_INPUT):
        super().__init__(parent, width=self.W, height=self.H, bg=bg_parent,
                         highlightthickness=0, bd=0)
        self._bg = bg_parent
        self.set(cps, limit)

    @staticmethod
    def grade(cps, limit):
        """(fraction of the limit, colour) — shared with the inspector so the
        number and the bar can never disagree about what counts as over."""
        if not limit or limit <= 0:
            return 0.0, FG_MUTE
        frac = min(1.0, cps / float(limit))
        if cps > limit:
            return 1.0, BAD
        return frac, (ACCENT if frac >= 0.8 else GOOD)

    def set(self, cps, limit):
        self.delete("all")
        frac, col = self.grade(cps, limit)
        self.create_text(self.W, 6, anchor="e", text="%.0f cps" % cps,
                         fill=col, font=(FONT_NUM, 8))
        by = 19
        _round_rect(self, 0, by, self.BAR_W, by + 4, 2,
                    fill=TRACK_OFF, outline=TRACK_OFF)
        if frac > 0:
            _round_rect(self, 0, by, max(4, self.BAR_W * frac), by + 4, 2,
                        fill=col, outline=col)


class GroupCard(tk.Canvas):
    """One titled group of settings, drawn as a card.

    A group used to be an 8pt caps label followed by rows floating on the same
    background as everything else, so nothing marked where it started or ended.
    Here the card owns a header band — icon tile, tracked title, and the group's
    current value summarised on the right — with its rows divided by hairlines
    underneath.

    Two things about hosting widgets on a Canvas drove the geometry:

    * A Canvas does not clip an embedded widget. A full-bleed Frame would paint
      straight over the rounded corners just drawn underneath it, so the hosted
      content is inset by INSET and the corner arcs stay visible in that margin.
      The hosted frames use the card's own fill, so the seam is invisible.
    * The card cannot know its own height in advance. The hosted frame's
      <Configure> drives the canvas height, which is why _sync guards against
      re-entering: setting the height fires another <Configure>.
    """

    INSET = 4
    RADIUS = 4
    HEAD_H = 28

    def __init__(self, parent, title, glyph=None, icon=None,
                 summary_var=None, bg_parent=BG):
        # width=80 for the same reason as RoundedField: a card always packs
        # fill="x", so Tk's 378px Canvas default would only ever overstate what
        # the card needs — and in a two-column page that overstatement is what
        # decides the page is too wide for the window.
        super().__init__(parent, bg=bg_parent, highlightthickness=0, bd=0,
                         width=80, height=self.HEAD_H + self.INSET * 2)
        self._active = False
        self._syncing = False
        self._last = (0, 0)

        self.inner = tk.Frame(self, bg=BG_CARD)
        self._win = self.create_window(self.INSET, self.INSET, anchor="nw",
                                       window=self.inner)

        self.head = tk.Frame(self.inner, bg=BG_PANEL2, height=self.HEAD_H)
        self.head.pack(fill="x")
        self.head.pack_propagate(False)
        RoundedIconTile(self.head, icon_name=icon,
                        text=(None if icon else (glyph or "•")),
                        size=24, radius=7, bg_parent=BG_PANEL2,
                        fill=BG_TILE, border=BORDER_TILE).pack(
            side="left", padx=(8, 9))
        self._title_lbl = tk.Label(self.head, text=title, bg=BG_PANEL2,
                                   fg=FG, font=(UI_FONT, 10, "bold"),
                                   anchor="w")
        self._title_lbl.pack(side="left")
        # The summary is bound by hand rather than by textvariable, because it
        # has to be shortened to whatever room the title leaves it. A card is
        # a column wide now, not a tab wide, and a value that no longer fits
        # was being cut mid-character — "15 chars · 1 ln" arriving on screen
        # as "ars · 1 ln", which reads as a bug rather than as a long value.
        self._sum_var = summary_var
        self._sum_lbl = None
        if summary_var is not None:
            self._sum_font = _font(FONT_NUM, 9)
            self._sum_lbl = tk.Label(self.head, text="", bg=BG_PANEL2,
                                     fg=FG_MUTE, font=(FONT_NUM, 9),
                                     anchor="e")
            self._sum_lbl.pack(side="right", padx=(8, 10))
            try:
                summary_var.trace_add("write", lambda *a: self._fit_summary())
            except AttributeError:
                summary_var.trace("w", lambda *a: self._fit_summary())

        self.rows = tk.Frame(self.inner, bg=BG_CARD)
        self.rows.pack(fill="x")

        self.inner.bind("<Configure>", lambda e: self._sync())
        self.bind("<Configure>", lambda e: self._sync())

    def _fit_summary(self):
        """Trim the header value to the room the title leaves, with an ellipsis.

        Trimmed from the end: these values read left to right in order of how
        much they matter — the character budget before the line count before
        the reading speed — so the tail is what can go.
        """
        lbl = self._sum_lbl
        if lbl is None or not lbl.winfo_exists():
            return
        text = self._sum_var.get() or ""
        used = 0
        for child in self.head.winfo_children():
            if child is not lbl:
                used += child.winfo_reqwidth()
        # 18 is this label's own padx (8 + 10); the rest is a gap after the
        # title, plus slack for the pixel or two pack settles on that a sum of
        # requested widths does not predict.
        avail = self.winfo_width() - self.INSET * 2 - used - 40
        if avail <= 12:
            lbl.configure(text="")
            return
        if self._sum_font.measure(text) <= avail:
            lbl.configure(text=text)
            return
        cut = text
        while cut and self._sum_font.measure(cut + "…") > avail:
            cut = cut[:-1]
        lbl.configure(text=(cut.rstrip(" ·") + "…") if cut else "")

    def set_active(self, on):
        """Light the left rail — 'the group you're working in'."""
        on = bool(on)
        if on != self._active:
            self._active = on
            self._draw(*self._last)

    def _sync(self):
        if self._syncing or not self.winfo_exists():
            return
        w = max(self.winfo_width(), 2)
        self.itemconfigure(self._win, width=max(10, w - self.INSET * 2))
        h = self.inner.winfo_reqheight() + self.INSET * 2
        self._last = (w, h)
        self._fit_summary()
        if abs(h - self.winfo_reqheight()) > 1:
            self._syncing = True
            try:
                self.configure(height=h)
            finally:
                self._syncing = False
        self._draw(w, h)

    def _draw(self, w, h):
        if not self.winfo_exists() or w < 4 or h < 4:
            return
        self.delete("bg")
        r = self.RADIUS
        _round_rect(self, 0, 0, w, h, r, fill=BORDER, outline=BORDER,
                    tags=("bg",))
        _round_rect(self, 1, 1, w - 1, h - 1, r - 1, fill=BG_CARD,
                    outline=BG_CARD, tags=("bg",))

        # Header band: rounded across the top, squared off where the rows start.
        hh = self.HEAD_H + self.INSET
        _round_rect(self, 1, 1, w - 1, hh, r - 1, fill=BG_PANEL2,
                    outline=BG_PANEL2, tags=("bg",))
        self.create_rectangle(1, hh - r, w - 1, hh, fill=BG_PANEL2,
                              outline=BG_PANEL2, tags=("bg",))
        self.create_line(r, 1, w - r, 1,
                         fill=_mix(BG_PANEL2, "#ffffff", 0.07), tags=("bg",))
        self.create_line(1, hh, w - 1, hh, fill=DIVIDER, tags=("bg",))

        if self._active:
            self.create_rectangle(0, r, 2, h - r, fill=SELECT, outline=SELECT,
                                  tags=("bg",))
        self.tag_lower("bg")


class ResultCard(tk.Canvas):
    """Rounded panel that grows to fit whatever is packed into `.inner`.

    RoundedField hosts one child at a fixed height, which the finished-run
    message can't promise: it is one sentence in the plain case, and a headline
    plus warnings and meta rows in the interesting ones. So this card measures
    its content and re-heights itself the way GroupCard does — re-entry guard
    included, since setting the height fires another <Configure>.

    Width is fixed rather than filled. The window is ~1000px wide for the form,
    and a full-bleed card stretches two short lines across all of it.
    """

    RADIUS = 5
    PAD_X = 20
    PAD_Y = 18

    def __init__(self, parent, width=620, bg_parent=BG, fill=BG_CARD,
                 border=BORDER_CARD, pad=None, radius=None):
        if pad is not None:
            self.PAD_X, self.PAD_Y = pad
        if radius is not None:
            self.RADIUS = radius
        super().__init__(parent, width=width, height=self.PAD_Y * 2,
                         bg=bg_parent, highlightthickness=0, bd=0)
        self._fill = fill
        self._border = border
        self._syncing = False
        self.inner = tk.Frame(self, bg=fill)
        self._win = self.create_window(self.PAD_X, self.PAD_Y, anchor="nw",
                                       window=self.inner)
        self.inner.bind("<Configure>", lambda e: self._sync())
        self.bind("<Configure>", lambda e: self._sync())
        # Content is filled in after construction; size to it once it is there,
        # in case no further <Configure> arrives.
        self.after_idle(self._sync)

    def _sync(self):
        if self._syncing or not self.winfo_exists():
            return
        w = max(self.winfo_width(), 2)
        self.itemconfigure(self._win, width=max(10, w - self.PAD_X * 2))
        h = self.inner.winfo_reqheight() + self.PAD_Y * 2
        if abs(h - self.winfo_reqheight()) > 1:
            self._syncing = True
            try:
                self.configure(height=h)
            finally:
                self._syncing = False
        self._draw(w, h)

    def _draw(self, w, h):
        if not self.winfo_exists() or w < 4 or h < 4:
            return
        self.delete("bg")
        r = self.RADIUS
        _round_rect(self, 0, 0, w, h, r, fill=self._border,
                    outline=self._border, tags=("bg",))
        _round_rect(self, 1, 1, w - 1, h - 1, r - 1, fill=self._fill,
                    outline=self._fill, tags=("bg",))
        # Lit top edge, same as the group cards on the form.
        self.create_line(r, 1, w - r, 1,
                         fill=_mix(self._fill, "#ffffff", 0.06), tags=("bg",))
        self.tag_lower("bg")


class StageList(tk.Frame):
    """The stages of a run, lit by the percentage the worker reports.

    A single bar plus a changing sentence tells you something is happening but
    not which part is slow, and when a run stalls it can't tell you where. Each
    stage owns a percentage range; anything below it is done, the range that
    contains the current percentage is running, the rest are still to come.
    """

    ROW_GAP = 10

    def __init__(self, parent, stages, bg_parent=BG):
        super().__init__(parent, bg=bg_parent, bd=0, highlightthickness=0)
        self._bg = bg_parent
        self._rows = []
        for i, (label, start) in enumerate(stages):
            end = stages[i + 1][1] if i + 1 < len(stages) else 100
            row = tk.Frame(self, bg=bg_parent)
            row.pack(fill="x", pady=(0, self.ROW_GAP))
            dot = tk.Canvas(row, width=16, height=16, bg=bg_parent,
                            highlightthickness=0, bd=0)
            dot.pack(side="left", padx=(0, 12))
            lbl = tk.Label(row, text=label, bg=bg_parent, fg=FG_MUTE,
                           font=(UI_FONT, 10), anchor="w")
            lbl.pack(side="left")
            # Right-hand note: "running" while a stage owns the percentage,
            # then how long it took. A stalled run looks identical to a slow
            # one until the stage that is stuck says how long it has been
            # stuck for, which is the question actually being asked of this
            # screen when nothing appears to be happening.
            note = tk.Label(row, text="", bg=bg_parent, fg=FG_MUTE,
                            font=(FONT_NUM, 8), anchor="e")
            note.pack(side="right")
            self._rows.append({"dot": dot, "lbl": lbl, "note": note,
                               "start": start, "end": end,
                               "began": None, "took": None})
        self.set_pct(0)

    @staticmethod
    def _fmt_elapsed(secs):
        if secs < 60:
            return "%.1f s" % secs
        return "%d m %02d s" % (int(secs) // 60, int(secs) % 60)

    def set_pct(self, pct):
        now = time.time()
        for r in self._rows:
            if pct >= r["end"]:
                state, fg, weight = "done", FG_DIM, "normal"
                if r["took"] is None and r["began"] is not None:
                    r["took"] = now - r["began"]
                note = ("" if r["took"] is None
                        else self._fmt_elapsed(r["took"]))
                ncol = FG_MUTE
            elif pct >= r["start"]:
                state, fg, weight = "now", FG, "bold"
                if r["began"] is None:
                    r["began"] = now
                note, ncol = "running", SELECT
            else:
                state, fg, weight = "todo", FG_MUTE, "normal"
                note, ncol = "", FG_MUTE
            self._draw_dot(r["dot"], state)
            if r["lbl"].winfo_exists():
                r["lbl"].configure(fg=fg, font=(UI_FONT, 10, weight))
            if r["note"].winfo_exists():
                r["note"].configure(text=note, fg=ncol)

    @staticmethod
    def _draw_dot(dot, state):
        if not dot.winfo_exists():
            return
        dot.delete("all")
        if state == "done":
            dot.create_oval(1, 1, 15, 15, fill=GOOD, outline=GOOD)
            dot.create_line(4.5, 8.5, 7, 11, fill=ACCENT_INK, width=2,
                            capstyle="round")
            dot.create_line(7, 11, 11.5, 5.0, fill=ACCENT_INK, width=2,
                            capstyle="round")
        elif state == "now":
            dot.create_oval(1, 1, 15, 15, fill=SELECT_GLOW, outline=SELECT,
                            width=2)
            dot.create_oval(6, 6, 10, 10, fill=SELECT, outline=SELECT)
        else:
            dot.create_oval(1, 1, 15, 15, fill="", outline=BORDER, width=2)


class App:
    # Corner radius for the frameless window. 8 is what Windows 11 itself
    # uses; the Win10 fallback matches it so the two look like one product.
    CORNER_R = 8

    def __init__(self, root, prompt_data, selection_path, args_path,
                 done_path, log_path, python_exe, script_path,
                 result_path, ack_path, run_id=None, run_marker=None):
        self.root = root
        # Before any widget: every font tuple below reads UI_FONT when the
        # widget is created, so this has to be settled first.
        resolve_ui_font()
        self.prompt_data = prompt_data
        self.selection_path = selection_path
        self.args_path = args_path
        self.done_path = done_path
        self.log_path = log_path
        self.python_exe = python_exe
        self.script_path = script_path
        self.result_path = result_path
        self.ack_path = ack_path
        # Run identity. The Resolve side stamps logs/current_run.txt with the
        # of the newest run; while this window is still on the form we watch
        # that file and close ourselves if a newer run has taken over, so two
        # loaders can never both answer the same Submit. Polling stops the
        # moment the form is submitted — a running transcription is never
        # interrupted by someone re-launching the script.
        self.run_id = run_id
        self.run_marker = run_marker
        self._submitted = False

        # Update state, filled in by the background check. Declared before
        # _build_form runs because the form's title bar creates the chip.
        self._update_info = None
        self._update_pill = None
        self._update_win = None
        # Guards a second check while one is in flight — the chip is clickable
        # the whole time it says "Checking…".
        self._update_checking = False

        # Rounded-corner bookkeeping. _corner_job coalesces the Windows 10
        # re-cut; _corner_size skips the Configure events that did not
        # actually change the window size.
        self._corner_job = None
        self._corner_size = None

        self.cancelled = False
        self.exit_code = None
        self.q = queue.Queue()
        self._anim_target = 0.0
        self._anim_value = 0.0
        # The running transcribe.py, so Cancel can actually stop it. Without a
        # handle, closing the window only killed the UI: the worker is a
        # detached child and the thread reading it is a daemon, so the Scribe
        # upload ran to completion and got billed for a run nobody was waiting
        # for. Guarded by a lock because it is set on the worker thread and read
        # on the Tk thread.
        self._proc = None
        self._proc_lock = threading.Lock()

        root.title("Srutilekha")
        root.configure(bg=BG_OUTER)
        root.resizable(False, False)
        try:
            root.overrideredirect(True)
        except Exception:
            pass
        try:
            root.attributes("-topmost", True)
        except Exception:
            pass

        # Single flat card window. Height is set by the tallest fixed thing in
        # it — the 9:16 preview in the stage — plus the title and action bars;
        # the tabs mean no single tab needs more vertical room than that, so
        # the window no longer has to be tall enough for every control at once.
        # Clamped to the screen, and the action bar is packed first so it can
        # never be pushed off the bottom.
        sw = root.winfo_screenwidth()
        sh = root.winfo_screenheight()
        # Sized to the page rather than to a round number. With the hints in
        # tooltips the settings need 610px of the scroll port, and the two
        # columns read comfortably at ~290 each. A Resolve panel is compact,
        # and a window larger than its contents was one of the things that
        # made this read as a guest in its own host.
        W = min(930, sw - 140)
        H = min(740, sh - 70)
        self._min_w, self._min_h = 880, 560
        root.geometry("%dx%d+%d+%d" % (W, H, (sw - W) // 2, max(20, (sh - H) // 2)))
        root.configure(bg=BG)
        self._maximized = False
        self._normal_geo = "%dx%d+%d+%d" % (W, H, (sw - W) // 2, max(20, (sh - H) // 2))

        self._setup_styles()

        self.subtitle_var = tk.StringVar(value="Subtitle generator")

        # Body fills the whole window. Padding is set per screen rather than
        # here: the form's title bar, presets strip and action bar are
        # full-bleed panel bands that have to touch the window edge, while the
        # progress / done / review screens want a normal inset margin.
        self.body = tk.Frame(root, bg=BG)
        self.body.pack(fill="both", expand=True)

        # Drag support: clicking anywhere on body bg (not on widgets)
        # moves the frameless window.
        self._drag_off = (0, 0)
        self.body.bind("<Button-1>", self._drag_start)
        self.body.bind("<B1-Motion>", self._drag_move)

        self._build_form()
        self._controls = TitleBarControls(root,
            on_minimize=self._minimize,
            on_maximize=self._toggle_maximize,
            on_close=self._on_cancel)
        self._controls.place(relx=1.0, y=0, anchor="ne")

        # Resize grip (frameless windows have no native resize border). A small
        # diagonal-hatch handle in the bottom-right corner drags to resize.
        self._grip = tk.Canvas(root, width=16, height=16, bg=BG,
                               highlightthickness=0, bd=0, cursor="sizing")
        for d in (5, 9, 13):
            self._grip.create_line(16 - d, 15, 15, 16 - d, fill=BORDER_BRIGHT)
        self._grip.place(relx=1.0, rely=1.0, x=-3, y=-3, anchor="se")
        self._grip.bind("<Button-1>", self._resize_start)
        self._grip.bind("<B1-Motion>", self._resize_move)

        # Rounded corners. Deferred: the HWND these need does not exist until
        # the window has been mapped. On Windows 10 the region is sized in
        # window coordinates, so it has to be re-cut on every resize — the
        # grip drag and the maximize toggle both change the size.
        root.after(0, self._apply_corners)
        if not DWM_ROUNDING:
            root.bind("<Configure>", self._on_configure_corners, add="+")

        root.after(60, lambda: _steal_focus(root))
        root.after(600, lambda: _keep_topmost(root))
        root.protocol("WM_DELETE_WINDOW", self._on_cancel)
        if self.run_id and self.run_marker:
            root.after(1200, self._poll_superseded)
        if updater is not None:
            self._start_update_check()

    # ── Rounded corners ─────────────────────────────────────────────────
    def _apply_corners(self):
        # Square while maximized, matching how Windows treats its own
        # maximized windows.
        round_corners(self.root, radius=self.CORNER_R,
                      square=self._maximized)

    def _on_configure_corners(self, event):
        """Re-cut the Windows 10 region after a resize, coalesced.

        Configure fires for every pixel of a grip drag and for child layout
        changes too; cutting a region per event is both wasted work and
        visible as flicker, so only the last one in a burst counts."""
        if event.widget is not self.root:
            return
        size = (self.root.winfo_width(), self.root.winfo_height())
        if size == getattr(self, "_corner_size", None):
            return
        self._corner_size = size
        if self._corner_job is not None:
            try:
                self.root.after_cancel(self._corner_job)
            except Exception:
                pass
        self._corner_job = self.root.after(40, self._apply_corners)

    # ── Supersede watchdog (form phase only) ─────────────────────────────
    def _poll_superseded(self):
        """Close this window if the Resolve side has started a newer run.

        Without this, an abandoned loader keeps its Resolve-side script
        spinning in the wait loop; when the user re-runs Srutilekha and
        submits, BOTH scripts read the submission and transcribe in parallel —
        one of them then looks for an SRT the other never wrote
        ("Transcription produced no output")."""
        if self._submitted or self.cancelled:
            return
        try:
            with open(self.run_marker, "r", encoding="utf-8") as f:
                current = f.read().strip()
        except Exception:
            current = ""
        if current and current != self.run_id:
            self.cancelled = True
            self.exit_code = 130
            try:
                with open(self.done_path, "w", encoding="utf-8") as f:
                    f.write("130")
            except Exception:
                pass
            self.root.destroy()
            return
        self.root.after(1200, self._poll_superseded)

    # ── Self-update ──────────────────────────────────────────────────────
    def _idle_pill_text(self):
        return "v%s" % updater.VERSION

    def _set_pill(self, state, text):
        pill = self._update_pill
        if pill is not None and pill.winfo_exists():
            pill.set_state(state, text)

    def _start_update_check(self, manual=False):
        """Ask GitHub whether a newer release exists, off the UI thread.

        Daemon thread: a slow or hanging network must never delay the window
        appearing, and must not keep the process alive after the user closes
        it. The answer comes back through root.after, so every widget touch
        still happens on the Tk thread.

        ``manual`` is a click on the chip rather than the check at startup.
        The difference is only in what a *negative* answer does: silence at
        startup, and a visible "Up to date" when someone asked.
        """
        if self._update_checking:
            return
        self._update_checking = True
        self._set_pill("checking", "Checking…")

        def work():
            try:
                info = updater.check()
            except Exception:
                info = None                # check() already swallows; belt and braces
            try:
                self.root.after(0, self._on_update_checked, info, manual)
            except Exception:
                pass                       # window already gone
        threading.Thread(target=work, daemon=True).start()

    def _on_update_checked(self, info, manual):
        self._update_checking = False
        # Anything past the form has a transcription in flight or finished;
        # replacing transcribe.py underneath either is not worth the chip.
        if self.cancelled or self._submitted:
            return
        if not info:
            self._set_pill("idle", self._idle_pill_text())
            if manual:
                # Say so, then fall back to the version. Without this a manual
                # check that finds nothing looks identical to one that never
                # ran.
                self._set_pill("idle", "Up to date")
                self.root.after(2500, self._restore_idle_pill)
            return
        self._update_info = info
        self._set_pill("available", "Update")
        if info.get("mandatory"):
            self._show_update_dialog()

    def _restore_idle_pill(self):
        # Only if nothing has happened since — a check that landed in the
        # meantime, or an install, owns the chip now.
        if self._update_info is None and not self._update_checking:
            self._set_pill("idle", self._idle_pill_text())

    def _on_update_click(self):
        """One control, two jobs: open the dialog when there is something to
        install, otherwise go and look again."""
        if self._update_info:
            self._show_update_dialog()
        else:
            self._start_update_check(manual=True)

    def _show_update_dialog(self):
        """Modal card: what changed, and a button that applies it."""
        info = self._update_info
        if not info:
            return
        if self._update_win is not None and self._update_win.winfo_exists():
            self._update_win.lift()
            return

        mandatory = bool(info.get("mandatory"))
        W = 470

        win = tk.Toplevel(self.root)
        self._update_win = win
        win.overrideredirect(True)
        try:
            win.attributes("-topmost", True)
        except Exception:
            pass
        win.configure(bg=BORDER)                    # 1px frame around the card

        card = tk.Frame(win, bg=BG)
        card.pack(fill="both", expand=True, padx=1, pady=1)

        head = tk.Frame(card, bg=BG_CARD)
        head.pack(fill="x")
        tk.Label(head, text="Update available", bg=BG_CARD, fg=FG,
                 font=(UI_FONT, 11, "bold")).pack(side="left", padx=(16, 10),
                                                     pady=11)
        stamp = "v%s → v%s" % (updater.VERSION, info["version"])
        if info.get("released"):
            stamp += "   ·   %s" % info["released"]
        tk.Label(head, text=stamp, bg=BG_CARD, fg=FG_MUTE,
                 font=(UI_FONT, 9)).pack(side="left")

        body = tk.Frame(card, bg=BG)
        body.pack(fill="both", expand=True, padx=16, pady=(14, 6))

        notes = info.get("notes") or []
        if notes:
            for line in notes[:6]:
                row = tk.Frame(body, bg=BG)
                row.pack(fill="x", pady=(0, 5))
                tk.Label(row, text="•", bg=BG, fg=ACCENT, font=(UI_FONT, 9)
                         ).pack(side="left", padx=(0, 8), anchor="n")
                tk.Label(row, text=line, bg=BG, fg=FG_DIM, font=(UI_FONT, 9),
                         wraplength=W - 60, justify="left", anchor="w"
                         ).pack(side="left", fill="x", expand=True)
        else:
            tk.Label(body, text="A newer version of Srutilekha is available.",
                     bg=BG, fg=FG_DIM, font=(UI_FONT, 9)).pack(anchor="w")

        if mandatory:
            tk.Label(body,
                     text="This update is required. Srutilekha cannot run on "
                          "the older version.",
                     bg=BG, fg=ACCENT, font=(UI_FONT, 9),
                     wraplength=W - 40, justify="left").pack(anchor="w",
                                                             pady=(10, 0))

        status = tk.StringVar(value="")
        tk.Label(body, textvariable=status, bg=BG, fg=FG_MUTE,
                 font=(UI_FONT, 9), wraplength=W - 40, justify="left",
                 anchor="w").pack(fill="x", pady=(10, 0))

        act = tk.Frame(card, bg=BG_CARD)
        act.pack(fill="x", side="bottom")
        inner = tk.Frame(act, bg=BG_CARD)
        inner.pack(fill="x", padx=16, pady=11)

        def place():
            """Centre horizontally on the main window, high enough that the
            card still fits after the notes and the status line have grown."""
            win.update_idletasks()
            h = win.winfo_reqheight()
            x = self.root.winfo_rootx() + (self.root.winfo_width() - W) // 2
            y = self.root.winfo_rooty() + (self.root.winfo_height() - h) // 3
            win.geometry("%dx%d+%d+%d" % (W, h, max(0, x), max(0, y)))
            # After the geometry, not before: the Windows 10 region is cut to
            # the window's current size, and the card grows as notes and the
            # status line are added.
            round_corners(win, radius=App.CORNER_R)

        def close():
            self._update_win = None
            try:
                win.grab_release()
            except Exception:
                pass
            win.destroy()

        def dismiss():
            # "Later" on a required update is the same as declining to run.
            if mandatory:
                self._on_cancel()
            else:
                close()

        state = {"running": False}

        def finished(_backup):
            status.set("Updated to v%s. Close this window, then start "
                       "Srutilekha again from Workspace ▸ Scripts — Resolve "
                       "loads the new version on the next run."
                       % info["version"])
            self._update_info = None
            self._set_pill("done", "Restart to finish")
            for w in inner.winfo_children():
                w.destroy()
            RoundedButton(inner, "Close Srutilekha", self._on_cancel,
                          primary=True, bg_parent=BG_CARD, height=34
                          ).pack(side="right")
            place()

        def failed(err):
            state["running"] = False
            go.set_text("Try again")
            status.set(str(err) or "The update failed.")
            place()

        def run():
            if state["running"]:
                return
            state["running"] = True
            go.set_text("Updating…")
            status.set("Starting…")

            def work():
                def report(msg):
                    _post(status.set, msg)
                try:
                    backup = updater.install(info, report)
                except Exception as e:
                    _post(failed, e)
                else:
                    _post(finished, backup)

            def _post(fn, arg):
                # The card can be gone by the time a step reports back.
                try:
                    win.after(0, fn, arg)
                except Exception:
                    pass

            threading.Thread(target=work, daemon=True).start()

        go = RoundedButton(inner, "Update now", run, primary=True,
                           bg_parent=BG_CARD, height=34)
        go.pack(side="right", padx=(8, 0))
        RoundedButton(inner, "Close Srutilekha" if mandatory else "Later",
                      dismiss, primary=False, bg_parent=BG_CARD, height=34
                      ).pack(side="right")

        place()
        if not mandatory:
            win.bind("<Escape>", lambda e: close())
        try:
            win.grab_set()
        except Exception:
            pass
        # An overrideredirect toplevel is not given keyboard focus by Windows,
        # so without this the Escape binding above would never fire and the
        # card would sit above a window it has already grabbed input from.
        _steal_focus(win)
        try:
            win.focus_force()
        except Exception:
            pass

    # ── window drag (frameless) ──────────────────────────────────────────
    def _drag_start(self, e):
        self._drag_off = (e.x_root - self.root.winfo_x(),
                          e.y_root - self.root.winfo_y())

    def _drag_move(self, e):
        x = e.x_root - self._drag_off[0]
        y = e.y_root - self._drag_off[1]
        self.root.geometry("+%d+%d" % (x, y))

    # ── window resize (frameless corner grip) ────────────────────────────
    def _resize_start(self, e):
        self._resize_ref = (e.x_root, e.y_root,
                            self.root.winfo_width(), self.root.winfo_height())

    def _resize_move(self, e):
        sx, sy, sw, sh = self._resize_ref
        nw = max(self._min_w, sw + (e.x_root - sx))
        nh = max(self._min_h, sh + (e.y_root - sy))
        self.root.geometry("%dx%d" % (nw, nh))

    def _minimize(self):
        self.root.overrideredirect(False)
        self.root.iconify()
        def _check():
            try:
                if self.root.state() == "normal":
                    self.root.overrideredirect(True)
                    # Toggling overrideredirect re-creates the native frame,
                    # which drops both the DWM attribute and the region.
                    self._apply_corners()
                    _steal_focus(self.root)
                else:
                    self.root.after(200, _check)
            except Exception:
                pass
        self.root.after(300, _check)

    def _toggle_maximize(self):
        if self._maximized:
            self.root.geometry(self._normal_geo)
            self._maximized = False
        else:
            self._normal_geo = "%dx%d+%d+%d" % (
                self.root.winfo_width(), self.root.winfo_height(),
                self.root.winfo_x(), self.root.winfo_y())
            sw = self.root.winfo_screenwidth()
            sh = self.root.winfo_screenheight()
            self.root.geometry("%dx%d+0+0" % (sw, sh))
            self._maximized = True
        self._controls.update_max_icon(self._maximized)
        self._apply_corners()

    def _make_draggable(self, widget):
        widget.bind("<Button-1>", self._drag_start)
        widget.bind("<B1-Motion>", self._drag_move)

    def _setup_styles(self):
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        # Only ttk widget still in use: progress bar.
        style.configure(
            "SubSync.Horizontal.TProgressbar",
            troughcolor=BG_INPUT,
            background=SELECT,
            bordercolor=BG,
            lightcolor=SELECT,
            darkcolor=SELECT,
            thickness=8,
        )

    # ── helpers ───────────────────────────────────────────────────────────
    def _clear_body(self, pad=22):
        """Empty the body and set the margin this screen wants.

        The form passes pad=0 because its title bar, presets strip and action
        bar are full-bleed bands; every other screen keeps the inset margin.

        The children are unmapped and the idle queue flushed *before* anything
        is destroyed. Destroying this form's widgets while they were still
        mapped killed the interpreter outright — Tk aborted with "ButtonProc
        called on an invalid HWND" a moment later, on the next trip through the
        event loop, rather than raising anything catchable. Taking them out of
        the geometry manager and letting Tk settle first avoids it; so does
        flushing between each destroy, which is the same fix more slowly.
        """
        kids = self.body.winfo_children()
        for w in kids:
            try:
                w.pack_forget()
            except Exception:
                pass
        self.body.update_idletasks()
        for w in kids:
            w.destroy()
        self.body.pack_configure(padx=pad, pady=pad)

    def _make_button(self, parent, text, command, primary=False):
        return RoundedButton(parent, text, command, primary=primary, bg_parent=BG)

    # ── Phase 1: form ─────────────────────────────────────────────────────
    # Layout, top to bottom:
    #
    #   title bar   logo · Srutilekha · timeline crumb · Generate/Sync switch
    #   ┌───────────┬───────────────────────────────────────────────┐
    #   │  stage    │  looks strip (five one-click presets)         │
    #   │  (fixed)  │  Source | Type | Timing | Refine              │
    #   │  preview  │  ...the selected tab's controls...            │
    #   └───────────┴───────────────────────────────────────────────┘
    #   action bar  what-will-happen summary · Cancel · ⋯ · Generate
    #
    # The stage never scrolls and is never rebuilt, so the live preview stays
    # put while you move between tabs. Only the tab body scrolls.
    def _build_form(self):
        self._clear_body(pad=0)
        items    = self.prompt_data.get("items", [])
        defaults = self.prompt_data.get("defaults", {})
        self._defaults = defaults

        self._declare_vars(items, defaults)

        # ── Title bar ────────────────────────────────────────────────────
        # Full-bleed panel band. The frameless window's own minimise/maximise/
        # close buttons are placed over its right end at the root level, so the
        # task switch sits left of centre and never collides with them.
        bar = tk.Frame(self.body, bg=BG_BAR, height=44)
        bar.pack(fill="x", side="top")
        bar.pack_propagate(False)
        # Hairline under the title bar, so the band reads as a raised surface
        # rather than as the top of the page. Tk has no gradient on a Frame,
        # and the bar hosts widgets, so it cannot become a Canvas without
        # re-placing all of them — a lit edge buys most of what the fill would.
        tk.Frame(self.body, bg=DIVIDER_MID, height=1).pack(fill="x", side="top")

        logo = LogoTile(bar, size=22, radius=6, bg_parent=BG_BAR)
        logo.pack(side="left", padx=(14, 10))
        title_lbl = tk.Label(bar, text="Srutilekha", bg=BG_BAR, fg=FG,
                             font=(UI_FONT, 11, "bold"))
        title_lbl.pack(side="left")

        crumb = self._timeline_crumb()
        crumb_lbl = tk.Label(bar, text=crumb, bg=BG_BAR, fg=FG_MUTE,
                             font=(UI_FONT, 9))
        crumb_lbl.pack(side="left", padx=(10, 0))
        for w in (bar, title_lbl, crumb_lbl):
            self._make_draggable(w)

        # Generate / Sync Existing — this switches what the whole window is
        # for, so it belongs in the title bar rather than among the settings.
        task_seg = tk.Frame(bar, bg=BG_BAR)
        task_seg.pack(side="left", padx=(18, 0))
        self._seg_gen = RoundedButton(
            task_seg, "Generate", lambda: self._set_task("Generate"),
            primary=True, bg_parent=BG_BAR, height=24)
        self._seg_gen.pack(side="left", padx=(0, 4))
        self._seg_sync = RoundedButton(
            task_seg, "Sync Existing", lambda: self._set_task("Sync Existing"),
            primary=False, bg_parent=BG_BAR, height=24)
        self._seg_sync.pack(side="left")

        # Update chip, always mounted. It used to be created hidden and packed
        # only once a check found something, which meant an install that was
        # current — the normal case — showed nothing, and "no update" was
        # indistinguishable from "the updater is broken". It now shows the
        # running version, and clicking it checks on demand. It is packed
        # clear of the minimise/maximise/close buttons, which are placed over
        # the right end of this bar at the root level and so are invisible to
        # pack().
        if updater is not None:
            if self._update_info:
                state, label = "available", "Update"
            elif self._update_checking:
                state, label = "checking", "Checking…"
            else:
                state, label = "idle", self._idle_pill_text()
            self._update_pill = UpdatePill(bar, label, self._on_update_click,
                                           bg_parent=BG_BAR, state=state)
            self._update_pill.pack(
                side="right", padx=(0, TitleBarControls.BTN_W * 3 + 12))

        # ── Action bar (packed before the middle so it can never be clipped)
        act = tk.Frame(self.body, bg=BG_BAR)
        act.pack(fill="x", side="bottom")
        tk.Frame(act, bg=_mix(BG_BAR, "#ffffff", 0.06),
                 height=1).pack(fill="x", side="top")
        inner = tk.Frame(act, bg=BG_BAR)
        inner.pack(fill="x", padx=16, pady=11)

        self.summary_var = tk.StringVar(value="")
        summary = tk.Label(inner, textvariable=self.summary_var, bg=BG_BAR,
                           fg=FG_MUTE, font=(UI_FONT, 9), anchor="w",
                           justify="left")
        summary.pack(side="left", fill="x", expand=True)

        self._generate_btn = RoundedButton(
            inner, "Generate captions",
            lambda: self._on_submit(
                "sync" if self.task_var.get() == "Sync Existing" else "generate"),
            primary=True, bg_parent=BG_BAR, height=36)
        self._generate_btn.pack(side="right", padx=(8, 0))

        # Undo deletes the last caption track. It is secondary to generating
        # and it is destructive, so it does not sit at Generate's size beside it.
        RoundedButton(inner, "Undo last captions",
                      lambda: self._on_submit("undo"), primary=False,
                      bg_parent=BG_BAR, height=36).pack(side="right",
                                                         padx=(8, 0))

        RoundedButton(inner, "Cancel", self._on_cancel, primary=False,
                      bg_parent=BG_BAR, height=36).pack(side="right")

        # ── Middle: stage | inspector ────────────────────────────────────
        main = tk.Frame(self.body, bg=BG)
        main.pack(fill="both", expand=True)

        self._stage = tk.Frame(main, bg=BG_OUTER, width=self.STAGE_W)
        self._stage.pack(side="left", fill="y")
        self._stage.pack_propagate(False)
        self._build_stage()

        tk.Frame(main, bg=DIVIDER, width=1).pack(side="left", fill="y")

        insp = tk.Frame(main, bg=BG)
        insp.pack(side="left", fill="both", expand=True)

        # ── Settings: one page, Source and Timing side by side ───────────
        # There were two tabs here. Everything they held fits in two columns
        # at this window width, and half the settings being one click away
        # meant the summary in the action bar described things you could not
        # see. The tab names survive as the column headings.
        wrap = tk.Frame(insp, bg=BG)
        wrap.pack(fill="both", expand=True)
        canvas = tk.Canvas(wrap, bg=BG, highlightthickness=0, bd=0)
        vsb = SlimScrollbar(wrap, canvas.yview, width=6, reserve=True)
        canvas.configure(yscrollcommand=vsb.set)
        canvas.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y", padx=(4, 4))
        self._scroll_canvas = canvas

        form = tk.Frame(canvas, bg=BG)
        form_id = canvas.create_window((0, 0), window=form, anchor="nw")
        self._form_id = form_id

        def _sync_scrollregion(_e=None):
            # A queued <Configure> can arrive after the form has been swapped
            # out for the progress view and this canvas destroyed.
            if not canvas.winfo_exists():
                return
            canvas.configure(scrollregion=canvas.bbox("all"))

        form.bind("<Configure>", _sync_scrollregion)
        canvas.bind("<Configure>",
                    lambda e: canvas.itemconfigure(form_id, width=e.width))
        self._sync_scrollregion = _sync_scrollregion

        def _on_wheel(e):
            if not canvas.winfo_exists():
                return
            try:
                # Wheel events inside a popup (font list, dropdown) scroll that
                # list, not the form behind it.
                if e.widget.winfo_toplevel() is not self.root:
                    return
            except Exception:
                return
            first, last = canvas.yview()
            if last - first >= 1.0:      # tab fits — nothing to scroll to
                return
            canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
        canvas.bind_all("<MouseWheel>", _on_wheel)

        self._tab_host = form
        self._cards = []          # every GroupCard, for the activity rail
        self._build_setup_page(form, defaults, items)

        self._apply_task()
        self._wire_summary()
        self._wire_card_activity()
        try:
            self.aspect_var.trace_add("write", self._apply_frame)
        except AttributeError:
            self.aspect_var.trace("w", self._apply_frame)

        self.root.after(0, _sync_scrollregion)
        self.root.bind("<Return>", lambda e: self._on_submit(
            "sync" if self.task_var.get() == "Sync Existing" else "generate"))
        self.root.bind("<Escape>", lambda e: self._on_cancel())

    STAGE_W = 300          # stage column; preview is this minus the padding

    def _timeline_crumb(self):
        """'· Timeline · 1080×1920' style context line for the title bar.

        Only shows what the Resolve-side script actually passed — no invented
        values.
        """
        d = self.prompt_data
        bits = []
        for key in ("timeline", "timeline_name"):
            if d.get(key):
                bits.append(str(d[key]))
                break
        for key in ("resolution", "timeline_res"):
            if d.get(key):
                bits.append(str(d[key]))
                break
        if d.get("duration"):
            bits.append(str(d["duration"]))
        return ("·  " + "  ·  ".join(bits)) if bits else ""

    # max characters, lines per cue, max seconds — in the order the Resolve
    # side reads them out of the comma-joined "settings" string. One source of
    # truth, because these three are positional and a blank shifts the rest.
    SETTINGS_DEFAULTS = ("15", "1", "2")

    def _declare_vars(self, items, defaults):
        """Every form variable, in one place.

        Declared before any widget is built so the tab frames — which are
        constructed in whatever order the tab list happens to be in — can all
        bind against them without caring who runs first.
        """
        self.task_var = tk.StringVar(value="Generate")

        # Blanks are backfilled from SETTINGS_DEFAULTS rather than left empty:
        # these three are positional on the wire (see _on_submit), so an empty
        # slot is not "unset", it is a shifted value.
        default_settings = defaults.get("settings", ",".join(self.SETTINGS_DEFAULTS))
        parts = [p.strip() for p in default_settings.split(",")]
        while len(parts) < len(self.SETTINGS_DEFAULTS):
            parts.append("")
        self.settings_vars = [tk.StringVar(value=p or d)
                              for p, d in zip(parts, self.SETTINGS_DEFAULTS)]

        self.min_var      = tk.StringVar(value=str(defaults.get("min_secs", "0.4")))
        self.cps_var      = tk.StringVar(value=str(defaults.get("cps", "25")))
        self.textsize_var = tk.StringVar(value=str(defaults.get("text_size", "55")))
        self.words_per_var = tk.StringVar(value=str(defaults.get("words_per", "0")))

        self.lang_var = tk.StringVar(value=defaults.get("lang", LANGUAGES[0]))
        if self.lang_var.get() not in LANGUAGES:
            self.lang_var.set(LANGUAGES[0])
        # Frame being designed for. Defaults to the timeline's own shape when
        # the Resolve-side script reported a resolution, and to Reel when it
        # did not — reel is what these captions are mostly cut for, and what
        # the preview has always drawn.
        self.aspect_var = tk.StringVar(
            value=defaults.get("aspect") or self._frame_from_timeline())
        if self.aspect_var.get() not in FRAME_FORMATS:
            self.aspect_var.set(DEFAULT_FRAME)
        # Where subtitles sit, as a fraction of frame height up from the
        # bottom. Always holds a number so the slider has something to show;
        # it starts at the professional default for the opening frame and
        # follows the frame until the user moves it, after which it is theirs.
        self.srt_posy_var = tk.StringVar(
            value=str(defaults.get("srt_posy")
                      or FRAME_FORMATS[self.aspect_var.get()]["srt_posy"]))
        self.combo_var = tk.StringVar(value=items[0] if items else "")
        self.sync_srt_path_var = tk.StringVar(value="")
        self.ref_script_var = tk.StringVar(value=defaults.get("ref_script", ""))

        self.punct_var   = tk.IntVar(value=int(defaults.get("punct", 0)))
        self.diarize_var = tk.IntVar(value=int(defaults.get("diarize", 0)))
        self.outline_var = tk.IntVar(value=int(defaults.get("outline", 1)))
        self.shadow_var  = tk.IntVar(value=int(defaults.get("shadow", 1)))
        self.safe_zone_var = tk.IntVar(value=int(defaults.get("safe_zone", 1)))
        self.review_var  = tk.IntVar(value=int(defaults.get("review", 1)))

        self.color_var   = tk.StringVar(value=str(defaults.get("color", "")))
        self.font_var = tk.StringVar(
            value=str(defaults.get("font", CAPTION_FONTS[0])))
        self.font_style_var = tk.StringVar(
            value=str(defaults.get("font_style", "Auto")))
        if self.font_style_var.get() not in FONT_STYLES:
            self.font_style_var.set("Auto")

        # One per group card. These are what make a collapsed card readable —
        # the header states the group's current value, so the whole
        # configuration can be read without opening anything.
        for name in ("src", "script", "detect",
                     "split", "review", "preset"):
            setattr(self, name + "_sum_var", tk.StringVar(value=""))

    # ── Card-based group builders ─────────────────────────────────────────
    CTRL_W = 172        # width of a dropdown in a row's control column
    CHIP_W = 92         # width of a numeric chip
    SLIDER_W = 96       # slider that shares its row with a chip

    def _card(self, parent, title, glyph=None, icon=None, summary_var=None):
        """Add a group card to a tab and register it for the activity rail."""
        c = GroupCard(parent, title, glyph=glyph, icon=icon,
                      summary_var=summary_var, bg_parent=BG)
        c.pack(fill="x", pady=(0, 9))
        self._cards.append(c)
        return c

    def _row(self, card, label, hint=None, stacked=False):
        """A row inside a card: hairline above (except the first), label and
        optional one-line explanation left, control column right.

        ``stacked`` puts the label above a full-width control instead — for a
        row whose control is a path or a name rather than a value.

        ``hint`` is a tooltip, not a line under the label: see Tooltip.

        Returns the control slot. ``slot.row_handle`` is a RowHandle for the row
        as a whole, for the few rows that have to be shown or hidden as the
        rest of the form changes.
        """
        divider = None
        if card.rows.pack_slaves():
            divider = tk.Frame(card.rows, bg=DIVIDER, height=1)
            divider._is_row_divider = True   # so RowHandle can tidy leading ones
            divider.pack(fill="x")
        row = tk.Frame(card.rows, bg=BG_CARD)
        row.pack(fill="x")
        row.grid_columnconfigure(0, weight=1)

        text = tk.Frame(row, bg=BG_CARD)
        slot = tk.Frame(row, bg=BG_CARD)
        if stacked:
            text.grid(row=0, column=0, columnspan=2, sticky="ew",
                      padx=10, pady=(5, 2))
            slot.grid(row=1, column=0, columnspan=2, sticky="ew",
                      padx=10, pady=(0, 6))
        else:
            text.grid(row=0, column=0, sticky="w", padx=(10, 8), pady=4)
            slot.grid(row=0, column=1, sticky="e", padx=(0, 9), pady=4)

        tk.Label(text, text=label, bg=BG_CARD, fg=FG,
                 font=(UI_FONT, 10), anchor="w").pack(anchor="w")
        if hint:
            # The hint is a tooltip now rather than a line under the label.
            # Bound again after idle because the caller fills `slot` after this
            # returns, and hovering the control has to raise it too.
            tip = Tooltip(row, hint, app_root=self.root)
            self.root.after_idle(tip.rebind)
            slot.tooltip = tip

        slot.row_handle = RowHandle(card.rows, row, divider)
        return slot

    def _row_full(self, card, label, hint=None):
        """A row whose control needs the full width — a path, a word list.

        ``hint`` is a tooltip on the row — see Tooltip.
        """
        if card.rows.pack_slaves():
            tk.Frame(card.rows, bg=DIVIDER, height=1).pack(fill="x")
        row = tk.Frame(card.rows, bg=BG_CARD)
        row.pack(fill="x")
        head = tk.Frame(row, bg=BG_CARD)
        head.pack(fill="x", padx=11, pady=(8, 5))
        tk.Label(head, text=label, bg=BG_CARD, fg=FG,
                 font=(UI_FONT, 10)).pack(side="left")
        self._row_full_head = head          # callers may add a right-side widget
        slot = tk.Frame(row, bg=BG_CARD)
        slot.pack(fill="x", padx=11, pady=(0, 8))
        if hint:
            tip = Tooltip(row, hint, app_root=self.root)
            self.root.after_idle(tip.rebind)
            slot.tooltip = tip
        return slot

    def _pick(self, slot, values, var, width=None, prefix="", fill=False,
              max_rows=None):
        """A dropdown sized to the row's control column, or to a stacked row."""
        d = Dropdown(slot, values, var, display_prefix=prefix,
                     bg_parent=BG_CARD, height=28, radius=4,
                     max_rows=max_rows)
        if fill:
            d.pack(fill="x")
        else:
            d.configure(width=width or self.CTRL_W)
            d.pack(side="left")
        return d

    def _chip(self, slot, var, unit=None, width=None):
        box = SmallInput(slot, var, unit=unit, bg_parent=BG_CARD)
        box.configure(width=width or self.CHIP_W, height=30)
        box._h = 30
        box.pack(side="left")
        return box

    def _knob(self, slot, var):
        sw = ToggleSwitch(slot, var)
        sw.configure(bg=BG_CARD)
        sw.pack()
        return sw

    def _toggle_card_row(self, card, label, var, hint=None):
        self._knob(self._row(card, label, hint), var)

    def _wire_card_activity(self):
        """Light a card's rail when one of its own controls is touched.

        Hover is the obvious trigger and was the first attempt, but <Motion>
        never arrives in this window — a frameless always-on-top toplevel does
        not get reliable pointer tracking here, and `winfo_containing` reports
        None anywhere over the window even while synthetic clicks land. So the
        rail follows what can actually be observed: the card whose variables
        last changed, plus focus for the text fields, which gives feedback
        before any value has been edited.

        Widgets are discovered by walking each card once and picking up the Tk
        variable every control already exposes, so the row builders don't have
        to register anything by hand.
        """
        def bound_vars(w):
            for attr in ("variable", "var", "_var"):
                v = getattr(w, attr, None)
                if isinstance(v, (tk.StringVar, tk.IntVar, tk.DoubleVar)):
                    yield v

        for card in self._cards:
            seen = set()
            stack = [card]
            while stack:
                w = stack.pop()
                stack.extend(w.winfo_children())
                for v in bound_vars(w):
                    if str(v) in seen:
                        continue
                    seen.add(str(v))
                    cb = lambda *a, c=card: self._activate_card(c)
                    try:
                        v.trace_add("write", cb)
                    except AttributeError:
                        v.trace("w", cb)
                if isinstance(w, tk.Entry):
                    w.bind("<FocusIn>",
                           lambda e, c=card: self._activate_card(c), add="+")

    def _activate_card(self, card):
        for c in getattr(self, "_cards", ()):
            if c.winfo_exists():
                c.set_active(c is card)

    # ── The setup page ────────────────────────────────────────────────────
    def _build_setup_page(self, form, defaults, items):
        """Source and Timing as two columns of one page.

        Presets spans both columns at the foot. It saves more than the split
        numbers — the language and the two detect switches go with them — so
        it belongs to neither column on its own. It only fits there as one
        row; as two it cost more height than the window has.
        """
        grid = tk.Frame(form, bg=BG)
        grid.pack(fill="both", expand=True, padx=16, pady=15)
        grid.grid_columnconfigure(0, weight=1, uniform="setup")
        grid.grid_columnconfigure(1, weight=1, uniform="setup")

        left = tk.Frame(grid, bg=BG)
        left.grid(row=0, column=0, sticky="new", padx=(0, 9))
        right = tk.Frame(grid, bg=BG)
        right.grid(row=0, column=1, sticky="new", padx=(9, 0))
        span = tk.Frame(grid, bg=BG)
        span.grid(row=1, column=0, columnspan=2, sticky="ew")

        self._group_head(left, "Source", "what goes in")
        self._col_source(left, defaults, items)

        self._group_head(right, "Timing", "how it is cut")
        self._col_timing(right, defaults, items)
        self._build_presets(span)

    def _group_head(self, parent, title, eyebrow):
        """A column heading — where a tab label used to be."""
        head = tk.Frame(parent, bg=BG)
        head.pack(fill="x", pady=(0, 9))
        tk.Label(head, text=title, bg=BG, fg=FG,
                 font=(UI_FONT, 11, "bold")).pack(side="left")
        TrackedLabel(head, eyebrow.upper(), bg_parent=BG,
                     color=FG_MUTE).pack(side="left", padx=(9, 0), pady=(3, 0))
        tk.Frame(parent, bg=DIVIDER, height=1).pack(fill="x", pady=(0, 11))
        return head

    def _chip_grid(self, card, specs):
        """The split numbers as a two-across grid of cells rather than a
        column of rows.

        Six values that only mean anything together: read as a block they can
        be compared at a glance, and each one carries a RangeBar saying where
        it sits between the limits it is allowed.
        """
        wrap = tk.Frame(card.rows, bg=BG_CARD)
        wrap.pack(fill="x", padx=11, pady=(9, 2))
        wrap.grid_columnconfigure(0, weight=1, uniform="chip")
        wrap.grid_columnconfigure(1, weight=1, uniform="chip")

        for i, (label, var, unit, lo, hi) in enumerate(specs):
            cell = tk.Frame(wrap, bg=BG_CARD)
            cell.grid(row=i // 2, column=i % 2, sticky="ew", pady=(0, 7),
                      padx=((0, 6) if i % 2 == 0 else (6, 0)))
            tk.Label(cell, text=label, bg=BG_CARD, fg=FG_DIM,
                     font=(UI_FONT, 9), anchor="w").pack(anchor="w")
            box = SmallInput(cell, var, unit=unit, bg_parent=BG_CARD,
                             size=12, height=30)
            box.pack(fill="x", pady=(3, 0))
            RangeBar(cell, var, lo, hi, bg_parent=BG_CARD).pack(
                fill="x", pady=(6, 0))
        return wrap

    def _pick_ref_script(self):
        """File picker for the reference script. Best-effort: if the dialog
        cannot open for any reason the field is still typeable, which is how
        the sync-SRT path has always worked."""
        try:
            from tkinter import filedialog
            path = filedialog.askopenfilename(
                parent=self.root, title="Choose the script this was read from",
                filetypes=[("Script files", "*.docx *.txt *.srt"),
                           ("Word document", "*.docx"),
                           ("Text file", "*.txt"),
                           ("Subtitle file", "*.srt"),
                           ("All files", "*.*")])
        except Exception:
            return
        if path:
            self.ref_script_var.set(os.path.normpath(path))

    def _col_source(self, pad, defaults, items):
        # mic / volume are the two glyphs RoundedIconTile can actually draw,
        # so the source and detect groups use real icons rather than a text
        # stand-in.
        c = self._card(pad, "Where it comes from", icon=ICO_MIC,
                       summary_var=self.src_sum_var)
        self._source_first_card = c

        # Sync Existing mode's SRT is a row in this card rather than a card of
        # its own above it. It is where the input comes from, so it belongs
        # here — and a card cost 132px that had to come from somewhere, which
        # meant every group below it jumped down the page as the task switched.
        # A row costs ~40 and the groups below barely move.
        slot = self._row(
            c, "Existing SRT",
            hint="The file whose text is right but whose timing is wrong. "
                 "Its words are kept; only the timings are rebuilt.",
            stacked=True)
        PillEntry(slot, self.sync_srt_path_var,
                  placeholder="Full path to the .srt…",
                  bg_parent=BG_CARD).pack(fill="x")
        self._sync_srt_handle = slot.row_handle
        self._pick(self._row(c, "Audio track"), items, self.combo_var)
        # 16 languages plus Auto-detect is a menu taller than the window it
        # opens over, so it shows four rows and scrolls (wheel, thumb drag or
        # the arrow keys), opening with the current pick already in view.
        self._pick(self._row(c, "Language",
                             "Auto-detect follows the audio; a fixed language "
                             "pins the transcript to its script"),
                   LANGUAGES, self.lang_var, max_rows=4)

        # The script the voice-over was read from. Scribe writes what it hears,
        # so names and anything carrying a nukta come out however the model
        # guessed; a script settles it. It has to be the script in the SPOKEN
        # language — for a dubbed reel that is the translated one, not the
        # English source, which matches nothing and is reported as such.
        c = self._card(pad, "Match my script", glyph="Sc",
                       summary_var=self.script_sum_var)
        slot = self._row_full(
            c, "Script file",
            hint="Optional. .docx, .txt or .srt — your spellings and your "
                 "punctuation win wherever it matches what was said.")
        row = tk.Frame(slot, bg=BG_CARD)
        row.pack(fill="x")
        PillEntry(row, self.ref_script_var,
                  placeholder="Full path to the script…",
                  bg_parent=BG_CARD).pack(side="left", fill="x", expand=True)
        RoundedButton(row, "Browse", self._pick_ref_script,
                      bg_parent=BG_CARD, height=30).pack(side="left",
                                                         padx=(7, 0))

        c = self._card(pad, "Detect while transcribing", icon=ICO_VOLUME,
                       summary_var=self.detect_sum_var)
        self._toggle_card_row(c, "Punctuation", self.punct_var,
                              "Adds commas and full stops to the transcript")
        self._toggle_card_row(c, "Separate speakers", self.diarize_var,
                              "Colours each voice differently")

        self._source_first = self._source_first_card

    # ── Column: Timing ────────────────────────────────────────────────────
    def _col_timing(self, pad, defaults, items):
        c = self._card(pad, "How cues are split", glyph="Cu",
                       summary_var=self.split_sum_var)
        # Limits match the review screen's sliders, so a value means the same
        # thing on both screens.
        self._chip_grid(c, (
            ("Max characters", self.settings_vars[0], "chars",   8, 60),
            ("Lines per cue",  self.settings_vars[1], "lines",   1,  4),
            ("Max length",     self.settings_vars[2], "sec",     1, 12),
            ("Min length",     self.min_var,          "sec",     0,  4),
            ("Reading speed",  self.cps_var,          "cps",     8, 30),
            ("Max words",      self.words_per_var,    "0 = off", 0, 12),
        ))

        ComfortMeter(pad, self.cps_var, self.settings_vars[0],
                     bg_parent=BG).pack(fill="x", pady=(0, 10))

        c = self._card(pad, "Before it reaches the timeline", glyph="Rv",
                       summary_var=self.review_sum_var)
        self._toggle_card_row(
            c, "Review captions first", self.review_var,
            "Stop to read and edit the cues, and re-split them without "
            "transcribing again")

    def _build_presets(self, parent):
        """Named bundles of every tunable setting, saved as JSON in presets/.

        Deliberately excludes the timeline track choices: a preset should
        survive being loaded on a different timeline.
        """
        c = self._card(parent, "Presets", glyph="Pr",
                       summary_var=self.preset_sum_var)
        presets_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "presets")
        preset_map = {
            "min_secs": self.min_var, "cps": self.cps_var,
            "text_size": self.textsize_var, "lang": self.lang_var,
            "punct": self.punct_var,
            "diarize": self.diarize_var,
            "outline": self.outline_var, "shadow": self.shadow_var,
            "color": self.color_var,
            "words_per": self.words_per_var,
            "safe_zone": self.safe_zone_var, "review": self.review_var,
            "font": self.font_var, "font_style": self.font_style_var,
            "srt_posy": self.srt_posy_var, "aspect": self.aspect_var,
        }

        def _list_presets():
            try:
                return sorted(f[:-5] for f in os.listdir(presets_dir)
                              if f.endswith(".json"))
            except Exception:
                return []

        self.preset_pick_var = tk.StringVar(value="Select a preset")
        self.preset_name_var = tk.StringVar(value="")
        # One row across both columns: pick on the left of the control group,
        # name and the two verbs after it. Two stacked rows cost 110px of a
        # page that has to fit the window, for a group nobody opens twice.
        slot = self._row(
            c, "Preset",
            hint="Everything on this page except the track choices, so a "
                 "preset survives being loaded on a different timeline.")
        preset_dd = self._pick(slot, _list_presets() or ["(none saved)"],
                               self.preset_pick_var, width=176)

        def _apply_preset(name):
            if not name or name in ("Select a preset", "(none saved)"):
                return
            try:
                with open(os.path.join(presets_dir, name + ".json"),
                          encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                return
            settings = data.pop("_settings", None)
            for k, v in data.items():
                if k in preset_map:
                    try:
                        preset_map[k].set(v)
                    except Exception:
                        pass
            if settings and len(self.settings_vars) == len(settings):
                for var, val in zip(self.settings_vars, settings):
                    var.set(val)
        preset_dd.on_pick = _apply_preset

        def _save_preset():
            # No need to check for the placeholder string: PillEntry keeps the
            # hint out of the variable, so an empty box reads back as empty.
            typed = self.preset_name_var.get().strip()
            name = typed or self.preset_pick_var.get().strip()
            if not name or name in ("Select a preset", "(none saved)"):
                return
            try:
                os.makedirs(presets_dir, exist_ok=True)
                data = {k: var.get() for k, var in preset_map.items()}
                data["_settings"] = [v.get() for v in self.settings_vars]
                with open(os.path.join(presets_dir, name + ".json"),
                          "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=1)
                preset_dd.values = _list_presets()
                self.preset_pick_var.set(name)
                self.preset_name_var.set("")
            except Exception as e:
                messagebox.showerror("Srutilekha", "Cannot save preset: %s" % e)

        def _remove_preset():
            name = self.preset_pick_var.get().strip()
            try:
                path = os.path.join(presets_dir, name + ".json")
                if os.path.exists(path):
                    os.remove(path)
                preset_dd.values = _list_presets() or ["(none saved)"]
                self.preset_pick_var.set("Select a preset")
            except Exception:
                pass

        name = PillEntry(slot, self.preset_name_var, placeholder="Save as…",
                         bg_parent=BG_CARD, height=34)
        name.configure(width=150)
        name.pack(side="left", padx=(7, 0))
        RoundedButton(slot, "Save", _save_preset, primary=False,
                      bg_parent=BG_CARD, height=32).pack(side="left",
                                                         padx=(7, 0))
        RoundedButton(slot, "Remove", _remove_preset, primary=False,
                      bg_parent=BG_CARD, height=32).pack(side="left",
                                                         padx=(5, 0))

    # ── The stage: live preview + placement ───────────────────────────────
    def _build_stage(self):
        """The preview and the one control that is purely spatial.

        Every styling decision in this window is judged by eye, and the
        preview is the only control that reports whether the others are right —
        so it gets the fixed column and roughly four times the area it had.
        """
        s = self._stage
        pad = tk.Frame(s, bg=BG_OUTER)
        pad.pack(fill="both", expand=True, padx=14, pady=14)

        head = tk.Frame(pad, bg=BG_OUTER)
        head.pack(fill="x", pady=(0, 9))
        TrackedLabel(head, "Preview", bg_parent=BG_OUTER).pack(side="left")
        LivePill(head, bg_parent=BG_OUTER).pack(side="right")

        # Which frame the captions are being judged in. Size is a share of
        # frame height and placement is frame-relative, so a preview in the
        # wrong shape misreports both.
        # Two pills rather than a segmented strip: the frame is named by its
        # ratio here ("Reel 9:16"), which is the thing being chosen, and a
        # segment that wide reads as a button anyway.
        framerow = tk.Frame(pad, bg=BG_OUTER)
        framerow.pack(fill="x", pady=(0, 9))
        self._frame_btns = {}
        for name, label in (("Reel", "Reel 9:16"), ("HD", "HD 16:9")):
            b = RoundedButton(framerow, label,
                              lambda n=name: self.aspect_var.set(n),
                              primary=(self.aspect_var.get() == name),
                              bg_parent=BG_OUTER, height=26)
            b.pack(side="left", padx=(0, 5))
            self._frame_btns[name] = b

        pw = self.STAGE_W - 28
        self._preview_max_w = pw
        self._preview = ReelPreview(pad, self.srt_posy_var, self.textsize_var,
                    color_var=self.color_var,
                    outline_var=self.outline_var, shadow_var=self.shadow_var,
                    safe_zone_var=self.safe_zone_var,
                    width=pw, bg_parent=BG_OUTER,
                    aspect=self._frame()["aspect"],
                    srt_posy_default=lambda: self._frame()["srt_posy"],
                    frame_height=lambda: (self._timeline_res() or (0, 0))[1] or None)
        self._preview.pack()

        # Spec plate: the timeline on the left, the frame being previewed on
        # the right. The right half is a var now because the preview frame can
        # be switched, and because it has to say so when the two disagree —
        # designing a 16:9 caption for a 9:16 timeline is a real mistake and an
        # easy one, since every position here is frame-relative.
        res = self._timeline_res()
        left_text = ("%d x %d" % res) if res else "Timeline resolution unknown"
        self._plate_right_var = tk.StringVar(value="")
        plate = RoundedField(pad, height=26, radius=6, padx=9,
                             bg_parent=BG_OUTER, fill=BG_CARD,
                             border=BORDER)
        pbody = tk.Frame(plate, bg=BG_CARD)
        tk.Label(pbody, text=left_text, bg=BG_CARD, fg=FG_MUTE,
                 font=(FONT_NUM, 8)).pack(side="left")
        right = tk.Label(plate, textvariable=self._plate_right_var,
                         bg=BG_CARD, fg=FG_MUTE, font=(FONT_NUM, 8))
        plate.set_child(pbody, right_child=right)
        plate.pack(fill="x", pady=(8, 0))
        self._sync_frame_plate()

        # Drag inside the frame to set the subtitle height; the number itself
        # lives under Type.
        # The height is set by dragging, so the one number that describes it
        # is worth stating in words rather than leaving to be read off the
        # frame — and it says why the default sits where it does.
        self._place_var = tk.StringVar(value="")
        place = ResultCard(pad, width=self.STAGE_W - 28, bg_parent=BG_OUTER,
                           fill=BG_CARD, border=BORDER, pad=(10, 9), radius=8)
        tk.Label(place.inner, textvariable=self._place_var, bg=BG_CARD,
                 fg=FG_MUTE, font=(UI_FONT, 8), anchor="w", justify="left",
                 wraplength=self.STAGE_W - 50).pack(anchor="w")
        place.pack(fill="x", pady=(12, 0))
        try:
            self.srt_posy_var.trace_add("write", self._sync_place_note)
        except AttributeError:
            self.srt_posy_var.trace("w", self._sync_place_note)
        self._sync_place_note()

        self._safe_label_var = tk.StringVar(value="Show platform safe zone")
        safe_row = self._toggle_row_stage(pad, self._safe_label_var,
                                          self.safe_zone_var)

        # Everything in this column except the preview is chrome with a fixed
        # height; the preview is 9:16 off its own width and does not care what
        # is left. At 300px of column it asks for 484px of height, 13 more than
        # a 790px window has after the header, plate, placement row and toggle
        # — so the toggle was drawn 13px short, sliced off at the bottom edge.
        # Rather than shave paddings until it happens to fit at one window
        # size, the preview is told what it may have: it is the only thing here
        # that can give, and it stays whole and correctly proportioned at any
        # size the resize grip produces.
        self._stage_chrome = ((head, 9), (framerow, 9), (plate, 8),
                              (place, 12), (safe_row, 12))
        s.bind("<Configure>", self._fit_stage)
        self.root.after_idle(self._fit_stage)

    def _fit_stage(self, _e=None):
        """Shrink the preview to whatever the column has left over."""
        prev = getattr(self, "_preview", None)
        if prev is None or not prev.winfo_exists():
            return
        avail = self._stage.winfo_height()
        if avail <= 1:                      # not laid out yet
            return
        used = 28                           # the stage pad's own pady, top+bottom
        for widget, gap in self._stage_chrome:
            if widget is not None and widget.winfo_exists():
                used += widget.winfo_reqheight() + gap
        budget = avail - used
        if budget <= 0:
            return
        # The budget is a height. Ask for the width a 9:16 frame would need to
        # use it up — that is the tallest case, so an HD frame in the same box
        # is simply shorter and never overflows.
        prev.set_width(min(self._preview_max_w, int(budget * 9 / 16)))

    def _toggle_row_stage(self, parent, label, var):
        """Same switch row, drawn against the stage's darker void ground.

        ``label`` may be a StringVar for a caption that changes with the
        frame."""
        row = RoundedField(parent, height=42, radius=10, padx=12,
                           bg_parent=BG_OUTER, fill=BG_CARD, border=BORDER)
        body = tk.Frame(row, bg=BG_CARD)
        text_kw = ({"textvariable": label} if isinstance(label, tk.Variable)
                   else {"text": label})
        lbl = tk.Label(body, bg=BG_CARD, fg=FG_DIM,
                       font=(UI_FONT, 9), cursor="hand2", **text_kw)
        lbl.pack(side="left")
        sw = ToggleSwitch(row, var)
        sw.configure(bg=BG_CARD)
        row.set_child(body, right_child=sw)
        lbl.bind("<Button-1>", lambda e: sw._toggle())
        row.pack(fill="x", pady=(12, 0))
        return row

    # ── Generate / Sync Existing ──────────────────────────────────────────
    def _set_task(self, task):
        self.task_var.set(task)
        self._seg_gen.set_primary(task == "Generate")
        self._seg_sync.set_primary(task == "Sync Existing")
        if getattr(self, "_generate_btn", None) is not None:
            self._generate_btn.set_text(
                "Sync timing" if task == "Sync Existing" else "Generate captions")
        self._apply_task()
        self._update_summary()

    # ── Frame format ──────────────────────────────────────────────────────
    def _timeline_res(self):
        """(width, height) of the timeline, or None when none was sent.

        The wrapper reports it as "1080 x 1920" (audio_to_srt.py builds the
        string from timelineResolutionWidth/Height)."""
        for key in ("resolution", "timeline_res"):
            raw = self.prompt_data.get(key)
            if not raw:
                continue
            m = re.search(r"(\d+)\s*[x×]\s*(\d+)", str(raw))
            if m:
                w, h = int(m.group(1)), int(m.group(2))
                if w > 0 and h > 0:
                    return w, h
        return None

    def _frame_from_timeline(self):
        """Frame format to open with: the timeline's own shape when known."""
        res = self._timeline_res()
        if res is None:
            return DEFAULT_FRAME
        return "Reel" if res[1] > res[0] else "HD"

    def _frame(self):
        return FRAME_FORMATS.get(self.aspect_var.get(),
                                 FRAME_FORMATS[DEFAULT_FRAME])

    def _srt_posy_frac(self):
        """Subtitle height as a fraction up from the bottom of the frame."""
        raw = (self.srt_posy_var.get() or "").strip()
        if raw:
            try:
                return max(0.0, min(1.0, float(raw)))
            except ValueError:
                pass
        return self._frame()["srt_posy"]

    def _retune_srt_posy(self):
        """Move the subtitle height to the new frame's professional default —
        but only while it is still sitting on a default.

        Switching between a reel and an HD cut should move the subtitles,
        because the right place genuinely differs. Doing that to a height the
        user chose by hand would just be losing their work, so a value that
        matches neither default is left alone."""
        cur = (self.srt_posy_var.get() or "").strip()
        defaults = {"%.3f" % f["srt_posy"] for f in FRAME_FORMATS.values()}
        defaults |= {str(f["srt_posy"]) for f in FRAME_FORMATS.values()}
        if cur in defaults or not cur:
            self.srt_posy_var.set("%.3f" % self._frame()["srt_posy"])

    def _srt_posy_px(self):
        """That fraction in pixels, for the subtitle item's posY property.

        Returns None when the timeline resolution is unknown, which leaves the
        value in subtitle_style.json in charge exactly as before — a guess at
        the frame height would move everyone's subtitles."""
        res = self._timeline_res()
        if res is None:
            return None
        return int(round(self._srt_posy_frac() * res[1]))

    def _apply_frame(self, *_a):
        """Re-shape the preview and re-read the position defaults."""
        self._retune_srt_posy()
        prev = getattr(self, "_preview", None)
        if prev is not None and prev.winfo_exists():
            prev.set_aspect(self._frame()["aspect"])
        safe = getattr(self, "_safe_label_var", None)
        if safe is not None:
            # The overlay draws platform furniture on a reel and the broadcast
            # title-safe box on a 16:9 frame; the label has to say which.
            safe.set("Show platform safe zone" if self._frame()["aspect"] < 1
                     else "Show title-safe area")
        for name, btn in getattr(self, "_frame_btns", {}).items():
            if btn.winfo_exists():
                btn.set_primary(self.aspect_var.get() == name)
        self._sync_frame_plate()
        self._sync_place_note()
        self._update_summary()

    def _sync_place_note(self, *_a):
        """The placement sentence, with the height it is actually at."""
        var = getattr(self, "_place_var", None)
        if var is None:
            return
        frac = self._srt_posy_frac()
        if self._frame()["aspect"] < 1:
            why = ("clear of the caption and buttons Reels park along the "
                   "bottom")
        else:
            why = "the broadcast lower third, inside the title-safe margin"
        var.set("Drag inside the frame to set the baseline. Sitting at "
                "%.2f of frame height — %s." % (frac, why))

    def _sync_frame_plate(self):
        """Keep the spec plate honest about which frame is on screen."""
        var = getattr(self, "_plate_right_var", None)
        if var is None:
            return
        f = self._frame()
        bits = [f["label"]]
        res = self._timeline_res()
        tl = None
        if res is not None:
            tl = "Reel" if res[1] > res[0] else "HD"
        if tl is not None and tl != self.aspect_var.get():
            # The warning matters more than the frame rate, and the plate has
            # room for one or the other.
            bits.append("timeline %s" % FRAME_FORMATS[tl]["label"])
        elif self.prompt_data.get("fps"):
            bits.append("%s fps" % self.prompt_data["fps"])
        var.set(" · ".join(bits))

    def _apply_task(self):
        """Show the existing-SRT field only in Sync Existing mode.

        Everything else stays visible: the Resolve-side sync branch ignores the
        split settings that don't apply to re-timing an SRT that already has
        its text, so there is nothing to hide.
        """
        handle = getattr(self, "_sync_srt_handle", None)
        if handle is None:
            return
        handle.set_visible(self.task_var.get() == "Sync Existing")

        # Settle the geometry here rather than leaving it to the canvas's own
        # <Configure>, which arrives a layout pass later: the cards moved on
        # this pass and were then re-sized on the next one, so the switch was
        # visibly two steps instead of one — and a Sync → Generate round trip
        # left the columns 7px narrower than they started until some later
        # event happened to correct them.
        canvas = getattr(self, "_scroll_canvas", None)
        form_id = getattr(self, "_form_id", None)
        if canvas is not None and canvas.winfo_exists() and form_id is not None:
            canvas.update_idletasks()
            canvas.itemconfigure(form_id, width=canvas.winfo_width())
        self._sync_scrollregion()

    # ── The what-will-happen line in the action bar ───────────────────────
    def _wire_summary(self):
        # Every variable that shows up in the action bar or in a card header.
        watched = (
            self.review_var, self.combo_var,
            self.lang_var, self.task_var, self.sync_srt_path_var,
            self.punct_var, self.diarize_var,
            self.font_var, self.font_style_var,
            self.outline_var, self.shadow_var, self.color_var,
            self.textsize_var,
            self.min_var, self.cps_var, self.words_per_var,
            self.preset_pick_var, self.aspect_var, self.srt_posy_var,
        ) + tuple(self.settings_vars)
        for v in watched:
            try:
                v.trace_add("write", lambda *a: self._update_summary())
            except AttributeError:
                v.trace("w", lambda *a: self._update_summary())
        self._update_summary()

    @staticmethod
    def _n(var, default="—"):
        """A variable's value for display, or a dash when it's empty."""
        try:
            v = str(var.get()).strip()
        except Exception:
            return default
        return v or default

    def _update_card_summaries(self):
        """Recompute every card header's right-hand value."""
        # Just the language. The track is the first field in this card and is
        # always on screen, so repeating it in the header only costs the room
        # the language needs. In Sync mode the SRT is the thing you chose, so
        # the header names that instead.
        if self.task_var.get() == "Sync Existing":
            self.src_sum_var.set(
                os.path.basename(self.sync_srt_path_var.get().strip())
                or "no file chosen")
        else:
            self.src_sum_var.set(self.lang_var.get())
        on = sum(int(bool(v.get())) for v in
                 (self.punct_var, self.diarize_var))
        # A count, not words: the header is a column wide now, and "both on"
        # was arriving as "both…", which says less than nothing.
        self.detect_sum_var.set("%d/2" % on)
        ref = self.ref_script_var.get().strip()
        self.script_sum_var.set(os.path.basename(ref) if ref else "None")

        # chars / lines / cps, in the order the cells are read.
        self.split_sum_var.set("%s / %s / %s" % (
            self._n(self.settings_vars[0]), self._n(self.settings_vars[1]),
            self._n(self.cps_var)))
        self.review_sum_var.set("on" if self.review_var.get() else "off")
        pick = self.preset_pick_var.get()
        self.preset_sum_var.set(
            "" if pick in ("Select a preset", "(none saved)") else pick)

    def _update_summary(self):
        """One line stating what pressing the primary button will do.

        The old form made you read four columns to work this out.
        """
        if getattr(self, "summary_var", None) is None:
            return
        try:
            self._update_card_summaries()
        except Exception:
            pass
        try:
            if self.task_var.get() == "Sync Existing":
                srt = self.sync_srt_path_var.get().strip()
                if srt:
                    bits = ["Re-time %s against %s"
                            % (os.path.basename(srt), self.combo_var.get())]
                else:
                    bits = ["Choose the SRT to re-time against %s"
                            % self.combo_var.get()]
            else:
                bits = ["%s · %s → a subtitle track"
                        % (self.combo_var.get(), self.lang_var.get())]
            bits.append("review first" if self.review_var.get()
                        else "applied straight away")
            self.summary_var.set("  ·  ".join(bits))
        except Exception:
            pass

    def _on_submit(self, action="generate"):
        chosen = self.combo_var.get()
        if action in ("generate", "sync") and not chosen:
            return
        if action == "sync" and not self.sync_srt_path_var.get().strip():
            messagebox.showerror("Srutilekha",
                                 "Enter the path to the existing SRT to sync.")
            return
        # Never send an empty field in the comma-joined settings triple. The old Lua
        # side splits it with "[^,]+", which SKIPS empty fields rather than
        # yielding a blank one — so a cleared "Lines per cue" box turned
        # "25,,2" into maxChars=25, maxLines=2, maxSecs=1 (its own fallback) and
        # silently ran with settings the user never chose. Substituting the
        # documented default here keeps the positions meaningful and keeps the
        # worker in step with what the review screen's _split_settings assumes.
        settings = ",".join(
            v.get().strip() or d
            for v, d in zip(self.settings_vars, self.SETTINGS_DEFAULTS))
        lang = self.lang_var.get()
        sel = {
            "action":   action,
            "chosen":   chosen,
            "srt_input_path": self.sync_srt_path_var.get().strip(),
            "settings": settings,
            "punct":    int(self.punct_var.get()),
            "lang":     lang,
            "lang_code": LANGUAGE_CODES.get(lang, "auto"),
            "diarize":  int(self.diarize_var.get()),
            "min_secs": self.min_var.get().strip() or "0",
            "cps":      self.cps_var.get().strip() or "0",
            "text_size": self.textsize_var.get().strip() or "55",
            "outline":  int(self.outline_var.get()),
            "shadow":   int(self.shadow_var.get()),
            "color":    self.color_var.get().strip(),
            "words_per": self.words_per_var.get().strip() or "0",
            "ref_script": self.ref_script_var.get().strip(),
            "review":    int(self.review_var.get()),
            "font":     self.font_var.get().strip(),
            "font_style": self.font_style_var.get().strip() or "Auto",
        }
        # Where subtitles sit, in pixels for the subtitle item's posY. Computed
        # here rather than in the Resolve-side script because this side knows
        # both the chosen fraction and the frame it was chosen against. Omitted
        # entirely when the timeline resolution is unknown, which leaves
        # subtitle_style.json in charge — the previous behaviour, and better
        # than scaling a fraction by a frame height nobody reported.
        srt_posy_px = self._srt_posy_px()
        if srt_posy_px is not None:
            sel["srt_posy"] = str(srt_posy_px)
        # One subtitle font per script, resolved against the fonts installed on
        # this machine.
        fonts = encode_subtitle_fonts(resolve_subtitle_fonts())
        if fonts:
            sel["srt_fonts"] = fonts
        # Write to a scratch file and rename it into place. The Resolve side
        # polls for this file every 150 ms and starts parsing the moment it can
        # read "chosen" and "settings" — fields 2 and 4 — so a
        # partially-flushed write let it proceed with every later field
        # (caption_style, lang_code, diarize …) silently falling back to a
        # default. os.replace is atomic on both platforms: the poller sees the
        # whole file or no file.
        try:
            tmp = self.selection_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(sel, f)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.selection_path)
        except Exception as e:
            messagebox.showerror("Srutilekha",
                                 "Cannot write selection file: %s" % e)
            return
        # Past this point the Resolve-side script is working on our behalf:
        # stop the supersede watchdog so a later launch can't pull the rug out.
        self._submitted = True
        self.root.unbind("<Return>")
        self.root.unbind("<Escape>")
        try:
            # bind_all, so it outlives the canvas it scrolls unless dropped.
            self.root.unbind_all("<MouseWheel>")
        except Exception:
            pass
        if action == "undo":
            # No transcription: the Resolve-side script removes the last track
            # it made and writes the result file when done.
            title = "Undoing"
            busy = "Removing the last caption track…"
            self._build_progress(title)
            self._set_progress(60, busy)
            self.root.after(30, self._animate_bar)
            self.root.after(300, self._poll_result_update)
            return
        self._build_progress(
            "Re-timing an existing SRT" if action == "sync"
            else "Transcribing audio",
            stages=self.SYNC_STAGES if action == "sync" else self.GEN_STAGES)
        threading.Thread(target=self._wait_for_args_and_run,
                         daemon=True).start()
        self.root.after(50, self._pump)
        self.root.after(30, self._animate_bar)

    # How long to wait for the Resolve-side half to write its result file
    # before giving up. Reached only when the Resolve-side script is no longer
    # there to write one — Resolve closed, the script errored out, or a newer
    # run superseded it. The old code polled forever, leaving the window pinned
    # at "Importing subtitles… 100%" with no way to learn that nothing was
    # coming.
    RESULT_TIMEOUT = 600.0

    def _poll_result_update(self):
        if self.cancelled:
            return
        if os.path.exists(self.result_path):
            self.exit_code = 0
            try:
                with open(self.result_path, "r", encoding="utf-8") as f:
                    msg = f.read().strip()
            except Exception:
                msg = "Done."
            self._build_done(msg)
            return
        if self._result_timed_out():
            self.exit_code = 1
            self._build_done(
                "DaVinci Resolve never reported back.\n\n"
                "The Srutilekha script is no longer running there — it may have "
                "been stopped, or Resolve was closed. Nothing was changed on "
                "the timeline. Start the script again from Workspace ▸ Scripts.")
            return
        self.root.after(250, self._poll_result_update)

    def _result_timed_out(self):
        """True once RESULT_TIMEOUT has passed since the wait began."""
        started = getattr(self, "_result_wait_start", None)
        if started is None:
            self._result_wait_start = time.monotonic()
            return False
        return (time.monotonic() - started) > self.RESULT_TIMEOUT

    def _kill_worker(self):
        """Stop transcribe.py if it is still running.

        terminate() first, then kill() if it ignores that — the worker spends
        most of its life inside a blocking HTTPS upload, which will not notice a
        polite request. Closing stdout as well so the reader thread's `for line
        in proc.stdout` cannot sit there holding the pipe open.
        """
        with self._proc_lock:
            proc, self._proc = self._proc, None
        if proc is None or proc.poll() is not None:
            return
        for stop in (proc.terminate, proc.kill):
            try:
                stop()
                proc.wait(timeout=3)
                break
            except Exception:
                continue
        try:
            if proc.stdout:
                proc.stdout.close()
        except Exception:
            pass

    def _on_cancel(self):
        self.cancelled = True
        # Before the sentinels: the Resolve-side script reacts to done_path
        # immediately, and a worker still uploading would keep spending money
        # after the window and the Resolve-side script have both moved on.
        self._kill_worker()
        try:
            with open(self.done_path, "w", encoding="utf-8") as f:
                f.write("130")
        except Exception:
            pass
        try:
            with open(self.ack_path, "w", encoding="utf-8") as f:
                f.write("cancel")
        except Exception:
            pass
        self.root.destroy()

    # ── Phase 2: progress ─────────────────────────────────────────────────
    # Stage thresholds mirror the _progress() calls in transcribe.py. Keep them
    # in step with that file: the stage a run is in is derived from the
    # percentage the worker reports, while the sentence beside the percentage is
    # whatever the worker actually said.
    GEN_STAGES = (("Preparing", 0), ("Transcribing", 40),
                  ("Building subtitles", 80), ("Finalising", 95))
    SYNC_STAGES = (("Preparing", 0), ("Transcribing for alignment", 40),
                   ("Writing synced SRT", 90))

    def _build_progress(self, title="Transcribing audio", stages=None):
        self._clear_body()
        self.subtitle_var.set(title)

        header = tk.Frame(self.body, bg=BG)
        header.pack(fill="x")
        htext = tk.Frame(header, bg=BG)
        htext.pack(side="left", anchor="w")
        title_lbl = tk.Label(htext, text="Srutilekha", bg=BG, fg=FG,
                             font=(UI_FONT, 11, "bold"))
        title_lbl.pack(anchor="w")
        sub_lbl = tk.Label(htext, text=title, bg=BG, fg=FG_MUTE,
                           font=(UI_FONT, 9))
        sub_lbl.pack(anchor="w")
        for w in (header, htext, title_lbl, sub_lbl):
            self._make_draggable(w)

        # The window is sized for the form, so the progress block is centred in
        # the leftover space rather than stranded under the header.
        outer = tk.Frame(self.body, bg=BG)
        outer.pack(expand=True, fill="both")
        wrap = tk.Frame(outer, bg=BG)
        wrap.place(relx=0.5, rely=0.42, anchor="center", relwidth=1.0)

        # Percentage and the worker's own message, on one baseline.
        top = tk.Frame(wrap, bg=BG)
        top.pack(fill="x")
        self.pct_var = tk.StringVar(value="0%")
        tk.Label(top, textvariable=self.pct_var, bg=BG, fg=SELECT,
                 font=(FONT_NUM, 30, "bold")).pack(side="left")
        self.status_var = tk.StringVar(value="Preparing…")
        tk.Label(top, textvariable=self.status_var, bg=BG, fg=FG_DIM,
                 font=(UI_FONT, 10), anchor="w").pack(
            side="left", padx=(14, 0), pady=(12, 0))

        self.pct = tk.DoubleVar(value=0.0)
        ttk.Progressbar(
            wrap, orient="horizontal", mode="determinate",
            maximum=100, variable=self.pct,
            style="SubSync.Horizontal.TProgressbar",
        ).pack(fill="x", pady=(14, 0))

        # Named stages: one bar and a changing sentence can't tell you which
        # part of a run is slow, or where it stopped when it stops.
        self._stages = None
        if stages:
            GradientDivider(wrap, height=1, bg_parent=BG).pack(
                fill="x", pady=(22, 18))
            self._stages = StageList(wrap, stages, bg_parent=BG)
            self._stages.pack(fill="x")

        self.detail_var = tk.StringVar(value="")
        tk.Label(wrap, textvariable=self.detail_var, bg=BG, fg=FG_MUTE,
                 font=(UI_FONT, 8), anchor="w").pack(anchor="w",
                                                       pady=(10, 0))

    def _set_progress(self, pct, msg):
        try:
            pct = float(pct)
        except (TypeError, ValueError):
            return
        pct = max(0.0, min(100.0, pct))
        self._anim_target = pct
        self.pct_var.set("%d%%" % int(round(pct)))
        if msg:
            self.status_var.set(msg)
        stages = getattr(self, "_stages", None)
        if stages is not None:
            stages.set_pct(pct)

    def _animate_bar(self):
        # Smoothly interpolate the visible bar toward the target percentage.
        if self._anim_value < self._anim_target:
            self._anim_value += max(0.4, (self._anim_target - self._anim_value) * 0.18)
            if self._anim_value > self._anim_target:
                self._anim_value = self._anim_target
            self.pct.set(self._anim_value)
        elif self._anim_value > self._anim_target:
            self._anim_value = self._anim_target
            self.pct.set(self._anim_value)
        if self.exit_code is None:
            self.root.after(30, self._animate_bar)

    # ── Phase 3: done ─────────────────────────────────────────────────────
    def _poll_result(self):
        if self.cancelled:
            return
        if os.path.exists(self.result_path):
            try:
                with open(self.result_path, "r", encoding="utf-8") as f:
                    msg = f.read().strip()
            except Exception:
                msg = "Done."
            self._build_done(msg)
            return
        if self._result_timed_out():
            self._build_done(
                "The subtitles were written, but DaVinci Resolve never "
                "reported back.\n\nThe Srutilekha script is no longer running "
                "there — it may have been stopped, or Resolve was closed. "
                "Start the script again from Workspace ▸ Scripts.")
            return
        self.root.after(200, self._poll_result)

    def _build_done(self, message):
        self._clear_body()

        header = tk.Frame(self.body, bg=BG)
        header.pack(fill="x")
        title_lbl = tk.Label(header, text="Srutilekha", bg=BG, fg=FG,
                             font=(UI_FONT, 11, "bold"))
        title_lbl.pack(side="left")
        for w in (header, title_lbl):
            self._make_draggable(w)

        # Same centred block as the progress screen, so finishing a run doesn't
        # jump the content to a different part of the window.
        outer = tk.Frame(self.body, bg=BG)
        outer.pack(expand=True, fill="both")
        block = tk.Frame(outer, bg=BG)
        block.place(relx=0.5, rely=0.42, anchor="center", relwidth=1.0)

        # Centred, unlike the progress screen's full-width block: the card is a
        # discrete object in an otherwise empty window, and left-aligning it
        # strands it against one edge.
        card = ResultCard(block, bg_parent=BG)
        card.pack(anchor="center")
        self._fill_done_card(card.inner, message)

        btn_frm = tk.Frame(self.body, bg=BG)
        btn_frm.pack(fill="x", side="bottom")
        RoundedButton(btn_frm, "Close", self._on_ok_done, primary=True,
                      bg_parent=BG, height=38).pack(side="right")
        self.root.bind("<Return>", lambda e: self._on_ok_done())
        self.root.bind("<Escape>", lambda e: self._on_ok_done())

    # Resolve reports a run back as one blob of text: a headline, sometimes a
    # warning line or two, then "Timeline: <name>" and "Project saved.". Poured
    # into a single grey Label that reads as a paragraph you have to parse
    # yourself. The pieces play different roles, so they are set differently —
    # the headline bright, warnings dotted in amber, the facts as label/value
    # rows under a hairline.
    @staticmethod
    def _done_meta(line):
        """('Timeline', 'Timeline 1') for a "Label: value" line, else None."""
        label, sep, value = line.partition(":")
        label, value = label.strip(), value.strip()
        if not sep or not label or not value:
            return None
        if len(label) > 18 or len(value) > 80 or not label[0].isalpha():
            return None
        if any(c in label for c in ".,;()"):
            return None
        return label, value

    @staticmethod
    def _wrap_label(parent, text, fg, size, bg=BG_CARD):
        """Label that re-wraps to whatever width it is handed.

        The card is one fixed width today, but a hard-coded wraplength has to be
        kept in step with it by hand and silently overflows when it isn't.
        """
        lbl = tk.Label(parent, text=text, bg=bg, fg=fg, justify="left",
                       anchor="w", font=(UI_FONT, size))
        lbl.bind("<Configure>",
                 lambda e, l=lbl: l.configure(wraplength=max(140, e.width - 2)))
        return lbl

    def _fill_done_card(self, parent, message):
        lines = [ln.strip() for ln in (message or "").splitlines()]
        lines = [ln for ln in lines if ln]
        headline = lines[0] if lines else "Done."

        body, meta, saved = [], [], False
        for ln in lines[1:]:
            if ln.rstrip(".").lower() == "project saved":
                saved = True
                continue
            kv = self._done_meta(ln)
            if kv:
                meta.append(kv)
            else:
                body.append(ln)

        head = tk.Frame(parent, bg=BG_CARD)
        head.pack(fill="x")
        tick = tk.Canvas(head, width=22, height=22, bg=BG_CARD,
                         highlightthickness=0, bd=0)
        tick.create_oval(1, 1, 21, 21, fill=GOOD, outline=GOOD)
        tick.create_line(6.5, 11.5, 9.5, 15, fill=ACCENT_INK, width=2,
                         capstyle="round")
        tick.create_line(9.5, 15, 15.5, 7, fill=ACCENT_INK, width=2,
                         capstyle="round")
        tick.pack(side="left", padx=(0, 11))
        tk.Label(head, text="Done", bg=BG_CARD, fg=FG,
                 font=(UI_FONT, 15, "bold")).pack(side="left")

        self._wrap_label(parent, headline, FG, 11).pack(fill="x", pady=(14, 0))

        for ln in body:
            low = ln.lower()
            warn = ("could not" in low or "unavailable" in low
                    or "never reported" in low)
            detail = ln.startswith("(")          # the raw error behind a warning
            row = tk.Frame(parent, bg=BG_CARD)
            row.pack(fill="x", pady=(8, 0))
            dot = tk.Canvas(row, width=7, height=15, bg=BG_CARD,
                            highlightthickness=0, bd=0)
            if warn:
                dot.create_oval(0, 5, 6, 11, fill=ACCENT, outline="")
            dot.pack(side="left", padx=(1, 9), anchor="n")
            self._wrap_label(row, ln, FG_MUTE if detail else FG_DIM,
                             8 if detail else 10).pack(side="left", fill="x",
                                                       expand=True)

        if meta or saved:
            tk.Frame(parent, bg=DIVIDER, height=1).pack(fill="x",
                                                        pady=(17, 13))
        for label, value in meta:
            row = tk.Frame(parent, bg=BG_CARD)
            row.pack(fill="x", pady=(0, 6))
            tk.Label(row, text=label, bg=BG_CARD, fg=FG_MUTE, width=11,
                     anchor="w", font=(UI_FONT, 9)).pack(side="left")
            tk.Label(row, text=value, bg=BG_CARD, fg=FG, anchor="w",
                     font=(UI_FONT, 9)).pack(side="left", fill="x",
                                                expand=True)
        if saved:
            row = tk.Frame(parent, bg=BG_CARD)
            row.pack(fill="x", pady=(2, 0))
            mark = tk.Canvas(row, width=13, height=13, bg=BG_CARD,
                             highlightthickness=0, bd=0)
            mark.create_line(1, 7, 4.5, 10.5, fill=GOOD, width=2,
                             capstyle="round")
            mark.create_line(4.5, 10.5, 12, 2, fill=GOOD, width=2,
                             capstyle="round")
            mark.pack(side="left", padx=(0, 9))
            tk.Label(row, text="Project saved", bg=BG_CARD, fg=FG_DIM,
                     font=(UI_FONT, 9)).pack(side="left")

    def _on_ok_done(self):
        try:
            with open(self.ack_path, "w", encoding="utf-8") as f:
                f.write("ok")
        except Exception:
            pass
        self.root.destroy()

    # ── Worker plumbing ───────────────────────────────────────────────────
    def _wait_for_args_and_run(self):
        # The Resolve side writes the args file after reading our selection. 10
        # min cap.
        deadline = time.time() + 600
        while time.time() < deadline:
            if self.cancelled:
                return
            if os.path.exists(self.args_path):
                break
            time.sleep(0.2)
        else:
            self.q.put(("error", "Timed out waiting for args."))
            self.q.put(("exit", 1))
            return
        self._run_transcribe()

    def _run_transcribe(self):
        try:
            log_dir = os.path.dirname(self.log_path)
            if log_dir and not os.path.isdir(log_dir):
                os.makedirs(log_dir, exist_ok=True)
            log_f = open(self.log_path, "w", encoding="utf-8", errors="replace")
        except Exception as e:
            self.q.put(("error", "Cannot open log file: %s" % e))
            self.q.put(("exit", 1))
            return

        creationflags = 0
        startupinfo = None
        if os.name == "nt":
            creationflags = CREATE_NO_WINDOW
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0  # SW_HIDE

        cmd = [self.python_exe, self.script_path,
               "--args-file", self.args_path]
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                bufsize=1,
                universal_newlines=True,
                encoding="utf-8",
                errors="replace",
                creationflags=creationflags,
                startupinfo=startupinfo,
            )
        except Exception as e:
            log_f.write("ERROR: failed to launch worker: %s\n" % e)
            log_f.close()
            self.q.put(("error", "Failed to launch worker: %s" % e))
            self.q.put(("exit", 1))
            return

        # Publish the handle so Cancel can kill it. If the user cancelled while
        # we were starting up, stop it right back down again.
        with self._proc_lock:
            self._proc = proc
        if self.cancelled:
            self._kill_worker()
            log_f.close()
            return

        try:
            for line in proc.stdout:
                log_f.write(line)
                log_f.flush()
                s = line.strip()
                if s.startswith("PROGRESS|"):
                    parts = s.split("|", 2)
                    if len(parts) >= 2:
                        pct = parts[1]
                        msg = parts[2] if len(parts) >= 3 else ""
                        self.q.put(("progress", pct, msg))
        except Exception:
            pass          # pipe closed under us by _kill_worker

        try:
            proc.wait(timeout=10)
        except Exception:
            pass
        log_f.close()
        with self._proc_lock:
            self._proc = None
        # A cancelled run has already written its own 130; queueing the killed
        # worker's exit code here would race that and be read as a failure.
        if not self.cancelled:
            self.q.put(("exit", proc.returncode))

    def _pump(self):
        try:
            while True:
                evt = self.q.get_nowait()
                kind = evt[0]
                if kind == "progress":
                    self._set_progress(evt[1], evt[2])
                elif kind == "error":
                    self._set_progress(100, evt[1])
                elif kind == "exit":
                    self.exit_code = evt[1]
                    # Optional review/edit pass before the Resolve-side script
                    # applies captions. Never for Sync mode: its args file has
                    # a different layout (SYNC sentinel + audio/srt-in/srt-out
                    # paths, no .cap sidecar), so
                    # _transcribe_paths()/_review_available() would misread it.
                    if (evt[1] == 0 and int(self.review_var.get())
                            and self.task_var.get() != "Sync Existing"
                            and self._review_available()):
                        self._begin_review()
                    else:
                        self._finish_after_transcribe(evt[1])
                    return
        except queue.Empty:
            pass
        self.root.after(50, self._pump)

    def _finish_after_transcribe(self, code):
        """Signal the waiting Resolve-side script (via done_path) and either
        poll for the result (success) or close (failure/cancel)."""
        try:
            with open(self.done_path, "w", encoding="utf-8") as f:
                f.write(str(code))
        except Exception:
            pass
        if code == 0:
            self._set_progress(100, "Importing subtitles…")
            self.detail_var.set("")
            self.root.after(200, self._poll_result)
        else:
            self.root.after(450, self.root.destroy)

    # ── Caption review / edit ─────────────────────────────────────────────
    def _transcribe_paths(self):
        """(srt_path, cap_path) read from the args file the Resolve-side
        script wrote, or (None, None) if unreadable."""
        try:
            with open(self.args_path, encoding="utf-8") as f:
                lines = [ln.rstrip("\r\n") for ln in f]
            srt = lines[1]
            return srt, srt + ".cap"
        except Exception:
            return None, None

    def _review_available(self):
        srt, _ = self._transcribe_paths()
        return bool(srt) and os.path.exists(srt)

    @staticmethod
    def _fmt_ts(sec):
        if sec < 0:
            sec = 0.0
        ms = int(round(sec * 1000))
        h, ms = divmod(ms, 3600000)
        m, ms = divmod(ms, 60000)
        s, ms = divmod(ms, 1000)
        return "%02d:%02d:%02d,%03d" % (h, m, s, ms)

    def _parse_cap(self, cap_path):
        """Parse the .cap sidecar into (header_lines, segments). Each segment:
        {s, e, spk, words:[(ws, we, text)], text}."""
        header, segs, cur = [], [], None
        try:
            with open(cap_path, encoding="utf-8") as f:
                for line in f:
                    line = line.rstrip("\n")
                    if line.startswith("FPS ") or line.startswith("SPK "):
                        header.append(line)
                    elif line.startswith("SEG "):
                        parts = line.split(None, 3)
                        s = float(parts[1]); e = float(parts[2])
                        spk = int(parts[3]) if len(parts) > 3 else 0
                        cur = {"s": s, "e": e, "spk": spk, "words": []}
                        segs.append(cur)
                    elif line.startswith("WRD ") and cur is not None:
                        parts = line.split(None, 3)
                        ws = float(parts[1]); we = float(parts[2])
                        txt = parts[3] if len(parts) > 3 else ""
                        cur["words"].append((ws, we, txt))
        except Exception:
            return [], []
        for seg in segs:
            seg["text"] = " ".join(w[2] for w in seg["words"])
        return header, segs

    def _write_srt_cap(self, srt_path, cap_path, header, segs):
        """Rewrite the SRT + .cap from edited segments. When a segment's text
        changed, its per-word timing is redistributed evenly across the
        segment so animated (karaoke) captions still line up."""
        # SRT (dummy t=0 entry keeps Resolve anchored to timeline start).
        srt = ["1\n00:00:00,000 --> 00:00:00,001\n \n"]
        for i, seg in enumerate(segs, start=1):
            srt.append("%d\n%s --> %s\n%s\n" % (
                i + 1, self._fmt_ts(seg["s"]), self._fmt_ts(seg["e"]),
                seg["text"]))
        with open(srt_path, "w", encoding="utf-8") as f:
            f.write("\n".join(srt))

        cap = list(header)
        for seg in segs:
            cap.append("SEG %.3f %.3f %d" % (seg["s"], seg["e"], seg["spk"]))
            orig = " ".join(w[2] for w in seg["words"])
            new_words = seg["text"].split()
            if seg["text"].strip() == orig.strip() and seg["words"]:
                for ws, we, txt in seg["words"]:
                    cap.append("WRD %.3f %.3f %s" % (ws, we, txt))
            elif new_words:
                # redistribute timing evenly across the segment duration
                n = len(new_words)
                span = max(0.001, seg["e"] - seg["s"])
                step = span / n
                for j, wtok in enumerate(new_words):
                    ws = seg["s"] + j * step
                    we = seg["s"] + (j + 1) * step
                    cap.append("WRD %.3f %.3f %s" % (ws, we, wtok))
        with open(cap_path, "w", encoding="utf-8") as f:
            f.write("\n".join(cap) + "\n")

    def _begin_review(self):
        srt_path, cap_path = self._transcribe_paths()
        header, segs = self._parse_cap(cap_path)
        if not segs:
            # No sidecar (shouldn't happen) — skip review, apply as-is.
            self._finish_after_transcribe(0)
            return
        self._build_review(srt_path, cap_path, header, segs)

    # ── Live re-split helpers ─────────────────────────────────────────────
    # The .cap sidecar already holds every word with its final timeline timing,
    # so re-splitting into different cues (new max chars / lines / CPS / max
    # secs / max words) is a purely local operation — the transcript is reused,
    # nothing is re-transcribed and no API is called. This is what makes the
    # split sliders in the review screen update instantly.
    @staticmethod
    def _parse_spk_colors(header):
        """{speaker_index: '#hex'} from the .cap SPK header lines."""
        colors = {}
        for line in header:
            if line.startswith("SPK "):
                parts = line.split(None, 3)
                if len(parts) >= 3:
                    try:
                        colors[int(parts[1])] = parts[2]
                    except ValueError:
                        pass
        return colors

    def _flatten_words(self, segs):
        """Flat list of transcribe._Word across all segments, each tagged with
        its segment's speaker index — the raw material re-splitting works on."""
        import transcribe as _T
        words = []
        for seg in segs:
            spk = seg.get("spk", 0)
            for ws, we, txt in seg["words"]:
                words.append(_T._Word(txt, ws, we, spk if spk else None))
        return words

    def _split_settings(self):
        """Current split settings from the form vars, with safe fallbacks."""
        def _i(var, d):
            try:
                return int(float(var.get()))
            except (ValueError, AttributeError):
                return d
        def _f(var, d):
            try:
                return float(var.get())
            except (ValueError, AttributeError):
                return d
        d0, d1, d2 = self.SETTINGS_DEFAULTS
        return {
            "max_chars": max(1, _i(self.settings_vars[0], int(d0))),
            "max_lines": max(1, _i(self.settings_vars[1], int(d1))),
            "max_secs":  max(0.1, _f(self.settings_vars[2], float(d2))),
            "cps":       max(0.0, _f(self.cps_var, 25.0)),
            "min_dur":   max(0.0, _f(self.min_var, 0.4)),
            "max_words": max(0, _i(self.words_per_var, 0)),
            "lang":      LANGUAGE_CODES.get(self.lang_var.get(), "auto"),
        }

    def _resplit_segments(self):
        """Regroup the cached words into segment dicts using the current split
        settings. Pure/local — never touches the network."""
        import transcribe as _T
        s = self._split_settings()
        cues = _T.build_cues(self._review_words, s["max_chars"], s["max_lines"],
                             s["max_secs"], include_punct="1", cps=s["cps"],
                             max_words=s["max_words"], lang=s["lang"])
        cues = _T._sanitize_cues(cues, read_dur=s["min_dur"])
        segs = []
        for _idx, cs, ce, text, words in cues:
            spk = 0
            for w in words:
                if len(w) > 3 and w[3]:
                    spk = w[3]
                    break
            segs.append({"s": cs, "e": ce, "spk": spk,
                         "words": [(w[1], w[2], w[0]) for w in words],
                         "text": text})
        return segs, s

    # Fields that drive the live cut: (label, var, lo, hi, step, fmt).
    def _split_field_specs(self):
        return (
            ("Max characters", self.settings_vars[0],  8, 60, 1,   "%d"),
            ("Lines per cue",  self.settings_vars[1],  1,  4, 1,   "%d"),
            ("Max seconds",    self.settings_vars[2], 0.5, 8, 0.1, "%.1f"),
            ("CPS limit",      self.cps_var,           0, 40, 1,   "%d"),
            ("Min duration",   self.min_var,           0,  3, 0.1, "%.1f"),
            ("Max words",      self.words_per_var,     0, 12, 1,   "%d"),
        )

    def _build_review(self, srt_path, cap_path, header, segs):
        self._clear_body()
        self.root.unbind("<Return>")

        self._srt_path = srt_path
        self._cap_path = cap_path
        self._review_header = header
        self._spk_colors = self._parse_spk_colors(header)
        self._review_words = self._flatten_words(segs)
        self._resplit_after = None
        self._sel_desc = None

        # ── Header: title + subtitle, with the "live" pill on the right ──────
        # Right padding clears the frameless window's own min/max/close
        # buttons, which sit placed over the root at the top-right corner
        # (TitleBarControls: 3 × 46px wide) — without it the pill runs in
        # underneath them.
        head = tk.Frame(self.body, bg=BG)
        head.pack(fill="x", pady=(0, 10), padx=(0, TitleBarControls.BTN_W * 3 - 22))
        htxt = tk.Frame(head, bg=BG)
        htxt.pack(side="left", anchor="w")
        tk.Label(htxt, text="Review & split", bg=BG, fg=FG,
                 font=(UI_FONT, 16, "bold")).pack(anchor="w")
        tk.Label(htxt, text="Drag any value to re-cut instantly — the "
                 "transcript is reused, nothing is re-transcribed.",
                 bg=BG, fg=FG_MUTE, font=(UI_FONT, 9),
                 wraplength=560, justify="left").pack(anchor="w")
        self._live_pill(head).pack(side="right", anchor="n", pady=(2, 0))
        for w in (head, htxt, *htxt.winfo_children()):
            self._make_draggable(w)
        GradientDivider(self.body, height=1, bg_parent=BG).pack(
            fill="x", pady=(0, 12))

        # ── Bottom action bar (packed first so it can never be clipped) ──────
        bar = tk.Frame(self.body, bg=BG)
        bar.pack(fill="x", side="bottom", pady=(12, 0))
        bar.grid_columnconfigure(0, weight=1, uniform="rv")
        bar.grid_columnconfigure(1, weight=2, uniform="rv")
        RoundedButton(bar, "Cancel", self._on_cancel, primary=False,
                      bg_parent=BG, height=40).grid(row=0, column=0,
                                                    sticky="ew", padx=(0, 5))
        RoundedButton(bar, "Apply captions",
                      lambda: self._apply_review(srt_path, cap_path, header),
                      primary=True, bg_parent=BG, height=40).grid(
            row=0, column=1, sticky="ew", padx=(5, 0))

        # ── Three columns: split controls · cue cards · live preview ─────────
        mid = tk.Frame(self.body, bg=BG)
        mid.pack(fill="both", expand=True)

        # LEFT — split controls (slider + linked number box per value).
        left = tk.Frame(mid, bg=BG, width=238)
        left.pack(side="left", fill="y", padx=(0, 14))
        left.pack_propagate(False)
        tk.Label(left, text="S P L I T", bg=BG, fg=FG_LABEL,
                 font=(UI_FONT, 8, "bold")).pack(anchor="w", pady=(2, 8))
        for spec in self._split_field_specs():
            self._build_split_field(left, *spec)

        # RIGHT — the reel preview of the selected cue, and the inspector that
        # reads its numbers back. One selection drives the waveform window, the
        # preview frame and these figures, so the three never disagree.
        right = tk.Frame(mid, bg=BG, width=214)
        right.pack(side="right", fill="y", padx=(14, 2))
        right.pack_propagate(False)
        tk.Label(right, text="P R E V I E W", bg=BG, fg=FG_LABEL,
                 font=(UI_FONT, 8, "bold")).pack(anchor="w", pady=(2, 8))
        self._review_preview = ReelPreview(
            right, self.srt_posy_var, self.textsize_var,
            color_var=self.color_var, outline_var=self.outline_var,
            shadow_var=self.shadow_var, safe_zone_var=self.safe_zone_var,
            width=182, bg_parent=BG,
            srt_posy_default=lambda: self._frame()["srt_posy"],
            frame_height=lambda: (self._timeline_res() or (0, 0))[1] or None)
        self._review_preview.pack(anchor="n")
        GradientDivider(right, height=1, bg_parent=BG).pack(
            fill="x", pady=(12, 10))
        self._build_inspector(right)

        # CENTER — the waveform strip over the scrollable cue cards, with the
        # run's totals pinned underneath.
        center = tk.Frame(mid, bg=BG)
        center.pack(side="left", fill="both", expand=True)

        self._review_status = tk.StringVar(value="")
        foot = tk.Frame(center, bg=BG)
        foot.pack(side="bottom", fill="x", pady=(8, 0))
        tk.Label(foot, textvariable=self._review_status, bg=BG, fg=FG_MUTE,
                 font=(UI_FONT, 8), justify="left").pack(side="left")
        tk.Label(foot, text="Enter splits · ⤵ merges · ✕ deletes",
                 bg=BG, fg=FG_LABEL, font=(UI_FONT, 8)).pack(side="right")

        # Created now, packed only once an envelope actually decodes — see
        # _waveform_ready. Without ffmpeg there is no strip at all.
        self._wave = WaveformStrip(center, on_seek=self._seek_review,
                                   bg_parent=BG)
        self._wave_shown = False

        body = tk.Frame(center, bg=BG)
        body.pack(side="top", fill="both", expand=True)
        self._review_body = body
        canvas = tk.Canvas(body, bg=BG, highlightthickness=0, bd=0)
        vsb = SlimScrollbar(body, canvas.yview, width=6)
        canvas.configure(yscrollcommand=vsb.set)
        canvas.pack(side="left", fill="both", expand=True, padx=(0, 6))
        vsb.pack(side="right", fill="y", padx=(6, 2))
        lst = tk.Frame(canvas, bg=BG)
        lst_id = canvas.create_window((0, 0), window=lst, anchor="nw")
        canvas.bind("<Configure>",
                    lambda e: canvas.itemconfigure(lst_id, width=e.width))
        self._review_lst = lst
        self._review_canvas = canvas

        def _sync(_e=None):
            if not canvas.winfo_exists():
                return
            canvas.configure(scrollregion=canvas.bbox("all"))
        lst.bind("<Configure>", _sync)
        self._review_sync = _sync

        def _wheel(e):
            if not canvas.winfo_exists():
                return
            first, last = canvas.yview()
            if last - first >= 1.0:      # all cards visible — no scrolling
                return
            canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
        canvas.bind_all("<MouseWheel>", _wheel)

        # Build rows from the initial cut, then re-split live on any change.
        self._rebuild_review_rows(segs, self._split_settings())
        for _l, var, *_r in self._split_field_specs():
            var.trace_add("write", lambda *_a: self._schedule_resplit())
        self._start_waveform()

    def _live_pill(self, parent):
        """Small green 'live' status pill: dot + 're-split · no re-transcribe'."""
        txt = "re-split · no API"
        f = _font(UI_FONT, 8)
        w = f.measure(txt) + 30
        c = tk.Canvas(parent, width=w, height=22, bg=BG,
                      highlightthickness=0, bd=0)
        _round_rect(c, 0, 0, w, 21, 10, fill="#1f4433", outline="#1f4433")
        _round_rect(c, 1, 1, w - 1, 20, 9, fill="#12251c", outline="#12251c")
        c.create_oval(10, 8, 16, 14, fill="#39d98a", outline="")
        c.create_text(22, 11, anchor="w", text=txt, fill="#bfe6cf", font=f)
        return c

    def _build_split_field(self, parent, label, var, lo, hi, step, fmt):
        """One split control: a label with a small number box, and a slider
        beneath — both bound to the same var (two-way)."""
        row = tk.Frame(parent, bg=BG)
        row.pack(fill="x", pady=(0, 11))
        top = tk.Frame(row, bg=BG)
        top.pack(fill="x")
        tk.Label(top, text=label, bg=BG, fg=FG_DIM,
                 font=(UI_FONT, 9)).pack(side="left")
        box = tk.Frame(top, bg=BG, width=52, height=30)
        box.pack(side="right")
        box.pack_propagate(False)
        SmallInput(box, var).pack(fill="both", expand=True)
        Slider(row, var, lo, hi, fmt=fmt, step=step,
               height=26, bg_parent=BG).pack(fill="x", pady=(6, 0))

    # ── Inspector: the selected cue's numbers, and its two structural edits ──
    # The row glyphs (✂ ⤵ ✕) are a fast path once you know them, but nothing on
    # screen said what they were. Here the same two edits carry their real
    # names, and the figures the split settings are judged by — duration,
    # characters against the limit, reading speed — are shown instead of
    # implied by a warning chip that only appears once it is too late.
    INSPECTOR_FIELDS = (("in", "In"), ("out", "Out"), ("dur", "Duration"),
                        ("chars", "Characters"), ("cps", "Reading speed"),
                        ("lines", "Lines"))

    def _build_inspector(self, parent):
        self._insp_vars = {}
        self._insp_title = tk.StringVar(value="No cue selected")
        tk.Label(parent, textvariable=self._insp_title, bg=BG, fg=FG,
                 font=(UI_FONT, 9, "bold")).pack(anchor="w", pady=(0, 7))
        for key, label in self.INSPECTOR_FIELDS:
            row = tk.Frame(parent, bg=BG)
            row.pack(fill="x", pady=1)
            tk.Label(row, text=label, bg=BG, fg=FG_DIM,
                     font=(UI_FONT, 8)).pack(side="left")
            var = tk.StringVar(value="—")
            lab = tk.Label(row, textvariable=var, bg=BG, fg=FG,
                           font=(FONT_NUM, 8))
            lab.pack(side="right")
            self._insp_vars[key] = (var, lab)
        # Packed from the bottom up so the two actions are the last thing the
        # column will give up space for. The window is a fixed size and the
        # field list above can grow, and a button you cannot reach is worse
        # than a number you have to scroll to.
        RoundedButton(parent, "Merge into previous", self._insp_merge_up,
                      primary=False, bg_parent=BG, height=28).pack(
            side="bottom", fill="x")
        RoundedButton(parent, "Split at caret", self._insp_split,
                      primary=False, bg_parent=BG, height=28).pack(
            side="bottom", fill="x")

    def _refresh_inspector(self, desc=None):
        """Repaint the inspector from ``desc`` (or clear it when there is none).

        Reads the cue text off the widget rather than seg["text"], which is only
        refreshed on Apply — so the character count and reading speed track
        what is being typed.
        """
        if not hasattr(self, "_insp_vars"):
            return
        if desc is None or desc not in getattr(self, "_review_rows", []):
            self._insp_title.set("No cue selected")
            for var, lab in self._insp_vars.values():
                var.set("—")
                lab.configure(fg=FG)
            return
        s = self._insp_settings
        seg = dict(desc["seg"])
        seg["text"] = desc["text"].get()
        cps, lines, over_cps, over_lines = self._cue_stats(seg, s)
        chars = len(seg["text"].replace("\n", ""))
        _frac, col = CueMeter.grade(cps, s["cps"])
        vals = {
            "in":    (self._fmt_short(seg["s"]), FG),
            "out":   (self._fmt_short(seg["e"]), FG),
            "dur":   ("%.2f s" % max(0.0, seg["e"] - seg["s"]), FG),
            # Amber, not red: wrap() deliberately overruns the character budget
            # rather than break a word that cannot be broken, so over-length is
            # worth seeing but is not by itself a fault.
            "chars": ("%d / %d" % (chars, s["max_chars"] * s["max_lines"]),
                      ACCENT if chars > s["max_chars"] * s["max_lines"] else FG),
            "cps":   ("%.0f cps" % cps, col),
            "lines": ("%d / %d" % (lines, s["max_lines"]),
                      BAD if over_lines else FG),
        }
        self._insp_title.set("Cue %02d" % (self._review_rows.index(desc) + 1))
        for key, (text, colour) in vals.items():
            var, lab = self._insp_vars[key]
            var.set(text)
            lab.configure(fg=colour)

    def _insp_split(self):
        desc = self._sel_desc
        if desc is not None and desc.get("split"):
            desc["split"]()

    def _insp_merge_up(self):
        """Merge the selected cue into the one above it.

        Implemented through the PREVIOUS row's own merge, so there is exactly
        one merge path and the timing/word-list bookkeeping cannot drift apart.
        """
        desc = self._sel_desc
        rows = getattr(self, "_review_rows", [])
        if desc is None or desc not in rows:
            return
        i = rows.index(desc)
        if i == 0:
            return
        prev = rows[i - 1]
        if prev.get("merge"):
            prev["merge"]()

    # ── Waveform ──────────────────────────────────────────────────────────
    def _audio_path(self):
        """The media the transcript came from — the first line of the args file
        the Resolve-side script wrote. Only the waveform needs it, so a miss
        just means the strip never appears."""
        try:
            with open(self.args_path, encoding="utf-8") as f:
                return f.readline().rstrip("\r\n") or None
        except Exception:
            return None

    def _start_waveform(self):
        """Decode the peak envelope off the UI thread.

        ffmpeg on a long timeline takes seconds and the review screen has to be
        usable the moment it appears, so the strip is packed later — when, and
        only if, an envelope arrives.
        """
        path = self._audio_path()
        if not path or not os.path.exists(path):
            return
        strip = self._wave

        def work():
            try:
                import transcribe as _T
                env, hop = _T._audio_envelope(path), _T._ENV_HOP
            except Exception:
                env, hop = None, 0.005
            try:
                self.root.after(
                    0, lambda: self._waveform_ready(strip, env, hop))
            except Exception:
                pass          # window already gone

        threading.Thread(target=work, daemon=True).start()

    def _waveform_ready(self, strip, env, hop):
        # `strip is not self._wave` means the review screen was rebuilt (or
        # left) while ffmpeg was still decoding — that envelope belongs to a
        # screen that no longer exists.
        if not env or strip is not getattr(self, "_wave", None):
            return
        try:
            if not strip.winfo_exists() or not self._review_alive():
                return
            dur = max([d["seg"]["e"] for d in self._review_rows] or [0.0])
            strip.set_audio(env, hop, dur)
            if not self._wave_shown:
                # padx matches the cue canvas's own inset plus the scrollbar,
                # so the strip's time axis lines up with the cards under it.
                strip.pack(side="top", fill="x", pady=(0, 10), padx=(0, 20),
                           before=self._review_body)
                self._wave_shown = True
            self._sync_waveform()
        except Exception:
            pass

    def _sync_waveform(self):
        """Point the strip's ticks and window at the current cue list."""
        strip = getattr(self, "_wave", None)
        if strip is None or not getattr(self, "_wave_shown", False):
            return
        try:
            if not strip.winfo_exists():
                return
            bounds = [(d["seg"]["s"], d["seg"]["e"])
                      for d in getattr(self, "_review_rows", [])]
            sel = self._sel_desc
            span = (sel["seg"]["s"], sel["seg"]["e"]) if sel else None
            strip.set_cues(bounds, span)
        except Exception:
            pass

    def _seek_review(self, t):
        """Select the cue at time ``t`` — clicking the waveform is navigation.

        Falls back to the nearest cue so a click in a gap between cues still
        lands somewhere useful instead of doing nothing.
        """
        rows = getattr(self, "_review_rows", None) or []
        if not rows:
            return
        best, best_gap = rows[0], None
        for d in rows:
            s, e = d["seg"]["s"], d["seg"]["e"]
            if s <= t <= e:
                best = d
                break
            gap = s - t if t < s else t - e
            if best_gap is None or gap < best_gap:
                best, best_gap = d, gap
        self._select_review(best)
        self._scroll_to_row(best)

    def _scroll_to_row(self, desc):
        """Bring a row into view, roughly a third down the viewport."""
        canvas = getattr(self, "_review_canvas", None)
        try:
            if canvas is None or not canvas.winfo_exists():
                return
            total = max(1, self._review_lst.winfo_reqheight())
            view = canvas.winfo_height()
            if total <= view:
                return
            top = desc["outer"].winfo_y() - view * 0.33
            canvas.yview_moveto(max(0.0, min(1.0, top / float(total))))
        except Exception:
            pass

    def _schedule_resplit(self):
        """Debounce rapid edits: re-split ~220 ms after the last change."""
        if getattr(self, "_resplit_after", None):
            try:
                self.root.after_cancel(self._resplit_after)
            except Exception:
                pass
        self._resplit_after = self.root.after(220, self._do_resplit)

    def _do_resplit(self):
        self._resplit_after = None
        if not self._review_alive():
            return
        try:
            segs, s = self._resplit_segments()
        except Exception:
            return
        self._rebuild_review_rows(segs, s)

    def _review_alive(self):
        """Is the review list still on screen?

        The traces that drive re-splitting are on App-level variables and are
        never removed, and the re-split itself is debounced by 220 ms — so a
        slider nudged just before Apply fired into a screen that _clear_body had
        already destroyed.
        """
        lst = getattr(self, "_review_lst", None)
        try:
            return lst is not None and lst.winfo_exists()
        except Exception:
            return False

    def _rebuild_review_rows(self, segs, s):
        """(Re)paint the cue cards for ``segs`` and refresh the status line."""
        if not self._review_alive():
            return
        for child in list(self._review_lst.winfo_children()):
            child.destroy()
        self._review_rows = []
        self._sel_desc = None
        # The inspector is repainted from whatever cue is selected, which can
        # happen long after this rebuild; it needs the settings this cut used.
        self._insp_settings = s
        for i, seg in enumerate(segs, start=1):
            self._add_review_row(i, seg, s, is_last=(i == len(segs)))
        cps_note = ("CPS ≤ %g" % s["cps"]) if s["cps"] > 0 else "CPS off"
        flagged = sum(1 for d in self._review_rows if d.get("issue"))
        # Lead with the count of cues that need attention: it is the only number
        # here that implies an action.
        attention = ("%d need attention" % flagged) if flagged else "all within limits"
        self._review_status.set(
            "%d cues · %d×%d · %s · %s\nre-split locally, no API call"
            % (len(segs), s["max_chars"], s["max_lines"], cps_note, attention))
        if self._review_rows:
            self._select_review(self._review_rows[0])
        else:
            self._preview_cue("")
            self._refresh_inspector(None)
        self._sync_waveform()
        self.root.after(0, self._review_sync)

    def _add_review_row(self, idx, seg, s, is_last=False):
        """One cue as a rounded card: speaker bar, timecode, editable text,
        split/merge/delete, and a reading-speed meter in the right column.
        State — selected, over a limit — is the card's hairline colour."""
        outer = tk.Frame(self._review_lst, bg=BG)
        outer.pack(fill="x", pady=3)
        # The stripe carries the speaker, which is the one thing about a row
        # that never changes as you edit it. State — selected, over a limit —
        # is carried by the card's own hairline instead, where it reads as a
        # property of the whole cue rather than as an ornament beside it.
        color = self._spk_colors.get(seg.get("spk", 0))
        selbar = tk.Frame(outer, bg=(color or BG), width=3)
        selbar.pack(side="left", fill="y")

        field = RoundedField(outer, height=62, radius=10, padx=10,
                             bg_parent=BG, fill=BG_INPUT, border=BORDER)
        field.pack(side="left", fill="x", expand=True, padx=(6, 0))
        inner = tk.Frame(field, bg=BG_INPUT)

        # Fixed right-hand column for the reading-speed meter, so every row's
        # bar starts and ends at the same x and the list can be scanned down.
        gutter = tk.Frame(inner, bg=BG_INPUT)
        gutter.pack(side="right", fill="y", padx=(12, 0))

        main = tk.Frame(inner, bg=BG_INPUT)
        main.pack(side="left", fill="both", expand=True)

        top = tk.Frame(main, bg=BG_INPUT)
        top.pack(fill="x", pady=(7, 0))
        tk.Label(top, text="%02d" % idx, bg=BG_INPUT, fg=FG_MUTE,
                 font=(UI_FONT, 8)).pack(side="left", padx=(0, 7))
        tk.Label(top, text="%s → %s" % (self._fmt_short(seg["s"]),
                                        self._fmt_short(seg["e"])),
                 bg=BG_INPUT, fg=FG_MUTE,
                 font=(UI_FONT, 8)).pack(side="left")
        dele = tk.Label(top, text="✕", bg=BG_INPUT, fg=FG_MUTE,
                        font=(UI_FONT, 9), cursor="hand2")
        dele.pack(side="right")
        split_btn = tk.Label(top, text="✂", bg=BG_INPUT, fg=FG_MUTE,
                             font=(UI_FONT, 9), cursor="hand2")
        split_btn.pack(side="right", padx=(0, 8))
        merge_btn = None
        if not is_last:
            merge_btn = tk.Label(top, text="⤵", bg=BG_INPUT, fg=FG_MUTE,
                                 font=(UI_FONT, 9), cursor="hand2")
            merge_btn.pack(side="right", padx=(0, 8))
        cps, lines, over_cps, over_lines = self._cue_stats(seg, s)
        # Reading speed as a bar, on every row rather than only the bad ones:
        # a row that is fine has to look fine for a row that isn't to stand out.
        meter = CueMeter(gutter, cps, s["cps"], bg_parent=BG_INPUT)
        meter.pack(anchor="ne", pady=(7, 0))
        if over_lines:
            # Line overflow is the one warning a number can't carry — the cue
            # simply won't fit the caption box.
            tk.Label(top, text="▲ %d lines" % lines, bg=BG_INPUT, fg=BAD,
                     font=(UI_FONT, 8)).pack(side="right", padx=(0, 10))

        # A cue is wrapped text: with "Lines per cue" above 1 it contains real
        # newlines. tk.Entry is single-line and renders an embedded newline as a
        # control glyph you cannot see or edit around, so the multi-line cues
        # this tool is built to produce were the ones you could not proofread.
        # A Text sized to max_lines shows the cue as it will appear on screen.
        ent = CueText(main, seg["text"], lines=max(1, s["max_lines"]))
        ent.pack(fill="x", pady=(3, 7))
        field.set_child(inner)
        # The card grows with the line budget, and RoundedField draws to a
        # fixed height — so it has to be told how tall this row actually is.
        # Measured from the hosted frame rather than guessed from the text
        # widget: a CueText has no useful requested height until Tk has laid
        # it out, so sizing here and never again left every multi-line cue
        # clipped, overlapping the card below it and cropping the meter in the
        # column beside it. The estimate keeps the first paint from flashing;
        # _fit corrects it once the real geometry is known, and stays bound so
        # a change to the line budget re-fits the card.
        PAD_Y, FLOOR = 14, CueMeter.H + 16

        def _fit(_e=None, f=field, host=inner):
            if not f.winfo_exists() or not host.winfo_exists():
                return
            f.set_height(max(FLOOR, host.winfo_reqheight() + PAD_Y))

        field.set_height(max(FLOOR, 42 + ent.winfo_reqheight()))
        inner.bind("<Configure>", _fit, add="+")
        self.root.after_idle(_fit)

        desc = {"seg": seg, "text": ent, "field": field, "selbar": selbar,
                "outer": outer, "color": color, "meter": meter,
                "issue": bool(over_cps or over_lines)}
        self._apply_row_state(desc)
        self._review_rows.append(desc)

        ent.bind_all_widgets("<FocusIn>",
                             lambda _e, d=desc: self._select_review(d))
        top.bind("<Button-1>", lambda _e, d=desc: self._select_review(d),
                 add="+")
        ent.bind_all_widgets("<Button-1>",
                             lambda _e, d=desc: self._select_review(d))
        ent.on_change(lambda d=desc: self._refresh_preview(d))

        def _del(_e=None):
            if desc not in self._review_rows:
                return
            i = self._review_rows.index(desc)
            segs = self._snapshot_segs(skip=desc)
            # Rebuild rather than just destroying the frame: the numbering, the
            # "merge with next" button on the new last row, and the selection all
            # have to follow the deletion.
            self._rebuild_review_rows(segs, s)
            if self._review_rows:
                self._select_review(
                    self._review_rows[min(i, len(self._review_rows) - 1)])
        dele.bind("<Button-1>", _del)

        def _merge_next(_e=None):
            if desc not in self._review_rows:
                return
            i = self._review_rows.index(desc)
            if i + 1 >= len(self._review_rows):
                return
            import transcribe as _T
            nxt = self._review_rows[i + 1]
            combined = (ent.get().strip() + " " + nxt["text"].get().strip()).strip()
            merged_text = _T.wrap(" ".join(combined.split()),
                                  s["max_chars"], s["max_lines"],
                                  s.get("lang"))
            new_seg = {"s": seg["s"], "e": nxt["seg"]["e"], "spk": seg.get("spk"),
                       "words": seg.get("words", []) + nxt["seg"].get("words", []),
                       "text": merged_text}
            # Snapshot every OTHER row's live text first. Reading d["seg"] alone
            # discarded any cue the user had already retyped, because seg["text"]
            # is only refreshed from the widget on Apply.
            segs = self._snapshot_segs()
            segs[i] = new_seg
            del segs[i + 1]
            self._rebuild_review_rows(segs, s)
            if i < len(self._review_rows):
                self._select_review(self._review_rows[i])
        if merge_btn is not None:
            merge_btn.bind("<Button-1>", _merge_next)

        def _split_here(_e=None, focus_right=False):
            if desc not in self._review_rows:
                return
            i = self._review_rows.index(desc)
            words_list = seg.get("words", [])
            if len(words_list) < 2:
                return
            import transcribe as _T
            n_left = ent.words_before_cursor()
            # Word count of the (possibly hand-edited) text is only an
            # approximation of where in seg["words"] the cursor really sits —
            # same "close enough, never crash" spirit as wrap()'s overflow rule.
            n_left = max(1, min(n_left, len(words_list) - 1))
            left_words, right_words = words_list[:n_left], words_list[n_left:]
            # word tuples are (start, end, text) — see _resplit_segments
            left_text = _T.wrap(" ".join(w[2] for w in left_words),
                                s["max_chars"], s["max_lines"],
                                s.get("lang"))
            right_text = _T.wrap(" ".join(w[2] for w in right_words),
                                 s["max_chars"], s["max_lines"],
                                 s.get("lang"))
            # A split adds ONE boundary; the cue's outer edges must not move.
            # Timing them from the words instead threw away whatever seg["s"]/
            # seg["e"] had already earned in _sanitize_cues — the readability
            # extension and the closed gap to the neighbouring cues — so every
            # manual split silently re-opened the holes on the timeline that the
            # split settings had just removed.
            cut = right_words[0][0]
            left_end = left_words[-1][1]
            if 0.0 < cut - left_end <= _T._GAP_CLOSE_MAX:
                left_end = cut - 0.001  # absorb the pause, same rule as the SRT
            # Both halves stay non-degenerate and ordered even when the ASR
            # hands back overlapping or zero-length words.
            left_end = max(seg["s"] + 0.001, min(left_end, cut - 0.001))
            seg_left = {"s": seg["s"], "e": left_end,
                        "spk": seg.get("spk"), "words": left_words, "text": left_text}
            seg_right = {"s": cut, "e": max(seg["e"], cut + 0.001),
                         "spk": seg.get("spk"), "words": right_words, "text": right_text}
            segs = self._snapshot_segs()
            segs[i:i + 1] = [seg_left, seg_right]
            self._rebuild_review_rows(segs, s)
            if focus_right:
                self._review_rows[i + 1]["text"].focus(at_start=True)
            else:
                self._select_review(self._review_rows[i])
        split_btn.bind("<Button-1>", _split_here)
        # Enter mid-cue means "the subtitle should break here" — split at the
        # caret rather than insert a newline the line budget has no room for.
        ent.on_return(lambda: _split_here(focus_right=True))
        # Same two edits the inspector offers under their full names.
        desc["split"] = _split_here
        desc["merge"] = _merge_next if merge_btn is not None else None

    def _snapshot_segs(self, skip=None):
        """Every row's segment with its on-screen text folded back in.

        The single source of truth for "what the cue list is right now". Merge,
        split, delete and Apply all go through this, so a hand-edited cue is
        never silently reverted by an unrelated structural change.
        """
        out = []
        for d in self._review_rows:
            if d is skip:
                continue
            seg = dict(d["seg"])
            seg["text"] = d["text"].get().strip()
            out.append(seg)
        return out

    @staticmethod
    def _cue_stats(seg, s):
        """(reading speed, line count, over CPS?, over lines?) for one cue.

        Measured from the cue TEXT, not the word list: the text is what a viewer
        reads, and it is what the user has been editing.
        """
        text = seg["text"] or ""
        lines = text.count("\n") + 1
        dur = max(0.001, seg["e"] - seg["s"])
        cps_val = len(text.replace("\n", "")) / dur
        return (cps_val, lines,
                bool(s["cps"] > 0 and cps_val > s["cps"]),
                lines > s["max_lines"])

    @staticmethod
    def _fmt_short(sec):
        if sec < 0:
            sec = 0.0
        m, s = divmod(sec, 60)
        return "%d:%05.2f" % (int(m), s)

    def _apply_row_state(self, desc):
        """Colour a cue card's hairline for what the cue currently is.

        Three states share one border, in priority order: the cue being edited
        is amber, a cue that breaks a limit is red, everything else is the
        ordinary hairline. Selection wins over the warning because the warning
        is still readable from the meter beside it, and a selected cue has to
        be findable in a list where several rows may be red.
        """
        field = desc.get("field")
        if field is None:
            return
        try:
            if not field.winfo_exists():
                return
            if desc is self._sel_desc:
                field.set_border(ACCENT)
            elif desc.get("issue"):
                field.set_border(BAD)
            else:
                field.set_border(BORDER)
        except Exception:
            pass

    def _select_review(self, desc):
        prev = self._sel_desc
        self._sel_desc = desc
        if prev is not None and prev is not desc:
            self._apply_row_state(prev)
        self._apply_row_state(desc)
        self._refresh_preview(desc)
        self._sync_waveform()

    def _refresh_preview(self, desc):
        if self._sel_desc is not desc:
            return
        self._preview_cue(desc["text"].get())
        self._refresh_inspector(desc)
        self._refresh_meter(desc)

    def _refresh_meter(self, desc):
        """Re-grade the row's bar for text typed since the last cut.

        Reading speed is characters over a fixed duration, so it moves as you
        type — a bar that only updated on re-split would be quietly wrong for
        exactly the cue being worked on.
        """
        meter = desc.get("meter")
        if meter is None:
            return
        try:
            if not meter.winfo_exists():
                return
            s = self._insp_settings
            seg = dict(desc["seg"])
            seg["text"] = desc["text"].get()
            cps, _lines, over_cps, over_lines = self._cue_stats(seg, s)
            meter.set(cps, s["cps"])
            desc["issue"] = bool(over_cps or over_lines)
            self._apply_row_state(desc)
        except Exception:
            pass

    def _preview_cue(self, text):
        """Feed the selected cue text into the animated reel preview."""
        try:
            # The preview lays out one line; a wrapped cue is still one caption.
            flat = " ".join((text or "").split())
            self._review_preview.SAMPLE = flat or ReelPreview.SAMPLE
            self._review_preview._draw()
        except Exception:
            pass

    def _apply_review(self, srt_path, cap_path, header):
        # Drop any debounced re-split before the rows are read: letting it land
        # would replace the list we are about to write with a freshly re-cut one,
        # discarding the user's edits at the last moment.
        if getattr(self, "_resplit_after", None):
            try:
                self.root.after_cancel(self._resplit_after)
            except Exception:
                pass
            self._resplit_after = None
        final = [seg for seg in self._snapshot_segs() if seg["text"]]
        if not final:
            messagebox.showerror(
                "Srutilekha",
                "Every cue was deleted or emptied, so there is nothing to "
                "apply. Undo a deletion, or press Cancel to leave the timeline "
                "untouched.")
            return
        try:
            self._write_srt_cap(srt_path, cap_path, header, final)
        except Exception as e:
            messagebox.showerror("Srutilekha",
                                 "Cannot write edited captions: %s" % e)
            return
        try:
            self.root.unbind_all("<MouseWheel>")
        except Exception:
            pass
        self._build_progress("Applying captions")
        self._set_progress(80, "Placing captions on the timeline…")
        self.root.after(30, self._animate_bar)
        self._finish_after_transcribe(0)


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

    root = tk.Tk()
    try:
        root.iconbitmap(default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico"))
    except Exception:
        pass
    # Stay hidden until the window is fully built and positioned. tk.Tk() maps a
    # default-sized window at once, and App.__init__ then flips
    # overrideredirect(True) on it — on Windows that forces Tk to destroy and
    # recreate the native frame, so the window visibly appeared, vanished, and
    # reappeared at its real geometry, with the half-built form showing in
    # between. Withdrawn, none of that is on screen: it appears once, finished,
    # centred.
    root.withdraw()
    app = App(root, prompt, a.selection, a.args_file, a.done, a.log,
              a.python, a.script, a.result, a.ack,
              run_id=a.run_id, run_marker=a.run_marker)
    root.update_idletasks()
    root.deiconify()
    # deiconify on an overrideredirect toplevel does not always activate it;
    # _steal_focus (queued by App at +60ms) finishes the job.
    try:
        root.lift()
    except Exception:
        pass
    root.mainloop()

    code = app.exit_code if app.exit_code is not None else (
        130 if app.cancelled else 1
    )
    sys.exit(code)


if __name__ == "__main__":
    main()
