v1.4.0 preview: the caption workflow moves to a WebView2 interface.

- Home, Caption Studio, progress, review and the done report open in one window built with pywebview and Microsoft WebView2, with animated progress, blurred dialogs and smooth transitions.
- The review editor adds a clickable waveform, per-cue reading-speed meters, All / Needs attention / Edited filters, search, Enter/Ctrl+M/Ctrl+Delete shortcuts and an inspector with split and merge.
- Selection files, presets, re-cuts, split/merge results and written SRT/.cap files are tested to match the previous Tkinter editor exactly.
- Without WebView2, or with SRUTILEKHA_CLASSIC_UI=1, the previous Tkinter interface is used.
- This is a prerelease: the new interface has not yet been run against a live Resolve session or a paid ElevenLabs transcription.

v1.3.9 preview: redesigned account connection and cumulative Studio improvements.

- Replaces the API settings page with clear page and provider headings, a larger key field, saved-key status and distinct Test connection / Save & return actions.
- Wide windows show setup guidance beside the connection card; compact windows retain the key field and all actions without clipping.
- Retains encrypted key storage, Show/Hide, removal, connection checks and Back/Escape/Enter behavior.
- Tests cover API settings at 620 × 550, 1040 × 720 and 1180 × 820 across 80/100/125/150/200% render scales.
- Includes the existing native-resolution fonts/icons, compact Studio layout, crisper illustrated preview, Resolve audio-track compatibility and large-review/split/Apply fixes from previous releases.
- All setup sections, presets, demo languages, caption styling and tray workflows are included.
- This remains a prerelease: real Resolve 21.1 caption import/styling and clean physical-PC validation remain outstanding.

v1.3.8 preview: repair large caption review, splitting and Apply.

- Rounded fields coalesce layout work at idle, preventing recursive Tk event-draining when large review lists open.
- Master Studio refits when embedded inputs settle; existing compact layouts and 100/125/150/200% render-scale checks are retained.
- Re-splitting and manual split/merge preserve edited words and deletions, with timing retained or redistributed within the original cue.
- Apply finishes a pending local cut before writing captions and signaling Resolve.
- SRT appends use clip-info dictionaries, the supported Resolve 21.1 API format, instead of the deprecated bare-item overload.
- Scroll regions and pointer coordinates use consistent logical DPI units.
- Unexpected Resolve workflow failures report back to the caption window instead of leaving it waiting; existing caption tracks remain protected by the import diff.
- English demos, all settings, saved presets and encrypted keys are retained.
- Large-list review/split/Apply tests use local files and mocked Resolve imports; no paid transcription or current-project mutations are performed.
- This remains a prerelease; real Resolve 21.1 caption import/styling still awaits validation.

v1.3.7 preview: Resolve 21.1 audio-track compatibility and refined account pages.

- Resolve 21.1 Lua clip collections include internal __flags metadata. The bridge now returns real clip lists, so existing audio sources are recognized.
- Both old running bridges and new Lua launchers are supported; clip APIs no longer fail silently.
- Source preparation failures appear inside the caption window with a Close action instead of leaving progress waiting for worker arguments.
- Account settings have a warm card accent, subtle background artwork and matching typography.
- Error dialogs use clear headings, smooth icons, rounded actions and actionable source guidance.
- All existing caption controls, English demos, encrypted keys and presets are retained.
- Read-only live validation found and mapped all clips on both audio tracks with readable source files. No paid transcription or timeline changes were performed.
- This remains a prerelease; real Resolve 21.1 caption import/styling still awaits validation.

v1.3.6 preview: clearer text and display-scaled icons.

- Per-monitor DPI awareness is embedded in the Windows EXE manifest.
- Interface dimensions, fonts, canvas coordinates and mouse interactions share logical units.
- Segoe UI numeric fields match the interface; output caption fonts and sizes stay independent.
- Main section, title-bar, logo and account icons use antialiased display-resolution artwork.
- Monitor-scale changes relayout controls and preserve caption settings.
- Scaling is capped on small displays to keep the full Master Studio visible without scrolling.
- Existing caption features, English demos, saved presets and encrypted keys are retained.
- This remains a prerelease; real Resolve 21.1 caption import/styling still awaits validation.

v1.3.5 preview: refined Master Studio presentation.

- Softer rounded cards with subtle shadows and quieter borders.
- Small waveform, clock, file, preset and style marks make sections easier to scan.
- Clearer headings, warm selected modes and a visible Demo badge in the preview.
- Consistent rounded inputs, outlined secondary actions, hover feedback and gold focus borders.
- Error borders remain red, and disabled file inputs remain dark.
- All caption features stay visible together without scrolling at supported window sizes.
- English demos, existing preset format, encrypted keys, tray workflow and caption processing are retained.
- This remains a prerelease; real Resolve 21.1 caption import/styling still awaits validation.

v1.3.4 fixed dark disabled file inputs:

- Existing SRT stays dark and readable in Generate mode; Sync enables the same input.
- Existing caption settings, presets, API keys and tray workflow are retained.
- Real Resolve 21.1 caption import/styling still awaits validation; this remains a prerelease.

v1.3.3 introduced the resident Windows tray helper:

- Setup starts a single tray helper and enables per-user Windows startup.
- Click Workspace > Scripts > Srutilekha to open captions; repeated clicks reopen or raise the existing caption window.
- Closing captions keeps the helper available. Quit helper leaves any active caption job running.
- Tray menu includes Open captions, API settings, Updates, Start with Windows and Quit helper.
- Windows startup can be disabled in the tray menu or home settings; upgrades preserve that choice.
- Idle helper checks local launch markers and does not send Resolve API requests. Old markers from previous Resolve sessions are ignored.
- Live script-click opening and reopening confirmed on Resolve 21.1.1 Free; subsequent clicks reused the resident bridge, with one caption form active.
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
