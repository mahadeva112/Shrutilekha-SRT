"""Friendly wording for anything that stops a caption run.

Every message the user can see when a run stops goes through describe(): the
alert window that Resolve's side opens (dialog.py), and the done screen in the
caption studio (web_run.py -> studio.js). The raw text is what the code that
stopped wrote: precise, but technical, and often about what went wrong. The
notice leads with what to do instead, in a calm, positive tone:

  title    a short heading that names the next step ("Open a project to begin")
  message  one or two plain sentences
  steps    what to do, in order
  details  the raw text, kept for troubleshooting; the UI shows it folded away

Rules are tried in order and the first match wins. Anything no rule knows gets
a gentle general notice, with the raw text still under details.
"""
import re

RUN_AGAIN = "Run Workspace > Scripts > Srutilekha in DaVinci Resolve again."
OPEN_SETTINGS = "Open API settings (the key button at the top right of Srutilekha)."

# (pattern, title, message, steps). Patterns are case-insensitive regexes
# searched in the raw text.
RULES = (
    (r"cannot connect to davinci resolve|resolve is not running|could not reach resolve",
     "Let's connect to DaVinci Resolve",
     "Srutilekha works together with DaVinci Resolve, so it needs Resolve open first.",
     ["Open DaVinci Resolve with your project.", RUN_AGAIN]),
    (r"no project is open",
     "Open a project to begin",
     "Srutilekha adds captions to the project that is open in DaVinci Resolve.",
     ["Open your project in DaVinci Resolve.", RUN_AGAIN]),
    (r"no active timeline|no timeline",
     "Open a timeline to begin",
     "Captions are made for the timeline you are working on.",
     ["Open your timeline on the Edit page.", RUN_AGAIN]),
    (r"no audio tracks",
     "Add audio to your timeline",
     "Captions come from the speech on an audio track, and this timeline has none yet.",
     ["Place the recording on an audio track.", RUN_AGAIN]),
    (r"audio source unavailable|no clips on the selected audio track|no audio on track|audio file not found",
     "Choose the track with the voice",
     "Pick the audio track that holds the speech, and Srutilekha will take it from there.",
     ["Check that the clips on that track are online in the Media Pool.",
      RUN_AGAIN + " Then choose the track that holds the voice."]),
    (r"api key not set|add your elevenlabs api key|paste your api key",
     "Connect your ElevenLabs key",
     "One quick step: Srutilekha needs your ElevenLabs API key to listen to the audio.",
     [OPEN_SETTINGS, "Paste your key and press Save key.", "Start the captions again."]),
    (r"rejected (your|the) api key|api key rejected|\b401\b|invalid api key",
     "Let's refresh your ElevenLabs key",
     "ElevenLabs is asking for an up-to-date API key.",
     ["Copy a current key from elevenlabs.io > Settings > API keys.", OPEN_SETTINGS,
      "Paste it, press Save key, then start the captions again."]),
    (r"rate limit|quota|\b429\b",
     "ElevenLabs needs a short pause",
     "Your ElevenLabs account has used its allowance for the moment.",
     ["See your usage at elevenlabs.io > Usage.",
      "Start the captions again in a little while, or top up your plan."]),
    (r"refused this request|\b403\b|access denied",
     "Let's enable speech-to-text on your key",
     "Your ElevenLabs key works, and it just needs speech-to-text access.",
     ["At elevenlabs.io > Settings > API keys, allow Speech to Text for this key.",
      "Start the captions again."]),
    (r"server error|\b50[0-9]\b|on their end",
     "ElevenLabs is catching its breath",
     "Their service is busy for a moment. Your settings are all kept.",
     ["Wait a minute.", "Start the captions again."]),
    (r"stopped responding|never reported back|no longer running",
     "Let's start a fresh run",
     "DaVinci Resolve and Srutilekha lost touch for a moment. Nothing on your timeline was changed.",
     [RUN_AGAIN]),
    (r"secure connection|certificate|ssl|tls|truststore",
     "Let's open a secure line to ElevenLabs",
     "This network checks secure connections in its own way, so Windows needs to vouch for ElevenLabs.",
     ["Install the latest Srutilekha from the update button.",
      "If your office uses a proxy, ask IT for its certificate."]),
    (r"could not connect|connection|timed out|timeout|getaddrinfo|name resolution|network|offline",
     "Let's get back online",
     "Srutilekha sends the audio to ElevenLabs, so it needs an internet connection.",
     ["Check that this PC is online.", "Start the captions again."]),
    (r"no word data|no subtitle cues generated|could not align any cues|produced no output",
     "Let's find the voice",
     "This audio did not give us any words to caption yet.",
     ["Choose the track where someone is speaking.",
      "Pick the spoken language, or Auto-detect.",
      "For Sync, use an SRT whose text matches the audio."]),
    (r"existing srt|srt file not found|cannot read the existing srt",
     "Choose the SRT to sync",
     "Sync re-times an SRT you already have, so it needs that file.",
     ["Browse to the SRT under Existing SRT.", "Start the sync again."]),
    (r"could not import the s?rt|could not append|placed no cues|wrong place|could not import the synced",
     "Your captions are ready to place again",
     "The captions were made, and Resolve just needs one more try to place them.",
     ["Make sure the timeline is open and its subtitle tracks are unlocked.", RUN_AGAIN]),
    (r"could not start the srutilekha window|loader\.pyw not found|cannot write (prompt|args|selection)",
     "Let's restart Srutilekha",
     "Srutilekha needs a fresh start to open its window.",
     ["Close Srutilekha from the tray if it is open.", RUN_AGAIN,
      "If it keeps happening, reinstall Srutilekha from the latest release."]),
)

GENERAL = ("Let's give it another go",
           "This run paused before the captions were placed. Another run usually sorts it out.",
           [RUN_AGAIN, "If it happens again, share the details below with support."])

def _details(raw):
    text = (raw or "").strip()
    if text.startswith("ERROR\n"):
        text = text[6:].strip()
    return text


def describe(raw):
    """{title, message, steps, details} for a run that stopped with `raw`."""
    details = _details(raw)
    for pattern, title, message, steps in RULES:
        if re.search(pattern, details, re.I):
            return {"title": title, "message": message, "steps": list(steps), "details": details}
    title, message, steps = GENERAL
    return {"title": title, "message": message, "steps": list(steps), "details": details}


def as_text(notice):
    """The notice as plain text, for places that show one block of text."""
    lines = [notice["message"]]
    if notice["steps"]:
        lines.append("")
        lines += ["%d. %s" % (n, step) for n, step in enumerate(notice["steps"], 1)]
    return "\n".join(lines)
