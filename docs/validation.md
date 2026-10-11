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
