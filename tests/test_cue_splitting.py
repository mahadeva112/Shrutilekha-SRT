import unittest

import transcribe as T


def spoken(text, word=0.30, step=0.38, pause=0.70):
    """Word timings for ``text``; "|" marks a pause the speaker made."""
    words, t = [], 0.0
    for tok in text.split():
        if tok == "|":
            t += pause
            continue
        words.append(T._Word(tok, t, t + word, None))
        t += step
    return words


SPEECH = ("আমি আজ সকালে বাজারে গিয়েছিলাম | তারপর বন্ধুর সাথে দেখা হল | "
          "আমরা অনেক গল্প করলাম আর চা খেলাম")


class PauseChunkingTest(unittest.TestCase):

    def test_no_cue_spans_a_pause(self):
        for lines in (1, 2):
            for cue in T.build_cues(spoken(SPEECH), 15, lines, 4.0):
                words = cue[4]
                gaps = [b[1] - a[2] for a, b in zip(words, words[1:])]
                self.assertTrue(all(g < 0.5 for g in gaps), (lines, cue[3]))

    def test_two_lines_gives_one_cue_per_spoken_phrase(self):
        cues = T.build_cues(spoken(SPEECH), 15, 2, 4.0)
        self.assertEqual([c[3] for c in cues], [
            "আমি আজ সকালে বাজারে\nগিয়েছিলাম",
            "তারপর বন্ধুর সাথে\nদেখা হল",
            "আমরা অনেক গল্প\nকরলাম আর চা খেলাম",
        ])


class WrapTest(unittest.TestCase):

    def test_phrase_moves_to_the_free_line_whole(self):
        self.assertEqual(T.wrap("वह घर जा रहा है", 8, 2, "hi"), "वह घर\nजा रहा है")

    def test_single_line_still_overflows_rather_than_orphaning(self):
        self.assertEqual(T.wrap("वह घर जा रहा है", 8, 1, "hi"), "वह घर जा रहा है")


if __name__ == "__main__":
    unittest.main()
