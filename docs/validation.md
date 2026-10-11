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
FFmpeg build and ships its corresponding source; its CI and final installer
checks are recorded separately in GitHub Actions/release notes.

No paid ElevenLabs transcription was performed during these validation
tests. Resolve 21.1+ Python-host integration and an actual clean physical PC
remain untested. A fresh hosted Windows runner is not a physical-PC install.
