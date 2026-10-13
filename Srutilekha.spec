from pathlib import Path
from PyInstaller.utils.hooks import copy_metadata, collect_data_files

root = Path(SPECPATH)
datas = [(str(root / 'loader.pyw'), '.'), (str(root / 'icon.ico'), '.'),
         (str(root / 'resolve_bridge.lua'), '.'),
         (str(root / 'version.json'), '.'), (str(root / 'data'), 'data'),
         (str(root / 'build' / 'vendor' / 'ffmpeg.exe'), 'bin'),
         (str(root / 'installer' / 'COPYING.LGPLv2.1'), 'licenses')]
datas += copy_metadata('elevenlabs', recursive=True)
datas += copy_metadata('truststore')
# LGPL pystray stays as replaceable Python source outside the executable archive.
datas += collect_data_files('pystray', include_py_files=True)
for package in ('pystray', 'psutil', 'Pillow', 'six'):
    datas += copy_metadata(package)
# Both processes share one runtime directory. The worker keeps a console
# subsystem for its UTF-8 progress pipe, but is started with CREATE_NO_WINDOW.
gui = Analysis(['app.py'], pathex=[str(root)], binaries=[], datas=datas,
               hiddenimports=['dialog', 'transcribe', 'release_updater', 'studio_form', 'truststore',
                              'tkinter.font', 'tkinter.filedialog', 'six', 'PIL.ImageWin'],
               hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=['pystray'], noarchive=False)
worker = Analysis(['worker.py'], pathex=[str(root)], binaries=[], datas=datas,
                  hiddenimports=['transcribe', 'truststore'], hookspath=[], hooksconfig={},
                  runtime_hooks=[], excludes=[], noarchive=False)
gui_pyz = PYZ(gui.pure)
worker_pyz = PYZ(worker.pure)
gui_exe = EXE(gui_pyz, gui.scripts, [], exclude_binaries=True, name='Srutilekha',
              console=False, icon=str(root / 'icon.ico'))
worker_exe = EXE(worker_pyz, worker.scripts, [], exclude_binaries=True,
                 name='Srutilekha-worker', console=True, icon=str(root / 'icon.ico'))
coll = COLLECT(gui_exe, worker_exe, gui.binaries, gui.datas, worker.binaries,
               worker.datas, strip=False, upx=False, name='Srutilekha')
