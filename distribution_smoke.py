"""Runs inside the packaged GUI to verify runtime, form, worker and key storage."""
import importlib.util
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
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
        assert len(transcribe.languages.LANGUAGES) == 13
        assert (resources() / "data" / "translit_beng.json.gz").is_file()
        import dpi
        dpi.enable()
        if os.name == 'nt':
            import ctypes
            u = ctypes.windll.user32
            u.GetThreadDpiAwarenessContext.restype = ctypes.c_void_p
            u.AreDpiAwarenessContextsEqual.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
            assert u.AreDpiAwarenessContextsEqual(u.GetThreadDpiAwarenessContext(), ctypes.c_void_p(-4))
        # Every window is WebView2: pywebview and the pages ship, Tcl/Tk does not.
        if getattr(sys, "frozen", False):
            assert importlib.util.find_spec("tkinter") is None
        import webview  # noqa: F401
        import web_ui
        import web_notice  # noqa: F401
        for page in ("home.html", "studio.html", "notice.html"):
            assert web_ui.page(page) is not None, page
        namespace = runpy.run_path(str(resources() / "loader.pyw"))
        families = namespace["font_families"]()
        assert families and not any(f.startswith("@") for f in families)
        import web_studio
        ctx = dict(languages=namespace["LANGUAGES"], language_codes=namespace["LANGUAGE_CODES"],
                   frames=namespace["FRAME_FORMATS"], default_frame=namespace["DEFAULT_FRAME"],
                   caption_fonts=namespace["CAPTION_FONTS"], font_styles=namespace["FONT_STYLES"],
                   families=families, demo_captions=web_studio.DEMO_CAPTIONS, updater=None,
                   frozen=True, run_id=None, run_marker=None)
        studio = web_studio.StudioApi({"items": ["A1 - Test voice"], "defaults": {}}, ctx).initial()
        assert studio["values"]["lang"] == "Auto-detect"
        assert set(web_studio.DEMO_CAPTIONS) == set(namespace["LANGUAGES"]) - {"Auto-detect"}
        api = web_ui.BaseApi()
        assert api.save_key("distribution-test-key")["ok"]
        assert credentials.get_key() == "distribution-test-key"
        assert api.key_state() == {"hasKey": True}
        assert api.remove_key()["ok"] and not credentials.get_key()
        # A large review: re-cut and written locally, as Apply does.
        import web_review
        segments = [{'s': i * 2., 'e': i * 2. + 1.8, 'spk': 0, 'text': 'A clear story',
                     'words': [(i * 2., i * 2. + .5, 'A'), (i * 2. + .6, i * 2. + 1., 'clear'),
                               (i * 2. + 1.1, i * 2. + 1.8, 'story')]} for i in range(255)]
        live = [web_review.live_segment(seg) for seg in segments]
        cut = web_review.resplit(live, web_review.settings({"max_chars": "30", "lang": "English"},
                                                           namespace["LANGUAGE_CODES"]))
        assert len(cut) >= 255
        srt = Path(scratch) / 'review.srt'
        web_review.write_srt_cap(str(srt), str(srt) + '.cap', [], cut)
        assert srt.stat().st_size
        worker = subprocess.run([str(install_dir() / "Srutilekha-worker.exe"), "--self-test"],
                                capture_output=True, text=True, encoding="utf-8", timeout=30,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if worker.returncode:
            raise RuntimeError(worker.stdout + worker.stderr)
        report = {"gui": "ok", "resolve_form": "ok", "master_studio": "web studio state",
                  "demo_languages": "all", "encrypted_key": "ok", "api_settings": "in-window",
                  "webview2": web_ui.runtime_version() or "missing", "tkinter": "not shipped",
                  "tray": "native icon and menu", "dpi": "PerMonitorV2",
                  "review": "255 cues, local re-cut and SRT/.cap write",
                  "worker": worker.stdout.strip()}
        Path(output).write_text(json.dumps(report, indent=2), encoding="utf-8")
