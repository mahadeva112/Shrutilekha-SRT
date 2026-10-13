# Resolve 21.1 connection — v1.3.8 preview

The old installer selected Python for every Resolve 21.1 installation. Python scripting requires Studio, so this hid the launcher in Free. The preview uses a local Lua bridge and keeps the UI and transcription in the desktop EXE.

1. Install Srutilekha-Setup-1.3.8.exe. Select **Resolve 21.1 or newer, Free or Studio (Lua bridge + desktop app)**, the detected default. Setup starts the tray helper and registers it for Windows login.
2. Save your work and restart Resolve when convenient to refresh the Scripts menu.
3. Click **Workspace > Scripts > Srutilekha**. The tray helper opens the caption form. Subsequent clicks reopen closed captions or bring the existing caption window forward.
4. Use the existing Master Studio controls, review and Generate/Sync workflow.

The desktop app cannot start the sandboxed Lua script in Free by itself. The helper must be running before script clicks can open the EXE. Windows startup handles this; if you quit the helper or disable startup, open Srutilekha manually to restart it. Automatic connection reads metadata and opens the form only. Generate, Sync and Undo remain explicit actions.

Right-click the tray icon for Open captions, API settings, Updates, Start with Windows and Quit helper. The home page also provides a Start quietly with Windows checkbox. Disabling startup writes a preference marker so an upgrade does not enable it again. Closing captions leaves the helper alive; Quit helper does not terminate caption jobs. Launch with `--home` to open the home/settings/update page directly.

Do not switch projects during a caption operation. The bridge stays available until Resolve closes; subsequent script clicks reuse a responsive bridge. Concurrent desktop workflows are blocked. Caption operations time out without automatic retries; inspect Resolve before repeating an import after a timeout. The helper only sends a read-only connection probe when a fresh script launch marker appears; it makes no idle Resolve API calls.

The bridge uses a per-user request file and Resolve-managed Fusion preferences for responses. Connecting requires no Python installation, external scripting server or paid API call. Existing encrypted API keys and presets retain their original storage.

Resolve 21.1 uses SetProperties/GetProperties and GetSpeed; the bridge adapts the old calls. Rejected caption styling properties are reported. Review caption styling in Resolve after import.

This is a **prerelease**, excluded from stable automatic updates. Connection and read-only timeline metadata were verified on Resolve 21.1.1.10 Free. Import logic was tested with isolated objects. Real 21.1 caption import/styling remains unverified because the current project must stay untouched. No paid transcription was run. Stable v1.3.0 remains the existing public stable release.
