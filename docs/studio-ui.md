# Master Studio UI feature mapping

The Studio form uses the existing Tkinter runtime and controls. Its presentation
is separated into `studio_form.py`; transcription, Resolve communication, worker
cancellation, progress and caption review remain in `loader.pyw` and the existing
worker. Browser and native font rendering are not pixel-identical.

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
| Save/load/remove named presets | Presets panel; existing JSON format retained |
| Reel / HD preview | Preview header |
| Demo caption language | Separate preview selector; English initially, all 14 supported languages available |
| Safe-zone overlay, draggable caption placement | Preview; linked position slider |
| Font, font style, colour, outline, shadow, size | Caption style panel; original output variables and preset fields |
| Caption editing, local re-split, recipes, filters, merge/split and apply | Existing review editor retained |
| Undo last captions, cancel | Footer |
| Encrypted API key, show/hide, connection test and removal | In-window API settings |
| Version check and installer update | Version pill in native title bar |

The setup form has no tabs or scrolling canvas. All five settings panels stay
visible alongside the preview. Controls are checked at 1180 × 820, 1040 × 780
and 1040 × 720 on the development Windows display. The preview resizes to fit
both aspect ratios. The initial window is 1180 × 820 and the minimum is
1040 × 720, clamped to the screen. Unusually small screens or different DPI settings need separate
validation. The review editor still scrolls its cue list, which can contain
arbitrarily many captions.

The illustrated placement preview is labelled as a sample. It is not a live
Resolve video frame. Mock-only playback and sample import simulations are not
included in the real application.


The refined UI uses explicit pixel type sizes rather than inheriting old widget
point sizes: 27 px bold heading, 13–14 px interface labels/buttons and 15 px input
values. Headings have stronger weights. Compact windows reduce gaps and field
height without reducing text size. The API panel and standalone home use the same
palette and type scale.

Illustrated setup captions are enlarged relative to the selected point size
for readability and labelled accordingly. Real review captions remain scaled
against the timeline dimensions. Saved caption point size, colour, outline,
shadow, placement and backend output are unchanged.

The demo selector is independent of the Audio panel's transcription language.
Every setup starts with the neutral English example, including when a saved
caption preset selects Bengali. Demo text is never written to SRT files or
presets. Changing demo language does not change Auto-detect or any output setting.
The preview stage has rounded corners; the setup's decorative anchor dot and
internal Y readout are omitted because the linked position slider already
displays the value. Dragging captions and platform safe-zone overlays remain.

Style controls use the original font, font-style, point-size, colour, outline
and shadow variables. The illustrated sample follows selected font and style;
real output continues through the existing Resolve payload. The colour picker
supports automatic colour via Delete or the context menu. Named preset storage
and callbacks are shared with the previous layout. Switching Generate/Sync
retains the SRT path and all panel values without moving or hiding panels.
