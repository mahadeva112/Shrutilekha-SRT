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
    def test_controls_and_tabs_fit_at_minimum_window(self):
        self.assertEqual(set(self.app.studio_controls),{'track','language','punctuation','speakers','review',
            'safe_zone','position','max_chars','max_lines','min_secs','max_secs','cps','max_words',
            'reference_script','sync_srt'})
        self.assertIsNone(self.app._scroll_canvas)
        for width,height in [(1040,780),(920,640)]:
            self.root.geometry(f'{width}x{height}');self.root.update()
            for tab,page in self.app.studio_pages.items():
                self.app._select_studio_tab(tab);self.root.update()
                bottom=page.winfo_rooty()+page.winfo_height()
                def check(widget):
                    for child in widget.winfo_children():
                        if child.winfo_ismapped():
                            self.assertLessEqual(child.winfo_rooty()+child.winfo_height(),bottom+2,(tab,str(child)))
                            self.assertLessEqual(child.winfo_rootx()+child.winfo_width(),page.winfo_rootx()+page.winfo_width()+2,(tab,str(child)))
                            check(child)
                check(page)
    def test_sync_reveals_file_without_losing_values(self):
        self.app.settings_vars[0].set('27');self.app.lang_var.set('Hindi')
        self.app._set_task('Sync Existing');self.root.update()
        self.assertEqual(self.app.studio_tab_var.get(),'Script')
        self.assertTrue(self.app.studio_controls['sync_srt'].winfo_ismapped())
        self.app._set_task('Generate');self.root.update()
        self.assertEqual(self.app.settings_vars[0].get(),'27')
        self.assertEqual(self.app.lang_var.get(),'Hindi')
        self.assertFalse(self.app.studio_controls['sync_srt'].winfo_ismapped())
    def test_presets_keep_full_legacy_configuration(self):
        self.app.font_var.set('Arial');self.app.textsize_var.set('64')
        self.app.settings_vars[0].set('29');self.app.preset_name_var.set('Studio test')
        self.app._preset_actions['save']()
        stored=json.loads((Path(self.scratch.name)/'presets/Studio test.json').read_text())
        self.assertEqual(stored['_settings'][0],'29')
        self.assertEqual(stored['font'],'Arial')
        self.assertIn('outline',stored);self.assertIn('shadow',stored);self.assertIn('srt_posy',stored)
        self.app.font_var.set('Auto');self.app._preset_actions['apply']('Studio test')
        self.assertEqual(self.app.font_var.get(),'Arial')
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
        for geometry in ('1040x780','920x640'):
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
