# Windows release validation

v1.3.5 preview: 39 checks passed, covering all visible Master Studio controls,
Generate/Sync switching, preset/output values, language demos and layout bounds
at normal and compact window sizes. An isolated native Windows preview was
visually inspected at 1180 x 820 for section marks, card depth, typography,
warm selected controls and dark inputs. Frozen and installed runtime checks
passed. Upgrade/reinstall preserved encrypted-key and preset/settings bytes.
Focus styling retains error borders. No Resolve project changes or paid API
calls were made. Real Resolve 21.1 caption import/styling remains unverified.

v1.3.4 preview: disabled PillEntry controls now use the same #191c22 background
as enabled controls, with muted disabled text. Generate/Sync widget inspection
confirmed the disabled/normal states and matching backgrounds. All 39 existing
tests passed, and frozen/installed runtime checks passed. The installed
upgrade preserved encrypted-key and preset/settings bytes and restarted one
tray helper and one caption form. The idle old form was closed through its
existing supersede protocol; no transcription worker or submitted selection
was active. No Resolve project changes or paid API calls were performed.

v1.3.3 preview: 39 tests passed. Tray tests cover one launch per script-click
marker, reopening on a new marker, raising an active caption window, ignoring
old Resolve sessions, opening the app before the script, single-helper locking,
startup settings and quitting without terminating caption jobs. The native
Windows tray icon/menu passed frozen and installed smoke tests. Upgrade and
reinstall retained encrypted-key/preset bytes; disabling Windows startup
survived reinstall and the original startup choice was restored. Duplicate
helper starts, quit and restart were verified against the installed EXE. The
home startup checkbox was visually checked and closing home left one helper
running (about 49 MB RSS on the development machine). Pystray source and license
texts are shipped as replaceable files outside the executable archive.

Live follow-up on Resolve 21.1.1.10 Free: the user clicked the Workspace script
and confirmed the caption window opened automatically. Logs show cancellation
and reopening, and process inspection found one helper, one caption workflow
and one caption form. A later launch marker differed from the active server
session, verifying that subsequent script clicks reused the resident bridge.
Read-only probes found the current project, timeline and two audio tracks.
No project switch/save, caption import or paid API request was performed.
Real 21.1 caption import/styling remains unverified, so this is a prerelease.

v1.3.2 preview: 32 checks passed. New GUI event-loop tests verify automatic
caption launch without a click, waiting when the bridge is absent, and avoiding
duplicate workflows. Packaged runtime and the installed upgrade passed smoke
checks; encrypted key and preset/settings bytes were preserved. The actual
waiting screen was visually inspected with Resolve closed. The bridge-ready
automatic launch was tested with an isolated handshake; real 21.1 import and
styling remain unverified. No project edits or paid transcription were performed.

v1.3.1 preview: 29 checks passed, including mailbox encoding, response errors,
timeout cleanup, lock exclusion, rejected styling writes, clip speed/range
mapping and import isolation from existing cues. Actual Lua handshake and
read-only audio-track/frame-rate metadata succeeded on Resolve 21.1.1.10 Free.
The current project was not switched, modified or saved. Real 21.1 caption
import/styling and paid transcription are not validated; this is a prerelease.
The installer upgraded the existing v1.3.0 installation to v1.3.1, selected the
Lua bridge automatically for Resolve 21.1, and preserved encrypted-key and
preset/settings bytes. Frozen runtime checks passed before and after upgrade,
including bridge modules/resources, all Master Studio sections, independent
demo languages, account settings, worker and FFmpeg. Resolve was not restarted.

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

v1.3.0 Master Studio: twenty-three checks passed. All setup sections and
controls stay mapped and within their panels at 1180 × 820, 1040 × 780,
1040 × 720, 1040 × 698 and 984 × 698. Generate/Sync retains values and writes the existing
selection protocol, including SRT input path and caption style. Named presets
round-trip the original font/style/colour and timing fields. The colour picker
can return to automatic colour. English remains the default demo when a saved
caption preset selects Bengali. Caption review/edit/local re-split checks pass.
Native screenshot capture was unavailable: the capture helper reported the
isolated Tk validation window as minimized, despite its normal Tk state.
Layout validation used mapped widget bounds; a visual pixel comparison remains
unverified. Paid transcription was not repeated for this presentation change.
The locally built installer passed upgrade from v1.2.2, reinstall, uninstall,
encrypted-key/preset preservation, frozen GUI/form/worker checks without
external Python on PATH and bundled FFmpeg trimming/decoding. The frozen
report confirms `master_studio: all sections`. Existing Resolve launcher files
and the installation pointer were restored.
