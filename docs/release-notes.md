v1.3.3 preview: resident Windows tray helper.

- Setup starts a single tray helper and enables per-user Windows startup.
- Click Workspace > Scripts > Srutilekha to open captions; repeated clicks reopen or raise the existing caption window.
- Closing captions keeps the helper available. Quit helper leaves any active caption job running.
- Tray menu includes Open captions, API settings, Updates, Start with Windows and Quit helper.
- Windows startup can be disabled in the tray menu or home settings; upgrades preserve that choice.
- Idle helper checks local launch markers and does not send Resolve API requests. Old markers from previous Resolve sessions are ignored.
- Existing features, encrypted keys and presets are retained. No automatic Generate, Sync, Undo or paid API calls.
- This remains a prerelease: real Resolve 21.1 caption import/styling awaits validation.

v1.3.2 introduced automatic desktop connection:

- Opening the desktop app automatically opens captions when the Lua bridge is available.
- If the bridge is not ready, the app waits and connects after Workspace > Scripts > Srutilekha is started.
- Existing caption workflows are detected so automatic connection does not launch duplicates.
- No automatic Generate, Sync, Undo, transcription or timeline changes.
- Start the Lua script once per Resolve session. Free edition cannot bootstrap it from the desktop app.
- Real caption import/styling on Resolve 21.1 remains unverified; this is a prerelease.

v1.3.1 preview introduced:

- Fixes the installer choosing Studio-only Python scripting for Free edition.
- Start Workspace > Scripts > Srutilekha once, then Connect in the desktop app.
- Retains Master Studio, English demos, processing/review, presets and encrypted keys.
- Prevents overlapping desktop workflows and reports rejected caption styling writes.
- 29 tests passed; connection and read-only metadata verified on Resolve 21.1.1.10 Free.
- Real Resolve 21.1 caption import/styling has not been tested. The current project was left untouched; no paid API calls were made.
- This prerelease does not replace v1.3.0 in stable automatic updates.

Features retained from the stable standalone Windows x64 release:

- Master Studio puts preview, audio, timing, script/files, presets and caption style in one workspace.
- Font, style, point size, colour, outline and shadow are directly editable with live sample feedback.
- Generate and Sync retain the same settings; the existing-SRT row stays visible and enables in Sync mode.
- English demo captions by default, independent of transcription language and saved presets.
- A separate Demo language selector offers examples for all 14 supported languages.
- Rounded preview stage, centred multiline captions and cleaner placement display.
- Refined Studio typography: 27 px bold heading, readable 13–15 px controls and consistent colours.
- Larger illustrated caption samples, softer artwork and linked placement controls.
- Existing preset JSON format, caption processing and review workflows are retained.
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

Validated for v1.3.0: twenty-three automated checks, all setup sections visible
at 1180 × 820, 1040 × 780 and 1040 × 720, demo languages isolated from
output settings, preset round-trip, Generate/Sync and styling payload, caption
editing/local re-split, frozen GUI/form/worker without external Python, upgrade
from v1.2.2, reinstall, key/preset preservation and bundled FFmpeg decoding. The earlier v1.1.1 runtime also passed clean Windows CI.
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
