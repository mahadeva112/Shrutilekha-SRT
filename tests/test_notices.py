"""Every stopped run is told kindly: a heading that names the next step, a plain
sentence, steps, and the raw text kept under details."""
import re
import unittest

import notices

HARSH = re.compile(r"\b(error|errors|failed|failure|fatal|exception|traceback|cannot|can't|"
                   r"couldn't|could not|rejected|denied|invalid|wrong|unable)\b", re.I)

# Real reports the app can show, each with the heading it should get.
REPORTS = (
    ("Cannot connect to DaVinci Resolve.\n\nIf you started this script from outside Resolve, ...",
     "Let's connect to DaVinci Resolve"),
    ("No project is open.", "Open a project to begin"),
    ("No active timeline. Open a timeline in the Edit page first.", "Open a timeline to begin"),
    ("No audio tracks in the current timeline.", "Add audio to your timeline"),
    ("Audio source unavailable\n\nNo clips on the selected audio track.", "Choose the track with the voice"),
    ("API key not set. Open Srutilekha > API settings and save your ElevenLabs key.\n\nFull log:\nC:/l.log",
     "Connect your ElevenLabs key"),
    ("ElevenLabs rejected your API key. Open Srutilekha > API settings and save a valid key.",
     "Let's refresh your ElevenLabs key"),
    ("ElevenLabs is rate limiting this account, or the character quota for the month is used up.",
     "ElevenLabs needs a short pause"),
    ("ElevenLabs refused this request (403).", "Let's enable speech-to-text on your key"),
    ("ElevenLabs had a server error (502). This is on their end - wait a moment and run it again.",
     "ElevenLabs is catching its breath"),
    ("Could not verify the secure connection to ElevenLabs.", "Let's open a secure line to ElevenLabs"),
    ("ConnectError: [Errno 11001] getaddrinfo failed", "Let's get back online"),
    ("ElevenLabs returned no word data for C:/a.wav", "Let's find the voice"),
    ("could not align any cues — check that the SRT text matches the audio.", "Let's find the voice"),
    ("Cannot read the existing SRT file:\nC:/x.srt", "Choose the SRT to sync"),
    ("The Srutilekha window stopped responding, so nothing was changed.", "Let's start a fresh run"),
    ("The subtitles were written, but DaVinci Resolve never reported back.\n\nThe Srutilekha script "
     "is no longer running there.", "Let's start a fresh run"),
    ("Resolve could not append the SRT to the timeline.", "Your captions are ready to place again"),
    ("Resolve put the captions in the wrong place and would not place them again.",
     "Your captions are ready to place again"),
    ("loader.pyw not found: C:/x/loader.pyw", "Let's restart Srutilekha"),
    ("KeyError: 'segments'", "Let's give it another go"),
)


class NoticeTest(unittest.TestCase):
    def test_each_report_gets_its_heading(self):
        for raw, title in REPORTS:
            with self.subTest(raw=raw[:40]):
                self.assertEqual(notices.describe(raw)["title"], title)

    def test_headings_messages_and_steps_stay_positive(self):
        for title, message, steps in [r[1:] for r in notices.RULES] + [notices.GENERAL]:
            for text in [title, message] + list(steps):
                with self.subTest(text=text):
                    self.assertIsNone(HARSH.search(text), text)
                    self.assertTrue(text.strip())

    def test_raw_text_is_kept_as_details(self):
        n = notices.describe("ERROR\nKeyError: 'segments'\n\nFull log:\nC:/l.log")
        self.assertEqual(n["details"], "KeyError: 'segments'\n\nFull log:\nC:/l.log")
        self.assertTrue(n["steps"])

    def test_plain_text_lists_the_steps(self):
        text = notices.as_text(notices.describe("No project is open."))
        self.assertIn("1. Open your project in DaVinci Resolve.", text)


if __name__ == "__main__":
    unittest.main()
