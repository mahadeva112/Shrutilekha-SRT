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
        app = app_class(root, {"items": ["A1 — Test voice"], "defaults": {}},
                        str(p / "selection"), str(p / "args"), str(p / "done"),
                        str(p / "log"), "unused", "unused", str(p / "result"), str(p / "ack"))
        root.update_idletasks()
        assert app.lang_var.get() == "Auto-detect"
        root.destroy()
        worker = subprocess.run([str(install_dir() / "Srutilekha-worker.exe"), "--self-test"],
                                capture_output=True, text=True, encoding="utf-8", timeout=30,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if worker.returncode:
            raise RuntimeError(worker.stdout + worker.stderr)
        report = {"gui": "ok", "resolve_form": "ok", "encrypted_key": "ok",
                  "worker": worker.stdout.strip()}
        Path(output).write_text(json.dumps(report, indent=2), encoding="utf-8")
