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
            "আমি আজ সকালে\nবাজারে গিয়েছিলাম",
            "তারপর\nবন্ধুর সাথে দেখা হল",
            "আমরা অনেক গল্প\nকরলাম আর চা খেলাম",
        ])


class WrapTest(unittest.TestCase):

    def test_phrase_moves_to_the_free_line_whole(self):
        self.assertEqual(T.wrap("वह घर जा रहा है", 8, 2, "hi"), "वह घर\nजा रहा है")

    def test_cue_gets_the_number_of_lines_asked_for(self):
        text = "आपको देखना होगा कि आप सच में यही करना चाहते हैं"
        for lines in (1, 2, 3):
            self.assertEqual(len(T.wrap(text, 60, lines, "hi").splitlines()), lines)

    def test_lines_are_balanced_not_filled(self):
        a, b = T.wrap("আমরা অনেক গল্প করলাম আর চা খেলাম", 60, 2, "bn").splitlines()
        self.assertLessEqual(abs(T._vlen(a) - T._vlen(b)), 6)

    def test_short_cue_stays_on_one_line(self):
        self.assertEqual(T.wrap("मेरी बहन", 60, 3, "hi"), "मेरी बहन")

    def test_line_never_opens_with_a_phrase_completing_word(self):
        for lines in (2, 3):
            for line in T.wrap("वह घर जा रहा है और खाना खा रहा है", 60, lines, "hi").splitlines()[1:]:
                self.assertFalse(T._binds_back(line.split()[0], "hi"), line)

    def test_single_line_still_overflows_rather_than_orphaning(self):
        self.assertEqual(T.wrap("वह घर जा रहा है", 8, 1, "hi"), "वह घर जा रहा है")


if __name__ == "__main__":
    unittest.main()
