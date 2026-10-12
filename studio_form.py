"""Studio presentation layer. Resolve protocol and processing remain in App."""
import tkinter as tk
from tkinter import font as tkfont
from settings_ui import RoundedAction, rounded_rect, show_settings


class StudioSurface(tk.Canvas):
    def __init__(self, parent, theme, padding=18):
        super().__init__(parent, bg=parent.cget("bg"), bd=0,
                         highlightthickness=0, width=100, height=100)
        self.theme, self.padding = theme, padding
        self.body = tk.Frame(self, bg=theme["card"])
        self._window = self.create_window(padding, padding, window=self.body, anchor="nw")
        self.bind("<Configure>", self._layout)

    def _layout(self, event):
        p = self.padding
        self.itemconfigure(self._window, width=max(1, event.width-p*2),
                           height=max(1, event.height-p*2))
        self.delete("surface")
        face = rounded_rect(self, 1, 1, event.width-1, event.height-1, 16,
                            fill=self.theme["card"], outline=self.theme["border"])
        self.addtag_withtag("surface", face)
        self.tag_lower("surface")


class StudioGroup(tk.Frame):
    """Adapter for the existing preset builder; keeps its storage callbacks."""
    def __init__(self, parent, bg):
        super().__init__(parent, bg=bg)
        self.rows = self

    def set_active(self, on):
        pass


class VisibilityHandle:
    def __init__(self, widget):
        self.widget = widget

    def set_visible(self, visible):
        if visible:
            self.widget.pack(fill="x", pady=(18, 0))
        else:
            self.widget.pack_forget()


def build_form(app):
    g = app.__class__.__init__.__globals__
    theme = dict(bg=g["BG"], card=g["BG_CARD"], field=g["BG_INPUT"],
                 text=g["FG"], muted=g["FG_DIM"], border="#3a414d",
                 accent=g["ACCENT"], font=g["UI_FONT"], button_size=-14)
    if "Segoe UI Semibold" in tkfont.families(app.root):
        theme["button_font"] = "Segoe UI Semibold"
    bg, card, font = theme["bg"], theme["card"], theme["font"]
    app._clear_body(pad=0)
    app._studio_form = True
    app._cards = []
    app._scroll_canvas = None
    app._sync_scrollregion = lambda: None
    items = app.prompt_data.get("items", [])
    defaults = app.prompt_data.get("defaults", {})
    app._defaults = defaults
    app._declare_vars(items, defaults)
    app.studio_controls = {}
    app._studio_theme = theme

    def label(parent, text=None, size=10, dim=False, bold=False, **kwargs):
        return tk.Label(parent, text=text, bg=parent.cget("bg"),
                        fg=theme["muted"] if dim else theme["text"],
                        font=(font, -round(size*1.4), "bold" if bold else "normal"), **kwargs)

    def button(parent, text, command, primary=False, tab=False, **kwargs):
        control = RoundedAction(parent, text, command, theme, primary=primary, **kwargs)
        if tab:
            control.selection_button = True
            control.set_primary(primary)
        return control

    def field(parent, text):
        wrap = tk.Frame(parent, bg=card)
        wrap.pack(fill="x", pady=(0, 15))
        label(wrap, text, bold=True).pack(anchor="w", pady=(0, 8))
        return wrap

    def dropdown(parent, text, variable, values, key):
        wrap = field(parent, text)
        pick = g["Dropdown"](wrap, values, variable, bg_parent=card,
                              height=42, radius=10, max_rows=6)
        pick._label.configure(font=(font, -15, "bold"))
        pick.studio_menu_font = (font, -14)
        pick.pack(fill="x")
        app.studio_controls[key] = pick
        return pick

    def toggle(parent, text, variable, key):
        row = tk.Frame(parent, bg=card)
        row.pack(fill="x", pady=9)
        label(row, text, bold=True).pack(side="left")
        switch = g["ToggleSwitch"](row, variable)
        switch.configure(bg=card)
        switch.pack(side="right")
        app.studio_controls[key] = switch
        return row

    # Preserve the 44px native title strip used by the window controls and API panel.
    bar = tk.Frame(app.body, bg=g["BG_BAR"], height=44)
    bar.pack(fill="x")
    bar.pack_propagate(False)
    g["LogoTile"](bar, size=26, radius=8, bg_parent=g["BG_BAR"]).pack(side="left", padx=(18, 10))
    brand = label(bar, "Srutilekha", size=13, bold=True)
    brand.pack(side="left")
    crumb = label(bar, app._timeline_crumb(), size=9, dim=True)
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
    actions.pack(fill="x", padx=22, pady=13)
    app.summary_var = tk.StringVar(value="")
    summary = label(actions, size=9, textvariable=app.summary_var, anchor="w")
    summary.pack(side="left", fill="x", expand=True)
    summary.bind("<Configure>", lambda e: summary.configure(wraplength=max(1, e.width)))
    app._generate_btn = button(actions, "Generate captions", lambda: app._on_submit(
        "sync" if app.task_var.get() == "Sync Existing" else "generate"), primary=True, height=40)
    app._generate_btn.pack(side="right", padx=(10, 0))
    button(actions, "Undo last captions", lambda: app._on_submit("undo"), height=40).pack(side="right", padx=(8, 0))
    button(actions, "Cancel", app._on_cancel, fill=g["BG_BAR"], ink=theme["muted"], height=40).pack(side="right")

    heading = tk.Frame(app.body, bg=bg)
    heading.pack(fill="x", padx=24, pady=(20, 18))
    title = tk.Frame(heading, bg=bg)
    title.pack(side="left")
    app._studio_title = label(title, "Caption studio", size=19, bold=True)
    app._studio_title.pack(anchor="w")
    label(title, "Your audio. Clear, readable captions.", size=10, dim=True).pack(anchor="w", pady=(4, 0))
    button(heading, "API settings", lambda: show_settings(app.root, theme=theme), height=36).pack(side="right", padx=(12, 0))
    app._seg_sync = button(heading, "Sync existing SRT", lambda: app._set_task("Sync Existing"), tab=True)
    app._seg_sync.pack(side="right", padx=(4, 0))
    app._seg_gen = button(heading, "Generate", lambda: app._set_task("Generate"), primary=True, tab=True)
    app._seg_gen.pack(side="right")

    workspace = tk.Frame(app.body, bg=bg)
    workspace.pack(fill="both", expand=True, padx=24, pady=(0, 20))
    workspace.grid_columnconfigure(0, weight=1)
    workspace.grid_columnconfigure(1, minsize=370)
    workspace.grid_rowconfigure(0, weight=1)
    preview_surface = StudioSurface(workspace, theme, padding=16)
    preview_surface.grid(row=0, column=0, sticky="nsew", padx=(0, 18))
    inspector_surface = StudioSurface(workspace, theme, padding=18)
    inspector_surface.grid(row=0, column=1, sticky="nsew")
    app._studio_surfaces = (preview_surface, inspector_surface)

    stage = preview_surface.body
    app._stage = stage
    preview_head = tk.Frame(stage, bg=card)
    preview_head.pack(fill="x", pady=(0, 12))
    label(preview_head, "Caption preview", size=10, bold=True).pack(side="left")
    app._frame_btns = {}
    for name, text in (("HD", "HD 16:9"), ("Reel", "Reel 9:16")):
        control = button(preview_head, text, lambda n=name: app.aspect_var.set(n),
                         primary=app.aspect_var.get() == name, height=30, tab=True)
        control.pack(side="right", padx=(5, 0))
        app._frame_btns[name] = control

    placement = tk.Frame(stage, bg=card)
    placement.pack(side="bottom", fill="x", pady=(14, 0))
    safe_row = toggle(placement, "Safe zone", app.safe_zone_var, "safe_zone")
    safe_row.pack_configure(side="left", fill="y", padx=(0, 16), pady=0)
    position_row = tk.Frame(placement, bg=card)
    position_row.pack(side="left", fill="x", expand=True)
    label(position_row, "Caption position", size=9).pack(side="left")
    app._studio_position_label = tk.StringVar()
    label(position_row, size=9, textvariable=app._studio_position_label).pack(side="right")
    position_slider = g["Slider"](position_row, app.srt_posy_var, 0, 1,
                                  bg_parent=card, height=26)
    position_slider.pack(side="left", fill="x", expand=True, padx=10)
    app.studio_controls["position"] = position_slider
    def position_changed(*args):
        app._studio_position_label.set("%.0f%%" % (app._srt_posy_frac()*100))
    app.srt_posy_var.trace_add("write", position_changed)
    position_changed()

    app._plate_right_var = tk.StringVar()
    label(stage, size=9, dim=True, textvariable=app._plate_right_var).pack(side="bottom", pady=(9, 0))
    viewport = tk.Frame(stage, bg="#101216")
    viewport.pack(fill="both", expand=True)
    app._preview = g["ReelPreview"](viewport, app.srt_posy_var, app.textsize_var,
        color_var=app.color_var, outline_var=app.outline_var, shadow_var=app.shadow_var,
        safe_zone_var=app.safe_zone_var, width=190, bg_parent="#101216",
        aspect=app._frame()["aspect"], srt_posy_default=lambda: app._frame()["srt_posy"],
        frame_height=lambda: (app._timeline_res() or (0, 0))[1] or None)
    app._preview.studio_illustration = True
    def sample_changed(*args):
        name = app.lang_var.get()
        sample = ("Your story.\nYour own words." if name == "English" else
                  "आपकी कहानी,\nआपकी भाषा।" if name == "Hindi" else
                  "তোমার গল্প,\nতোমার ভাষায়।" if name in ("Auto-detect", "Bengali") else
                  "Your caption\npreview.")
        app._preview.SAMPLE = sample
        if app._preview.winfo_exists():
            app._preview._draw()
    app.lang_var.trace_add("write", sample_changed)
    sample_changed()
    app._preview.place(relx=.5, rely=.5, anchor="center")
    viewport.bind("<Configure>", lambda e: app._preview.set_bounds(e.width-24, e.height-24))
    app._sync_frame_plate()
    label(viewport, "Illustrated sample · enlarged text", size=8, dim=True).place(relx=1, rely=1, x=-8, y=-6, anchor="se")

    inspector = inspector_surface.body
    tabbar = tk.Frame(inspector, bg=card)
    tabbar.pack(fill="x", pady=(0, 20))
    host = tk.Frame(inspector, bg=card)
    host.pack(fill="both", expand=True)
    app._tab_host = host
    app.studio_pages, app._studio_tabs = {}, {}
    app.studio_tab_var = tk.StringVar(value="Audio")
    def select_tab(name):
        if name not in app.studio_pages:
            return
        for key, page in app.studio_pages.items():
            page.pack_forget()
            app._studio_tabs[key].set_primary(key == name)
        app.studio_pages[name].pack(fill="both", expand=True)
        app.studio_tab_var.set(name)
    app._select_studio_tab = select_tab
    for name in ("Audio", "Timing", "Script", "Presets"):
        page = tk.Frame(host, bg=card)
        app.studio_pages[name] = page
        control = button(tabbar, name, lambda n=name: select_tab(n), primary=name == "Audio", height=35, tab=True)
        control.pack(side="left", fill="x", expand=True, padx=(0, 3))
        app._studio_tabs[name] = control

    audio = app.studio_pages["Audio"]
    dropdown(audio, "Audio track", app.combo_var, items, "track")
    dropdown(audio, "Language", app.lang_var, g["LANGUAGES"], "language")
    toggle(audio, "Punctuation", app.punct_var, "punctuation")
    toggle(audio, "Separate speakers", app.diarize_var, "speakers")
    tk.Frame(audio, bg=theme["border"], height=1).pack(fill="x", pady=(18, 12))
    toggle(audio, "Review captions first", app.review_var, "review")

    timing = app.studio_pages["Timing"]
    timing_labels = []
    for i, (text, var, unit, key) in enumerate((
        ("Max characters", app.settings_vars[0], "chars", "max_chars"),
        ("Lines per cue", app.settings_vars[1], "lines", "max_lines"),
        ("Min length", app.min_var, "sec", "min_secs"),
        ("Max length", app.settings_vars[2], "sec", "max_secs"),
        ("Reading speed", app.cps_var, "cps", "cps"),
        ("Max words", app.words_per_var, "0 = off", "max_words"))):
        timing.grid_columnconfigure(i % 2, weight=1, uniform="studio-number")
        cell = tk.Frame(timing, bg=card)
        cell.grid(row=i//2, column=i%2, sticky="ew", padx=(0, 7) if i%2 == 0 else (7, 0), pady=(0, 4))
        timing_label = label(cell, text, size=10, bold=True)
        timing_label.pack(anchor="w", pady=(0, 7))
        timing_labels.append(timing_label)
        control = g["SmallInput"](cell, var, unit=unit, bg_parent=card, size=-15, height=40)
        control.entry.configure(font=(font, -15, "bold"))
        control.pack(fill="x")
        app.studio_controls[key] = control
        limits = ((8, 60), (1, 4), (0, 4), (1, 12), (8, 30), (0, 12))[i]
        g["RangeBar"](cell, var, *limits, bg_parent=card).pack(fill="x", pady=(4, 0))
    g["ComfortMeter"](timing, app.cps_var, app.settings_vars[0], bg_parent=card).grid(row=3, column=0, columnspan=2, sticky="ew")

    script = app.studio_pages["Script"]
    def file_field(parent, text, variable, browse, key):
        wrap = field(parent, text)
        row = tk.Frame(wrap, bg=card)
        row.pack(fill="x")
        control = g["PillEntry"](row, variable, placeholder="Choose a file or paste its path…", bg_parent=card, height=42)
        control.entry.configure(font=(font, -15))
        control.pack(side="left", fill="x", expand=True)
        button(row, "Browse", browse).pack(side="right", padx=(8, 0))
        app.studio_controls[key] = control
        return wrap
    file_field(script, "Reference script · optional", app.ref_script_var, app._pick_ref_script, "reference_script")
    label(script, "Use a .docx, .txt or .srt script to match spellings and punctuation.", size=9, dim=True,
          wraplength=300, justify="left").pack(anchor="w", pady=(0, 8))
    sync = tk.Frame(script, bg=card)
    file_field(sync, "Existing SRT", app.sync_srt_path_var, app._pick_sync_srt, "sync_srt")
    app._sync_srt_handle = VisibilityHandle(sync)
    app._build_presets(app.studio_pages["Presets"])

    compact_state = {"value": None}
    def fit_spacing(event=None):
        if event is not None and event.widget is not app.root:
            return
        if not heading.winfo_exists():
            return
        compact = app.root.winfo_height() < 700
        if compact_state["value"] == compact:
            return
        compact_state["value"] = compact
        heading.pack_configure(pady=(16, 14) if compact else (20, 18))
        tabbar.pack_configure(pady=(0, 16 if compact else 20))
        for widget in timing_labels:
            widget.pack_configure(pady=(0, 5 if compact else 7))
    app.root.bind("<Configure>", fit_spacing, add="+")
    app.root.after_idle(fit_spacing)

    select_tab("Audio")
    app._apply_task()
    app._wire_summary()
    app.aspect_var.trace_add("write", app._apply_frame)
    app.root.bind("<Return>", lambda e: app._on_submit(
        "sync" if app.task_var.get() == "Sync Existing" else "generate"))
    app.root.bind("<Escape>", lambda e: app._on_cancel())
