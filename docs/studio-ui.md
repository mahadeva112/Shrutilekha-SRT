# Studio UI feature mapping

The Studio form uses the existing Tkinter runtime and controls. Its presentation
is separated into `studio_form.py`; transcription, Resolve communication, worker
cancellation, progress and caption review remain in `loader.pyw` and the existing
worker. Browser and native font rendering are not pixel-identical.

| Existing feature | Studio location |
| --- | --- |
| Generate / sync existing SRT | Workflow buttons beside the heading |
| Audio track and language | Audio tab |
| Punctuation and speaker separation | Audio tab |
| Review before import | Audio tab |
| Max characters, lines, min/max duration, CPS, max words | Timing tab |
| Numeric range feedback and reading comfort | Timing tab |
| Reference script path and Browse | Script tab |
| Existing SRT path and Browse | Files tab in Sync mode |
| Save/load/remove named presets | Presets tab; existing JSON format retained |
| Reel / HD preview | Preview header |
| Demo caption language | Separate preview selector; English initially, all 14 supported languages available |
| Safe-zone overlay, draggable caption placement | Preview; linked position slider |
| Font, font style, colour, outline, shadow, size and position saved in presets | Existing preset fields retained |
| Caption editing, local re-split, recipes, filters, merge/split and apply | Existing review editor retained |
| Undo last captions, cancel | Footer |
| Encrypted API key, show/hide, connection test and removal | In-window API settings |
| Version check and installer update | Version pill in native title bar |

The setup form has no scrolling canvas. Its controls are checked at 1040 × 780
and 920 × 640 on the development Windows display. The preview resizes to fit
both aspect ratios. The minimum usable window is 920 × 640 on sufficiently
large displays; unusually small screens or different DPI settings need separate
validation. The review editor still scrolls its cue list, which can contain
arbitrarily many captions.

The illustrated placement preview is labelled as a sample. It is not a live
Resolve video frame. Mock-only playback and sample import simulations are not
included in the real application.


The refined UI uses explicit pixel type sizes rather than inheriting old widget
point sizes: 27 px bold heading, 14 px interface labels/buttons and 15 px input
values. Headings and labels have stronger weights. Compact windows reduce gaps
without reducing text size. The API panel and standalone home use the same
palette and type scale.

Illustrated setup captions are enlarged relative to the selected point size
for readability and labelled accordingly. Real review captions remain scaled
against the timeline dimensions. Saved caption point size, colour, outline,
shadow, placement and backend output are unchanged.

The demo selector is independent of the Audio tab's transcription language.
Every setup starts with the neutral English example, including when a saved
caption preset selects Bengali. Demo text is never written to SRT files or
presets. Changing demo language does not change Auto-detect or any output setting.
The preview stage has rounded corners; the setup's decorative anchor dot and
internal Y readout are omitted because the linked position slider already
displays the value. Dragging captions and platform safe-zone overlays remain.
