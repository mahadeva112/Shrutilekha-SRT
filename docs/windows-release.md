# Windows app and release workflow

The desktop UI is still Tkinter. `browser-preview/` is a separate visual demo.
The installed application needs no external Python. It includes a GUI EXE and
a hidden console worker that reports progress to the existing Resolve form.

## Build

Use Windows x64, Python 3.12+ and Inno Setup 6.
Build FFmpeg first in MSYS2 UCRT64 with GCC, make, nasm, curl, tar and xz:
`bash scripts/build_ffmpeg.sh`. The GitHub workflow does this automatically.

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements-build.txt
.venv/Scripts/python.exe -m unittest discover -s tests -v
.venv/Scripts/python.exe scripts/build_release.py
```

If needed, set `ISCC` to the absolute path of Inno Setup's ISCC.exe.
Deliver `dist/release/Srutilekha-Setup-<version>.exe` and `SHA256SUMS.txt`.
Keep the app runtime folder intact; users receive one installer, which installs
the GUI, worker, runtime and Resolve menu script together.

## User setup

Install Setup.exe, open API settings, paste the user's own ElevenLabs key and
save. The optional connection check reads the user's profile and does not
perform a paid transcription. Restricted keys need profile-read permission
for this check and speech-to-text permission for actual transcription.

Restart Resolve, open a timeline, and run Workspace → Scripts → Srutilekha.
Setup offers the packaged Lua launcher for Resolve 21.0 and earlier, or the
Lua bridge for Resolve 21.1+ Free or Studio, with an optional Studio-only
Python launcher. It detects the usual Windows installation
path to preselect an option; users can override it for custom installations.
The bridge starts in Resolve; the resident tray helper opens the bundled form
when the script is clicked. Setup enables per-user Windows startup, which can
be disabled in the tray/home settings. Legacy Lua launching and SRT timeline import were
verified in Resolve 21.0.4.5; see [validation details](validation.md). The Python
launcher requires a working Python scripting host in Resolve. The bundled app
runtime does not configure Resolve's Python host. Resolve 21.1.1 Free connection
was verified; real caption import/styling awaits validation. See [bridge usage](resolve-bridge.md).

API keys are encrypted by Windows DPAPI for the current Windows user and
stored under `%LOCALAPPDATA%/Srutilekha`. Keys never enter the installer,
GitHub, release assets or command-line arguments. Cache, logs and presets also
live there. Uninstall retains personal data; API settings can remove the key.
Existing source-install `.env` keys are not automatically migrated.

## Publish an update

1. Bump `version.json`, update `docs/release-notes.md`, and commit the build
   inputs without secrets, caches or generated artifacts.
2. Push a matching `vX.Y.Z` tag. The workflow tests, builds, and creates a
   **draft** release containing the installer and SHA-256 checksum.
3. Test the installer on a clean PC without Python and in Resolve. Test an
   upgrade from the previous installed release and ensure keys/presets survive.
4. Publish the tested draft. Existing installs check GitHub's latest stable
   release on launch and expose an update action.

Downloads are verified against release checksums before Setup starts. The
user can retry installation if it fails. No running EXE is overwritten by
the app itself: Inno Setup manages file-in-use handling. Checksums verify
download integrity, not publisher identity. Authenticode signing is a
separate release-hardening step requiring the publisher's certificate.

Release assets include the exact FFmpeg 7.1.1 source archive, reproduction
script, configuration, package versions and LGPL license. Native components
are compiled with external-library detection disabled and no GPL components.
Do not publish the initial draft before the clean-PC/Resolve tests pass.
