v2.0.12: Devanagari sample caption on the home screen.

- The animated sample caption on the home screen now reads "हर शब्द सही जगह पर" (Hindi, Devanagari script) instead of the Bengali "সব কথা ঠিক জায়গায়".
- The caption uses the Vesper Libre Bold font, shipped inside the app (`ui/fonts/`, SIL Open Font License, see `ui/fonts/OFL.txt`), so it looks the same on every PC. Nirmala UI is the fallback. Nothing else changed.

v2.0.11: one input per task in Script & files.

- **Generate** shows only the reference script (Browse file / Paste text). **Sync existing SRT** shows only the SRT to re-time. Before, both rows were always on screen and the SRT row sat greyed out in Generate.
- The note under the panel and the summary in the footer follow the task. Sync no longer names a script, since Sync never reads one.
- The test suite passes. The change was checked in a browser mock of the caption studio, not yet in a live Resolve session.

v2.0.10: a colour for each speaker.

- With **Separate speakers** on and two or more people speaking, each speaker's captions now get their own colour in Resolve. Resolve does not let scripts colour subtitle cues, but it does read colour tags in an SRT, so Srutilekha writes `<font color>` tags into the SRT it imports. This was checked live on Resolve 21.2.0.6 Free. The first speaker stays white and untagged, so the track's Track Style colour applies to them. With one speaker, nothing changes.
- Review **Apply** writes the same colours. If your edits leave only one speaker, no colours are written.
- The review editor's preview shows the selected cue in its speaker's colour.
- The done screen no longer says Resolve "did not accept" the caption styling on every run. It now says which styles to set in Inspector > Track > Track Style (font, size, outline, shadow, position), and that text, timing and speaker colours were imported.
- Sync Existing and reference scripts ignore colour tags in an SRT they read. Sync Existing writes its re-timed SRT without them.
- Subtitle Regions and one track per speaker were tried and dropped: Resolve shows only one subtitle track at a time and has no scripting call for regions.
- 143 tests: the new colour and review tests pass. 2 fail on the build PC without this change too: `pystray` is not installed, and the WebView2 check fails there. One timing test in `test_web_run` sometimes fails when the PC is busy. Not yet checked with a real transcription in Resolve.

v2.0.9: choose Scribe v2 or Scribe v3.

- The caption studio's Audio & language panel has a new **Model** dropdown next to Language: **Scribe v2** (the default) or **Scribe v3**, ElevenLabs' newer speech-to-text model (released 9 November 2026). Every run starts on Scribe v2; pick Scribe v3 for a run, or save it in a preset.
- The chosen model is used for Generate, Sync Existing and Regenerate from review. Changing it after review counts as a transcription change, so the button becomes Regenerate.
- Transcripts are cached per model, so a Scribe v2 transcript is never reused for a Scribe v3 run, or the other way round.
- 137 tests pass. The new dropdown was checked in a browser mock of the caption studio. Scribe v3 has not yet been checked in a live Resolve session.

v2.0.8: one interface, WebView2 everywhere; a tidier caption studio; fewer re-uploads.

- The classic Tkinter windows are gone. Every Srutilekha window (home, caption studio, review, and the notices Resolve opens) is the WebView2 one, so there is no second, older-looking app any more. `SRUTILEKHA_CLASSIC_UI` no longer does anything.
- Setup now checks for the Microsoft Edge WebView2 runtime and, when a PC lacks it, downloads Microsoft's installer and adds it before installing Srutilekha. Windows 11 already has it. If the download fails, Setup says so and lets you try again.
- If WebView2 is missing anyway (removed later, or blocked), Srutilekha shows a plain Windows message saying how to add it, instead of an old-style window. A caption run started from Resolve is cancelled cleanly in that case; the timeline is left untouched.
- Srutilekha checks for the real WebView2 runtime, not just the pywebview library. Without the runtime, pywebview quietly used Internet Explorer's engine.
- The font list in the caption studio comes straight from Windows. Legacy aliases such as "Arial CYR" no longer appear in it.
- Tcl/Tk is no longer shipped, so the install is smaller.
- Caption studio: in Audio & language the heading, both dropdowns and a short language note now sit together on the left, level with the three switches, so the empty band above the dropdowns is gone. The full audio track name fits (and shows in a tooltip if it is still too long), and the small descriptions under the switches are easier to read.
- Shortening a trim no longer re-uploads audio that was already transcribed. A window that sits inside a larger cached one is cut from that transcript, with no API call and no ElevenLabs credit used.
- The test suite's hidden windows no longer show a taskbar button or take keyboard focus while tests run.
- 133 tests pass. They check the web form, presets and review editor against what the classic form and editor produced, recorded before removal. The new Setup step compiles and finds WebView2 on this PC; the download-and-install path still needs a run on a PC without WebView2. The caption studio layout was checked in a browser mock at 1180 × 820 and 1040 × 720. Not yet checked in a live Resolve session.

v2.0.7: the playhead stays where you left it.

- After a run placed its captions, the playhead was left far past the clips, often at the end of the video. Placing moves it twice: to the timeline start, as the anchor the SRT import needs, and then past whatever Resolve appended. Srutilekha now notes where the playhead was before placing and puts it back afterwards, whether the placement worked or not. This applies to Resolve 21.1 and 21.2 (the bridge) and to Resolve 21.0 and earlier (the Lua launcher).
- 128 tests pass, including a check in Resolve's own Lua engine (fuscript) that the playhead comes back. Not yet checked in a live Resolve session.

v2.0.6: the windows Resolve opens now look like the app.

- Warning and error windows that open from Resolve (a paused run, a short message) used Tk with an older palette. They now open as a small WebView2 window built from the caption studio's own stylesheet: the Srutilekha title bar, gold buttons, numbered "What to do" steps, and "Show details" with Copy details. The window fits its text, opens centred on the screen Resolve is on, comes in front of Resolve, and has rounded corners on Windows 11.
- PCs without WebView2, or with `SRUTILEKHA_CLASSIC_UI=1`, still get the Tk window. Its colours now match the app.
- The test suite no longer flashes windows over the screen while it runs.
- 126 tests pass. The new window was opened and checked locally (error notice, plain message, and the Tk fallback); not yet run in a live Resolve session.

v2.0.5: Save SRT, and friendlier guidance when a run pauses.

- **Save SRT…** on the done screen saves the captions this run placed (with any review edits) as an .srt file. The blank anchor cue is left out and cues are numbered from 1. Sync runs can be saved too. Edits made later in Resolve are not in the file; use Resolve's Export Subtitle for those.
- When a run pauses, every place that reports it (the caption studio's done screen, the classic window, and the window Resolve opens) now shows a heading that names the next step, one plain sentence, numbered "What to do" steps, and the original report folded under "Show details" with a Copy details button. 17 situations are recognised, such as no project or timeline open, no audio, the ElevenLabs key missing or out of date, the ElevenLabs allowance used up, no internet, and Resolve not answering. Anything else gets a general notice with the same layout.
- Short messages (toasts, the API key window, review, Undo) are worded the same way, and their colour is a soft gold instead of red.
- When Resolve does not answer within 10 minutes, the done screen now shows that as a paused run instead of "Done".
- 120 tests: 119 pass. The one error is the tray test needing `pystray`, which is not installed on the build PC and errors the same way before this change. Screens checked in a browser mock and the Resolve-side window rendered locally; not yet run in a live Resolve session.

v2.0.4: captions land in the right place on older Resolve; earlier subtitle tracks are turned off.

- On older Resolve a new run could land at the end of the video. Asked for the new track at the timeline start, Resolve put the whole run where the video ends, and there is no `Timeline.MoveItems` there to bring it back. Each placement is now checked: when the first caption is more than 2 frames from where it belongs and cannot be moved, this run's cues are deleted again and the next way is tried (other subtitle tracks locked, then a plain append as in v1.4.7). Your earlier cues are never moved or deleted.
- When the new captions have a track of their own, every other subtitle track is turned off, so only they show. A track you had already turned off is left as it is. Undo deletes the new track and turns back on only the tracks that run turned off.
- The Lua script for Resolve 21.0 and earlier gets the same checks, and now finds a track's lock with `GetTrackLock` too, so its locked-append way runs there.
- 110 tests: 109 pass, including the import in Resolve's own Lua with a fake older Resolve. The one error is the tray test needing `pystray`, which is not installed on the build PC and errors the same way before this change. Not yet run live on an older Resolve.

v2.0.3: captions open sooner after a script click.

- The tray helper looked for a click once a second, and scanned every running process (about 0.2 s) each time. It now reads the bridge's small launch marker every 0.1 s and scans processes only when a click is new. The large Fusion.prefs, which only an older bridge uses, is read every 2 seconds.
- A script click no longer makes the tray check the bridge before starting the caption workflow, which connects to it anyway.
- The caption window no longer loads the update checker's network code (urllib and the Windows certificate store) at startup; it loads on the first update check. The API key connection check sets up the Windows certificate store itself.
- Live in Resolve 21.2.0.6 with v2.0.2: 100% to Done took 1 s (27 s in v2.0.1), and 50 cues were moved to their own new track with the first caption on its frame.
- 104 tests pass.

v2.0.2: faster bridge, captions on their own track in Resolve 21.2.

- The wait after transcription reached 100% is gone. Every Resolve call through the bridge waited up to 100 ms in Resolve and 40 ms in the app; a 44-cue run made hundreds of them and sat at 100% for 27 seconds (8 more before transcription, reading 13 clips). The bridge now checks every 5 ms while the app is working (back to 100 ms when idle), names, start and end frames of a whole track come back in one call, and once Resolve refuses a full batch of style writes the rest are not sent. Measured per call: 109 ms before, 16 ms now.
- Bridge replies are no longer copied into Resolve's preferences, which had grown Fusion.prefs by hundreds of KB.
- Resolve 21.2 ignores the track number for an SRT and appends it to track 1 after the cues already there (44 cues landed 1431 frames late). The new cues are now moved with `Timeline.MoveItems` onto the new subtitle track, with the first caption at its own time. Your earlier cues are never moved.
- 102 tests pass. Speed was measured with the bridge in Resolve's own Lua. Live in Resolve 21.2.0.6: 100% to Done in 1 s, and 50 cues moved to their own new track with the first caption on its frame.

v2.0.1: works with DaVinci Resolve 21.2.

- Resolve 21.2 removed `loadfile`, `dofile` and `SavePrefs` from script Lua and writes settings to disk only about every 30 seconds, so the bridge stopped at its first line and nothing opened. The bridge now reads requests and writes replies through Resolve's own file access (`OpenFile`), and clicks reach the tray helper at once. Resolve 21.1 keeps working the old way.
- Captions made through the bridge go on a new subtitle track at the timeline start. Before, Resolve could append them to an earlier run's track after its cues: on 21.2 a 45-cue run landed 1429 frames late. The same three placement attempts as the Lua launcher are used, with 21.2's renamed `GetIsTrackLocked`.
- Resolve 21.2 refuses every subtitle style write from scripts (font, size, outline, position), through both `SetProperties` and `SetProperty`. Text and timing are imported; set the look under Inspector > Track > Track Style.
- Checked live on Resolve 21.2.0.6 Free: connection, timeline reading, transcription and import through the bridge. The new track placement is covered by tests but not yet seen in a live run. 98 tests pass, including the bridge run in Resolve's own Lua with 21.2's restrictions.

v2.0.0: new logo, Back from review, pasted scripts, safer imports, new look.

- New logo: a speech bubble with two subtitle lines on the gold tile, the same in the app header, the classic window and the installer icon.
- Review screen has a Back button. It keeps the transcript and your cue edits. Changing only timing re-cuts the same transcript with no API call; changing language, punctuation, speakers or the script offers Regenerate.
- Reference script: a Browse file / Paste text switch. Pasted text is used exactly like a .txt script and comes back next time the app opens.
- The Presets panel is gone from the caption studio. Preset files and the classic form's presets are untouched.
- New captions stay off subtitle tracks that already hold cues: an earlier run's track is locked while the new one is imported, then unlocked. If Resolve refuses the import, two other ways are tried, and a failure now shows in the app instead of leaving it on "Importing subtitles..." for up to ten minutes.
- New look: panels, buttons and switches with more depth, short descriptions under the Audio & language switches, full-size fields in the default window, and a dusk scene on the home screen.
- 95 tests pass. Screens checked in a browser UI mock. Not yet run in a live Resolve session.

v1.4.7: punctuation in the caption's own language; Urdu removed.

- With Punctuation on, a sentence ends with । in Bengali, Assamese, Hindi, Nepali, Sanskrit, Punjabi and Odia instead of a full stop. Marathi, Gujarati, Tamil, Telugu, Kannada and Malayalam keep the full stop they normally use.
- Straight quotes become curly quotes “ ” and ‘ ’ in every language. Numbers such as 3.5 and 1,000 and the ellipsis ... are left as they are.
- With Punctuation off, nothing changes.
- Urdu is removed: it is no longer in the language list, the demo captions or the font list, and its word tables and Perso-Arabic script handling are gone.
- 83 of 84 tests passed; the one failure is a tray-helper test that already failed before these changes. Not yet run in a live Resolve session.

v1.4.6: new look for every screen.

- Setup page: Audio & language is a large card across the top, with Timing, Script & files and Presets below. The panels sit in the middle of the window instead of leaving an empty strip.
- New dropdowns for audio track, language and presets: an icon on each, a gold tick on the current choice, each language shown in its own script, and a search box for languages. Arrow keys, Enter and Escape work inside the list.
- Review & split: cue count, average reading speed and cues needing attention at the top; numbered cue badges; monospace timecodes; a labelled preview.
- Progress: a ring shows the percentage, with the stages as a horizontal step line.
- Done: summary tiles for captions imported, track and project saved.
- Checked in a browser UI mock and with 84 tests. Not yet run in a live Resolve session.

v1.4.5: setup page without caption style or preview.

- The setup page no longer has the Caption preview (Reel/HD, demo language, title-safe area, position) or Caption style (font, style, size, colour, outline, shadow). Resolve's scripting API cannot style subtitle cues, so these settings never reached Resolve. Style the track in Resolve under Inspector > Track > Track Style.
- Review screen layout: cue preview and Split settings stacked on the left, cue list on the right. The duplicate per-cue stats (In/Out/Duration/…) and Split at caret / Merge into previous buttons are gone; each cue card already has them.
- New title-bar icon: a caption frame with a sound wave, replacing the শ্রু letter mark.
- Presets keep language, timing and toggles. Style fields in older presets are ignored.
- The classic Tkinter form is unchanged.
- 84 tests passed and the screens were checked in a UI mock. Not yet run in a live Resolve session.

v1.4.4: review editor without the waveform.

- The review editor no longer shows a waveform above the cue list. It never played audio; clicking it only selected the nearest cue. Use search and the All / Needs attention / Edited filters to find cues.
- The review page opens faster because it no longer decodes the audio with ffmpeg. Caption timing still uses ffmpeg exactly as before.
- The classic Tkinter review (used without WebView2 or with SRUTILEKHA_CLASSIC_UI=1) is unchanged.
- Saved keys, presets and caption settings are preserved. Checked in a live Resolve session.

v1.4.3: captions use the number of lines you choose.

- Each caption is split evenly into the "Lines per cue" you set. Previously line 1 was filled up to Max characters before line 2 started, so with a large Max characters (e.g. 60) every caption stayed on one line.
- Line breaks prefer punctuation, phrase ends and clause starts (कि, और, কিন্তু …) and put the shorter line on top. A line never starts with a phrase-completing word (है, का, সাথে …) or ends on a conjunction.
- Captions shorter than about 16 letters stay on one line rather than being split into fragments.
- Review, split and merge use the same line splitting.
- Checked on five cached real transcripts at 60 characters, 2 lines, 3 seconds: 222 of 535 captions now use two lines (v1.4.2: none). Not yet run against a live Resolve session.

v1.4.2: multi-line captions and pause-based cue breaks.

- "Lines per cue" is respected: 2- and 3-line settings now produce 2- and 3-line captions. The review step used to rebuild each cue's text without its line breaks, so Apply wrote every cue as one line.
- Cues break where the speaker pauses. The cue-balancing pass could pull words across a pause to fill a short cue; it no longer does.
- A phrase-ending word (है, হল, ছিল …) moves to the next free line together with the word it completes, instead of overflowing line 1. Bengali হল, হলো, হলাম and হলেন are now treated as phrase-ending words.
- Changing only line breaks in the review keeps the real word timings.
- Checked by re-splitting five cached real transcripts: cues spanning a pause fell from 1–14 per file to 0 in four files and 3–4 in the fifth, where a pause sits before है or तो. Not yet run against a live Resolve session.

v1.4.1: caption preview fix.

- Captions in the Caption Studio preview and the review editor's preview now use the full frame width. Previously they could use only half of it, so captions such as the Bengali demo broke onto one word per line.
- Includes everything from v1.4.0. Saved keys, presets and caption settings are preserved.

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
