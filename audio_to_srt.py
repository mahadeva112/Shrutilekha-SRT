#!/usr/bin/env python
"""audio_to_srt.py  --  Srutilekha  (Workspace -> Scripts -> Srutilekha)

Transcribes the audio on the current timeline via ElevenLabs and imports the
result as a subtitle track. Cross-platform: Mac + Windows. All dialogs use
dialog.py (tkinter), the form and progress window is loader.pyw, and the
transcription itself is transcribe.py -- this file is only the Resolve-side
half: it reads the timeline, launches the window, and imports what comes back.

WHY THIS IS PYTHON AND NOT LUA
------------------------------
This is a port of audio_to_srt.lua, which no longer runs. Resolve 21.1 moved
menu and console scripts onto built-in interpreters and runs the Lua one in a
sandbox with the `io` and `package` tables removed, so the old script died on
its first file read -- before the menu entry appeared to do anything at all:

    Srutilekha.lua:18: attempt to index global 'io' (a nil value)

`io` is not optional here: every handshake with loader.pyw is a file. Nor can
it be shimmed, because `package`/`require` are gone too, which puts LuaJIT's
FFI (the old script's route to WinExec and Sleep) out of reach as well.

The Python host has the full standard library, so the port is also a large
simplification: subprocess with CREATE_NO_WINDOW replaces the WinExec/FFI and
VBScript/ShellExecute launch routes and the console-flash workarounds around
them, and json replaces the hand-written JSON and the patterns that read it
back.

audio_to_srt.lua is kept in the repo for DaVinci Resolve 21.0 and earlier.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

IS_WINDOWS = (os.name == "nt")

# Windows process-creation flags. Resolve is a GUI process with no console of
# its own, so a child launched without these gets a brand new console window --
# the black box that used to blink on screen at every launch.
CREATE_NO_WINDOW = 0x08000000
DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200


# ── Where the project lives ─────────────────────────────────────────────────

def get_project_dir():
    home = os.path.expanduser("~")
    config = os.path.join(home, ".audio_to_srt_path")
    try:
        with open(config, encoding="utf-8", errors="replace") as f:
            p = f.readline().strip()
        if p:
            return p
    except OSError:
        pass
    return os.path.join(home, "DaVinci-Audio2SRT")


PROJECT_DIR = get_project_dir()

TRANSCRIBE_PY = os.path.join(PROJECT_DIR, "transcribe.py")
DIALOG_PY = os.path.join(PROJECT_DIR, "dialog.py")
LOADER_PY = os.path.join(PROJECT_DIR, "loader.pyw")
LOGS_DIR = os.path.join(PROJECT_DIR, "logs")
LOG_FILE = os.path.join(LOGS_DIR, "audio_to_srt.log")
LOADER_LOG = LOG_FILE + ".transcribe"
STYLE_JSON = os.path.join(PROJECT_DIR, "subtitle_style.json")


# ── Finding the user's Python ───────────────────────────────────────────────
# Deliberately not sys.executable: on Resolve 21.1 this script runs inside
# Resolve's own Python, which ships without Tk and without pip, so it can
# neither draw the loader window nor import elevenlabs. The loader and the
# worker need the interpreter setup.bat installed those packages into.

def find_python():
    # IMPORTANT: bare "python" on PATH must remain the LAST Windows fallback
    # and ideally never be hit. On modern Windows, %LOCALAPPDATA%\Microsoft\
    # WindowsApps\python.exe is an App Execution Alias stub that satisfies a
    # file-existence check but prints "Python was not found..." when run. Real
    # install locations (including the official `py` launcher) are listed ahead
    # of it so a working interpreter is found first.
    if IS_WINDOWS:
        local = os.environ.get("LOCALAPPDATA", "")
        candidates = [os.path.join(local, "Python", "bin", "python.exe")]
        for ver in ("315", "314", "313", "312", "311"):
            candidates.append(os.path.join(
                local, "Programs", "Python", "Python" + ver, "python.exe"))
        for ver in ("315", "314", "313", "312", "311"):
            candidates.append("C:\\Python%s\\python.exe" % ver)
        candidates.append(os.path.join(
            os.environ.get("SystemRoot", "C:\\Windows"), "py.exe"))
        fallback = "python"
    else:
        candidates = ["/opt/homebrew/bin/python3", "/usr/local/bin/python3",
                      "/usr/bin/python3"]
        fallback = "python3"
    for p in candidates:
        if p and os.path.isfile(p):
            return p
    return shutil.which(fallback) or fallback


PYTHON3 = find_python()


def find_pythonw():
    """The windowless sibling of the interpreter above -- used for the loader
    and the dialogs so nothing allocates a console inside Resolve."""
    if not IS_WINDOWS:
        return PYTHON3
    base = os.path.basename(PYTHON3).lower()
    cand = None
    if base == "python.exe":
        cand = os.path.join(os.path.dirname(PYTHON3), "pythonw.exe")
    elif base == "py.exe":
        cand = os.path.join(os.path.dirname(PYTHON3), "pyw.exe")
    if cand and os.path.isfile(cand):
        return cand
    return PYTHON3


PYTHONW = find_pythonw()


# ── Logging ─────────────────────────────────────────────────────────────────

def ensure_logs_dir():
    try:
        os.makedirs(LOGS_DIR, exist_ok=True)
    except OSError:
        pass


def log(msg):
    try:
        ensure_logs_dir()
        with open(LOG_FILE, "a", encoding="utf-8", errors="replace") as f:
            f.write("%s  %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg))
    except OSError:
        pass
    try:
        print(msg)
    except Exception:
        pass


def hidden_flags():
    """Keyword args that keep a child process off the screen on Windows."""
    if not IS_WINDOWS:
        return {}
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = 0                      # SW_HIDE
    return {"creationflags": CREATE_NO_WINDOW, "startupinfo": si}


def pydialog(*args):
    """Run dialog.py and return its stdout, stripped."""
    cmd = [PYTHONW, DIALOG_PY] + [str(a) for a in args]
    try:
        out = subprocess.run(cmd, stdin=subprocess.DEVNULL,
                             stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL,
                             cwd=PROJECT_DIR, timeout=900, **hidden_flags())
        return (out.stdout or b"").decode("utf-8", "replace").strip()
    except Exception as e:
        log("dialog.py failed: %r" % (e,))
        return ""


def alert(title, msg):
    pydialog("alert", title, msg)


def alert_error(title, msg):
    pydialog("alert_error", title, msg)


# ── Small file helpers ──────────────────────────────────────────────────────

def read_text(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return None


def write_text(path, text):
    try:
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        return True
    except OSError as e:
        log("Cannot write %s: %r" % (path, e))
        return False


def rm(path):
    try:
        os.remove(path)
    except OSError:
        pass


# ── Resolve handle ──────────────────────────────────────────────────────────

def get_resolve():
    """The Resolve object. A menu script gets it injected as a global; the
    fallbacks cover being run from fuscript or an external interpreter."""
    try:
        return resolve                    # noqa: F821  (injected by Resolve)
    except NameError:
        pass
    for name in ("fusion", "fu", "app"):
        obj = globals().get(name)
        if obj is not None:
            try:
                r = obj.GetResolve()
                if r:
                    return r
            except Exception:
                pass
    try:
        import DaVinciResolveScript as dvr
        return dvr.scriptapp("Resolve")
    except Exception:
        return None


# ── Which script a cue is written in ────────────────────────────────────────
# Ported from SCRIPT_BY_B2 in audio_to_srt.lua, which ran the same test against
# raw UTF-8 lead bytes. Every Indic block this tool targets is one contiguous
# range; Perso-Arabic (Urdu) is U+0600-06FF.
SCRIPT_RANGES = (
    (0x0600, 0x06FF, "arab"),
    (0x0900, 0x097F, "deva"),
    (0x0980, 0x09FF, "beng"),      # Bengali and Assamese share the block
    (0x0A00, 0x0A7F, "guru"),
    (0x0A80, 0x0AFF, "gujr"),
    (0x0B00, 0x0B7F, "orya"),
    (0x0B80, 0x0BFF, "taml"),
    (0x0C00, 0x0C7F, "telu"),
    (0x0C80, 0x0CFF, "knda"),
    (0x0D00, 0x0D7F, "mlym"),
    (0xA8E0, 0xA8FF, "deva"),      # Devanagari Extended
)

# The danda and double danda sit in the Devanagari block but are punctuation for
# every Indic script, so they are never counted -- otherwise a Tamil cue ending
# in one could be typeset in a Devanagari font.
DANDA = (0x0964, 0x0965)


def script_of(s):
    """The script the majority of a string's letters are in, or None for
    Latin/none. Counted rather than first-match; see DANDA above."""
    if not s:
        return None
    counts = {}
    best, best_n = None, 0
    for ch in s:
        cp = ord(ch)
        if cp < 0x0600 or cp in DANDA:
            continue
        for lo, hi, tag in SCRIPT_RANGES:
            if lo <= cp <= hi:
                n = counts.get(tag, 0) + 1
                counts[tag] = n
                if n > best_n:
                    best, best_n = tag, n
                break
    return best


def script_summary(counts, fonts):
    """"  (12 deva -> Vesper Libre, 4 taml -> Nirmala UI)" for the completion
    log, so a wrong font shows up in the log and not only on the timeline."""
    if not counts:
        return ""
    parts = sorted("%d %s -> %s" % (n, tag, fonts.get(tag, "?"))
                   for tag, n in counts.items())
    return "  (" + ", ".join(parts) + ")"


# ── Colours ─────────────────────────────────────────────────────────────────

def hex_rgb3(h):
    m = re.match(r"^#?([0-9a-fA-F]{2})([0-9a-fA-F]{2})([0-9a-fA-F]{2})$",
                 str(h or ""))
    if not m:
        return None
    return tuple(int(m.group(i), 16) / 255.0 for i in (1, 2, 3))


# ── Subtitle style ──────────────────────────────────────────────────────────
# Styling comes from subtitle_style.json so it can be changed without editing
# this script. "fontFace" is the default font and "fontFaceDevanagari" the one
# for Devanagari cues (one font per cue). Falls back to the historical
# hardcoded style when the file is missing or unreadable.

DEFAULT_STYLE = {
    "fontFace": "Noto Serif Bengali", "fontFaceDevanagari": "Vesper Libre",
    "bold": 1, "fontSize": 55, "strokeEnabled": 1, "strokeOutsideOnly": 1,
    "customPosition": 1, "posY": 620, "shadowEnabled": 1,
    "shadowXOffset": 3, "shadowYOffset": 3, "shadowOpacity": 100,
}

# The two fonts are applied per cue by font_for(); strokeColor is nested and
# left to Resolve's own default.
SKIP_STYLE_KEYS = {"fontFace", "fontFaceDevanagari", "strokeColor",
                   "r", "g", "b", "a"}


def load_style():
    body = read_text(STYLE_JSON)
    if not body or not body.strip():
        return dict(DEFAULT_STYLE)
    try:
        data = json.loads(body)
    except ValueError as e:
        log("subtitle_style.json is not valid JSON (%s) — using defaults." % e)
        return dict(DEFAULT_STYLE)
    if not isinstance(data, dict):
        return dict(DEFAULT_STYLE)
    # Scalars only: a nested object (strokeColor's r/g/b/a) is not a property
    # value, and bool would reach SetProperty as True rather than 1.
    style = {}
    for k, v in data.items():
        if isinstance(v, bool):
            style[k] = 1 if v else 0
        elif isinstance(v, (str, int, float)):
            style[k] = v
    return style or dict(DEFAULT_STYLE)


# ── Caption sidecar (per-word timing + per-speaker colour) ──────────────────
# transcribe.py writes "<srt>.cap" next to the SRT in a simple line format:
#   FPS <rate>
#   SPK <idx> <#hex> <style>        (1-based speaker, in appearance order)
#   SEG <start_s> <end_s> <spkIdx>  (times are timeline-relative seconds)
#   WRD <start_s> <end_s> <word>    (words follow their SEG; spkIdx 0 = none)

def parse_caption(cap_path, fps):
    caption = {"fps": fps, "speakers": {}, "segments": []}
    body = read_text(cap_path)
    if body is None:
        log("Caption sidecar missing: " + cap_path)
        return caption
    cur = None
    for line in body.splitlines():
        line = line.rstrip("\r")
        if line.startswith("FPS"):
            m = re.match(r"^FPS\s+([\d.]+)", line)
            if m:
                caption["fps"] = float(m.group(1))
        elif line.startswith("SPK"):
            m = re.match(r"^SPK\s+(\d+)\s+(\S+)\s*(\S*)", line)
            if m:
                caption["speakers"][int(m.group(1))] = {
                    "hex": m.group(2), "style": m.group(3) or "Fill"}
        elif line.startswith("SEG"):
            m = re.match(r"^SEG\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(\d+)", line)
            if m:
                cur = {"start": float(m.group(1)), "end": float(m.group(2)),
                       "spk": int(m.group(3)), "words": []}
                caption["segments"].append(cur)
        elif line.startswith("WRD") and cur is not None:
            m = re.match(r"^WRD\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(.*)$", line)
            if m:
                cur["words"].append({"start": float(m.group(1)),
                                     "end": float(m.group(2)),
                                     "word": m.group(3)})
    # A segment that parsed without any WRD line has lost its word timings,
    # which is worth saying here, where the numbers are still in front of us.
    total = sum(len(s["words"]) for s in caption["segments"])
    wordless = sum(1 for s in caption["segments"] if not s["words"])
    log("Caption sidecar: %d segment(s), %d word(s)%s" % (
        len(caption["segments"]), total,
        " — %d with NO words (blank captions)" % wordless if wordless else ""))
    return caption


def speaker_color(caption, spk):
    """Speaker index -> subtitle-item colour as {r,g,b,a} in 0-1 range (the
    same shape as strokeColor in subtitle_style.json). None when unknown."""
    if not spk:
        return None
    sp = caption["speakers"].get(spk)
    if not sp:
        return None
    rgb = hex_rgb3(sp.get("hex"))
    if not rgb:
        return None
    return {"r": rgb[0], "g": rgb[1], "b": rgb[2], "a": 1}


def segment_for_time(caption, sec):
    """Match a subtitle item to its caption segment by nearest start time. The
    subtitle track can carry a dummy blank cue at t=0, so index alignment is
    not reliable. Times are timeline-relative seconds."""
    best, best_delta = None, 0.30
    for seg in caption["segments"]:
        d = abs(seg["start"] - sec)
        if d <= best_delta:
            best, best_delta = seg, d
    return best


# ── The run ─────────────────────────────────────────────────────────────────

class Run(object):
    """One invocation: its handshake files, its waits, its cleanup."""

    def __init__(self):
        # Every launch gets its own handshake files. They used to have fixed
        # names, which broke as soon as two instances overlapped (script
        # started, loader left open, script started again): both instances read
        # the same selection.json on Submit and transcribed in parallel, each
        # into its own SRT, so one of them then failed with "Transcription
        # produced no output". The id is time plus this object's address --
        # unique even within the same second.
        self.id = "%d-%x" % (int(time.time()), id(self) & 0xFFFFFF)
        sfx = "-" + self.id
        self.marker = os.path.join(LOGS_DIR, "current_run.txt")
        self.prompt = os.path.join(LOGS_DIR, "prompt%s.json" % sfx)
        self.selection = os.path.join(LOGS_DIR, "selection%s.json" % sfx)
        self.done = os.path.join(LOGS_DIR, "transcribe%s.done" % sfx)
        self.args = os.path.join(LOGS_DIR, "transcribe_args%s.txt" % sfx)
        self.result = os.path.join(LOGS_DIR, "transcribe%s.result" % sfx)
        self.ack = os.path.join(LOGS_DIR, "transcribe%s.ack" % sfx)
        self.ranges = os.path.join(LOGS_DIR, "clip_ranges%s.txt" % sfx)
        # Records the track created by the last generation so Undo can remove
        # it. Not per-run: it outlives the run by design.
        self.last_gen = os.path.join(LOGS_DIR, "last_gen.txt")

    # Retire the previous run: drop its already-consumed input files and claim
    # the marker. A still-running transcription keeps its .done/.result/.ack,
    # so it finishes and reports normally; only a loader still sitting on the
    # form reacts to the marker change (it watches this file and closes).
    def claim(self):
        prev = (read_text(self.marker) or "").strip()
        if prev and prev != self.id:
            sfx = "-" + prev
            for name in ("prompt%s.json", "selection%s.json",
                         "selection%s.json.tmp", "transcribe_args%s.txt",
                         "clip_ranges%s.txt", "launch%s.vbs", "launch%s.ok"):
                rm(os.path.join(LOGS_DIR, name % sfx))
            log("Superseding earlier run " + prev)
        # Legacy fixed-name leftovers from before per-run naming.
        for name in ("selection.json", "transcribe.done",
                     "transcribe_args.txt", "transcribe.result",
                     "transcribe.ack"):
            rm(os.path.join(LOGS_DIR, name))
        write_text(self.marker, self.id)

    def superseded(self):
        """True once a newer launch has claimed the marker -- this instance
        must bow out, or it would also act on that launch's submission."""
        cur = (read_text(self.marker) or "").strip()
        return bool(cur) and cur != self.id

    def cleanup(self):
        for p in (self.prompt, self.selection, self.args, self.done,
                  self.result, self.ack, self.ranges):
            rm(p)

    # ── Bounded waits ──────────────────────────────────────────────────────
    # Both handshake waits used to be `while true` with no timeout and no
    # supersede check: if the loader died -- killed, crashed, or closed by
    # Windows -- this script waited forever inside Resolve.

    def wait_for_done(self, timeout_s=7200):
        """The loader's completion sentinel: its exit code, or (None, why)."""
        deadline = time.time() + timeout_s
        while True:
            body = read_text(self.done)
            if body is not None:
                m = re.search(r"(-?\d+)", body)
                return (int(m.group(1)) if m else 1), None
            if self.superseded():
                return None, "superseded"
            if time.time() > deadline:
                return None, "timeout"
            time.sleep(0.25)

    def wait_for_ack(self, timeout_s=300):
        """Wait for the loader to acknowledge the result screen, so the window
        is not torn down before the user has read it. Best-effort: the run is
        already done either way."""
        deadline = time.time() + timeout_s
        while True:
            if os.path.exists(self.ack):
                rm(self.ack)
                return True
            if time.time() > deadline:
                return False
            time.sleep(0.25)

    def wait_for_selection(self):
        """Block until the loader writes selection.json (Generate/Sync/Undo),
        or reports done (the user closed it). Returns the parsed selection, or
        None if there is nothing to do."""
        while True:
            if self.superseded():
                log("Superseded by a newer Srutilekha run — this instance is "
                    "exiting.")
                rm(self.done)
                self.cleanup()
                return None
            if os.path.exists(self.done):
                log("User cancelled (loader closed before submit)")
                rm(self.done)
                self.cleanup()
                return None
            body = read_text(self.selection)
            if body:
                try:
                    sel = json.loads(body)
                except ValueError:
                    # The loader renames its scratch file into place, so a
                    # half-written read should not happen -- but a truncated
                    # file must not be parsed with every later field silently
                    # falling back to a default either. Wait for the whole one.
                    sel = None
                if isinstance(sel, dict) and sel.get("chosen") \
                        and sel.get("settings"):
                    return sel
            time.sleep(0.15)

    def report(self, msg):
        """Write the completion message for the loader window to display in
        place, then wait for the user to click OK."""
        write_text(self.result, msg)
        self.wait_for_ack()

    def launch_loader(self):
        """Start loader.pyw. It shows the form first, then transitions in place
        to the progress view once the user submits."""
        cmd = [PYTHONW, LOADER_PY,
               "--prompt", self.prompt,
               "--selection", self.selection,
               "--args-file", self.args,
               "--done", self.done,
               "--log", LOADER_LOG,
               "--python", PYTHON3,
               "--script", TRANSCRIBE_PY,
               "--result", self.result,
               "--ack", self.ack,
               "--run-id", self.id,
               "--run-marker", self.marker]
        kwargs = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL,
                  "stderr": subprocess.DEVNULL, "cwd": PROJECT_DIR,
                  "close_fds": True}
        if IS_WINDOWS:
            # pythonw.exe is a GUI-subsystem binary, so with these flags no
            # console is created and the window outlives this script.
            kwargs["creationflags"] = (CREATE_NO_WINDOW | DETACHED_PROCESS
                                       | CREATE_NEW_PROCESS_GROUP)
        else:
            kwargs["start_new_session"] = True
        try:
            subprocess.Popen(cmd, **kwargs)
        except OSError as e:
            log("Cannot launch the loader: %r" % (e,))
            alert_error("Srutilekha",
                        "Could not start the Srutilekha window:\n%s\n\n"
                        "Python used: %s" % (e, PYTHONW))
            return False
        log("Launched loader: %s" % (" ".join(cmd),))
        return True


# ── Selection field access ──────────────────────────────────────────────────
# The loader writes numbers as numbers (punct, diarize, outline, shadow) and
# everything else as strings. Both sides of this script's logic want strings,
# so normalise once here rather than testing types at each use.

def field(sel, key, default=""):
    v = sel.get(key)
    if v is None:
        return default
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return str(int(v)) if v.is_integer() else str(v)
    v = str(v).strip()
    return v if v else default


# ── Importing an SRT without destroying anything ────────────────────────────
# This used to be three lines:
#
#     for i = timeline:GetTrackCount("subtitle"), 1, -1 do
#         timeline:DeleteTrack("subtitle", i)
#     end
#     timeline:AddTrack("subtitle")
#
# i.e. every generation and every sync silently deleted EVERY subtitle track on
# the timeline -- hand-authored subtitles, a forced-narrative track, an earlier
# language pass, all of it, with no warning and nothing recorded for Undo. The
# only reason it was there is that the code afterwards wanted the imported cues
# to be on a known track index, and wiping the timeline made that index 1.
#
# Instead: add a track, import, then find out where the cues actually landed by
# diffing the subtitle tracks. Nothing is deleted, and the answer is observed
# rather than assumed.

def import_srt_to_new_track(timeline, mp, srt_file, timecode):
    """Returns (ok, track_index, items, created_track, error).

    `items` is only the cues THIS import added, which is not the same as the
    contents of the track they landed on. Resolve picks the track itself, and it
    will happily append onto one that already holds an earlier run's subtitles:
    on 2026-08-07 a 57-cue run landed on the track a 36-cue run had used and the
    old code returned all 93. That reported "Imported 92 subtitle cues" for 57,
    and -- worse -- ran the styling pass over the earlier run's cues, re-fonting
    and re-colouring subtitles the user had never asked to touch.
    """

    def item_start(item):
        try:
            return item.GetStart()
        except Exception:
            return None

    def track_items(idx):
        try:
            return timeline.GetItemListInTrack("subtitle", idx) or []
        except Exception:
            return []

    def snapshot():
        # Per-track set of occupied start frames. A start frame identifies a cue
        # well enough for this: cues on one subtitle track cannot overlap, so no
        # two of them share one.
        s = {}
        for i in range(1, timeline.GetTrackCount("subtitle") + 1):
            seen = set()
            for item in track_items(i):
                f = item_start(item)
                if f is not None:
                    seen.add(f)
            s[i] = seen
        return s

    before = snapshot()
    before_tracks = timeline.GetTrackCount("subtitle")
    # A fresh empty track for the import to land on. Resolve gives no way to
    # nominate a subtitle track, but an empty one at the end is where it puts an
    # appended subtitle clip in practice; if it chooses elsewhere, the diff
    # below still finds it.
    added_track = None
    try:
        if timeline.AddTrack("subtitle") \
                and timeline.GetTrackCount("subtitle") > before_tracks:
            added_track = timeline.GetTrackCount("subtitle")
    except Exception:
        added_track = None

    def drop_added():
        if added_track:
            try:
                timeline.DeleteTrack("subtitle", added_track)
            except Exception:
                pass

    # Anchor so the SRT times align with the timeline start.
    try:
        timeline.SetCurrentTimecode(timecode)
    except Exception:
        pass

    imported = mp.ImportMedia([srt_file])
    if not imported:
        drop_added()
        return False, None, None, False, \
            "Resolve could not import the SRT file."
    if not mp.AppendToTimeline([imported[0]]):
        drop_added()
        return False, None, None, False, \
            "Resolve could not append the SRT to the timeline."

    # Which track grew, and by which items? Both answers come from the same
    # pass: an item at a start frame that was not occupied before this import is
    # one of ours. Items stay in timeline order, so items[0] is the first cue of
    # this run.
    landed, new_items, prior_count = None, [], 0
    for i in range(1, timeline.GetTrackCount("subtitle") + 1):
        prior = before.get(i, set())
        added = []
        for item in track_items(i):
            f = item_start(item)
            # No readable start frame: treat as ours. Leaving a cue of this run
            # unstyled is worse than the unlikely alternative, and a handle that
            # cannot answer GetStart is broken anyway.
            if f is None or f not in prior:
                added.append(item)
        if len(added) > len(new_items):
            landed, new_items, prior_count = i, added, len(prior)

    if not landed:
        drop_added()
        return False, None, None, False, \
            "The SRT imported but Resolve placed no cues on any subtitle track."

    log("SRT cues landed on subtitle track %d: %d new, %d cue(s) already "
        "there (left untouched)." % (landed, len(new_items), prior_count))

    # If the cues went somewhere other than the track we made, drop ours again
    # rather than leaving an empty track behind -- and do NOT claim it for Undo,
    # because that track is the user's, not ours.
    created = (added_track is not None and landed == added_track)
    if added_track and not created and not track_items(added_track):
        drop_added()
    return True, landed, new_items, created, None


def count_real_cues(items):
    """How many of these cues are the user's.

    to_srt() writes a blank cue at t=0 so Resolve pins the imported clip to the
    timeline start. It is not a subtitle anyone asked for, so it must not be
    counted -- but subtracting a fixed 1 for it was wrong, because Resolve DROPS
    it on import rather than keeping it. Verified across the eight clean runs in
    the log: a 36-segment sidecar yields exactly 36 items, never 37, so every
    run reported one cue fewer than it produced. Counting the cues that carry
    text is correct whether Resolve keeps the anchor or discards it.
    """
    n = 0
    for item in items or []:
        try:
            if (item.GetName() or "").strip():
                n += 1
        except Exception:
            pass
    return n


def record_undo(run, timeline, kind, idx, created):
    """Remember the track for Undo only when we created it ourselves. Undo
    deletes a whole track, so pointing it at a track that already held the
    user's cues would turn "undo my captions" into "delete my subtitles"."""
    if created:
        write_text(run.last_gen, "%s %d %s" % (kind, idx, timeline.GetName()))
    else:
        rm(run.last_gen)


# ── Undo mode ───────────────────────────────────────────────────────────────

def do_undo(run, pm, timeline):
    """Remove the track the last generation created. Reads logs/last_gen.txt
    ("<video|subtitle> <trackIndex> <timelineName>"). Only removes the track if
    it belongs to the current timeline, so we never delete something on a
    different timeline the user has since switched to."""
    body = read_text(run.last_gen)
    if body is None:
        msg = "Nothing to undo — no caption track has been generated yet."
    else:
        m = re.match(r"^(\S+)\s+(\d+)\s*(.*?)\s*$", body.strip())
        if not m:
            msg = "Nothing to undo — the undo record is empty or unreadable."
        else:
            ttype, tidx, tname = m.group(1), int(m.group(2)), m.group(3)
            if tname and tname != timeline.GetName():
                msg = ("Last captions were made on timeline \"%s\".\n"
                       "Switch to that timeline, then Undo again." % tname)
            else:
                removed = True
                try:
                    if 1 <= tidx <= timeline.GetTrackCount(ttype):
                        timeline.DeleteTrack(ttype, tidx)
                except Exception:
                    removed = False
                if removed:
                    rm(run.last_gen)
                    pm.SaveProject()
                    msg = ("Removed the last generated caption track (%s track "
                           "%d).\nProject saved." % (ttype, tidx))
                else:
                    msg = ("Could not remove the caption track — it may have "
                           "been deleted or moved already.")
    log("Undo mode: " + msg.replace("\n", " | "))
    run.report(msg)
    run.cleanup()


# ── Clip ranges for the timeline remap ──────────────────────────────────────

def collect_clip_ranges(run, timeline, clips, fps, tl_start):
    """Write the per-clip source ranges transcribe.py remaps words with, and
    return (count, primary_audio_path).

    Each clip records its own source file path so correction clips (re-takes
    from a different file dropped on the same track) are transcribed too,
    rather than skipped.
    """
    lines = []
    audio_path = ""
    for c in clips:
        try:
            cmpi = c.GetMediaPoolItem()
        except Exception:
            cmpi = None
        if not cmpi:
            log("Skipping clip with no media pool item")
            continue
        cpath = (cmpi.GetClipProperty() or {}).get("File Path") or ""
        if not cpath:
            log("Skipping clip with no source file path")
            continue
        src_start = c.GetLeftOffset()
        c_tl_start = c.GetStart()
        tl_frames = c.GetEnd() - c_tl_start
        try:
            speed = c.GetPlayBackSpeed()
        except Exception:
            speed = 1.0
        if not speed:
            speed = 1.0
        # A reversed clip reports a negative speed, which made src_end land
        # BEFORE src_start. transcribe.py selects words with
        # src_start <= t < src_end, so an inverted window matched nothing and
        # the clip silently got no subtitles at all. Use the magnitude: the
        # source region covered is the same either way (the words' order within
        # it is a separate problem, and one this pipeline cannot solve by
        # reversing timestamps).
        span = int(abs(tl_frames * speed) + 0.5)
        if speed < 0:
            log("Clip at frame %d is reversed (speed %.3f) — transcribing its "
                "source range, but cue order inside it will follow the source, "
                "not the reverse." % (c_tl_start, speed))
        src_end = src_start + max(1, span)
        lines.append("%d %d %d %s %d %s" % (src_start, src_end, c_tl_start,
                                            ("%g" % fps), tl_start, cpath))
        if not audio_path:
            audio_path = cpath
    if lines:
        write_text(run.ranges, "\n".join(lines) + "\n")
    return len(lines), audio_path


def timeline_timecode(fps, tl_start):
    """Timecode string for SetCurrentTimecode (needed to anchor SRT import).

    Timecode counts at the NOMINAL rate, never the real one: frame 86400 on a
    23.976 timeline is 01:00:00:00, not the 01:00:03:24 that dividing by 23.976
    gives. Using fps here left the frame field fractional (86400 % 23.976 =
    24.9), which %02d then truncated, and the anchor landed ~86 frames off on
    every NTSC timeline. Integer rates are unaffected -- 24, 25, 30 round to
    themselves.
    """
    tc_fps = max(1, int(fps + 0.5))
    frames = int(tl_start % tc_fps)
    secs = int(tl_start // tc_fps)
    return "%02d:%02d:%02d:%02d" % (secs // 3600, (secs // 60) % 60,
                                    secs % 60, frames)


# ── Styling the imported cues ───────────────────────────────────────────────

def apply_styles(items, caption, style, script_fonts, font_override,
                 style_override, text_size, srt_posy, outline, shadow,
                 cap_color, fps, tl_start):
    """The user's font/colour/stroke/shadow/weight choices, applied to the
    subtitle cues. Returns (script counts, font used per script) for the log."""
    def_font = style.get("fontFace", "Noto Serif Bengali")
    dev_font = style.get("fontFaceDevanagari", "Vesper Libre")
    script_counts, font_used = {}, {}

    def font_for(text):
        """The font one cue should be set in. An explicit choice in the form
        always wins; otherwise the cue's own script decides, and only a cue in
        no script we know about falls back to the default."""
        if font_override:
            return font_override
        tag = script_of(text)
        if tag:
            if script_fonts.get(tag):
                return script_fonts[tag]
            # No map (an older loader) -- the one script that had its own font
            # before this existed still gets it.
            if tag == "deva" and dev_font:
                return dev_font
        return def_font

    manual_rgb = hex_rgb3(cap_color) if cap_color else None
    size = None
    try:
        size = float(text_size) if text_size else None
    except ValueError:
        size = None
    posy = None
    try:
        posy = float(srt_posy) if srt_posy else None
    except ValueError:
        posy = None

    for item in items:
        try:
            text = item.GetName() or ""
        except Exception:
            text = ""
        # One font per cue, chosen by the script the cue is written in, so a
        # mixed-language timeline sets each subtitle in a family that has its
        # glyphs instead of putting everything but Devanagari in one default.
        fam = font_for(text)
        item.SetProperty("fontFace", fam)
        tag = script_of(text)
        if tag:
            script_counts[tag] = script_counts.get(tag, 0) + 1
            font_used[tag] = fam
        for k, v in style.items():
            if k not in SKIP_STYLE_KEYS:
                item.SetProperty(k, v)
        # User style overrides from the dialog: text size + outline/shadow.
        if size and size > 0:
            item.SetProperty("fontSize", size)
        # Where the cue sits. The loader sends this already converted to pixels
        # for this timeline's height, because it is the side that knows both the
        # fraction the user picked and the frame it was picked against. A reel
        # needs the text much higher than an HD cut does, so a single hardcoded
        # posY cannot serve both.
        if posy and posy > 0:
            item.SetProperty("customPosition", 1)
            item.SetProperty("posY", posy)
        item.SetProperty("strokeEnabled", 1 if outline == "1" else 0)
        item.SetProperty("shadowEnabled", 1 if shadow == "1" else 0)
        # Weight/style: subtitle items only expose bold/italic flags, so map the
        # chosen weight onto those ("Medium"/"Light" -> regular weight).
        if style_override:
            low = style_override.lower()
            item.SetProperty("bold", 1 if "bold" in low else 0)
            item.SetProperty("italic", 1 if "italic" in low else 0)
        # Colour: a manual dialog colour applies to every cue; otherwise fall
        # back to the per-speaker colour matched by time.
        col = None
        if manual_rgb:
            col = {"r": manual_rgb[0], "g": manual_rgb[1],
                   "b": manual_rgb[2], "a": 1}
        else:
            try:
                sec = (item.GetStart() - tl_start) / fps
            except Exception:
                sec = None
            if sec is not None:
                seg = segment_for_time(caption, sec)
                col = speaker_color(caption, seg["spk"] if seg else 0)
        if col:
            try:
                item.SetProperty("color", col)
            except Exception:
                pass
    return script_counts, font_used


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    r = get_resolve()
    if not r:
        # A menu script gets `resolve` handed to it, so reaching this means the
        # script is being run some other way -- from fuscript or an external
        # interpreter, where the connection is the one the External scripting
        # preference governs.
        alert_error("Srutilekha",
                    "Cannot connect to DaVinci Resolve.\n\nIf you started this "
                    "script from outside Resolve, set Preferences > System > "
                    "General > External scripting using to Local, then try "
                    "again.\n\nOtherwise run it from Workspace > Scripts > "
                    "Srutilekha.")
        return

    log("Script started (Python host: %s)" % sys.version.split()[0])
    pm = r.GetProjectManager()
    project = pm.GetCurrentProject()
    if not project:
        alert_error("Srutilekha", "No project is open.")
        return

    timeline = project.GetCurrentTimeline()
    if not timeline:
        alert_error("Srutilekha",
                    "No active timeline. Open a timeline in the Edit page "
                    "first.")
        return

    track_count = timeline.GetTrackCount("audio")
    if not track_count:
        alert_error("Srutilekha", "No audio tracks in the current timeline.")
        return

    track_items = []
    for i in range(1, track_count + 1):
        name = timeline.GetTrackName("audio", i) or ("Audio %d" % i)
        track_items.append("Track %d: %s" % (i, name))

    ensure_logs_dir()
    run = Run()
    run.claim()

    # ── The form's data. The UI only renders what is actually present here, so
    #    a Resolve build that doesn't answer these settings simply shows less
    #    rather than showing a guess.
    prompt = {"items": track_items}

    def setting(key):
        try:
            v = timeline.GetSetting(key)
        except Exception:
            return None
        return v if v not in (None, "") else None

    tl_name = timeline.GetName()
    res_w, res_h = setting("timelineResolutionWidth"), \
        setting("timelineResolutionHeight")
    tl_fps = setting("timelineFrameRate")
    if tl_name:
        prompt["timeline"] = tl_name
    if res_w and res_h:
        prompt["resolution"] = "%s x %s" % (res_w, res_h)
    if tl_fps:
        # Resolve hands frame rate back as "25.0" as often as "25"; trim the
        # pointless decimal so the plate reads "25 fps", not "25.0 fps".
        prompt["fps"] = re.sub(r"\.0+$", "", str(tl_fps))
    prompt["defaults"] = {
        "settings": "15,1,2", "punct": 0, "lang": "Auto-detect", "diarize": 0,
        "min_secs": "0.4", "cps": "25", "text_size": "55", "outline": 1,
        "shadow": 1, "font": "Auto (by language)", "font_style": "Auto",
        "color": "",
    }

    if not write_text(run.prompt, json.dumps(prompt)):
        alert_error("Srutilekha", "Cannot write prompt file: " + run.prompt)
        return
    if not os.path.exists(LOADER_PY):
        alert_error("Srutilekha", "loader.pyw not found: " + LOADER_PY)
        return
    if not run.launch_loader():
        run.cleanup()
        return

    sel = run.wait_for_selection()
    if sel is None:
        return
    # Both handshake inputs are fully consumed now; the loader has them in
    # memory.
    rm(run.prompt)
    rm(run.selection)

    chosen = field(sel, "chosen")
    settings = field(sel, "settings")
    # "auto" makes transcribe.py omit language_code so Scribe detects whatever
    # is spoken; matches the form's Auto-detect default.
    lang_code = field(sel, "lang_code", "auto")
    include_punct = field(sel, "punct", "0")
    diarize = field(sel, "diarize", "0")
    min_secs = field(sel, "min_secs", "0")
    cps = field(sel, "cps", "0")
    text_size = field(sel, "text_size")
    outline = field(sel, "outline", "1")
    shadow = field(sel, "shadow", "1")
    action = field(sel, "action", "generate")
    srt_input_path = field(sel, "srt_input_path")
    # Empty means the loader could not work out the frame height, so posY stays
    # whatever subtitle_style.json says.
    srt_posy = field(sel, "srt_posy")
    words_per = field(sel, "words_per", "0")
    ref_script = field(sel, "ref_script")
    cap_font = field(sel, "font")
    cap_color = field(sel, "color")
    font_style = field(sel, "font_style", "Auto")
    # "deva=Vesper Libre|taml=Nirmala UI|...": one installed font per script,
    # resolved by the loader because only that side can ask the system what is
    # actually present. See resolve_subtitle_fonts().
    script_fonts = dict(re.findall(r"([A-Za-z]+)=([^|]+)",
                                   field(sel, "srt_fonts")))
    # "Auto" font means keep the script-aware choice; treat as no override.
    font_override = cap_font if cap_font and cap_font != "Auto (by language)" \
        else None
    # Weight/style override ("Medium", "Bold", ...). "Auto" keeps defaults.
    style_override = font_style if font_style != "Auto" else None

    log("Language code: %s  diarize=%s min_secs=%s cps=%s"
        % (lang_code, diarize, min_secs, cps))

    if action == "undo":
        do_undo(run, pm, timeline)
        return

    m = re.match(r"^Track (\d+)", chosen)
    track_index = int(m.group(1)) if m else 1
    log("Selected track index: %d" % track_index)

    clips = timeline.GetItemListInTrack("audio", track_index)
    if not clips:
        alert_error("Srutilekha", "No clips on the selected audio track.")
        run.cleanup()
        return

    try:
        fps = float(timeline.GetSetting("timelineFrameRate"))
    except (TypeError, ValueError):
        fps = 24.0
    tl_start = timeline.GetStartFrame()
    tc = timeline_timecode(fps, tl_start)

    range_count, audio_path = collect_clip_ranges(run, timeline, clips, fps,
                                                  tl_start)
    if not range_count:
        alert_error("Srutilekha",
                    "No clips on the selected track have a usable source file.")
        run.cleanup()
        return
    log("Audio file (primary): " + audio_path)
    log("Mapped %d clip range(s); anchor=frame %d" % (range_count, tl_start))

    mp = project.GetMediaPool()

    # ── Sync mode: re-time an existing SRT against this audio, text unchanged
    #    v1 scope: single audio track (no multi-clip retake remapping), no
    #    per-speaker/font styling -- the original SRT's formatting is left
    #    as-is, only start/end times change. Reuses the same args-file /
    #    done / result plumbing as Generate (loader.pyw is already running and
    #    polling the args file).
    if action == "sync":
        if not srt_input_path:
            alert_error("Srutilekha",
                        "No existing SRT path was given to sync.")
            run.cleanup()
            return
        if not os.path.exists(srt_input_path):
            alert_error("Srutilekha",
                        "Cannot read the existing SRT file:\n"
                        + srt_input_path)
            run.cleanup()
            return

        srt_out = os.path.join(tempfile.gettempdir(),
                               "srutilekha-%s-sync.srt" % run.id)
        log("Sync mode: re-timing %s against %s" % (srt_input_path, audio_path))
        if not write_text(run.args, "\n".join(
                ["SYNC", audio_path, srt_input_path, srt_out, lang_code,
                 diarize]) + "\n"):
            alert_error("Srutilekha", "Cannot write args file: " + run.args)
            run.cleanup()
            return

        code, why = run.wait_for_done()
        rm(run.done)
        if code is None:
            # The loader is gone without reporting. Say so rather than hanging.
            log("Sync abandoned (%s) — no captions applied." % why)
            if why == "timeout":
                alert_error("Srutilekha",
                            "The Srutilekha window stopped responding, so "
                            "nothing was changed on the timeline.\n\nRun the "
                            "script again.")
            run.cleanup()
            return
        # 130 = user cancelled. Not an error: stop quietly.
        if code == 130:
            log("User cancelled sync (code 130) — no captions applied.")
            run.cleanup()
            return
        if code != 0:
            err = read_text(LOADER_LOG) or "Unknown error"
            alert_error("Srutilekha - Sync failed", err[:400])
            run.cleanup()
            return
        if not os.path.exists(srt_out):
            alert_error("Srutilekha",
                        "Sync produced no output. Check:\n" + LOADER_LOG)
            run.cleanup()
            return

        ok, strack, items, created, ierr = import_srt_to_new_track(
            timeline, mp, srt_out, tc)
        rm(srt_out)
        if not ok:
            alert_error("Srutilekha", ierr or "Could not import the synced SRT.")
            run.cleanup()
            return
        record_undo(run, timeline, "subtitle", strack, created)

        cue_count = count_real_cues(items)
        pm.SaveProject()
        log("Sync done. Re-timed and imported %d subtitle cues on subtitle "
            "track %d." % (cue_count, strack))
        run.report("%d subtitle cues re-timed and imported on %s subtitle "
                   "track %d.\n\nTimeline: %s\nProject saved."
                   % (cue_count, "a new" if created else "existing", strack,
                      timeline.GetName()))
        rm(run.result)
        run.cleanup()
        return

    # ── Generate mode ──────────────────────────────────────────────────────
    # Split "settings" POSITIONALLY. The old Lua pattern skipped empty fields
    # rather than yielding them: "25,,2" came out as {"25","2"}, so a cleared
    # "Lines per cue" box silently became maxLines=2 and maxSecs=1 (the
    # fallback) instead of the values on screen. The loader now backfills blanks
    # before sending, but this side must not be the kind of parser that can
    # shift values either. Defaults match SETTINGS_DEFAULTS in loader.pyw.
    parts = [p.strip() for p in settings.split(",")[:3]]
    parts += [""] * (3 - len(parts))
    max_chars = parts[0] or "15"
    max_lines = parts[1] or "1"
    max_secs = parts[2] or "2"
    log("Split settings: chars=%s lines=%s secs=%s (raw %r)"
        % (max_chars, max_lines, max_secs, settings))

    srt_path = os.path.join(tempfile.gettempdir(),
                            "srutilekha-%s.srt" % run.id)
    log("Transcribing...")

    # Args go through a UTF-8 file, not argv, so non-ASCII paths (e.g. a curly
    # apostrophe) survive on Windows. The loader is already running and polling
    # for this file -- once written, it spawns transcribe.py and updates its
    # progress view in place.
    if not write_text(run.args, "\n".join(
            [audio_path, srt_path, max_chars, max_lines, max_secs, run.ranges,
             include_punct, lang_code, diarize, cps, min_secs, words_per,
             ref_script]) + "\n"):
        alert_error("Srutilekha", "Cannot write args file: " + run.args)
        run.cleanup()
        return
    if ref_script:
        log("Reference script: " + ref_script)

    code, why = run.wait_for_done()
    rm(run.done)
    if code is None:
        log("Run abandoned (%s) — no captions applied." % why)
        if why == "timeout":
            alert_error("Srutilekha",
                        "The Srutilekha window stopped responding, so nothing "
                        "was changed on the timeline.\n\nRun the script again.")
        run.cleanup()
        return
    if code == 130:
        log("User cancelled (code 130) — no captions applied.")
        run.cleanup()
        return
    if code != 0:
        log_text = read_text(LOADER_LOG) or ""
        # Show the ERROR line transcribe.py writes, not the head of the log. The
        # log opens with PROGRESS/status lines, so taking the first 400
        # characters showed the startup chatter and cut off before the cause.
        m = re.search(r"^ERROR: (.*)$", log_text, re.S | re.M)
        err = m.group(1) if m else ""
        if not err.strip():
            # No tagged error (crash, or killed outright): fall back to the
            # tail, which is where a traceback ends up.
            err = ("…\n" + log_text[-700:]) if len(log_text) > 700 else log_text
        if not err.strip():
            err = "Unknown error. Full log:\n" + LOADER_LOG
        alert_error("Srutilekha - Transcription failed",
                    err + "\n\nFull log:\n" + LOADER_LOG)
        run.cleanup()
        return

    if not os.path.exists(srt_path):
        alert_error("Srutilekha",
                    "Transcription produced no output.\n\nExpected: %s\n"
                    "Check:\n%s" % (srt_path, LOADER_LOG))
        run.cleanup()
        return
    log("SRT written to: " + srt_path)

    # Keep a copy of both: they are deleted with the run, and the .cap sidecar
    # -- not the SRT -- carries the per-speaker colours. Without a copy there is
    # nothing left to inspect when the cues come out wrong.
    cap_path = srt_path + ".cap"
    for src, dst in ((srt_path, os.path.join(LOGS_DIR, "last.srt")),
                     (cap_path, os.path.join(LOGS_DIR, "last.srt.cap"))):
        try:
            if os.path.exists(src):
                shutil.copyfile(src, dst)
        except OSError:
            pass

    style = load_style()
    caption = parse_caption(cap_path, fps)

    ok, strack, items, created, ierr = import_srt_to_new_track(
        timeline, mp, srt_path, tc)
    rm(srt_path)
    rm(cap_path)
    if not ok:
        alert_error("Srutilekha", ierr or "Could not import the SRT file.")
        run.cleanup()
        return
    record_undo(run, timeline, "subtitle", strack, created)

    # Any blank anchor cue that did survive is still styled below, so it stays
    # invisible rather than becoming a differently-fonted blank frame.
    count = count_real_cues(items)

    # Where the first cue landed. This used to compare against tl_start and
    # report a "delta" of 3-6 frames on every healthy run, which reads as a
    # broken anchor and is not one: the anchor cue is gone, so the first item is
    # the first REAL cue, and it belongs at the frame its own timestamp says.
    # Compare against that instead, so a non-zero delta means something.
    if items:
        first = caption["segments"][0] if caption["segments"] else None
        want = tl_start + (int(first["start"] * fps) if first else 0)
        try:
            got = items[0].GetStart()
            log("First SRT cue at frame %d (expected %d, delta %d)"
                % (got, want, got - want))
        except Exception:
            pass

    script_counts, font_used = apply_styles(
        items, caption, style, script_fonts, font_override, style_override,
        text_size, srt_posy, outline, shadow, cap_color, fps, tl_start)

    pm.SaveProject()
    log("Done. Imported %d subtitle cues%s."
        % (count, script_summary(script_counts, font_used)))

    run.report("%d subtitle cues imported%s.\n\nTimeline: %s\nProject saved."
               % (count,
                  " on subtitle track %d" % strack if strack else "",
                  timeline.GetName()))
    run.cleanup()


try:
    main()
except Exception:
    # A traceback printed to Resolve's console is easy to miss, and an
    # unhandled error here otherwise looks exactly like the menu entry doing
    # nothing -- the very symptom this port exists to fix.
    import traceback
    tb = traceback.format_exc()
    log("UNHANDLED ERROR\n" + tb)
    try:
        alert_error("Srutilekha - script error",
                    tb.strip().splitlines()[-1] + "\n\nFull traceback:\n"
                    + LOG_FILE)
    except Exception:
        pass
    raise
