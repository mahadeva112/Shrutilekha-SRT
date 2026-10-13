import json
from pathlib import Path
import runpy
import tempfile
import tkinter as tk
from tkinter import font
import unittest
from unittest.mock import patch

from dpi import attach, fit_scale
from ui_icons import artwork


class DpiTests(unittest.TestCase):
    def make_app(self,factor):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        ns=runpy.run_path(str(Path(__file__).resolve().parents[1]/'loader.pyw'))
        ns['App'].__init__.__globals__.update(updater=None,data_dir=lambda:temp.name,
            _steal_focus=lambda r:None,_keep_topmost=lambda r:None)
        root=tk.Tk();root.withdraw()
        context=attach(root,factor,watch=False)
        context.work=(0,0,3840,2160)  # Simulated large display; OS settings stay untouched.
        p=Path(temp.name)
        app=ns['App'](root,{'items':['Track 1: Audio 1'],'defaults':{}},str(p/'selection'),
            str(p/'args'),str(p/'done'),str(p/'log'),'unused','unused',str(p/'result'),str(p/'ack'))
        root.deiconify();root.update()
        def close():
            for job in root.tk.call('after','info'):root.after_cancel(job)
            root.destroy()
        self.addCleanup(close)
        return root,context,app,p

    def check_bounds(self,app):
        for name,page in app._studio_sections.items():
            bottom=page.winfo_rooty()+page.winfo_height()
            right=page.winfo_rootx()+page.winfo_width()
            def check(widget):
                for child in widget.winfo_children():
                    if child.winfo_ismapped():
                        self.assertLessEqual(child.winfo_rooty()+child.winfo_height(),bottom+3,(name,str(child)))
                        self.assertLessEqual(child.winfo_rootx()+child.winfo_width(),right+3,(name,str(child)))
                        check(child)
            check(page)

    def test_four_render_scales_have_native_font_pixels_and_no_clipped_controls(self):
        for factor in (.8,1,1.25,1.5,2):
            with self.subTest(scale=factor):
                root,context,app,p=self.make_app(factor)
                self.assertEqual(int(context.raw.call('winfo','width',root._w)),round(root.winfo_width()*factor))
                entry=app.studio_controls['max_chars'].entry
                physical=context.raw.splitlist(context.raw.call(entry._w,'cget','-font'))
                self.assertEqual(int(physical[1]),-context.pixels(15))
                copied=font.Font(root=root,font=entry.cget('font'))
                self.assertEqual(copied.cget('size'),-15)
                self.assertEqual(app.textsize_var.get(),'55')
                self.assertEqual(app.demo_language_var.get(),'English')
                self.assertIsNone(app._scroll_canvas)
                self.check_bounds(app)
                self.doCleanups()

    def test_monitor_transition_keeps_controls_values_and_output_font_size(self):
        root,context,app,p=self.make_app(1)
        app.font_var.set('Arial');app.textsize_var.set('68')
        for factor in (1.5,2,1.25,1):
            context.rescale(factor);root.update()
            self.check_bounds(app)
            self.assertEqual(app.textsize_var.get(),'68')
        with patch.object(app,'_build_progress'),patch('threading.Thread'):
            app._on_submit('generate')
        selection=json.loads((p/'selection').read_text())
        self.assertEqual(selection['text_size'],'68')
        self.assertEqual(selection['font'],'Arial')

    def test_mouse_events_and_canvas_coordinates_use_same_logical_space(self):
        root,context,app,p=self.make_app(1.5)
        canvas=tk.Canvas(root,width=100,height=100);canvas.pack();root.update()
        item=canvas.create_line(10,20,40,50,width=2)
        canvas.configure(scrollregion=(0,0,100,500))
        self.assertEqual(canvas.cget('scrollregion'),(0,0,100,500))
        self.assertEqual(context.raw.splitlist(context.raw.call(canvas._w,'cget','-scrollregion')),
                         ('0','0','150','750'))
        self.assertEqual(canvas.coords(item),[10.,20.,40.,50.])
        self.assertEqual(context.raw.call(canvas._w,'coords',item),(15.,30.,60.,75.))
        events=[];canvas.bind('<Motion>',lambda e:events.append((e.x,e.y)))
        canvas.event_generate('<Motion>',x=20,y=30);root.update()
        self.assertEqual(events[-1],(20,30))

    def test_pixel_and_point_font_specs_are_normalized_consistently(self):
        root,context,app,p=self.make_app(2)
        label=tk.Label(root,font=('Segoe UI',10))
        named=font.Font(root=root,family='Segoe UI',size=10)
        self.assertEqual(label.cget('font')[1],named.cget('size'))
        self.assertEqual(named.cget('size'),-13)

    def test_icons_are_display_sized_and_have_antialiased_edges(self):
        for size in (18,23,27,36):
            image=artwork('Timing',size,'#eed185')
            self.assertEqual(image.size,(size,size))
            self.assertTrue(any(0<a<255 for a in image.getchannel('A').get_flattened_data()))

    def test_small_display_scale_is_capped_to_preserve_all_features(self):
        factor=fit_scale(2,(0,0,1920,1032))
        self.assertLess(factor,2)
        self.assertGreaterEqual(1032/factor,768)
