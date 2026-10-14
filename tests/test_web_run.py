import json
import os
from pathlib import Path
import runpy
import sys
import tempfile
import threading
import time
import tkinter as tk
import unittest
from unittest import mock

import web_run
import web_studio

ROOT = Path(__file__).resolve().parents[1]
PROMPT = {"items": ["Track 1: Audio 1"], "defaults": {"lang": "Bengali"},
          "resolution": "1080x1920", "timeline": "Timeline 1"}


def wait_for(predicate, timeout=15):
    end = time.time() + timeout
    while time.time() < end:
        if predicate():
            return True
        time.sleep(0.05)
    return False


class RunControllerTest(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.dir = Path(scratch.name)
        self.paths = {name: str(self.dir / name) for name in
                      ("selection", "args", "done", "log", "result", "ack")}
        self.paths.update(python=sys.executable, script=str(self.dir / "worker.py"))
        self.closed = threading.Event()

    def worker(self, body):
        Path(self.paths["script"]).write_text(body, encoding="utf-8")

    def resolve(self, srt=None, result="Imported 3 captions.\nTimeline: T1\nProject saved."):
        """Play the Resolve side: selection → args, done → result."""
        def run():
            wait_for(lambda: os.path.exists(self.paths["selection"]))
            Path(self.paths["args"]).write_text("ARGS\n%s\n" % (srt or self.dir / "none.srt"), encoding="utf-8")
            if wait_for(lambda: os.path.exists(self.paths["done"])) and result is not None:
                if Path(self.paths["done"]).read_text() == "0":
                    Path(self.paths["result"]).write_text(result, encoding="utf-8")
        threading.Thread(target=run, daemon=True).start()

    def job(self):
        return web_run.RunController(self.paths, self.closed.set)

    def test_successful_run_reports_progress_then_resolve_result(self):
        self.worker("import time\nfor p in (10, 50, 90):\n    print('PROGRESS|%d|step %d' % (p, p), flush=True); time.sleep(.1)\n")
        self.resolve()
        job = self.job()
        job.start({"action": "generate", "chosen": "T"}, review_wanted=False)
        self.assertEqual(json.loads(Path(self.paths["selection"]).read_text())["chosen"], "T")
        self.assertTrue(wait_for(lambda: job.snapshot()["phase"] == "done"))
        state = job.snapshot()
        self.assertFalse(state["failed"])
        self.assertTrue(state["message"].startswith("Imported 3 captions."))
        self.assertEqual(Path(self.paths["done"]).read_text(), "0")
        self.assertIn("PROGRESS|90|step 90", Path(self.paths["log"]).read_text())
        job.close_done()
        self.assertEqual(Path(self.paths["ack"]).read_text(), "ok")
        self.assertEqual(job.outcome, {"action": "finished", "code": 0})
        self.assertTrue(self.closed.is_set())

    def test_failed_worker_reports_its_code_and_closes(self):
        self.worker("import sys\nsys.exit(3)\n")
        self.resolve(result=None)
        job = self.job()
        job.start({"action": "generate"}, review_wanted=False)
        self.assertTrue(self.closed.wait(15))
        self.assertEqual(Path(self.paths["done"]).read_text(), "3")
        self.assertEqual(job.outcome, {"action": "finished", "code": 3})

    def test_resolve_preflight_error_is_shown_as_failure(self):
        job = self.job()
        Path(self.paths["result"]).write_text("No audio on track 3.", encoding="utf-8")
        job.start({"action": "generate"}, review_wanted=False)
        self.assertTrue(wait_for(lambda: job.snapshot()["phase"] == "done"))
        self.assertTrue(job.snapshot()["failed"])
        self.assertEqual(job.exit_code, 1)

    def test_review_pauses_then_apply_writes_edits_and_imports(self):
        srt = self.dir / "out.srt"
        srt.write_text("1\n", encoding="utf-8")
        Path(str(srt) + ".cap").write_text(
            "SPK 1 #ffffff A\nSEG 0.000 1.000 1\nWRD 0.000 0.500 Hello\nWRD 0.500 1.000 world\n"
            "SEG 1.500 2.000 1\nWRD 1.500 2.000 Bye\n", encoding="utf-8")
        self.worker("print('PROGRESS|100|done', flush=True)\n")
        self.resolve(srt=srt)
        job = self.job()
        job.start({"action": "generate"}, review_wanted=True)
        self.assertTrue(wait_for(lambda: job.snapshot()["phase"] == "review"))
        self.assertFalse(os.path.exists(self.paths["done"]))      # Resolve still waits
        self.assertEqual([s["text"] for s in job.review["segs"]], ["Hello world", "Bye"])
        self.assertFalse(job.apply_review([dict(s, text=" ") for s in job.review["segs"]])["ok"])
        edited = [dict(job.review["segs"][0], text="Hello there"), dict(job.review["segs"][1], text="")]
        self.assertTrue(job.apply_review(edited)["ok"])
        self.assertTrue(wait_for(lambda: job.snapshot()["phase"] == "done"))
        self.assertEqual(Path(self.paths["done"]).read_text(), "0")
        self.assertIn("Hello there", srt.read_text(encoding="utf-8"))
        self.assertNotIn("Bye", srt.read_text(encoding="utf-8"))
        self.assertFalse(self.closed.is_set())

    def test_review_without_cues_imports_directly(self):
        srt = self.dir / "out.srt"
        srt.write_text("1\n", encoding="utf-8")
        self.worker("print('PROGRESS|100|done', flush=True)\n")
        self.resolve(srt=srt)
        job = self.job()
        job.start({"action": "generate"}, review_wanted=True)
        self.assertTrue(wait_for(lambda: job.snapshot()["phase"] == "done"))
        self.assertEqual(Path(self.paths["done"]).read_text(), "0")

    def test_cancel_stops_the_worker(self):
        self.worker("import time\nprint('PROGRESS|40|uploading', flush=True)\ntime.sleep(60)\n")
        self.resolve(result=None)
        job = self.job()
        job.start({"action": "generate"}, review_wanted=False)
        self.assertTrue(wait_for(lambda: job.snapshot()["pct"] == 40))
        started = time.time()
        job.cancel()
        self.assertLess(time.time() - started, 10)
        self.assertIsNone(job._proc)
        self.assertFalse(os.path.exists(self.paths["done"]))   # loader writes 130

    def test_undo_waits_for_resolve(self):
        job = self.job()
        job.start({"action": "undo"}, review_wanted=False)
        self.assertEqual(job.snapshot()["title"], "Undoing")
        Path(self.paths["result"]).write_text("ERROR\nNo Srutilekha track to undo.", encoding="utf-8")
        self.assertTrue(wait_for(lambda: job.snapshot()["phase"] == "done"))
        self.assertEqual(job.snapshot()["message"], "No Srutilekha track to undo.")
        self.assertEqual(job.exit_code, 1)


class SelectionParityTest(unittest.TestCase):
    """build_selection must write what the Tk form's _on_submit writes."""
    def test_matches_tk_form(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        ns = runpy.run_path(str(ROOT / "loader.pyw"))
        ns["App"].__init__.__globals__.update(
            updater=None, data_dir=lambda: scratch.name,
            _steal_focus=lambda root: None, _keep_topmost=lambda root: None)
        ctx = dict(languages=ns["LANGUAGES"], language_codes=ns["LANGUAGE_CODES"],
                   frames=ns["FRAME_FORMATS"], default_frame=ns["DEFAULT_FRAME"],
                   caption_fonts=ns["CAPTION_FONTS"], font_styles=ns["FONT_STYLES"])
        values = web_studio.initial_values(PROMPT, ctx)
        values.update(aspect="HD", srt_posy="0.137", max_lines="", cps=" 21 ", diarize=1,
                      sync_srt=" C:/x.srt ", color=" #abcdef ", font_style="")
        root = tk.Tk()
        root.withdraw()
        p = Path(scratch.name)
        with mock.patch.object(ns["App"], "_wait_for_args_and_run", lambda self: None):
            ns["App"](root, PROMPT, str(p / "tk-sel"), str(p / "a"), str(p / "d"), str(p / "l"),
                      "u", "u", str(p / "r"), str(p / "k"), prefill={"action": "sync", "values": values})
            ctx["srt_fonts"] = ns["encode_subtitle_fonts"](ns["resolve_subtitle_fonts"]())
        try:
            root.update()
        except tk.TclError:
            pass
        root.destroy()
        tk_sel = json.loads((p / "tk-sel").read_text(encoding="utf-8"))
        web_sel = web_run.build_selection("sync", values, PROMPT, ctx, web_studio.timeline_res)
        self.assertEqual(web_sel, tk_sel)


if __name__ == "__main__":
    unittest.main()
