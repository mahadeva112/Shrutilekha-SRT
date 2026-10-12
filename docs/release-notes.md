Public stable release: standalone Windows x64 installer for Srutilekha.

- English demo captions by default, independent of transcription language and saved presets.
- A separate Demo language selector offers examples for all 14 supported languages.
- Rounded preview stage, centred multiline captions and cleaner placement display.
- Refined Studio typography: 27 px bold heading, readable 14–15 px controls, stronger labels and consistent colours.
- Larger illustrated caption samples, softer artwork and horizontal preview controls.
- Audio, Timing, Script/Files and Presets tabs retain existing caption workflows.
- Setup controls fit without scrolling at supported desktop window sizes.
- Generate has no sparkle icon. Existing transcription and Resolve workflow are retained.
- Bundled Python runtime and transcription worker; no separate Python install.
- Save your own ElevenLabs API key encrypted for your Windows user.
- API settings open inside the captions window with matching dark styling.
- Rounded account card, rounded input and buttons, and clearer spacing.
- Integrated Show/Hide, connection check and key removal stay in the same panel.
- Back/Escape return to captions; Enter saves the key.
- Installer registers a Lua or Python launcher for your Resolve version.
- Stable GitHub release updates preserve API keys, presets, cache and logs.

Open Srutilekha to enter your API key. Restart Resolve after installation, then
launch Workspace → Scripts → Srutilekha to generate captions.

Windows x64. Setup offers Lua for Resolve 21.0 and earlier, or Python for 21.1+.
Lua launching and SRT timeline import were tested in Resolve 21.0.4.5.
Resolve 21.1+ remains untested and needs a working Resolve Python scripting
host. This app does not configure that host.

Validated for v1.2.2: twenty-two automated checks, all demo languages isolated
from output settings, setup controls at 1040 × 780
and 920 × 640, preset round-trip, Generate/Sync settings payload, caption
editing/local re-split, frozen GUI/form/worker without external Python, upgrade
from v1.2.1, reinstall, key/preset preservation and bundled FFmpeg decoding. The earlier v1.1.1 runtime also passed clean Windows CI.
The native desktop uses the existing Tkinter runtime; font rendering differs
slightly from the browser mock. The illustrated preview is not a live Resolve
video frame. Its sample text is explicitly enlarged for readability; real cue
review keeps timeline-scaled text. Output caption point sizes are unchanged.
Review cue lists still scroll to support long transcripts.
An actual clean physical PC and paid ElevenLabs transcription remain untested.

This stable release is offered through the app's GitHub update checker to
users on older versions. Use Check for updates, then Install update.

The release includes exact FFmpeg 7.1.1 source, LGPL license, build script,
configuration and toolchain versions alongside Setup.exe and SHA256SUMS.txt.
