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
