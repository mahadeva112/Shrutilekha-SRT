# macOS support — phase 1 (from source)

There is no Mac installer yet. Phase 1 makes the Python code run on macOS; a `.app`/`.dmg` build comes in a later phase.

## What changed for macOS

| Area | Windows | macOS |
| --- | --- | --- |
| User data | `%LOCALAPPDATA%\Srutilekha` | `~/Library/Application Support/Srutilekha` |
| API key | DPAPI file `api-key.dpapi` | login Keychain, service "Srutilekha ElevenLabs API key" |
| Resolve Fusion prefs (bridge replies) | `%APPDATA%\Blackmagic Design\DaVinci Resolve\Support\Fusion\Profiles\Default\Fusion.prefs` | `~/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Profiles/Default/Fusion.prefs` |
| Resolve Scripts menu folder | `...\Support\Fusion\Scripts\Utility` | `.../DaVinci Resolve/Fusion/Scripts/Utility` |
| Start helper at login | `HKCU\...\Run` registry value | `~/Library/LaunchAgents/org.srutilekha.tray.plist` (takes effect at next login) |
| Single-instance locks | `msvcrt.locking` | `fcntl.flock` |
| Resolve process detection | `Resolve.exe` | `Resolve` |
| UI | WebView2 pages | classic Tkinter UI (the web UI stays Windows-only for now) |

## Run from source

```bash
python3 -m pip install -r requirements-build.txt
python3 app.py --home
```

## Not verified yet

- Unit tests run on a GitHub `macos-latest` runner (`.github/workflows/tests.yml`). Nobody has run this with DaVinci Resolve on a Mac yet.
- The menu bar icon (pystray), the Lua bridge with Resolve 21.1+ and the Keychain prompts all need a test on a real Mac.

## Later phases

- PyInstaller `.app` bundle, a macOS FFmpeg build and an unsigned `.dmg` from CI.
- An installer step that copies the Resolve script into the Scripts folder above.
- The updater downloading the `.dmg` instead of `Setup.exe`.
