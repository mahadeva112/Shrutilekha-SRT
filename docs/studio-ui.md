# Master Studio UI feature mapping

The Studio form is a WebView2 page (`ui/studio.*`, driven by `web_studio.py`).
It is the only interface: the earlier Tkinter window has been removed, and
Setup installs the WebView2 runtime on PCs that lack it. If the runtime is
missing anyway, Srutilekha shows a plain Windows message box saying how to add
it, and tells Resolve's side the run was cancelled.

`web_run.py` writes the selection file, runs the worker, shows progress and the
done report in the same window, and exchanges the done/result/ack files with
Resolve. When "Review captions first" is on, the same window shows the review
editor (`ui/review.js`); every re-cut, split, merge, delete and Apply goes
through `web_review.py`. `tests/data/tk_editor_golden.json` records what the
retired Tkinter form and editor produced (initial values, selections, presets,
cues and SRT/.cap bytes), and the tests hold the web path to it. Preset files
keep the same JSON format.

| Existing feature | Studio location |
| --- | --- |
| Generate / sync existing SRT | Workflow buttons beside the heading |
| Audio track and language | Audio & language panel |
| Punctuation and speaker separation | Audio & language panel |
| Review before import | Audio & language panel |
| Max characters, lines, min/max duration, CPS, max words | Timing & readability panel |
| Numeric range feedback and reading comfort | Timing fields and compact comfort strip |
| Reference script: Browse a file or Paste the text | Script & files panel; pasted text is saved to `scripts/pasted_script.txt` in the data folder and passed to the worker as the script path |
| Existing SRT path and Browse | Always-visible row; enabled in Sync mode |
| Save/load/remove named presets | Not in the Studio form since v2.0.0; the classic Tkinter form keeps them. The `list/load/save/remove_preset` API and JSON format are retained, caption style fields no longer saved |
| Cue preview at the timeline's frame | Review editor, after Generate |
| Caption editing, local re-split, recipes, filters, merge/split and apply | Existing review editor retained |
| Undo last captions, cancel | Footer |
| Encrypted API key, show/hide, connection test and removal | In-window API settings |
| Version check and installer update | Version pill in native title bar |

The setup form has no preview and no caption style controls. Resolve's
scripting API cannot style subtitle cues (TimelineItem.SetProperty only takes
transform and composite keys), so font, size, colour, outline, shadow and
position never reached Resolve; set them in Resolve under Inspector > Track >
Track Style. The real cues are previewed in the review editor after Generate.
Per-speaker colour is the exception: it travels in the SRT as `<font color>`
tags, which Resolve's SRT import shows (`transcribe.color_cue_text`).

The setup form has no tabs or scrolling canvas. All three settings panels stay
visible. In Audio & language the heading, both dropdowns and a one-line
language note stack on the left at the same height as the three switches on the
right; the selected track's full name is in the dropdown's tooltip. Controls are checked at 1180 × 820, 1040 × 780
and 1040 × 720 on the development Windows display. The initial window is 1180 × 820 and the minimum is
1040 × 720, clamped to the screen. Unusually small screens or different DPI settings need separate
validation. The review editor still scrolls its cue list, which can contain
arbitrarily many captions.

The refined UI uses explicit pixel type sizes rather than inheriting old widget
point sizes: 27 px bold heading, 13–14 px interface labels/buttons and 15 px input
values. Headings have stronger weights. Compact windows reduce gaps and field
height without reducing text size. The API panel and standalone home use the same
palette and type scale.

Named preset storage and callbacks are shared with the previous layout.
Switching Generate/Sync
retains the SRT path and all panel values without moving or hiding panels.
