import json
import sys
from pathlib import Path
from PyInstaller.utils.hooks import copy_metadata, collect_data_files

root = Path(SPECPATH)
mac = sys.platform == 'darwin'
ffmpeg = root / 'build' / 'vendor' / ('ffmpeg' if mac else 'ffmpeg.exe')
datas = [(str(root / 'loader.pyw'), '.'), (str(root / 'icon.ico'), '.'),
         (str(root / 'resolve_bridge.lua'), '.'), (str(root / 'ui'), 'ui'),
         (str(root / 'version.json'), '.'), (str(root / 'data'), 'data'),
         (str(root / 'installer' / 'COPYING.LGPLv2.1'), 'licenses')]
# On macOS FFmpeg is a Mach-O binary, so PyInstaller must treat it as one
# (it lands in Contents/Frameworks/bin and gets the bundle's ad-hoc signature).
binaries = [(str(ffmpeg), 'bin')] if mac else []
if not mac:
    datas.append((str(ffmpeg), 'bin'))
datas += copy_metadata('elevenlabs', recursive=True)
datas += copy_metadata('truststore')
# LGPL pystray stays as replaceable Python source outside the executable archive.
datas += collect_data_files('pystray', include_py_files=True)
for package in ('pystray', 'psutil', 'Pillow', 'six') + (() if mac else ('pywebview', 'pythonnet', 'bottle')):
    datas += copy_metadata(package)
gui_hidden = ['dialog', 'web_ui', 'web_home', 'web_studio', 'web_run', 'web_review', 'transcribe', 'release_updater', 'studio_form', 'truststore',
              'tkinter.font', 'tkinter.filedialog', 'six', 'PIL.ImageWin']
if mac:
    # pystray is excluded from the archive, so its macOS backend's PyObjC
    # dependencies have to be named explicitly.
    gui_hidden += ['objc', 'Foundation', 'AppKit', 'Quartz', 'PyObjCTools', 'PyObjCTools.MachSignals']
# Both processes share one runtime directory. The worker keeps a console
# subsystem for its UTF-8 progress pipe, but is started with CREATE_NO_WINDOW.
gui = Analysis(['app.py'], pathex=[str(root)], binaries=binaries, datas=datas,
               hiddenimports=gui_hidden,
               hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=['pystray'], noarchive=False)
worker = Analysis(['worker.py'], pathex=[str(root)], binaries=binaries, datas=datas,
                  hiddenimports=['transcribe', 'truststore'], hookspath=[], hooksconfig={},
                  runtime_hooks=[], excludes=[], noarchive=False)
gui_pyz = PYZ(gui.pure)
worker_pyz = PYZ(worker.pure)
gui_exe = EXE(gui_pyz, gui.scripts, [], exclude_binaries=True, name='Srutilekha',
              console=False, icon=str(root / 'icon.ico'),
              manifest=None if mac else str(root / 'app.manifest'))
worker_exe = EXE(worker_pyz, worker.scripts, [], exclude_binaries=True,
                 name='Srutilekha-worker', console=True, icon=str(root / 'icon.ico'))
coll = COLLECT(gui_exe, worker_exe, gui.binaries, gui.datas, worker.binaries,
               worker.datas, strip=False, upx=False, name='Srutilekha')
if mac:
    version = json.loads((root / 'version.json').read_text(encoding='utf-8'))['version']
    # Pillow converts icon.ico to .icns during the build.
    app = BUNDLE(coll, name='Srutilekha.app', icon=str(root / 'icon.ico'),
                 bundle_identifier='org.srutilekha.app',
                 info_plist={'CFBundleShortVersionString': version, 'CFBundleVersion': version,
                             'NSHighResolutionCapable': True,
                             'LSMinimumSystemVersion': '12.0',
                             'NSHumanReadableCopyright': 'Srutilekha'})
