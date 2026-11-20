import json
from pathlib import Path
import re
import runpy
import tempfile
import unittest

import web_review

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = json.loads((ROOT / "tests" / "data" / "tk_editor_golden.json").read_text(encoding="utf-8"))["review"]
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


def plain(value):
    """Tuples as lists, the way the recorded JSON holds them."""
    return json.loads(json.dumps(value, ensure_ascii=False))


class ReviewParityTest(unittest.TestCase):
    """The web review must cut, split, merge and write exactly as the Tk editor
    did. GOLDEN is that editor's output for CAP, recorded before it was retired."""

    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.dir = Path(scratch.name)
        self.codes = runpy.run_path(str(ROOT / "loader.pyw"))["LANGUAGE_CODES"]
        self.cap = self.dir / "out.srt.cap"
        self.cap.write_text(CAP, encoding="utf-8")
        self.header, self.segs = web_review.parse_cap(str(self.cap))
        self.values = dict(GOLDEN["values"])
        self.s = web_review.settings(self.values, self.codes)

    def live(self):
        return [web_review.live_segment(seg) for seg in self.segs]

    def test_parse_and_settings_match(self):
        self.assertEqual(plain([self.header, self.segs]), [GOLDEN["header"], GOLDEN["segs"]])
        self.assertEqual(plain({str(k): v for k, v in web_review.spk_colors(self.header).items()}),
                         GOLDEN["spk_colors"])
        self.assertEqual(plain(self.s), GOLDEN["settings"])
        self.assertEqual(plain(self.live()), GOLDEN["live"])

    def test_resplit_matches(self):
        for max_chars in ("8", "30"):
            s = web_review.settings(dict(self.values, max_chars=max_chars), self.codes)
            expected = GOLDEN["resplit"][max_chars]
            self.assertEqual(plain(s), expected["settings"])
            self.assertEqual(plain(web_review.resplit(self.live(), s)), expected["segs"])

    def test_edited_text_split_and_merge_match(self):
        segs = [dict(seg) for seg in self.segs]
        segs[0]["text"] = "আমি আজ বাড়ি ফিরব"
        live = [web_review.live_segment(seg) for seg in segs]
        self.assertEqual(plain(live), GOLDEN["edited_live"])
        split = [web_review.live_segment(x) for x in
                 web_review.split(live, 0, GOLDEN["split_n_left"], self.s)]
        self.assertEqual(plain(split), GOLDEN["after_split"])
        merged = [web_review.live_segment(x) for x in web_review.merge(split, 1, self.s)]
        self.assertEqual(plain(merged), GOLDEN["after_merge"])

    def test_written_files_match(self):
        live = self.live()
        live[1]["text"] = "তুমি কখন আসবে"
        out = self.dir / "web"
        out.mkdir()
        web_review.write_srt_cap(str(out / "a.srt"), str(out / "a.cap"), self.header, live)
        srt = (out / "a.srt").read_bytes().decode("utf-8")
        # Since the per-speaker colour tags, the SRT is the Tk editor's plus a
        # <font color> per cue from its speaker's SPK colour; nothing else moves.
        self.assertEqual(re.sub(r"</?font[^>]*>", "", srt), GOLDEN["written_srt"])
        self.assertIn('<font color="#7fb3ff">আমি আজ বাড়ি যাব।</font>', srt)
        self.assertIn('<font color="#ffb37f">তুমি কখন আসবে</font>', srt)
        self.assertIn('<font color="#7fb3ff">ঠিক আছে।</font>', srt)
        self.assertEqual((out / "a.cap").read_bytes(), GOLDEN["written_cap"].encode("utf-8"))

    def test_one_speaker_left_writes_no_colour(self):
        live = [seg for seg in self.live() if seg["spk"] == 1]
        out = self.dir / "web"
        out.mkdir()
        web_review.write_srt_cap(str(out / "a.srt"), str(out / "a.cap"), self.header, live)
        self.assertNotIn("<font", (out / "a.srt").read_text(encoding="utf-8"))

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
        self.assertIn('<font color="#7fb3ff">আমি আজ</font>\n<font color="#7fb3ff">বাড়ি যাব।</font>',
                      (out / "a.srt").read_text(encoding="utf-8"))
        # Reading the tagged SRT back gives the plain wrapped text again.
        _, again = web_review.parse_cap(str(out / "a.cap"), str(out / "a.srt"))
        self.assertEqual(again[0]["text"], "আমি আজ\nবাড়ি যাব।")
        # A wrap is not an edit: the real word timings survive.
        self.assertIn("WRD 0.450 0.900 আজ", (out / "a.cap").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
