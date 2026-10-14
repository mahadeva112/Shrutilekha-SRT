import json
from pathlib import Path
import runpy
import tempfile
import tkinter as tk
import unittest
from unittest import mock

import web_studio

ROOT = Path(__file__).resolve().parents[1]
PROMPT = {"items": ["Track 1: Audio 1", "Track 2: Audio 2"],
          "defaults": {"lang": "Hindi", "settings": "30,,3", "review": 0, "shadow": 0},
          "resolution": "1080x1920", "timeline": "Timeline 1", "fps": 25}


class WebStudioTest(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.ns = runpy.run_path(str(ROOT / "loader.pyw"))
        self.ns["App"].__init__.__globals__.update(
            updater=None, data_dir=lambda: self.scratch.name,
            _steal_focus=lambda root: None, _keep_topmost=lambda root: None)
        self.ctx = dict(languages=self.ns["LANGUAGES"], frames=self.ns["FRAME_FORMATS"],
                        default_frame=self.ns["DEFAULT_FRAME"], caption_fonts=self.ns["CAPTION_FONTS"],
                        font_styles=self.ns["FONT_STYLES"], families=[], demo_captions={},
                        updater=None, frozen=False, run_id=None, run_marker=None)
        patcher = mock.patch("web_studio.data_dir", return_value=self.scratch.name)
        patcher.start()
        self.addCleanup(patcher.stop)

    def app(self, prefill=None):
        root = tk.Tk()
        root.withdraw()

        def close():
            # Run queued layout jobs first: the prefill path replaces the
            # form before its idle refit fires.
            try:
                root.update()
            except tk.TclError:
                pass
            root.destroy()
        self.addCleanup(close)
        p = Path(self.scratch.name)
        with mock.patch.object(self.ns["App"], "_wait_for_args_and_run", lambda self: None):
            return self.ns["App"](root, PROMPT, str(p / "selection"), str(p / "args"), str(p / "done"),
                                  str(p / "log"), "unused", "unused", str(p / "result"), str(p / "ack"),
                                  prefill=prefill)

    def tk_values(self, app):
        names = dict(chosen=app.combo_var, lang=app.lang_var, min_secs=app.min_var, cps=app.cps_var,
                     text_size=app.textsize_var, words_per=app.words_per_var, aspect=app.aspect_var,
                     srt_posy=app.srt_posy_var, ref_script=app.ref_script_var, color=app.color_var,
                     font=app.font_var, font_style=app.font_style_var, punct=app.punct_var,
                     diarize=app.diarize_var, outline=app.outline_var, shadow=app.shadow_var,
                     safe_zone=app.safe_zone_var, review=app.review_var)
        values = {k: v.get() for k, v in names.items()}
        values.update(zip(web_studio.SETTINGS_KEYS, (v.get() for v in app.settings_vars)))
        return values

    def test_initial_values_match_the_tk_form(self):
        web = web_studio.initial_values(PROMPT, self.ctx)
        tk_values = self.tk_values(self.app())
        for key, value in tk_values.items():
            self.assertEqual(web[key], value, key)

    def test_prefilled_submit_writes_the_same_selection_as_the_tk_form(self):
        values = web_studio.initial_values(PROMPT, self.ctx)
        values.update(chosen="Track 2: Audio 2", aspect="HD", srt_posy="0.200", max_chars="22",
                      punct=1, color="#ffcc00", review=1)
        self.app({"action": "generate", "values": values})
        sel = json.loads((Path(self.scratch.name) / "selection").read_text(encoding="utf-8"))
        self.assertEqual(sel["action"], "generate")
        self.assertEqual(sel["chosen"], "Track 2: Audio 2")
        self.assertEqual(sel["settings"], "22,1,3")
        self.assertEqual((sel["lang"], sel["lang_code"]), ("Hindi", "hin"))
        self.assertEqual((sel["punct"], sel["review"], sel["shadow"]), (1, 1, 0))
        self.assertEqual(sel["color"], "#ffcc00")
        self.assertEqual(sel["srt_posy"], str(round(0.2 * 1920)))

    def test_presets_are_shared_with_the_tk_form(self):
        api = web_studio.StudioApi(PROMPT, self.ctx)
        values = web_studio.initial_values(PROMPT, self.ctx)
        values.update(cps="18", font_style="Bold", outline=0, max_lines="2")
        self.assertTrue(api.save_preset("Talk", values)["ok"])
        app = self.app()
        app._preset_actions["apply"]("Talk")
        self.assertEqual((app.cps_var.get(), app.font_style_var.get(), app.outline_var.get()), ("18", "Bold", 0))
        self.assertEqual(app.settings_vars[1].get(), "2")
        app.cps_var.set("21")
        app.preset_name_var.set("FromTk")
        app._preset_actions["save"]()
        loaded = api.load_preset("FromTk")
        self.assertTrue(loaded["ok"])
        self.assertEqual(loaded["values"]["cps"], "21")
        self.assertEqual(api.remove_preset("Talk")["presets"], ["FromTk"])

    def test_preset_names_cannot_leave_the_presets_folder(self):
        api = web_studio.StudioApi(PROMPT, self.ctx)
        self.assertFalse(api.save_preset("..\\evil", {})["ok"])
        self.assertFalse(api.load_preset("../evil")["ok"])

    def test_submit_validates_before_closing(self):
        api = web_studio.StudioApi(PROMPT, dict(self.ctx, frozen=True))
        api._window = mock.Mock()
        values = web_studio.initial_values(PROMPT, self.ctx)
        with mock.patch("credentials.get_key", return_value=""):
            self.assertTrue(api.submit("generate", values)["needKey"])
        with mock.patch("credentials.get_key", return_value="k"):
            self.assertFalse(api.submit("sync", values)["ok"])
            self.assertFalse(api.submit("generate", dict(values, chosen=""))["ok"])
            api._window.destroy.assert_not_called()
            self.assertTrue(api.submit("generate", values)["ok"])
        api._window.destroy.assert_called_once()
        self.assertEqual(api.result["action"], "generate")

    def test_superseded_run_closes_the_window(self):
        marker = Path(self.scratch.name) / "current_run.txt"
        marker.write_text("newer", encoding="utf-8")
        api = web_studio.StudioApi(PROMPT, dict(self.ctx, run_id="mine", run_marker=str(marker)))
        api._window = mock.Mock()
        closed = mock.Mock(is_set=mock.Mock(return_value=False))
        api._watch(closed)
        self.assertEqual(api.result, {"action": "superseded"})
        api._window.destroy.assert_called_once()


if __name__ == "__main__":
    unittest.main()
