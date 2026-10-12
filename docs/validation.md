# Windows release validation

Tested on 11 October 2026:

- Nine distribution tests: encrypted key round-trip/corruption, stable release
  selection, verified downloads, truncation, wrong URL/checksum rejection,
  preservation of user data and packaged Lua adaptation.
- v1.1.0 fresh install, reinstall and uninstall on the development PC. Existing
  Resolve scripts and installation pointer were backed up and restored.
- Frozen GUI, full caption form, SDK, bundled worker and FFmpeg with external
  Python removed from PATH. CI also passed this on a fresh Windows runner.
- Resolve 21.0.4.5: isolated project with a synthetic six-second WAV. The exact
  production Lua import function imported an SRT into subtitle track 1 with
  two cues. The packaged Lua launcher opened the standalone caption form and
  correctly discovered Audio 1 and the timeline dimensions. The form was
  cancelled using the run-supersession protocol.

The Resolve test used an existing v1.1.0 packaged runtime. v1.1.1 changes the
FFmpeg build and ships its corresponding source. Its clean Windows CI build
and frozen GUI/form/worker/key tests passed (run 38136544286).
The downloaded v1.1.1 installer matched its release SHA-256 checksum. Upgrade
from v1.1.0, reinstall and uninstall passed. Encrypted test-key and preset
files retained identical bytes throughout. Bundled FFmpeg trimmed a WAV to
one second and decoded it to 16 kHz mono float samples. Its reported license
and configuration confirmed LGPL, with GPL/version3/nonfree disabled.

No paid ElevenLabs transcription was performed during these validation
tests. Resolve 21.1+ Python-host integration and an actual clean physical PC
remain untested. A fresh hosted Windows runner is not a physical-PC install.


v1.1.2 API settings update: thirteen automated checks passed, including
in-window ownership, save/remove, failed saves, Back cancellation and restored
caption shortcuts. Native dark layout was visually checked at 580 × 380.
The locally built Windows installer passed upgrade from v1.1.0, reinstall,
uninstall and frozen GUI/form/worker tests without external Python on PATH.
The frozen report confirms `api_settings: in-window`. Test key and preset bytes
were preserved; existing Resolve launcher files and install pointer were
restored after validation. This UI update has not yet run on a fresh CI runner.


v1.1.3 rounded settings update: fourteen checks passed, including the integrated
Show/Hide control and disabled connection action. Native layout was visually
checked at 580 × 380 and 930 × 700. The locally built installer passed upgrade,
reinstall, uninstall, encrypted-key/preset preservation and frozen runtime
checks with external Python removed from PATH. Existing Resolve launchers and
installation pointer were restored after testing.


v1.2.0 Studio layout: twenty checks passed, including controls at 1040 × 780
and 920 × 640, Sync/Generate switching with settings retained, preset save/load/
remove with all legacy style fields, Resolve selection payload, bounded aspect
ratios and caption placement, and a real review/edit/local-resplit/SRT-save
regression check. The new frozen report confirms `studio_tabs: ok`.
The local installer passed upgrade from v1.1.3, reinstall, uninstall,
encrypted-key/preset preservation and frozen runtime checks without external
Python on PATH. Existing Resolve launchers and installation pointer were
restored. Native layout was inspected on the development Windows display.
See [feature mapping](studio-ui.md) for preserved features and rendering limits.


v1.2.1 refinement: twenty-one checks passed, including explicit typography token
checks, Bengali/English sample switching, preservation of the real output point
size, all setup controls at normal/minimum window dimensions and the existing
workflow regression checks. The new native layout was visually inspected on
Windows. The local installer passed upgrade from v1.2.0, reinstall, uninstall,
encrypted-key/preset preservation and frozen runtime checks without external
Python on PATH. Paid transcription was not repeated for this presentation change.

v1.2.2 neutral demos: twenty-two checks passed. All 14 supported demo languages
are available; setup starts in English even when the actual transcription
language changes to Bengali. Demo selection leaves output settings and point
size unchanged. Both Reel and HD keep their aspect ratios within the normal
and minimum window sizes. The rounded native preview was visually inspected.
The locally built installer passed upgrade from v1.2.1, reinstall, uninstall,
encrypted-key/preset preservation and frozen runtime checks without external
Python on PATH. The frozen report confirms `demo_languages: independent`.
Existing Resolve launchers and the installation pointer were restored.
