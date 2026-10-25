"""Master Studio presentation; Resolve protocol and processing remain in App."""
import tkinter as tk
from tkinter import colorchooser, font as tkfont
from settings_ui import RoundedAction, rounded_rect, show_settings


# Presentation examples only; never written into generated captions or presets.
DEMO_CAPTIONS = {
    "English": "Your story.\nYour voice.",
    "Assamese": "আপোনাৰ কাহিনী।\nআপোনাৰ কণ্ঠ।",
    "Bengali": "আপনার গল্প।\nআপনার কণ্ঠ।",
    "Gujarati": "તમારી વાર્તા.\nતમારો અવાજ.",
    "Hindi": "आपकी कहानी।\nआपकी आवाज़।",
    "Kannada": "ನಿಮ್ಮ ಕಥೆ.\nನಿಮ್ಮ ಧ್ವನಿ.",
    "Malayalam": "നിങ്ങളുടെ കഥ.\nനിങ്ങളുടെ ശബ്ദം.",
    "Marathi": "तुमची गोष्ट.\nतुमचा आवाज.",
    "Nepali": "तपाईंको कथा।\nतपाईंको आवाज।",
    "Odia": "ଆପଣଙ୍କ କାହାଣୀ।\nଆପଣଙ୍କ ସ୍ୱର।",
    "Punjabi": "ਤੁਹਾਡੀ ਕਹਾਣੀ।\nਤੁਹਾਡੀ ਆਵਾਜ਼।",
    "Tamil": "உங்கள் கதை.\nஉங்கள் குரல்.",
    "Telugu": "మీ కథ.\nమీ స్వరం.",
}


class StudioSurface(tk.Canvas):
    def __init__(self, parent, theme, padding=12):
        super().__init__(parent, bg=parent.cget("bg"), bd=0,
                         highlightthickness=0, width=100, height=100)
        self.theme, self.padding = theme, padding
        self.body = tk.Frame(self, bg=theme["card"])
        self._window = self.create_window(padding, padding, window=self.body, anchor="nw")
        self.bind("<Configure>", self._layout)

    def _layout(self, event=None):
        p, width, height = self.padding, self.winfo_width(), self.winfo_height()
        self.coords(self._window, p, p)
        self.itemconfigure(self._window, width=max(1, width-p*2), height=max(1, height-p*2))
        self.delete("surface")
        shadow = rounded_rect(self, 2, 4, width-2, height-1, 16,
                              fill="#101318", outline="")
        face = rounded_rect(self, 1, 1, width-1, height-3, 16,
                            fill=self.theme["card"], outline=self.theme["border"])
        highlight = self.create_line(17, 2, max(17, width-17), 2, fill="#303641")
        for shape in (shadow, face, highlight):
            self.addtag_withtag("surface", shape)
        self.tag_lower("surface")


class SectionMark(tk.Canvas):
    """Small semantic marks drawn with the native canvas, without emoji fonts."""
    def __init__(self, parent, kind, theme):
        super().__init__(parent, width=18, height=18, bg=theme['card'],
                         bd=0, highlightthickness=0)
        def draw(event=None):
            from ui_icons import photo
            self.delete('all')
            self._photo = photo(self,kind,18,theme['accent'])
            self.create_image(9,9,image=self._photo)
        self.bind('<Configure>',draw)
        draw()


class StudioGroup(tk.Frame):
    """Adapter for the existing preset builder and its storage callbacks."""
    def __init__(self, parent, bg):
        super().__init__(parent, bg=bg)
        self.rows = self

    def set_active(self, on):
        pass


class SyncInputHandle:
    """Keep the SRT row visible; enable it when Sync is selected."""
    def __init__(self, field, browse):
        self.field, self.browse = field, browse

    def set_visible(self, visible):
        state = "normal" if visible else "disabled"
        self.field.entry.configure(state=state)
        self.browse.configure(state=state)


class ColorSwatch(RoundedAction):
    def __init__(self, parent, variable, root, theme):
        self.variable, self.root = variable, root
        super().__init__(parent, "Auto", self.choose, theme, height=34, width=88)
        self.bind("<Delete>", lambda e: self.reset())
        self.bind("<BackSpace>", lambda e: self.reset())
        self.menu = tk.Menu(self, tearoff=False)
        self.menu.add_command(label="Automatic colour", command=self.reset)
        self.bind("<Button-3>", lambda e: self.menu.tk_popup(e.x_root, e.y_root))
        variable.trace_add("write", lambda *a: self._draw())

    def reset(self):
        self.variable.set("")
        return "break"

    def choose(self):
        result = colorchooser.askcolor(self.variable.get() or "#ffffff",
                                      parent=self.root, title="Caption colour")
        if result and result[1]:
            self.variable.set(result[1])

    def _draw(self, event=None):
        if not self.winfo_exists():
            return
        self.text = "Colour" if self.variable.get() else "Auto"
        super()._draw(event)
        try:
            self.create_rectangle(9, 11, 20, self.winfo_height()-11,
                                  fill=self.variable.get() or "#fff3d1", outline="")
        except tk.TclError:
            pass


def build_form(app):
    g = app.__class__.__init__.__globals__
    theme = dict(bg=g["BG"], card=g["BG_CARD"], field=g["BG_INPUT"],
                 text=g["FG"], muted=g["FG_DIM"], border="#323b48",
                 accent=g["ACCENT"], font=g["UI_FONT"], button_size=-14,
                 button_fill="#2c3440", button_hover="#384354", button_border="#3c4758",
                 selected="#393427", selected_text=g["ACCENT"], radius=10)
    if "Segoe UI Semibold" in tkfont.families(app.root):
        theme["button_font"] = "Segoe UI Semibold"
    bg, card, font = theme["bg"], theme["card"], theme["font"]
    app._clear_body(pad=0)
    app._studio_form = app._master_studio = True
    app._cards = []
    app._scroll_canvas = None
    app._sync_scrollregion = lambda: None
    items = app.prompt_data.get("items", [])
    app._defaults = app.prompt_data.get("defaults", {})
    app._declare_vars(items, app._defaults)
    app.studio_controls = {}
    app._studio_theme = theme
    field_labels, timing_cells, file_wraps = [], [], []

    def label(parent, text=None, size=14, dim=False, bold=False, **kwargs):
        return tk.Label(parent, text=text, bg=parent.cget("bg"),
                        fg=theme["muted"] if dim else theme["text"],
                        font=(font, -size, "bold" if bold else "normal"), padx=0, pady=0, **kwargs)

    def button(parent, text, command, primary=False, selected=False, **kwargs):
        control = RoundedAction(parent, text, command, theme, primary=primary, **kwargs)
        if selected:
            control.selection_button = True
            control.set_primary(primary)
        return control

    def field(parent, text):
        wrap = tk.Frame(parent, bg=card)
        head = label(wrap, text, size=13, dim=True)
        head.pack(anchor="w", pady=(0, 2))
        field_labels.append(head)
        return wrap

    def dropdown(parent, variable, values, key, height=34):
        pick = g["Dropdown"](parent, values, variable, bg_parent=card,
                              height=height, radius=8, max_rows=6)
        pick._label.configure(font=(theme.get("button_font",font), -15))
        pick.studio_menu_font = (font, -14)
        pick.pack(fill="x")
        app.studio_controls[key] = pick
        return pick

    def toggle(parent, text, variable, key, size=14):
        row = tk.Frame(parent, bg=card)
        label(row, text, size=size).pack(side="left")
        switch = g["ToggleSwitch"](row, variable)
        switch.configure(bg=card)
        switch.pack(side="right", padx=(8, 0))
        app.studio_controls[key] = switch
        return row

    # Keep the existing native title strip and version/update control.
    bar = tk.Frame(app.body, bg=g["BG_BAR"], height=44)
    bar.pack(fill="x")
    bar.pack_propagate(False)
    g["LogoTile"](bar, size=26, radius=8, bg_parent=g["BG_BAR"]).pack(side="left", padx=(18, 10))
    brand = label(bar, "Srutilekha", size=18, bold=True)
    brand.pack(side="left")
    crumb = label(bar, app._timeline_crumb(), size=12, dim=True)
    crumb.pack(side="left", padx=12)
    for widget in (bar, brand, crumb):
        app._make_draggable(widget)
    if g.get("updater") is not None:
        state = "available" if app._update_info else "checking" if app._update_checking else "idle"
        app._update_pill = g["UpdatePill"](bar, "Update" if app._update_info else app._idle_pill_text(),
                                             app._on_update_click, bg_parent=g["BG_BAR"], state=state)
        app._update_pill.pack(side="right", padx=(0, g["TitleBarControls"].BTN_W*3+12))

    footer = tk.Frame(app.body, bg=g["BG_BAR"])
    footer.pack(side="bottom", fill="x")
    tk.Frame(footer, bg=theme["border"], height=1).pack(fill="x")
    actions = tk.Frame(footer, bg=g["BG_BAR"])
    actions.pack(fill="x", padx=22, pady=12)
    app.summary_var = tk.StringVar(value="")
    summary = label(actions, size=12, textvariable=app.summary_var, anchor="w", dim=True)
    summary.pack(side="left", fill="x", expand=True)
    summary.bind("<Configure>", lambda e: summary.configure(wraplength=max(1, e.width)))
    app._generate_btn = button(actions, "Generate captions", lambda: app._on_submit(
        "sync" if app.task_var.get() == "Sync Existing" else "generate"), primary=True, height=40)
    app._generate_btn.pack(side="right", padx=(10, 0))
    button(actions, "Undo last captions", lambda: app._on_submit("undo"), height=40).pack(side="right", padx=(8, 0))
    button(actions, "Cancel", app._on_cancel, fill=g["BG_BAR"], ink=theme["muted"], height=40).pack(side="right")

    heading = tk.Frame(app.body, bg=bg)
    heading.pack(fill="x", padx=22, pady=(18, 16))
    title = tk.Frame(heading, bg=bg)
    title.pack(side="left")
    app._studio_title = label(title, "Caption studio", size=27, bold=True)
    app._studio_title.pack(anchor="w")
    label(title, "Your audio. Clear, readable captions.", size=14, dim=True).pack(anchor="w", pady=(3, 0))
    button(heading, "API settings", lambda: show_settings(app.root, theme=theme), height=36).pack(side="right", padx=(12, 0))
    app._seg_sync = button(heading, "Sync existing SRT", lambda: app._set_task("Sync Existing"), selected=True)
    app._seg_sync.pack(side="right", padx=(5, 0))
    app._seg_gen = button(heading, "Generate", lambda: app._set_task("Generate"), primary=True, selected=True)
    app._seg_gen.pack(side="right")

    workspace = tk.Frame(app.body, bg=bg)
    workspace.pack(fill="both", expand=True, padx=22, pady=(0, 18))
    workspace.grid_columnconfigure(0, weight=3, minsize=260)
    workspace.grid_columnconfigure(1, weight=7, minsize=660)
    workspace.grid_rowconfigure(0, weight=1)
    preview_surface = StudioSurface(workspace, theme)
    preview_surface.grid(row=0, column=0, sticky="nsew", padx=(0, 16))
    settings = tk.Frame(workspace, bg=bg)
    settings.grid(row=0, column=1, sticky="nsew")
    settings.grid_columnconfigure(0, weight=1, uniform="master-panel")
    settings.grid_columnconfigure(1, weight=1, uniform="master-panel")
    for row in range(3):
        settings.grid_rowconfigure(row, weight=1 if row == 0 else 0)
    app._master_settings = settings
    app._studio_sections, surfaces, section_heads = {}, {}, []

    def section(name, title, row, column, span=1):
        surface = StudioSurface(settings, theme)
        surface.grid(row=row, column=column, columnspan=span, sticky="nsew",
                     padx=(0, 6) if span == 1 and column == 0 else (6, 0) if span == 1 else 0,
                     pady=(0, 12) if row < 2 else 0)
        head = tk.Frame(surface.body, bg=card)
        head.pack(anchor="w", pady=(0, 10))
        SectionMark(head, name, theme).pack(side="left", padx=(0,8))
        caption = label(head, title, size=15, bold=True)
        caption.configure(font=(theme.get("button_font",font), -15))
        caption.pack(side="left")
        section_heads.append(head)
        content = tk.Frame(surface.body, bg=card)
        content.pack(fill="both", expand=True)
        app._studio_sections[name], surfaces[name] = content, surface
        return content

    audio = section("Audio", "Audio & language", 0, 0)
    timing = section("Timing", "Timing & readability", 0, 1)
    files = section("Files", "Script & files", 1, 0)
    presets = section("Presets", "Presets", 1, 1)
    style = section("Style", "Caption style", 2, 0, span=2)
    app._studio_surfaces = (preview_surface, *surfaces.values())

    source_pair = tk.Frame(audio, bg=card)
    source_pair.pack(fill="x", pady=(0, 13))
    for column, (text, var, values, key) in enumerate((
            ("Audio track", app.combo_var, items, "track"),
            ("Language", app.lang_var, g["LANGUAGES"], "language"))):
        source_pair.grid_columnconfigure(column, weight=1, uniform="audio-field")
        wrap = field(source_pair, text)
        wrap.grid(row=0, column=column, sticky="ew", padx=(0, 5) if column == 0 else (5, 0))
        dropdown(wrap, var, values, key)
    toggle(audio, "Punctuation", app.punct_var, "punctuation").pack(fill="x", pady=(0, 10))
    toggle(audio, "Separate speakers", app.diarize_var, "speakers").pack(fill="x", pady=(0, 10))
    tk.Frame(audio, bg=theme["border"], height=1).pack(fill="x", pady=(2, 12))
    toggle(audio, "Review captions first", app.review_var, "review").pack(fill="x")

    for i, (text, var, unit, key, limits) in enumerate((
        ("Max characters", app.settings_vars[0], "chars", "max_chars", (8, 60)),
        ("Lines per cue", app.settings_vars[1], "lines", "max_lines", (1, 4)),
        ("Min length", app.min_var, "sec", "min_secs", (0, 4)),
        ("Max length", app.settings_vars[2], "sec", "max_secs", (1, 12)),
        ("Reading speed", app.cps_var, "cps", "cps", (8, 30)),
        ("Max words", app.words_per_var, "0 = off", "max_words", (0, 12)))):
        timing.grid_columnconfigure(i % 2, weight=1, uniform="timing-field")
        cell = field(timing, text)
        cell.grid(row=i//2, column=i%2, sticky="ew", padx=(0, 5) if i%2 == 0 else (5, 0), pady=(0, 5))
        timing_cells.append(cell)
        control = g["SmallInput"](cell, var, unit=unit, bg_parent=card, size=-15, height=34)
        control.entry.configure(font=(font, -15, "bold"))
        control.pack(fill="x")
        app.studio_controls[key] = control
        # Preserve numeric range feedback within each field's existing height.
        rail = g["RangeBar"](control, var, *limits, bg_parent=theme["field"], height=2)
        rail.place(x=6, rely=1, y=-4, relwidth=1, width=-12, height=2)
    comfort = g["ComfortMeter"](timing, app.cps_var, app.settings_vars[0], bg_parent=card)
    comfort.compact = True
    comfort.configure(height=24)
    comfort.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(1, 0))
    g["Tooltip"](comfort, "Reading comfort reflects the selected reading speed. Lower CPS allows more time per cue.", app_root=app.root)

    def file_field(parent, text, variable, browse, key):
        wrap = field(parent, text)
        wrap.pack(fill="x", pady=(0, 7))
        file_wraps.append(wrap)
        row = tk.Frame(wrap, bg=card)
        row.pack(fill="x")
        pick = button(row, "Browse", browse, height=32)
        pick.pack(side="right", padx=(7, 0))
        control = g["PillEntry"](row, variable, placeholder="Choose a file or paste its path…", bg_parent=card, height=32)
        control.entry.configure(font=(font, -14))
        control._r = 8
        control.pack(side="left", fill="x", expand=True)
        app.studio_controls[key] = control
        return control, pick
    reference, _ = file_field(files, "Reference script · optional", app.ref_script_var, app._pick_ref_script, "reference_script")
    g["Tooltip"](reference, "Use a .docx, .txt or .srt script to match spellings and punctuation.", app_root=app.root)
    sync, sync_browse = file_field(files, "Existing SRT · Sync mode", app.sync_srt_path_var, app._pick_sync_srt, "sync_srt")
    app._sync_srt_handle = SyncInputHandle(sync, sync_browse)
    app._build_presets(presets)

    # These are the original preset/output variables, now directly editable.
    families = (g["CAPTION_FONTS"][0],) + tuple(sorted(set(tkfont.families(app.root))))
    for column, (text, var, values, key, weight) in enumerate((
            ("Font", app.font_var, families, "font", 3),
            ("Style", app.font_style_var, g["FONT_STYLES"], "font_style", 2),
            ("Size · pt", app.textsize_var, None, "text_size", 1),
            ("Colour", app.color_var, None, "color", 1))):
        style.grid_columnconfigure(column, weight=weight)
        wrap = field(style, text)
        wrap.grid(row=0, column=column, sticky="ew", padx=(0, 8))
        if values is not None:
            dropdown(wrap, var, values, key)
        elif key == "text_size":
            control = g["SmallInput"](wrap, var, bg_parent=card, size=-15, height=34)
            control.entry.configure(font=(font, -15, "bold"))
            control.configure(width=60)
            control.pack(fill="x")
            app.studio_controls[key] = control
        else:
            control = ColorSwatch(wrap, var, app.root, theme)
            control.pack(fill="x")
            app.studio_controls[key] = control
            g["Tooltip"](control, "Choose caption colour. Press Delete or right-click for automatic colour.", app_root=app.root)
    effects = tk.Frame(style, bg=card)
    effects.grid(row=0, column=4, sticky="se", pady=(0, 7))
    toggle(effects, "Outline", app.outline_var, "outline", size=13).pack(side="left", padx=(0, 10))
    toggle(effects, "Shadow", app.shadow_var, "shadow", size=13).pack(side="left")

    # The preview uses a neutral English demo even when a saved preset is Indic.
    stage = preview_surface.body
    app._stage = stage
    preview_head = tk.Frame(stage, bg=card)
    preview_head.pack(fill="x", pady=(0,12))
    label(preview_head, "Caption preview", size=15, bold=True).pack(side="left")
    RoundedAction(preview_head, 'Demo', lambda:None, dict(theme,button_size=-11),
                  fill="#393427", ink=theme['accent'], height=20, width=46,
                  interactive=False).pack(side="right")
    aspect_row = tk.Frame(stage, bg=card)
    aspect_row.pack(fill="x", pady=(0, 12))
    app._frame_btns = {}
    for name, text in (("Reel", "Reel 9:16"), ("HD", "HD 16:9")):
        control = button(aspect_row, text, lambda n=name: app.aspect_var.set(n),
                         primary=app.aspect_var.get() == name, selected=True, height=30)
        control.pack(side="left", fill="x", expand=True, padx=(0, 5) if name == "Reel" else 0)
        app._frame_btns[name] = control
    demo_row = tk.Frame(stage, bg=card)
    demo_row.pack(fill="x", pady=(0, 10))
    label(demo_row, "Demo language", size=12, dim=True).pack(side="left", padx=(0, 8))
    app.demo_language_var = tk.StringVar(value="English")
    demo_pick = dropdown(demo_row, app.demo_language_var, tuple(sorted(DEMO_CAPTIONS)), "demo_language", height=30)
    demo_pick._label.configure(font=(font, -13))
    app._demo_language_control = demo_pick

    placement = tk.Frame(stage, bg=card)
    placement.pack(side="bottom", fill="x", pady=(0, 0))
    app._safe_label_var = tk.StringVar(value="Platform safe zone" if app._frame()["aspect"] < 1 else "Title-safe area")
    row = toggle(placement, "", app.safe_zone_var, "safe_zone", size=13)
    row.pack(fill="x", pady=(0, 9))
    row.pack_slaves()[0].configure(textvariable=app._safe_label_var)
    position_row = tk.Frame(placement, bg=card)
    position_row.pack(fill="x")
    label(position_row, "Position", size=13).pack(side="left")
    app._studio_position_label = tk.StringVar()
    label(position_row, size=12, textvariable=app._studio_position_label).pack(side="right")
    slider = g["Slider"](position_row, app.srt_posy_var, 0, 1, bg_parent=card, height=26)
    slider.pack(side="left", fill="x", expand=True, padx=9)
    app.studio_controls["position"] = slider
    def position_changed(*args):
        app._studio_position_label.set("%.0f%%" % (app._srt_posy_frac()*100))
    app.srt_posy_var.trace_add("write", position_changed)
    position_changed()
    app._plate_right_var = tk.StringVar()
    label(stage, size=11, dim=True, textvariable=app._plate_right_var).pack(side="bottom", pady=(8, 10))
    viewport_theme = dict(theme, card="#11161e", border="#303844")
    viewport_surface = StudioSurface(stage, viewport_theme, padding=8)
    viewport_surface.pack(fill="both", expand=True)
    viewport = viewport_surface.body
    app._preview = g["ReelPreview"](viewport, app.srt_posy_var, app.textsize_var,
        color_var=app.color_var, outline_var=app.outline_var, shadow_var=app.shadow_var,
        safe_zone_var=app.safe_zone_var, font_var=app.font_var, font_style_var=app.font_style_var,
        width=190, bg_parent=viewport_theme["card"], aspect=app._frame()["aspect"],
        srt_posy_default=lambda: app._frame()["srt_posy"],
        frame_height=lambda: (app._timeline_res() or (0, 0))[1] or None)
    app._preview.studio_illustration = True
    def sample_changed(*args):
        app._preview.SAMPLE = DEMO_CAPTIONS.get(app.demo_language_var.get(), DEMO_CAPTIONS["English"])
        if app._preview.winfo_exists():
            app._preview._draw()
    app.demo_language_var.trace_add("write", sample_changed)
    sample_changed()
    app._preview.place(relx=.5, rely=.5, anchor="center")
    viewport.bind("<Configure>", lambda e: app._preview.set_bounds(e.width-16, e.height-34))
    label(viewport, "Demo only · enlarged text", size=11, dim=True).place(relx=.5, rely=1, y=-2, anchor="s")
    app._sync_frame_plate()
    # Consistent rounded field chrome, including controls supplied by presets.
    for control in app.studio_controls.values():
        if isinstance(control, g["RoundedField"]):
            control._r = 9
            control.set_border(theme["border"])

    # All sections stay mapped. Compact sizes reduce gaps, not the type scale.
    fit_job = {"id": None}
    def fit_spacing():
        fit_job["id"] = None
        if not heading.winfo_exists():
            return
        compact = (app.root.winfo_height() < 800
                   or getattr(app.root.tk, 'scale', 1) < 1)
        padding, gap = (8, 6) if compact else (12, 12)
        heading.pack_configure(pady=(12, 10) if compact else (18, 16))
        workspace.pack_configure(pady=(0, 12 if compact else 18))
        actions.pack_configure(pady=9 if compact else 12)
        for head in section_heads:
            head.pack_configure(pady=(0, 3 if compact else 10))
        for head in field_labels:
            head.pack_configure(pady=(0, 1 if compact else 2))
        for cell in timing_cells:
            cell.grid_configure(pady=(0, 2 if compact else 5))
        for wrap in file_wraps:
            wrap.pack_configure(pady=(0, 3 if compact else 7))
        for key, control in app.studio_controls.items():
            if key in ("max_chars", "max_lines", "min_secs", "max_secs", "cps", "max_words"):
                control.set_height(30 if compact else 34)
            elif key in ("track", "language", "font", "font_style", "text_size", "preset", "preset_name"):
                control.set_height(32 if compact else 34)
            elif key in ("reference_script", "sync_srt"):
                control.set_height(30 if compact else 32)
            elif key == "color":
                control.configure(height=32 if compact else 34)
        comfort.configure(height=20 if compact else 24)
        for name, surface in surfaces.items():
            surface.padding = padding
            surface.grid_configure(pady=(0, gap) if name in ("Audio", "Timing", "Files", "Presets") else 0)
            surface._layout()
        def size_sections():
            if not heading.winfo_exists():
                return
            for surface in surfaces.values():
                surface.configure(height=surface.body.winfo_reqheight()+surface.padding*2)
        app.root.after_idle(size_sections)
    def schedule_fit(event=None):
        # Hosted inputs settle their requested sizes asynchronously. Refit
        # when their child geometry changes as well as on a root resize.
        if event is not None and event.widget is not app.root and not any(
                event.widget is surface.body for surface in surfaces.values()) and not any(
                event.widget is getattr(control, '_child', None)
                or event.widget is control for control in app.studio_controls.values()):
            return
        if fit_job["id"] is None and heading.winfo_exists():
            fit_job["id"] = app.root.after_idle(fit_spacing)
    app.root.bind("<Configure>", schedule_fit, add="+")
    schedule_fit()
    app._apply_task()
    app._wire_summary()
    app.aspect_var.trace_add("write", app._apply_frame)
    app.root.bind("<Return>", lambda e: app._on_submit(
        "sync" if app.task_var.get() == "Sync Existing" else "generate"))
    app.root.bind("<Escape>", lambda e: app._on_cancel())
