"""WebView2 Master Studio form.

loader.pyw calls run() before it builds any Tk window. The page collects the
same values as the Tk form; the result goes back to loader, which feeds them
into App._on_submit so the selection file, Resolve handshake, progress and
review all stay on the existing, tested path.

run() returns None when the web UI is unavailable (the caller then shows the
Tk form), or a dict: {"action": "cancel" | "superseded"} or
{"action": "generate" | "sync" | "undo", "values": {...}}.
"""
import json
import os
import re
import threading

import web_ui
from app_runtime import data_dir, frozen, user_dir

# What a preset stores. Preset files keep the Tk form's format: these keys
# plus "_settings" = [max chars, lines, max secs]. Caption style (font, size,
# colour, outline, shadow, position) is left out: Resolve's scripting API cannot
# style subtitle cues, so the page no longer offers it and an older preset's
# style fields are ignored on load.
PRESET_KEYS = ("min_secs", "cps", "lang", "punct", "diarize", "words_per",
               "review")
SETTINGS_KEYS = ("max_chars", "max_lines", "max_secs")
SETTINGS_DEFAULTS = ("15", "1", "2")
TOGGLES = ("punct", "diarize", "outline", "shadow", "safe_zone", "review")


def timeline_res(prompt):
    for key in ("resolution", "timeline_res"):
        raw = prompt.get(key)
        m = re.search(r"(\d+)\s*[x×]\s*(\d+)", str(raw or ""))
        if m and int(m.group(1)) > 0 and int(m.group(2)) > 0:
            return int(m.group(1)), int(m.group(2))
    return None


def timeline_crumb(prompt):
    bits = []
    for keys in (("timeline", "timeline_name"), ("resolution", "timeline_res"), ("duration",)):
        for key in keys:
            if prompt.get(key):
                bits.append(str(prompt[key]))
                break
    return " · ".join(bits)


def initial_values(prompt, ctx):
    """The Tk form's _declare_vars, as plain data."""
    d = prompt.get("defaults", {}) or {}
    items = prompt.get("items", []) or []
    parts = [p.strip() for p in str(d.get("settings", ",".join(SETTINGS_DEFAULTS))).split(",")]
    parts += [""] * (len(SETTINGS_DEFAULTS) - len(parts))
    frames = ctx["frames"]
    res = timeline_res(prompt)
    aspect = d.get("aspect") or (ctx["default_frame"] if res is None else "Reel" if res[1] > res[0] else "HD")
    if aspect not in frames:
        aspect = ctx["default_frame"]
    lang = d.get("lang", ctx["languages"][0])
    if lang not in ctx["languages"]:
        lang = ctx["languages"][0]
    style = str(d.get("font_style", "Auto"))
    values = {
        "task": "Generate",
        "chosen": items[0] if items else "",
        "lang": lang,
        "min_secs": str(d.get("min_secs", "0.4")),
        "cps": str(d.get("cps", "25")),
        "text_size": str(d.get("text_size", "55")),
        "words_per": str(d.get("words_per", "0")),
        "aspect": aspect,
        "srt_posy": str(d.get("srt_posy") or frames[aspect]["srt_posy"]),
        "sync_srt": "",
        "ref_script": d.get("ref_script", ""),
        "color": str(d.get("color", "")),
        "font": str(d.get("font", ctx["caption_fonts"][0])),
        "font_style": style if style in ctx["font_styles"] else "Auto",
    }
    for key, part, default in zip(SETTINGS_KEYS, parts, SETTINGS_DEFAULTS):
        values[key] = part or default
    for key, default in (("punct", 0), ("diarize", 0), ("outline", 1),
                         ("shadow", 1), ("safe_zone", 1), ("review", 1)):
        values[key] = int(d.get(key, default))
    return values


class StudioApi(web_ui.BaseApi):
    def __init__(self, prompt, ctx):
        super().__init__(ctx.get("updater"))
        self._prompt = prompt
        self._ctx = ctx
        self._presets_dir = os.path.join(data_dir(), "presets")
        self.result = None

    # ── page state ────────────────────────────────────────────────────────
    def initial(self):
        ctx, prompt = self._ctx, self._prompt
        res = timeline_res(prompt)
        return {
            "version": getattr(self._updater, "VERSION", ""),
            "hasKey": self._has_key(),
            "needsKey": bool(ctx.get("frozen")),
            "items": prompt.get("items", []) or [],
            "languages": list(ctx["languages"]),
            "frames": ctx["frames"],
            "fonts": list(ctx["caption_fonts"][:1]) + sorted(set(ctx.get("families") or ctx["caption_fonts"][1:])),
            "fontStyles": list(ctx["font_styles"]),
            "demo": ctx["demo_captions"],
            "crumb": timeline_crumb(prompt),
            "timelineRes": list(res) if res else None,
            "fps": prompt.get("fps") or "",
            "presets": self.list_presets(),
            "values": initial_values(prompt, ctx),
        }

    # ── presets ───────────────────────────────────────────────────────────
    def list_presets(self):
        try:
            return sorted(f[:-5] for f in os.listdir(self._presets_dir) if f.endswith(".json"))
        except OSError:
            return []

    def _preset_path(self, name):
        name = (name or "").strip()
        if not name or os.path.basename(name) != name or name.startswith("."):
            raise ValueError("Use a preset name without slashes.")
        return os.path.join(self._presets_dir, name + ".json")

    def load_preset(self, name):
        try:
            with open(self._preset_path(name), encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return {"ok": False, "message": "Could not read that preset."}
        values = {k: data[k] for k in PRESET_KEYS if k in data}
        settings = data.get("_settings")
        if isinstance(settings, list) and len(settings) == len(SETTINGS_KEYS):
            values.update(zip(SETTINGS_KEYS, (str(v) for v in settings)))
        return {"ok": True, "values": values}

    def save_preset(self, name, values):
        try:
            path = self._preset_path(name)
            os.makedirs(self._presets_dir, exist_ok=True)
            data = {k: values.get(k) for k in PRESET_KEYS}
            data["_settings"] = [str(values.get(k, "")) for k in SETTINGS_KEYS]
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=1)
        except (OSError, ValueError) as exc:
            return {"ok": False, "message": "Cannot save preset: %s" % exc}
        return {"ok": True, "presets": self.list_presets()}

    def remove_preset(self, name):
        try:
            path = self._preset_path(name)
            if os.path.exists(path):
                os.remove(path)
        except (OSError, ValueError):
            return {"ok": False, "message": "Could not remove that preset."}
        return {"ok": True, "presets": self.list_presets()}

    # ── files ─────────────────────────────────────────────────────────────
    def pick_file(self, kind):
        import webview
        types = (("Script files (*.docx;*.txt;*.srt)", "Word document (*.docx)", "Text file (*.txt)",
                  "Subtitle file (*.srt)", "All files (*.*)") if kind == "script"
                 else ("Subtitle file (*.srt)", "All files (*.*)"))
        dialog = getattr(getattr(webview, "FileDialog", None), "OPEN", None) or webview.OPEN_DIALOG
        try:
            picked = self._window.create_file_dialog(dialog, allow_multiple=False, file_types=types)
        except Exception:
            return ""
        return os.path.normpath(picked[0]) if picked else ""

    # ── submit / cancel ───────────────────────────────────────────────────
    def submit(self, action, values):
        if action not in ("generate", "sync", "undo"):
            return {"ok": False, "message": "Unknown action."}
        if action != "undo":
            if self._ctx.get("frozen") and not self._has_key():
                return {"ok": False, "needKey": True, "message": "Add your ElevenLabs API key to continue."}
            if not str(values.get("chosen") or "").strip():
                return {"ok": False, "message": "Choose an audio track first."}
            if action == "sync" and not str(values.get("sync_srt") or "").strip():
                return {"ok": False, "message": "Enter the path to the existing SRT to sync."}
        if not self._ctx.get("paths"):
            # No Resolve job attached: hand the values back to the caller.
            self.result = {"action": action, "values": values}
            self.close()
            return {"ok": True}
        import web_run
        job = web_run.RunController(self._ctx["paths"], self.close)
        sel = web_run.build_selection(action, values, self._prompt, self._ctx, timeline_res)
        try:
            job.start(sel, review_wanted=bool(int(values.get("review") or 0)))
        except OSError as exc:
            return {"ok": False, "message": "Cannot write selection file: %s" % exc}
        self._job = job
        return {"ok": True, "running": True}

    # ── review (the job pauses in its "review" phase) ─────────────────────
    def review_init(self, values):
        import web_review
        review = getattr(getattr(self, "_job", None), "review", None)
        if review is None:
            return None
        self._review_s = web_review.settings(values, self._ctx["language_codes"])
        return {"segs": review["segs"], "s": self._review_s,
                "colors": {str(k): v for k, v in web_review.spk_colors(review["header"]).items()},
                "fields": web_review.SPLIT_FIELDS, "recipes": web_review.RECIPES}

    def review_resplit(self, segs, values):
        import web_review
        s = web_review.settings(values, self._ctx["language_codes"])
        try:
            out = web_review.resplit([web_review.live_segment(x) for x in segs], s)
        except Exception as exc:
            return {"ok": False, "message": "Could not re-split: %s" % exc}
        self._review_s = s
        return {"ok": True, "segs": out, "s": s}

    def review_edit(self, op, index, segs, n_left=0):
        """Split at the caret, merge with the next cue, or delete — on the live cues."""
        import web_review
        live = [web_review.live_segment(x) for x in segs]
        index = int(index)
        if not 0 <= index < len(live):
            return {"ok": False}
        if op == "split":
            out = web_review.split(live, index, n_left, self._review_s)
        elif op == "merge":
            out = web_review.merge(live, index, self._review_s)
        elif op == "delete":
            out = live[:index] + live[index + 1:]
        else:
            out = None
        return {"ok": out is not None, "segs": out}

    def review_apply(self, segs):
        job = getattr(self, "_job", None)
        return job.apply_review(segs) if job else {"ok": False, "message": "Nothing to apply."}

    def run_state(self):
        job = getattr(self, "_job", None)
        return job.snapshot() if job else None

    def close_done(self):
        job = getattr(self, "_job", None)
        if job:
            job.close_done()

    def cancel(self):
        job = getattr(self, "_job", None)
        if job:
            job.cancel()
        self.result = {"action": "cancel"}
        self.close()

    def _outcome(self):
        """What loader.pyw does once the window has closed."""
        job = getattr(self, "_job", None)
        if job is None:
            return self.result or {"action": "cancel"}
        if job.outcome is None or self.result == {"action": "cancel"}:
            job.cancel()                 # window closed mid-run counts as Cancel
            return {"action": "cancel"}
        return job.outcome

    def _after_update(self):
        # Setup replaces this install; leave Resolve's wait loop cleanly.
        self.cancel()

    # ── watchdog: newer run, raise requests ───────────────────────────────
    def _watch(self, closed):
        marker, run_id = self._ctx.get("run_marker"), self._ctx.get("run_id")
        flag = user_dir() / "raise-caption.flag"
        while not closed.is_set():
            if marker and run_id:
                try:
                    with open(marker, encoding="utf-8") as f:
                        current = f.read().strip()
                except OSError:
                    current = ""
                if (current and current != run_id and self.result is None
                        and getattr(self, "_job", None) is None):
                    self.result = {"action": "superseded"}
                    self.close()
                    return
            if flag.exists():
                try:
                    flag.unlink()
                    self._window.restore()
                    self._window.show()
                except Exception:
                    pass
            closed.wait(0.6)


def run(prompt, ctx):
    page = web_ui.page("studio.html")
    if not web_ui.available() or page is None:
        return None
    import webview
    api = StudioApi(prompt, ctx)
    try:
        screen = webview.screens[0]
        sw, sh = screen.width, screen.height
    except Exception:
        sw, sh = 1920, 1080
    width, height = min(1220, sw - 40), min(840, sh - 70)
    closed = threading.Event()
    try:
        window = webview.create_window(
            "Srutilekha", url=str(page), js_api=api, width=width, height=height,
            min_size=(min(1000, width), min(680, height)), frameless=True,
            easy_drag=False, on_top=True, background_color="#0d0f10")
        api._window = window
        window.events.closed += closed.set
        webview.start(api._watch, (closed,), gui="edgechromium", private_mode=True)
    except Exception:
        if api.result is None and getattr(api, "_job", None) is None:
            return None
    closed.set()
    return api._outcome()
