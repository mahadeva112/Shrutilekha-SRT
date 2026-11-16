import os
import shutil
import tempfile
import unittest
from unittest import mock

import transcribe as T


class _W:
    def __init__(self, text, start, end, speaker_id=None):
        self.text, self.start, self.end, self.speaker_id = text, start, end, speaker_id


class CoveringWindowCacheTest(unittest.TestCase):
    """A smaller window inside an already-transcribed one must not be paid
    for again."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cache = os.path.join(self.tmp, "cache")
        os.makedirs(self.cache)
        self.audio = os.path.join(self.tmp, "a.wav")
        with open(self.audio, "wb") as f:
            f.write(b"RIFF" + os.urandom(4096))
        self.uploads = []
        self.slices = []

        def slice_audio(path, start, end, dest):
            self.slices.append((start, end))
            with open(dest, "wb") as f:
                f.write(b"x" * 2048)
            return True

        def upload(path, lang, diarize, client):
            start, end = self.slices[-1]
            self.uploads.append((start, end))
            # One word per second, relative to the uploaded slice.
            return [_W("w%d" % t, float(t - start), float(t - start) + 0.5)
                    for t in range(int(start), int(end))]

        patches = [mock.patch.object(T, "_cache_dir", return_value=self.cache),
                   mock.patch.object(T, "_slice_audio", side_effect=slice_audio),
                   mock.patch.object(T, "_transcribe_upload", side_effect=upload)]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def fetch(self, windows):
        return T.fetch_words_ranged(self.audio, windows, "ben", False, None)

    def test_shrunk_window_reuses_larger_transcript(self):
        self.fetch([(10.0, 40.0)])
        self.assertEqual(self.uploads, [(10.0, 40.0)])
        words = self.fetch([(15.0, 30.0)])
        self.assertEqual(self.uploads, [(10.0, 40.0)])  # no second upload
        self.assertEqual([w.text for w in words],
                         ["w%d" % t for t in range(15, 30)])
        self.assertEqual(words[0].start, 15.0)  # still in source timebase

    def test_two_windows_in_one_cached_window_do_not_duplicate(self):
        self.fetch([(0.0, 60.0)])
        words = self.fetch([(5.0, 10.0), (20.0, 25.0)])
        self.assertEqual(len(self.uploads), 1)
        texts = [w.text for w in words]
        self.assertEqual(texts, ["w5", "w6", "w7", "w8", "w9",
                                 "w20", "w21", "w22", "w23", "w24"])

    def test_resplit_path_uses_covering_window(self):
        self.fetch([(10.0, 40.0)])
        got = T._cached_words_for_windows(self.audio, [(12.0, 20.0)],
                                          "scribe_v2", "ben", False)
        self.assertIsNotNone(got)
        self.assertEqual([w.text for w in got],
                         ["w%d" % t for t in range(12, 20)])

    def test_grown_window_is_still_transcribed(self):
        self.fetch([(10.0, 40.0)])
        self.fetch([(10.0, 45.0)])
        self.assertEqual(self.uploads, [(10.0, 40.0), (10.0, 45.0)])

    def test_other_language_is_not_a_cover(self):
        self.fetch([(10.0, 40.0)])
        T.fetch_words_ranged(self.audio, [(15.0, 30.0)], "hin", False, None)
        self.assertEqual(len(self.uploads), 2)

    def test_unindexed_window_joins_index_on_exact_hit(self):
        key = T._slice_cache_key(self.audio, "scribe_v2", "ben", False, 0.0, 30.0)
        T._cache_store(key, [_W("w%d" % t, float(t), t + 0.5) for t in range(30)])
        self.fetch([(0.0, 30.0)])        # exact hit, no upload
        self.fetch([(5.0, 10.0)])        # now served by the indexed window
        self.assertEqual(self.uploads, [])


if __name__ == "__main__":
    unittest.main()
