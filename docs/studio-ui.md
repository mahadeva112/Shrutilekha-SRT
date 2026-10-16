# Master Studio UI feature mapping

The Studio form opens as a WebView2 page (`ui/studio.*`, driven by
`web_studio.py`) when pywebview and WebView2 are available. It collects the same
values as the Tkinter form. `web_run.py` then writes the same selection file,
runs the worker, shows progress and the done report in the same window, and
exchanges the done/result/ack files with Resolve exactly as `App` does. When
"Review captions first" is on, the same window shows the review editor
(`ui/review.js`); every re-cut, split, merge, delete and Apply goes through
`web_review.py`, a Tk-free port of the Tkinter editor's logic that tests pin to
the same cues and the same SRT/.cap bytes. Presets use the same JSON files in
both forms. Without
WebView2, or with `SRUTILEKHA_CLASSIC_UI=1`, the Tkinter form in
`studio_form.py` is shown instead. Browser and native font rendering are not
pixel-identical.

| Existing feature | Studio location |
| --- | --- |
| Generate / sync existing SRT | Workflow buttons beside the heading |
| Audio track and language | Audio & language panel |
| Punctuation and speaker separation | Audio & language panel |
| Review before import | Audio & language panel |
| Max characters, lines, min/max duration, CPS, max words | Timing & readability panel |
| Numeric range feedback and reading comfort | Timing fields and compact comfort strip |
| Reference script path and Browse | Script & files panel |
| Existing SRT path and Browse | Always-visible row; enabled in Sync mode |
| Save/load/remove named presets | Presets panel; existing JSON format retained, caption style fields no longer saved |
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

The setup form has no tabs or scrolling canvas. All four settings panels stay
visible. Controls are checked at 1180 × 820, 1040 × 780
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
