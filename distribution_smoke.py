"""Runs inside the packaged GUI to verify runtime, form, worker and key storage."""
import json
import os
from pathlib import Path
import runpy
import subprocess
import tempfile
import tkinter as tk
from app_runtime import resources, install_dir, prepare_environment


def run(output):
    prepare_environment()
    with tempfile.TemporaryDirectory() as scratch:
        os.environ["SRUTILEKHA_USER_DIR"] = scratch
        import resolve_bridge
        import tray_helper
        import audio_to_srt
        assert callable(resolve_bridge.run_workflow)
        assert callable(audio_to_srt.import_srt_to_new_track)
        assert (resources() / 'resolve_bridge.lua').is_file()
        tray_report = Path(scratch) / 'tray-test.json'
        subprocess.run([str(install_dir() / 'Srutilekha.exe'), '--tray-self-test', str(tray_report)],
                       check=True, timeout=20, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        assert json.loads(tray_report.read_text())['visible']
        import credentials
        credentials.save_key("distribution-test-key")
        assert credentials.get_key() == "distribution-test-key"
        credentials.delete_key()
        assert not credentials.get_key()
        import transcribe
        from elevenlabs.client import ElevenLabs
        assert callable(ElevenLabs(api_key="distribution-test-key").user.get)
        assert len(transcribe.languages.LANGUAGES) == 14
        assert (resources() / "data" / "translit_beng.json.gz").is_file()
        root = tk.Tk()
        root.withdraw()
        namespace = runpy.run_path(str(resources() / "loader.pyw"))
        app_class = namespace["App"]
        app_class.__init__.__globals__["updater"] = None
        p = Path(scratch)
        app = app_class(root, {"items": ["A1 â€” Test voice"], "defaults": {}},
                        str(p / "selection"), str(p / "args"), str(p / "done"),
                        str(p / "log"), "unused", "unused", str(p / "result"), str(p / "ack"))
        root.update_idletasks()
        assert app.lang_var.get() == "Auto-detect"
        assert set(app._studio_sections) == {"Audio", "Timing", "Files", "Presets", "Style"}
        assert app._scroll_canvas is None
        from studio_form import DEMO_CAPTIONS
        assert app.demo_language_var.get() == "English"
        assert app._preview.SAMPLE == DEMO_CAPTIONS["English"]
        app.demo_language_var.set("Tamil")
        assert app._preview.SAMPLE == DEMO_CAPTIONS["Tamil"]
        assert app.lang_var.get() == "Auto-detect"
        app._set_task("Sync Existing")
        assert app.studio_controls["sync_srt"].entry.cget("state") == "normal"
        app._set_task("Generate")
        assert app.studio_controls["sync_srt"].entry.cget("state") == "disabled"
        from settings_ui import ApiSettingsPanel
        bindings = {key: root.bind(key) for key in ("<Return>", "<Escape>")}
        panel = ApiSettingsPanel(root)
        assert panel.winfo_toplevel() is root
        panel.value.set("distribution-test-key")
        panel.save()
        assert credentials.get_key() == "distribution-test-key"
        assert all(root.bind(key) == script for key, script in bindings.items())
        root.destroy()
        worker = subprocess.run([str(install_dir() / "Srutilekha-worker.exe"), "--self-test"],
                                capture_output=True, text=True, encoding="utf-8", timeout=30,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if worker.returncode:
            raise RuntimeError(worker.stdout + worker.stderr)
        report = {"gui": "ok", "resolve_form": "ok", "master_studio": "all sections", "demo_languages": "independent", "encrypted_key": "ok", "api_settings": "in-window",
                  "tray": "native icon and menu",
                  "worker": worker.stdout.strip()}
        Path(output).write_text(json.dumps(report, indent=2), encoding="utf-8")
