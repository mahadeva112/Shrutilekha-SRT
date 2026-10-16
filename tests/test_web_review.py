from pathlib import Path
import runpy
import tempfile
import tkinter as tk
import unittest

import web_review

ROOT = Path(__file__).resolve().parents[1]
CAP = """FPS 25
SPK 1 #7fb3ff Speaker 1
SPK 2 #ffb37f Speaker 2
SEG 0.000 1.900 1
WRD 0.000 0.400 আমি
WRD 0.450 0.900 আজ
WRD 0.950 1.400 বাড়ি
WRD 1.450 1.900 যাব।
SEG 2.400 4.100 2
WRD 2.400 2.800 তুমি
WRD 2.850 3.300 কখন
WRD 3.350 3.700 আসবে
WRD 3.750 4.100 বলো?
SEG 4.600 5.500 1
WRD 4.600 5.000 ঠিক
WRD 5.050 5.500 আছে।
"""


class ReviewParityTest(unittest.TestCase):
    """The web review must cut, split, merge and write exactly as the Tk editor."""

    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.dir = Path(scratch.name)
        self.ns = runpy.run_path(str(ROOT / "loader.pyw"))
        self.ns["App"].__init__.__globals__.update(
            updater=None, data_dir=lambda: scratch.name,
            _steal_focus=lambda root: None, _keep_topmost=lambda root: None)
        self.cap = self.dir / "out.srt.cap"
        self.cap.write_text(CAP, encoding="utf-8")
        self.root = tk.Tk()
        self.root.withdraw()

        def close():
            # Cancel at the Tcl level: after_cancel would also drop the
            # Python callback that destroy() still expects to delete.
            for job in self.root.tk.call("after", "info"):
                self.root.tk.call("after", "cancel", job)
            self.root.destroy()
        self.addCleanup(close)
        p = self.dir
        self.app = self.ns["App"](self.root, {"items": ["T1"], "defaults": {"lang": "Bengali"},
                                              "resolution": "1080x1920"},
                                  str(p / "sel"), str(p / "args"), str(p / "done"), str(p / "log"),
                                  "u", "u", str(p / "result"), str(p / "ack"))
        self.header, self.segs = self.app._parse_cap(str(self.cap))
        self.app._build_review(str(p / "out.srt"), str(self.cap), self.header, self.segs)
        self.root.update()
        self.values = {k: v for k, v in dict(
            max_chars=self.app.settings_vars[0].get(), max_lines=self.app.settings_vars[1].get(),
            max_secs=self.app.settings_vars[2].get(), cps=self.app.cps_var.get(),
            min_secs=self.app.min_var.get(), words_per=self.app.words_per_var.get(),
            lang=self.app.lang_var.get()).items()}
        self.s = web_review.settings(self.values, self.ns["LANGUAGE_CODES"])

    def web_live(self):
        return [web_review.live_segment(dict(d["seg"], text=d["text"].get())) for d in self.app._review_rows]

    def test_parse_and_settings_match(self):
        header, segs = web_review.parse_cap(str(self.cap))
        self.assertEqual((header, segs), (self.header, self.segs))
        self.assertEqual(web_review.spk_colors(header), self.app._parse_spk_colors(header))
        self.assertEqual(self.s, self.app._split_settings())

    def test_resplit_matches(self):
        for max_chars in ("8", "30"):
            self.values["max_chars"] = max_chars
            self.app.settings_vars[0].set(max_chars)
            s = web_review.settings(self.values, self.ns["LANGUAGE_CODES"])
            tk_segs, tk_s = self.app._resplit_segments()
            self.assertEqual(s, tk_s)
            self.assertEqual(web_review.resplit(self.web_live(), s), tk_segs)

    def test_edited_text_split_and_merge_match(self):
        text = self.app._review_rows[0]["text"].text
        text.delete("1.0", "end")
        text.insert("1.0", "আমি আজ বাড়ি ফিরব")
        live = self.web_live()
        self.assertEqual(live, self.app._snapshot_segs())
        text.mark_set("insert", "1.6")
        n_left = len(text.get("1.0", "insert").split())
        expected_split = web_review.split(live, 0, n_left, self.s)
        self.app._review_rows[0]["split"]()
        self.root.update()
        self.assertEqual(self.app._snapshot_segs(), [web_review.live_segment(x) for x in expected_split])
        live = self.web_live()
        expected_merge = web_review.merge(live, 1, self.s)
        self.app._review_rows[1]["merge"]()
        self.root.update()
        self.assertEqual(self.app._snapshot_segs(), [web_review.live_segment(x) for x in expected_merge])

    def test_written_files_match(self):
        live = self.web_live()
        live[1]["text"] = "তুমি কখন আসবে"
        tk_dir, web_dir = self.dir / "tk", self.dir / "web"
        tk_dir.mkdir()
        web_dir.mkdir()
        self.app._write_srt_cap(str(tk_dir / "a.srt"), str(tk_dir / "a.cap"), self.header, live)
        web_review.write_srt_cap(str(web_dir / "a.srt"), str(web_dir / "a.cap"), self.header, live)
        for name in ("a.srt", "a.cap"):
            self.assertEqual((web_dir / name).read_bytes(), (tk_dir / name).read_bytes(), name)

    def test_two_line_cues_keep_their_wrap_through_review(self):
        srt = self.dir / "out.srt"
        srt.write_text("1\n00:00:00,000 --> 00:00:00,001\n \n\n"
                       "2\n00:00:00,000 --> 00:00:01,900\nআমি আজ\nবাড়ি যাব।\n\n"
                       "3\n00:00:02,400 --> 00:00:04,100\nতুমি কখন আসবে বলো?\n\n"
                       "4\n00:00:04,600 --> 00:00:05,500\nঠিক\nআছে।\n", encoding="utf-8")
        header, segs = web_review.parse_cap(str(self.cap), str(srt))
        self.assertEqual([s["text"] for s in segs],
                         ["আমি আজ\nবাড়ি যাব।", "তুমি কখন আসবে বলো?", "ঠিক\nআছে।"])
        live = [web_review.live_segment(s) for s in segs]
        out = self.dir / "web"
        out.mkdir()
        web_review.write_srt_cap(str(out / "a.srt"), str(out / "a.cap"), header, live)
        self.assertIn("আমি আজ\nবাড়ি যাব।", (out / "a.srt").read_text(encoding="utf-8"))
        # A wrap is not an edit: the real word timings survive.
        self.assertIn("WRD 0.450 0.900 আজ", (out / "a.cap").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
