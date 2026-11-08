# macOS support

- **Phase 1:** the Python code runs on macOS from source.
- **Phase 2:** CI builds an unsigned `Srutilekha-<version>-macOS.dmg` for Apple Silicon, and the release includes it.

What end users read is in [macos-install.txt](macos-install.txt), shipped inside the `.dmg` as "Read me first.txt".

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

## Packaged app (phase 2)

- `scripts/build_ffmpeg_macos.sh` builds the same LGPL FFmpeg 7.1.1 for the host architecture.
- `Srutilekha.spec` builds `dist/Srutilekha.app`. It holds the GUI and `Srutilekha-worker` in `Contents/MacOS`, and FFmpeg in `Contents/Frameworks/bin`.
- `scripts/build_release.py` on macOS wraps the app in a `.dmg` together with an Applications link and the read-me.
- There is no installer, so `mac_integration.py` runs every time the packaged app or helper starts. It writes the Lua bridge to Resolve's Scripts folder, but only once Resolve has created its settings folder. It also enables start-at-login, unless the user turned that off before.
- The updater looks for `Srutilekha-<version>-macOS.dmg` and opens it. A release without a `.dmg` is not offered as an update on a Mac.
- CI: `.github/workflows/build-macos.yml` runs on pull requests. It runs the tests, builds the app, runs the packaged `--self-test` and checks the `.dmg`. `release.yml` calls it on tags, then merges the Windows and macOS assets into one draft release with a single `SHA256SUMS.txt`.

## Limits

- Apple Silicon only. Intel Macs need a separate or universal2 build.
- Unsigned: users click "Open Anyway" in System Settings > Privacy & Security on first launch.
- The Mac app supports only Resolve 21.1+ (the Lua bridge). The legacy launcher for 21.0 and earlier still works from source.

## Not verified yet

- CI checks only the build and the packaged self-test. Nobody has run the app with DaVinci Resolve on a Mac yet.
- The menu bar icon, the Lua bridge with Resolve 21.1+, the Keychain prompts and the Gatekeeper first launch all need a test on a real Mac.
