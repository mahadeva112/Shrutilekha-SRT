import json
import os
from pathlib import Path
import runpy
import tempfile
import tkinter as tk
from tkinter import font as tkfont
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]

class StudioFormTests(unittest.TestCase):
    def test_source_preparation_error_shows_in_window_without_launching_worker(self):
        self.app._build_progress()
        Path(self.app.result_path).write_text('Audio source unavailable\nNo transcription was started.',encoding='utf-8')
        with patch.object(self.app,'_run_transcribe') as worker:
            self.app._wait_for_args_and_run()
            worker.assert_not_called()
        self.app._pump();self.root.update()
        self.assertEqual(self.app.exit_code,1)
        def texts(widget):
            result=[]
            if isinstance(widget,tk.Label):result.append(widget.cget('text'))
            for child in widget.winfo_children():result.extend(texts(child))
            return result
        self.assertIn("Couldn't start captions",texts(self.root))
        self.assertEqual(self.app.demo_language_var.get(),'English')

    def setUp(self):
        self.scratch=tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.ns=runpy.run_path(str(ROOT/'loader.pyw'))
        self.ns['App'].__init__.__globals__.update(updater=None, data_dir=lambda:self.scratch.name,
            _steal_focus=lambda root:None, _keep_topmost=lambda root:None)
        self.root=tk.Tk();self.root.withdraw()
        self.errors=[]
        self.root.report_callback_exception=lambda *args:self.errors.append(str(args[1]))
        p=Path(self.scratch.name)
        self.app=self.ns['App'](self.root,{'items':['Track 1: Audio 1'],'defaults':{},
            'resolution':'1080x1920','timeline':'Timeline 1','fps':25},
            str(p/'selection'),str(p/'args'),str(p/'done'),str(p/'log'),
            'unused','unused',str(p/'result'),str(p/'ack'))
        self.root.attributes('-topmost',False)
        self.root.deiconify();self.root.update()
        def close_root():
            for job in self.root.tk.call('after','info'):
                self.root.after_cancel(job)
            self.root.destroy()
        self.addCleanup(close_root)
    def tearDown(self):
        self.assertFalse(self.errors,self.errors)
    def test_all_master_controls_are_visible_and_fit(self):
        self.assertEqual(set(self.app.studio_controls),{'track','language','punctuation','speakers','review',
            'safe_zone','position','max_chars','max_lines','min_secs','max_secs','cps','max_words',
            'reference_script','sync_srt','preset','preset_name','font','font_style',
            'text_size','color','outline','shadow','demo_language'})
        self.assertIsNone(self.app._scroll_canvas)
        self.assertFalse(hasattr(self.app,'_studio_tabs'))
        for width,height in [(1180,820),(1040,780),(1040,720),(1040,698),(984,698)]:
            self.root.geometry(f'{width}x{height}');self.root.update()
            for tab,page in self.app._studio_sections.items():
                self.assertTrue(page.winfo_ismapped(),tab)
                bottom=page.winfo_rooty()+page.winfo_height()
                def check(widget):
                    for child in widget.winfo_children():
                        if child.winfo_ismapped():
                            self.assertLessEqual(child.winfo_rooty()+child.winfo_height(),bottom+2,(tab,str(child)))
                            self.assertLessEqual(child.winfo_rootx()+child.winfo_width(),page.winfo_rootx()+page.winfo_width()+2,(tab,str(child)))
                            check(child)
                check(page)
            for key,control in self.app.studio_controls.items():
                self.assertTrue(control.winfo_ismapped(),key)
    def test_sync_reveals_file_without_losing_values(self):
        self.app.settings_vars[0].set('27');self.app.lang_var.set('Hindi')
        self.app._set_task('Sync Existing');self.root.update()
        self.assertTrue(self.app.studio_controls['sync_srt'].winfo_ismapped())
        self.assertEqual(self.app.studio_controls['sync_srt'].entry.cget('state'),'normal')
        self.app.sync_srt_path_var.set('saved.srt')
        self.app._set_task('Generate');self.root.update()
        self.assertEqual(self.app.settings_vars[0].get(),'27')
        self.assertEqual(self.app.lang_var.get(),'Hindi')
        self.assertTrue(self.app.studio_controls['sync_srt'].winfo_ismapped())
        self.assertEqual(self.app.studio_controls['sync_srt'].entry.cget('state'),'disabled')
        self.assertEqual(self.app.sync_srt_path_var.get(),'saved.srt')
        self.app._set_task('Sync Existing');self.root.update()
        self.assertEqual(self.app.studio_controls['sync_srt'].entry.get(),'saved.srt')
        with patch.object(self.app,'_build_progress'),patch('threading.Thread'):
            self.app._on_submit('sync')
        selection=json.loads((Path(self.scratch.name)/'selection').read_text())
        self.assertEqual(selection['action'],'sync')
        self.assertEqual(selection['srt_input_path'],'saved.srt')
        self.assertEqual(selection['lang'],'Hindi')
        self.assertEqual(selection['settings'],'27,1,2')
    def test_presets_keep_full_legacy_configuration(self):
        self.app.font_var.set('Arial');self.app.textsize_var.set('64')
        self.app.font_style_var.set('Bold Italic');self.app.color_var.set('#f0ca80')
        self.app.lang_var.set('Bengali')
        self.app.settings_vars[0].set('29');self.app.preset_name_var.set('Studio test')
        self.app._preset_actions['save']()
        stored=json.loads((Path(self.scratch.name)/'presets/Studio test.json').read_text())
        self.assertEqual(stored['_settings'][0],'29')
        self.assertEqual(stored['font'],'Arial')
        self.assertIn('outline',stored);self.assertIn('shadow',stored);self.assertIn('srt_posy',stored)
        self.app.font_var.set('Auto');self.app._preset_actions['apply']('Studio test')
        self.assertEqual(self.app.font_var.get(),'Arial')
        self.assertEqual(self.app.font_style_var.get(),'Bold Italic')
        self.assertEqual(self.app.color_var.get(),'#f0ca80')
        self.assertEqual(self.app.demo_language_var.get(),'English')
        self.app._preset_actions['remove']()
        self.assertFalse((Path(self.scratch.name)/'presets/Studio test.json').exists())
    def test_submission_keeps_resolve_wire_fields(self):
        self.app.ref_script_var.set('reference.txt');self.app.diarize_var.set(1)
        with patch.object(self.app,'_build_progress'),patch('threading.Thread'):
            self.app._on_submit('generate')
        selection=json.loads((Path(self.scratch.name)/'selection').read_text())
        for key in ('action','chosen','settings','lang','diarize','outline','shadow','color',
                    'words_per','ref_script','review','font','font_style','text_size','srt_posy'):
            self.assertIn(key,selection)
        self.assertEqual(selection['settings'],'15,1,2')
        self.assertEqual(selection['ref_script'],'reference.txt')
    def test_frame_switch_and_position_keep_preview_in_bounds(self):
        self.app.srt_posy_var.set('.31')
        for geometry in ('1180x820','1040x720'):
            self.root.geometry(geometry);self.root.update()
            for aspect,ratio in [('HD',16/9),('Reel',9/16)]:
                self.app.aspect_var.set(aspect);self.root.update()
                self.assertEqual(self.app.srt_posy_var.get(),'.31')
                preview=self.app._preview
                self.assertLessEqual(preview.winfo_height(),preview.master.winfo_height())
                self.assertLessEqual(preview.winfo_width(),preview.master.winfo_width())
                self.assertAlmostEqual(preview._pw/preview._ph,ratio,delta=.03)

    def test_typography_and_sample_match_design_tokens(self):
        title_font=tkfont.Font(font=self.app._studio_title.cget('font'))
        self.assertEqual(int(self.root.tk.splitlist(self.app._studio_title.cget('font'))[1]),-27)
        self.assertEqual(title_font.cget('weight'),'bold')
        value_font=tkfont.Font(font=self.app.studio_controls['track']._label.cget('font'))
        self.assertEqual(int(self.root.tk.splitlist(self.app.studio_controls['track']._label.cget('font'))[1]),-15)
        self.assertEqual(self.app._generate_btn.font.cget('size'),-14)
        self.assertEqual(self.app.demo_language_var.get(),'English')
        self.assertIn('Your story',self.app._preview.SAMPLE)
        # Changing sample language leaves the real caption point size untouched.
        self.assertEqual(self.app.textsize_var.get(),'55')

    def test_style_controls_use_real_output_variables(self):
        color=self.app.studio_controls['color']
        with patch('studio_form.colorchooser.askcolor',return_value=((12,34,56),'#0c2238')):
            color.choose()
        self.assertEqual(self.app.color_var.get(),'#0c2238')
        color.reset();self.assertEqual(self.app.color_var.get(),'')
        self.app.font_var.set('Arial');self.app.font_style_var.set('Italic')
        self.app.textsize_var.set('68');self.app.color_var.set('#cceeff')
        self.app.outline_var.set(0);self.app.shadow_var.set(1)
        with patch.object(self.app,'_build_progress'),patch('threading.Thread'):
            self.app._on_submit('generate')
        selection=json.loads((Path(self.scratch.name)/'selection').read_text())
        self.assertEqual(selection['font'],'Arial')
        self.assertEqual(selection['font_style'],'Italic')
        self.assertEqual(selection['text_size'],'68')
        self.assertEqual(selection['color'],'#cceeff')
        self.assertEqual(selection['outline'],0)
        self.assertEqual(selection['shadow'],1)

    def test_demo_languages_are_complete_and_do_not_change_output(self):
        from studio_form import DEMO_CAPTIONS
        self.assertEqual(set(DEMO_CAPTIONS),set(self.ns['LANGUAGES'])-{'Auto-detect'})
        self.assertEqual(self.app.lang_var.get(),'Auto-detect')
        self.app.lang_var.set('Bengali')
        self.assertEqual(self.app._preview.SAMPLE,DEMO_CAPTIONS['English'])
        settings=[v.get() for v in self.app.settings_vars]
        for language,sample in DEMO_CAPTIONS.items():
            self.app.demo_language_var.set(language);self.root.update()
            self.assertEqual(self.app._preview.SAMPLE,sample)
            self.assertEqual(self.app.lang_var.get(),'Bengali')
            self.assertEqual([v.get() for v in self.app.settings_vars],settings)
            self.assertEqual(self.app.textsize_var.get(),'55')
        self.app.demo_language_var.set('Unknown')
        self.assertEqual(self.app._preview.SAMPLE,DEMO_CAPTIONS['English'])

    def test_review_edit_and_local_resplit_still_work(self):
        p=Path(self.scratch.name)
        srt,cap=str(p/'sample.srt'),str(p/'sample.cap')
        segments=[{'s':0.,'e':1.5,'spk':0,'text':'Hello world',
                   'words':[(0.,.6,'Hello'),(.7,1.5,'world')]},
                  {'s':2.,'e':3.5,'spk':0,'text':'Another moment',
                   'words':[(2.,2.7,'Another'),(2.8,3.5,'moment')]}]
        self.app._write_srt_cap(srt,cap,[],segments)
        self.app._build_review(srt,cap,[],segments)
        self.root.update()
        self.assertEqual(len(self.app._review_rows),2)
        self.assertEqual(len(self.app._insp_vars),6)
        resplit,settings=self.app._resplit_segments()
        self.assertTrue(resplit)
        self.assertEqual(settings['max_chars'],15)
        edit=self.app._review_rows[0]['text'].text
        edit.delete('1.0','end');edit.insert('1.0','Edited caption')
        with patch.object(self.app,'_build_progress'),patch.object(self.app,'_set_progress'),\
             patch.object(self.app,'_finish_after_transcribe'):
            self.app._apply_review(srt,cap,[])
        self.assertIn('Edited caption',Path(srt).read_text(encoding='utf-8'))

if __name__=='__main__':unittest.main()
