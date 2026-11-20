"""Per-speaker colour through SRT <font color> tags.

Resolve refuses every scripted subtitle style write, but its SRT import shows
<font color> tags (checked live on Resolve 21.2.0.6 Free, 2026-11-20)."""
from pathlib import Path
import tempfile
import unittest

import transcribe as T

PALETTE = ["#FFFFFF", "#FFD400", "#00E5FF"]


def cue(i, s, e, text, spk):
    words = [(w, s, e, spk) for w in text.split()]
    return (i, s, e, text, words)


class SpeakerColourTest(unittest.TestCase):
    def test_two_speakers_are_coloured_and_white_stays_bare(self):
        cues = [cue(1, 1.0, 2.0, "first voice", "speaker_0"),
                cue(2, 2.5, 3.5, "second voice", "speaker_1"),
                cue(3, 4.0, 5.0, "first again", "speaker_0")]
        srt = T.to_srt(cues, PALETTE)
        # Speaker 1 gets palette white: untagged, so Track Style colours it.
        self.assertIn("\nfirst voice\n", srt)
        self.assertIn('<font color="#FFD400">second voice</font>', srt)
        self.assertEqual(srt.count("<font"), 1)

    def test_single_speaker_or_no_palette_writes_no_tags(self):
        one = [cue(1, 1.0, 2.0, "only me", "speaker_3"),
               cue(2, 2.5, 3.5, "still me", "speaker_3")]
        self.assertNotIn("<font", T.to_srt(one, ["#FF0000", "#00FF00"]))
        two = [cue(1, 1.0, 2.0, "a", "x"), cue(2, 2.5, 3.5, "b", "y")]
        self.assertNotIn("<font", T.to_srt(two))

    def test_numbering_matches_the_sidecar(self):
        cues = [cue(1, 1.0, 2.0, "a", "speaker_7"), cue(2, 2.5, 3.5, "b", "speaker_2")]
        palette = ["#111111", "#222222"]
        srt = T.to_srt(cues, palette)
        cap = T.to_caption_sidecar(cues, 25, palette)
        self.assertIn('<font color="#111111">a</font>', srt)
        self.assertIn('<font color="#222222">b</font>', srt)
        self.assertIn("SPK 1 #111111", cap)
        self.assertIn("SPK 2 #222222", cap)

    def test_each_line_is_tagged_on_its_own(self):
        self.assertEqual(T.color_cue_text("one\ntwo", "#00E5FF"),
                         '<font color="#00E5FF">one</font>\n<font color="#00E5FF">two</font>')
        self.assertEqual(T.color_cue_text("x", "not a colour"), "x")
        self.assertEqual(T.color_cue_text("x", "#ffffff"), "x")

    def test_parse_srt_drops_colour_tags(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "a.srt"
            path.write_text('1\n00:00:01,000 --> 00:00:02,000\n<font color="#FF0000">red words</font>\n',
                            encoding="utf-8")
            self.assertEqual(T.parse_srt(str(path)), [(1.0, 2.0, "red words")])


if __name__ == "__main__":
    unittest.main()
