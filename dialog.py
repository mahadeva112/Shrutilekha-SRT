"""Alert helper called by Resolve's side (audio_to_srt.py and the Lua launcher).

Usage:
  Srutilekha.exe --dialog alert       <title> <message>
  Srutilekha.exe --dialog alert_error <title> <message>
  Srutilekha.exe --dialog notify      <title> <message>

Alerts open as the app's WebView2 popup (web_notice.py). On a PC without
WebView2 they fall back to a plain Windows message box with the same words.

Exit code: 0 always (errors are printed to stderr).
"""

import sys


def alert(title, message, error=False):
    """A short message: the caller's title, its text, and OK."""
    import web_notice
    web_notice.tell({"kind": "error" if error else "info", "kicker": "",
                     "title": title, "message": message, "steps": [], "details": "",
                     "button": "OK"})


def alert_error(title, message):
    """Show a stopped run as a friendly notice. `title` is the caller's own
    label; the notice's heading, which names the next step, replaces it."""
    import notices
    import web_notice
    web_notice.tell(dict(notices.describe(message), kind="error",
                         kicker="One more step", button="Got it"))


def notify(title, message):
    # Lightweight toast — just print; a real Windows toast needs extra libs
    print(f"[{title}] {message}", file=sys.stderr)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)

    cmd = sys.argv[1]

    if cmd == "alert" and len(sys.argv) >= 4:
        alert(sys.argv[2], sys.argv[3])

    elif cmd == "alert_error" and len(sys.argv) >= 4:
        alert_error(sys.argv[2], sys.argv[3])

    elif cmd == "notify" and len(sys.argv) >= 4:
        notify(sys.argv[2], sys.argv[3])

    else:
        print(f"Unknown command or missing args: {sys.argv[1:]}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
