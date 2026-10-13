# Resolve 21.1 connection — v1.3.2 preview

The old installer selected Python for every Resolve 21.1 installation. Python scripting requires Studio, so this hid the launcher in Free. The preview uses a local Lua bridge and keeps the UI and transcription in the desktop EXE.

1. Install Srutilekha-Setup-1.3.2.exe. Select **Resolve 21.1 or newer, Free or Studio (Lua bridge + desktop app)**, the detected default.
2. Save your work and restart Resolve when convenient to refresh the Scripts menu.
3. Start **Workspace > Scripts > Srutilekha** once per Resolve session. It prints a ready message.
4. Open the desktop app. It connects automatically and opens the caption form. If you open the app before starting the script, it waits and connects after you start the script. Use the existing Master Studio controls, review and Generate/Sync workflow.

The desktop app cannot start the sandboxed Lua script in Free by itself. Start the script once per Resolve session; no Connect click is needed. Automatic connection reads metadata and opens the form only. Generate, Sync and Undo remain explicit actions. Launch with `--home` to keep the home/settings/update page open without automatic connection.

Do not switch projects during a caption operation. The bridge stays available until Resolve closes; starting it again replaces the older bridge. Concurrent desktop workflows are blocked. Requests time out without automatic retries; inspect Resolve before repeating an import after a timeout.

The bridge uses a per-user request file and Resolve-managed Fusion preferences for responses. Connecting requires no Python installation, external scripting server or paid API call. Existing encrypted API keys and presets retain their original storage.

Resolve 21.1 uses SetProperties/GetProperties and GetSpeed; the bridge adapts the old calls. Rejected caption styling properties are reported. Review caption styling in Resolve after import.

This is a **prerelease**, excluded from stable automatic updates. Connection and read-only timeline metadata were verified on Resolve 21.1.1.10 Free. Import logic was tested with isolated objects. Real 21.1 caption import/styling remains unverified because the current project must stay untouched. No paid transcription was run. Stable v1.3.0 remains the existing public stable release.
