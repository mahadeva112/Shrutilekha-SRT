Public stable release: standalone Windows x64 installer for Srutilekha.

- Bundled Python runtime and transcription worker; no separate Python install.
- Save your own ElevenLabs API key encrypted for your Windows user.
- API settings open inside the captions window with matching dark styling.
- Rounded account card, rounded input and buttons, and clearer spacing.
- Integrated Show/Hide, connection check and key removal stay in the same panel.
- Back/Escape return to captions; Enter saves the key.
- Installer registers a Lua or Python launcher for your Resolve version.
- Stable GitHub release updates preserve API keys, presets, cache and logs.

Open Srutilekha to enter your API key. Restart Resolve after installation, then
launch Workspace → Scripts → Srutilekha to generate captions.

Windows x64. Setup offers Lua for Resolve 21.0 and earlier, or Python for 21.1+.
Lua launching and SRT timeline import were tested in Resolve 21.0.4.5.
Resolve 21.1+ remains untested and needs a working Resolve Python scripting
host. This app does not configure that host.

Validated for v1.1.3: fourteen automated checks, native settings layout at
small and large window sizes, frozen GUI/form/worker without external Python,
upgrade from v1.1.0, reinstall, key/preset preservation, and bundled FFmpeg
audio trimming/decoding. The earlier v1.1.1 runtime also passed clean Windows CI.
An actual clean physical PC and paid ElevenLabs transcription remain untested.

This stable release is offered through the app's GitHub update checker to
users on older versions. Use Check for updates, then Install update.

The release includes exact FFmpeg 7.1.1 source, LGPL license, build script,
configuration and toolchain versions alongside Setup.exe and SHA256SUMS.txt.
