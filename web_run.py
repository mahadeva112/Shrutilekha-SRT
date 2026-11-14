"""Run a caption job for the WebView2 studio: selection → worker → Resolve.

A Tk-free port of App._on_submit, _wait_for_args_and_run, _run_transcribe,
_pump, _finish_after_transcribe and the result polling in loader.pyw. The
files exchanged with the Resolve-side script are byte-for-byte the same:

  selection  written atomically by us, read by Resolve
  args       written by Resolve once it has read the selection
  done       our exit code for Resolve's wait loop
  result     Resolve's report, shown on the done screen
  ack        "ok" when the done screen is closed, "cancel" on cancel

The page polls state(); nothing here touches the window except through the
on_close callback.
"""
import json
import os
import subprocess
import threading
import time

from app_runtime import frozen, install_dir

SETTINGS_KEYS = ("max_chars", "max_lines", "max_secs")
SETTINGS_DEFAULTS = ("15", "1", "2")
GEN_STAGES = (("Preparing", 0), ("Transcribing", 40),
              ("Building subtitles", 80), ("Finalising", 95))
SYNC_STAGES = (("Preparing", 0), ("Transcribing for alignment", 40),
               ("Writing synced SRT", 90))
ARGS_TIMEOUT = 600.0
RESULT_TIMEOUT = 600.0
CREATE_NO_WINDOW = 0x08000000


def _s(value):
    return "" if value is None else str(value)


def build_selection(action, values, prompt, ctx, timeline_res):
    """The selection dict App._on_submit writes, from plain form values."""
    settings = ",".join(_s(values.get(k)).strip() or d
                        for k, d in zip(SETTINGS_KEYS, SETTINGS_DEFAULTS))
    lang = _s(values.get("lang"))
    sel = {
        "action": action,
        "chosen": _s(values.get("chosen")),
        "srt_input_path": _s(values.get("sync_srt")).strip(),
        "settings": settings,
        "punct": int(values.get("punct") or 0),
        "lang": lang,
        "lang_code": ctx["language_codes"].get(lang, "auto"),
        "diarize": int(values.get("diarize") or 0),
        "min_secs": _s(values.get("min_secs")).strip() or "0",
        "cps": _s(values.get("cps")).strip() or "0",
        "text_size": _s(values.get("text_size")).strip() or "55",
        "outline": int(values.get("outline") or 0),
        "shadow": int(values.get("shadow") or 0),
        "color": _s(values.get("color")).strip(),
        "words_per": _s(values.get("words_per")).strip() or "0",
        "ref_script": _s(values.get("ref_script")).strip(),
        "review": int(values.get("review") or 0),
        "font": _s(values.get("font")).strip(),
        "font_style": _s(values.get("font_style")).strip() or "Auto",
    }
    res = timeline_res(prompt)
    if res is not None:
        frames = ctx["frames"]
        frame = frames.get(values.get("aspect"), frames[ctx["default_frame"]])
        try:
            frac = max(0.0, min(1.0, float(_s(values.get("srt_posy")).strip())))
        except ValueError:
            frac = frame["srt_posy"]
        sel["srt_posy"] = str(int(round(frac * res[1])))
    if ctx.get("srt_fonts"):
        sel["srt_fonts"] = ctx["srt_fonts"]
    return sel


class RunController:
    def __init__(self, paths, on_close):
        # paths: selection, args, done, log, result, ack, python, script
        self.paths = paths
        self._on_close = on_close
        self._lock = threading.Lock()
        self._proc = None
        self.cancelled = False
        self.exit_code = None
        self.review = None
        self.outcome = None          # what loader.pyw should do after the window
        self.started = time.time()
        self.state = {"phase": "progress", "pct": 0, "msg": "Preparing…",
                      "title": "", "stages": [], "detail": ""}

    # ── page-facing ───────────────────────────────────────────────────────
    def snapshot(self):
        with self._lock:
            state = dict(self.state)
        state["elapsed"] = round(time.time() - self.started, 1)
        return state

    def _set(self, **fields):
        with self._lock:
            self.state.update(fields)

    def _progress(self, pct, msg=""):
        try:
            pct = max(0.0, min(100.0, float(pct)))
        except (TypeError, ValueError):
            return
        self._set(pct=pct, **({"msg": msg} if msg else {}))

    def _done(self, message, failed=False):
        self._set(phase="done", message=message, failed=failed,
                  elapsed_final=round(time.time() - self.started, 1))

    # ── start ─────────────────────────────────────────────────────────────
    def start(self, sel, review_wanted):
        """Write the selection, then follow the job. Raises OSError on write."""
        tmp = self.paths["selection"] + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(sel, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.paths["selection"])
        action = sel["action"]
        if action == "undo":
            self._set(title="Undoing", stages=[], pct=60, msg="Removing the last caption track…")
            threading.Thread(target=self._poll_result, args=(True,), daemon=True).start()
            return
        stages = SYNC_STAGES if action == "sync" else GEN_STAGES
        self._set(title="Re-timing an existing SRT" if action == "sync" else "Transcribing audio",
                  stages=[list(s) for s in stages])
        threading.Thread(target=self._job, args=(review_wanted and action != "sync",),
                         daemon=True).start()

    # ── job ───────────────────────────────────────────────────────────────
    def _job(self, review_wanted):
        deadline = time.time() + ARGS_TIMEOUT
        while time.time() < deadline:
            if self.cancelled:
                return
            if os.path.exists(self.paths["result"]):
                with open(self.paths["result"], encoding="utf-8") as f:
                    message = f.read().strip()
                self.exit_code = 1
                self._done(message, failed=True)
                return
            if os.path.exists(self.paths["args"]):
                break
            time.sleep(0.2)
        else:
            self._progress(100, "Timed out waiting for args.")
            self._finish(1)
            return
        code = self._run_worker()
        if self.cancelled or code is None:
            return
        self.exit_code = code
        if code == 0 and review_wanted and self._review_available():
            self._begin_review()
            return
        self._finish(code)

    # ── review ────────────────────────────────────────────────────────────
    def _begin_review(self):
        """App._begin_review: stop on the cue list before anything is applied."""
        import web_review
        with open(self.paths["args"], encoding="utf-8") as f:
            srt = [ln.rstrip("\r\n") for ln in f][1]
        header, segs = web_review.parse_cap(srt + ".cap", srt)
        if not segs:
            self._finish(0)              # no sidecar: apply as transcribed
            return
        self.review = {"srt": srt, "cap": srt + ".cap", "header": header, "segs": segs}
        self._set(phase="review")

    def apply_review(self, segs):
        """App._apply_review: write the edited cues, then let Resolve import."""
        import web_review
        review = getattr(self, "review", None)
        if review is None or self.state.get("phase") != "review":
            return {"ok": False, "message": "Nothing to apply."}
        final = [seg for seg in (web_review.live_segment(x) for x in segs) if seg["text"]]
        if not final:
            return {"ok": False, "message": "Every cue was deleted or emptied, so there is nothing to "
                                            "apply. Undo a deletion, or press Cancel to leave the "
                                            "timeline untouched."}
        try:
            web_review.write_srt_cap(review["srt"], review["cap"], review["header"], final)
        except Exception as exc:
            return {"ok": False, "message": "Cannot write edited captions: %s" % exc}
        self._set(phase="progress", title="Applying captions", stages=[], pct=80,
                  msg="Placing captions on the timeline…")
        threading.Thread(target=self._finish, args=(0,), daemon=True).start()
        return {"ok": True}

    def _run_worker(self):
        try:
            log_dir = os.path.dirname(self.paths["log"])
            if log_dir and not os.path.isdir(log_dir):
                os.makedirs(log_dir, exist_ok=True)
            log_f = open(self.paths["log"], "w", encoding="utf-8", errors="replace")
        except Exception as exc:
            self._progress(100, "Cannot open log file: %s" % exc)
            self._finish(1)
            return None
        startupinfo = None
        flags = 0
        if os.name == "nt":
            flags = CREATE_NO_WINDOW
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0
        cmd = [self.paths["python"], self.paths["script"], "--args-file", self.paths["args"]]
        if frozen():
            cmd = [str(install_dir() / "Srutilekha-worker.exe"), "--args-file", self.paths["args"]]
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    stdin=subprocess.DEVNULL, bufsize=1, universal_newlines=True,
                                    encoding="utf-8", errors="replace", creationflags=flags,
                                    startupinfo=startupinfo)
        except Exception as exc:
            log_f.write("ERROR: failed to launch worker: %s\n" % exc)
            log_f.close()
            self._progress(100, "Failed to launch worker: %s" % exc)
            self._finish(1)
            return None
        with self._lock:
            self._proc = proc
        if self.cancelled:
            self._kill()
            log_f.close()
            return None
        try:
            for line in proc.stdout:
                log_f.write(line)
                log_f.flush()
                text = line.strip()
                if text.startswith("PROGRESS|"):
                    parts = text.split("|", 2)
                    if len(parts) >= 2:
                        self._progress(parts[1], parts[2] if len(parts) >= 3 else "")
        except Exception:
            pass
        try:
            proc.wait(timeout=10)
        except Exception:
            pass
        try:
            proc.stdout.close()
        except Exception:
            pass
        log_f.close()
        with self._lock:
            self._proc = None
        return None if self.cancelled else proc.returncode

    def _review_available(self):
        try:
            with open(self.paths["args"], encoding="utf-8") as f:
                lines = [ln.rstrip("\r\n") for ln in f]
            return bool(lines[1]) and os.path.exists(lines[1])
        except Exception:
            return False

    def _finish(self, code):
        """Tell Resolve's wait loop how the worker ended, then follow it."""
        self.exit_code = code
        try:
            with open(self.paths["done"], "w", encoding="utf-8") as f:
                f.write(str(code))
        except Exception:
            pass
        if code == 0:
            self._progress(100, "Importing subtitles…")
            self._set(detail="")
            self._poll_result(False)
        else:
            time.sleep(0.45)
            self.outcome = {"action": "finished", "code": code}
            self._on_close()

    def _poll_result(self, undo):
        started = time.monotonic()
        while not self.cancelled:
            if os.path.exists(self.paths["result"]):
                try:
                    with open(self.paths["result"], encoding="utf-8") as f:
                        message = f.read().strip()
                except Exception:
                    message = "Done."
                failed = message.startswith("ERROR\n")
                self.exit_code = 1 if failed else 0
                self._done(message[6:] if failed else message, failed=failed)
                return
            if time.monotonic() - started > RESULT_TIMEOUT:
                if undo:
                    self.exit_code = 1
                    self._done("DaVinci Resolve never reported back.\n\n"
                               "The Srutilekha script is no longer running there — it may have "
                               "been stopped, or Resolve was closed. Nothing was changed on "
                               "the timeline. Start the script again from Workspace ▸ Scripts.")
                else:
                    self._done("The subtitles were written, but DaVinci Resolve never "
                               "reported back.\n\nThe Srutilekha script is no longer running "
                               "there — it may have been stopped, or Resolve was closed. "
                               "Start the script again from Workspace ▸ Scripts.")
                return
            time.sleep(0.25 if undo else 0.2)

    # ── leaving ───────────────────────────────────────────────────────────
    def _kill(self):
        with self._lock:
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

    def cancel(self):
        """Stop the worker first; loader.pyw then writes the 130/cancel sentinels."""
        self.cancelled = True
        self._kill()

    def close_done(self):
        try:
            with open(self.paths["ack"], "w", encoding="utf-8") as f:
                f.write("ok")
        except Exception:
            pass
        code = self.exit_code if self.exit_code is not None else 1
        self.outcome = {"action": "finished", "code": code}
        self._on_close()
