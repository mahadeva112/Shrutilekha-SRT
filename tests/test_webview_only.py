"""WebView2 is Srutilekha's only interface: no Tk fallback, Setup brings the
runtime, and every entry point explains itself when a window cannot open."""
import os
from pathlib import Path
import re
import runpy
import sys
import tempfile
import unittest
from unittest import mock

import app
import web_notice
import web_ui

ROOT = Path(__file__).resolve().parents[1]


class LoaderOutcomeTest(unittest.TestCase):
    """loader.pyw main(): how each studio outcome ends the run for Resolve."""

    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.dir = Path(scratch.name)
        (self.dir / "prompt.json").write_text('{"items": ["A1"], "defaults": {}}', encoding="utf-8")
        self.main = runpy.run_path(str(ROOT / "loader.pyw"))["main"]
        self.argv = ["loader.pyw"]
        for name in ("prompt", "selection", "args-file", "done", "log", "python", "script", "result", "ack"):
            self.argv += ["--" + name, str(self.dir / (name + (".json" if name == "prompt" else "")))]

    def run_main(self, outcome):
        g = self.main.__globals__
        with mock.patch.dict(g, _run_web_studio=lambda prompt, a: outcome), \
             mock.patch.object(sys, "argv", self.argv), \
             mock.patch("web_notice.tell") as tell:
            with self.assertRaises(SystemExit) as stop:
                self.main()
        done, ack = self.dir / "done", self.dir / "ack"
        return (stop.exception.code, done.read_text() if done.exists() else None,
                ack.read_text() if ack.exists() else None, tell)

    def test_finished_run_exits_with_the_studios_code(self):
        code, done, ack, tell = self.run_main({"action": "finished", "code": 0})
        self.assertEqual((code, done, ack), (0, None, None))   # web_run already wrote them
        tell.assert_not_called()

    def test_cancel_tells_resolve_and_shows_nothing(self):
        code, done, ack, tell = self.run_main({"action": "cancel"})
        self.assertEqual((code, done, ack), (130, "130", "cancel"))
        tell.assert_not_called()

    def test_superseded_run_only_writes_done(self):
        code, done, ack, tell = self.run_main({"action": "superseded"})
        self.assertEqual((code, done, ack), (130, "130", None))
        tell.assert_not_called()

    def test_missing_webview2_cancels_the_run_and_says_how_to_fix_it(self):
        code, done, ack, tell = self.run_main(None)
        self.assertEqual((code, done, ack), (130, "130", "cancel"))
        tell.assert_called_once_with(web_notice.MISSING_RUNTIME)

    def test_window_failure_cancels_the_run_with_a_restart_notice(self):
        code, done, ack, tell = self.run_main({"action": "failed", "details": "Traceback: boom"})
        self.assertEqual((code, done, ack), (130, "130", "cancel"))
        notice = tell.call_args[0][0]
        self.assertEqual(notice["title"], "Let's restart Srutilekha")
        self.assertIn("Traceback: boom", notice["details"])

    def test_no_webview2_opens_no_studio(self):
        run_web_studio = self.main.__globals__["_run_web_studio"]
        with mock.patch("web_ui.available", return_value=False), \
             mock.patch("web_studio.run") as studio:
            self.assertIsNone(run_web_studio({}, mock.Mock()))
        studio.assert_not_called()


class AppEntryTest(unittest.TestCase):
    def test_home_without_webview2_shows_the_missing_runtime_notice(self):
        with mock.patch("web_ui.available", return_value=False), \
             mock.patch("web_home.run") as home, \
             mock.patch("web_notice.tell") as tell:
            app.show_home()
        home.assert_not_called()
        tell.assert_called_once_with(web_notice.MISSING_RUNTIME)

    def test_home_window_failure_is_explained(self):
        with mock.patch("web_ui.available", return_value=True), \
             mock.patch("web_home.run", side_effect=RuntimeError("no edge")), \
             mock.patch("web_notice.tell") as tell:
            app.show_home()
        notice = tell.call_args[0][0]
        self.assertEqual(notice["title"], "Let's restart Srutilekha")
        self.assertIn("no edge", notice["details"])

    def test_bridge_error_is_shown_as_a_notice(self):
        with mock.patch("sys.argv", ["app.py", "--bridge-run"]), \
             mock.patch("resolve_bridge.run_workflow", side_effect=RuntimeError("No project is open.")), \
             mock.patch("web_notice.tell") as tell:
            app.main()
        notice = tell.call_args[0][0]
        self.assertEqual(notice["title"], "Open a project to begin")
        self.assertEqual(notice["kind"], "error")


class NoTkTest(unittest.TestCase):
    SKIP = {"tests", ".venv", "build", "dist", ".git", ".claude", ".tools", "browser-preview"}

    def sources(self):
        for path in ROOT.rglob("*"):
            if path.suffix in (".py", ".pyw") and not self.SKIP & set(path.relative_to(ROOT).parts):
                yield path

    def test_no_module_imports_tkinter(self):
        pattern = re.compile(r"^\s*(import\s+tkinter|from\s+tkinter\s+import)", re.M)
        found = [p.name for p in self.sources() if pattern.search(p.read_text(encoding="utf-8"))]
        self.assertEqual(found, [])

    def test_classic_ui_switch_and_modules_are_gone(self):
        for name in ("studio_form.py", "settings_ui.py"):
            self.assertFalse((ROOT / name).exists(), name)
        for path in self.sources():
            self.assertNotIn("SRUTILEKHA_CLASSIC_UI", path.read_text(encoding="utf-8"), path.name)

    def test_build_leaves_tcl_tk_out(self):
        spec = (ROOT / "Srutilekha.spec").read_text(encoding="utf-8")
        self.assertNotIn("studio_form", spec)
        self.assertEqual(spec.count("'tkinter', '_tkinter'"), 2)     # GUI and worker


class InstallerTest(unittest.TestCase):
    def test_setup_installs_webview2_before_any_file(self):
        iss = (ROOT / "installer" / "Srutilekha.iss").read_text(encoding="utf-8")
        # The same runtime key and bootstrapper the app checks and names.
        self.assertIn("Microsoft\\EdgeUpdate\\Clients\\" + web_ui.WEBVIEW2_CLIENT, iss)
        self.assertIn(web_ui.WEBVIEW2_DOWNLOAD, iss)
        self.assertIn("CreateDownloadPage", iss)
        self.assertRegex(iss, r"if CurPageID = wpReady then\s+Result := InstallWebView2;")
        self.assertIn("'/silent /install'", iss)
        for root in ("HKLM32", "HKLM64", "HKCU"):
            self.assertIn("WebView2Found(%s," % root, iss)


@unittest.skipUnless(sys.platform == "win32", "Windows font enumeration")
class FontFamiliesTest(unittest.TestCase):
    def test_lists_installed_families_without_tk(self):
        families = runpy.run_path(str(ROOT / "loader.pyw"))["font_families"]()
        self.assertEqual(families, sorted(set(families)))
        self.assertIn("Segoe UI", families)
        self.assertIn("Arial", families)
        self.assertFalse([f for f in families if f.startswith("@")])


if __name__ == "__main__":
    unittest.main()
