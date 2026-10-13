"""In-window API settings shared by the home screen and Resolve form."""
import queue
import threading
import tkinter as tk
from tkinter import font as tkfont
import credentials


def rounded_rect(canvas, x1, y1, x2, y2, radius, **style):
    """Draw rounded surfaces without platform-dependent native button chrome."""
    r = min(radius, (x2-x1)/2, (y2-y1)/2)
    return canvas.create_polygon(
        x1+r, y1, x2-r, y1, x2, y1, x2, y1+r,
        x2, y2-r, x2, y2, x2-r, y2, x1+r, y2,
        x1, y2, x1, y2-r, x1, y1+r, x1, y1,
        smooth=True, splinesteps=24, **style)


class RoundedSurface(tk.Canvas):
    def __init__(self, parent, bg, fill, border, radius=18, padding=26):
        super().__init__(parent, bg=bg, width=600, height=360,
                         highlightthickness=0, bd=0)
        self.fill, self.border = fill, border
        self.radius, self.padding = radius, padding
        self.body = tk.Frame(self, bg=fill)
        self.body_id = self.create_window(padding, padding, window=self.body, anchor="nw")
        self.bind("<Configure>", self._layout)
        self.body.bind("<Configure>", self._layout)

    def set_padding(self, padding):
        if padding != self.padding:
            self.padding = padding
            self._layout()

    def _layout(self, event=None):
        width = self.winfo_width()
        height = self.body.winfo_reqheight() + self.padding*2 + 4
        self.configure(height=height)
        self.coords(self.body_id, self.padding, self.padding)
        self.itemconfigure(self.body_id, width=max(1, width-self.padding*2))
        self.delete("surface")
        shadow = rounded_rect(self, 2, 5, width-2, height-1, self.radius,
                              fill="#161619", outline="")
        face = rounded_rect(self, 1, 1, width-1, height-5, self.radius,
                            fill=self.fill, outline=self.border)
        for shape in (shadow, face):
            self.addtag_withtag("surface", shape)
        self.tag_lower("surface")


class RoundedAction(tk.Canvas):
    def __init__(self, parent, text, command, colors, primary=False,
                 fill=None, ink=None, height=36, width=None, interactive=True):
        self.colors, self.text, self.command = colors, text, command
        self.primary, self.fill, self.ink = primary, fill, ink
        self.interactive, self.hover = interactive, False
        self.font = tkfont.Font(family=colors.get("button_font", colors["font"]),
                                size=colors.get("button_size", -14),
                                weight="bold" if primary else "normal")
        super().__init__(parent, width=width or self.font.measure(text)+26,
                         height=height, bg=parent.cget("bg"), highlightthickness=0,
                         bd=0, takefocus=interactive, cursor="hand2" if interactive else "")
        self.bind("<Configure>", self._draw)
        self.bind("<FocusIn>", self._draw)
        self.bind("<FocusOut>", self._draw)
        if interactive:
            self.bind("<Enter>", lambda e: self._hover(True))
            self.bind("<Leave>", lambda e: self._hover(False))
            self.bind("<ButtonRelease-1>", self._invoke)
            self.bind("<space>", self._invoke)
            self.bind("<Return>", self._invoke)

    def _hover(self, on):
        self.hover = on
        self._draw()

    def _invoke(self, event=None):
        if self.cget("state") != "disabled":
            self.command()
        return "break"

    def configure(self, cnf=None, **kwargs):
        result = super().configure(cnf, **kwargs)
        if "state" in kwargs:
            self._draw()
        return result

    def set_text(self, text):
        self.text = text
        self._draw()

    def set_primary(self, primary):
        if getattr(self, "selection_button", False):
            self.primary = False
            self.fill = self.colors.get("selected", "#3a3d45") if primary else self.master.cget("bg")
            self.ink = self.colors.get("selected_text",self.colors["text"]) if primary else self.colors["muted"]
        else:
            self.primary = primary
            self.font.configure(weight="bold" if primary else "normal")
        self._draw()

    def _draw(self, event=None):
        self.delete("all")
        c = self.colors
        disabled = self.cget("state") == "disabled"
        fill = self.fill or (c["accent"] if self.primary else c.get("button_fill", "#323239"))
        ink = self.ink or ("#242016" if self.primary else c["text"])
        if self.hover and not disabled:
            fill = "#f0d66d" if self.primary else c.get("button_hover", "#3b3b43")
        if disabled:
            ink = c["muted"]
        border = c.get("button_border",fill) if not self.primary and self.fill is None else fill
        if self.focus_get() is self and self.interactive:
            border = c["accent"]
        radius = c.get("radius",8)
        rounded_rect(self, 2, 3, self.winfo_width()-2, self.winfo_height()-1,
                     radius, fill="#14171d", outline="")
        rounded_rect(self, 1, 1, self.winfo_width()-1, self.winfo_height()-3,
                     radius, fill=fill, outline=border)
        self.create_text(self.winfo_width()/2, self.winfo_height()/2,
                         text=self.text, fill=ink, font=self.font)


class ApiSettingsPanel(tk.Frame):
    """A modal child panel; the Resolve form stays intact underneath it."""
    def __init__(self, parent, theme=None):
        colors = dict(bg="#17191e", card="#22252c", field="#191c22",
                      text="#f1f2f5", muted="#afb5c2", border="#3a414d",
                      accent="#eed185", font="Segoe UI", button_size=-14)
        colors.update(theme or {})
        self.colors = colors
        self.parent = parent
        self._closed = False
        self._poll_job = None
        self._testing = False
        self._events = queue.Queue()
        self._bindings = {key: parent.bind(key) for key in ("<Return>", "<Escape>")}
        self._binding_ids = {}
        self._previous_focus = parent.focus_get()
        self._previous_grab = parent.grab_current()
        super().__init__(parent, bg=colors["bg"])
        # Keep the host's existing frameless title bar and window controls.
        inset = 44 if parent.overrideredirect() else 0
        self.place(x=0, y=inset, relwidth=1, relheight=1, height=-inset)
        self.lift()
        font = colors["font"]
        bar = tk.Frame(self, bg=colors["bg"])
        bar.pack(fill="x", padx=24, pady=(14, 10))
        self._button(bar, "‹  Back to captions", self.close).pack(side="left")
        tk.Label(bar, text="SETTINGS  /  API CONNECTION", bg=colors["bg"],
                 fg=colors["muted"], font=(font, -12)).pack(side="right")
        space = tk.Frame(self, bg=colors["bg"])
        space.pack(fill="both", expand=True, padx=24, pady=(0, 18))
        card = RoundedSurface(space, colors["bg"], colors["card"],
                              colors["border"], radius=18, padding=26)
        card.place(relx=.5, rely=.5, anchor="center", width=600)
        body = card.body
        provider = tk.Frame(body, bg=colors["card"])
        provider.pack(fill="x", pady=(0, 22))
        mark = tk.Canvas(provider, width=42, height=42, bg=colors["card"],
                         highlightthickness=0)
        mark.pack(side="left", padx=(0, 12))
        rounded_rect(mark, 1, 1, 41, 41, 12, fill="#373326", outline="#4e4630")
        for x, y in ((15, 13), (24, 10)):
            mark.create_line(x, y, x, 30, width=4, fill=colors["accent"], capstyle="round")
        provider_text = tk.Frame(provider, bg=colors["card"])
        provider_text.pack(side="left")
        tk.Label(provider_text, text="ElevenLabs", bg=colors["card"], fg=colors["text"],
                 font=(font, -16, "bold"), anchor="w").pack(anchor="w")
        tk.Label(provider_text, text="Speech-to-text provider", bg=colors["card"],
                 fg=colors["muted"], font=(font, -13)).pack(anchor="w", pady=(2, 0))
        badge = RoundedAction(provider, "Personal account", lambda: None, colors,
                              fill="#343126", ink=colors["accent"], height=28,
                              interactive=False)
        badge.pack(side="right")
        title = tk.Label(body, text="Connect your account", bg=colors["card"],
                        fg=colors["text"], font=(font, -27, "bold"), anchor="w")
        title.pack(fill="x")
        description = tk.Label(body, text="Bring your own API key to generate captions.",
                               bg=colors["card"], fg=colors["muted"],
                               font=(font, -14), anchor="w")
        description.pack(fill="x", pady=(5, 16))
        tk.Label(body, text="ELEVENLABS API KEY", bg=colors["card"],
                 fg=colors["muted"], font=(font, -13, "bold"), anchor="w").pack(fill="x", pady=(0, 7))
        self.value = tk.StringVar(master=self)
        load_error = False
        try:
            self.value.set(credentials.get_key())
        except Exception:
            load_error = True
        field = tk.Canvas(body, height=46, width=80, bg=colors["card"],
                          highlightthickness=0)
        field.pack(fill="x")
        row = tk.Frame(field, bg=colors["field"])
        self.entry = tk.Entry(row, textvariable=self.value, show="•", bd=0,
                              bg=colors["field"], fg=colors["text"],
                              insertbackground=colors["accent"], relief="flat",
                              highlightthickness=0, font=(font, -15))
        self.entry.pack(side="left", fill="x", expand=True)
        self.reveal = tk.BooleanVar(master=self)
        self.reveal_button = RoundedAction(row, "Show", self._toggle_reveal, colors,
                                           fill=colors["field"], height=28, width=54)
        self.reveal_button.pack(side="right", padx=(8, 0))
        row_id = field.create_window(14, 23, window=row, anchor="w")
        def draw_field(event=None):
            width = field.winfo_width()
            field.delete("outline")
            outline = rounded_rect(field, 1, 1, width-1, 45, 9,
                         fill=colors["field"], outline=(colors["accent"]
                         if self.entry.focus_get() is self.entry else colors["border"]))
            field.addtag_withtag("outline", outline)
            field.tag_lower("outline")
            field.itemconfigure(row_id, width=max(1, width-28))
        field.bind("<Configure>", draw_field)
        field.bind("<Button-1>", lambda e: self.entry.focus_set())
        self.entry.bind("<FocusIn>", draw_field)
        self.entry.bind("<FocusOut>", draw_field)
        self.status = tk.StringVar(master=self, value=(
            "Saved key could not be read. Paste your key again." if load_error else
            "Encrypted on this device. Your key stays saved through updates."))
        note = tk.Frame(body, bg=colors["card"])
        note.pack(fill="x", pady=(12, 16))
        shield = tk.Canvas(note, width=18, height=20, bg=colors["card"], highlightthickness=0)
        shield.pack(side="left", anchor="n", padx=(0, 8))
        shield.create_polygon(9, 2, 16, 5, 15, 12, 9, 18, 3, 12, 2, 5,
                              fill="", outline="#94aa97", width=1)
        shield.create_line(5, 9, 8, 12, 13, 7, fill="#94aa97", width=1.5)
        status_label = tk.Label(note, textvariable=self.status, bg=colors["card"],
                                fg=colors["muted"], font=(font, -13), anchor="w",
                                justify="left", wraplength=480)
        status_label.pack(side="left", fill="x", expand=True)
        note.bind("<Configure>", lambda e: status_label.configure(wraplength=max(1, e.width-26)))
        tk.Frame(body, bg=colors["border"], height=1).pack(fill="x", pady=(0, 16))
        actions = tk.Frame(body, bg=colors["card"])
        actions.pack(fill="x")
        self._button(actions, "Remove key", self.remove, subtle=True).pack(side="left")
        self._button(actions, "Save key  →", self.save, primary=True).pack(side="right")
        self.test_button = self._button(actions, "Test connection", self.test)
        self.test_button.pack(side="right", padx=(0, 10))
        def fit(event):
            card.place_configure(width=min(600, max(1, event.width-4)))
            compact = event.height < 410
            if compact:
                provider.pack_forget()
            elif not provider.winfo_manager():
                provider.pack(fill="x", pady=(0, 22), before=title)
            card.set_padding(18 if compact else 26)
        space.bind("<Configure>", fit)
        self._binding_ids["<Return>"] = parent.bind("<Return>", self.save)
        self._binding_ids["<Escape>"] = parent.bind("<Escape>", self.close)
        self.grab_set()
        self.entry.focus_set()
        self._poll_job = self.after(100, self._poll)

    def _button(self, parent, text, command, primary=False, subtle=False):
        return RoundedAction(parent, text, command, self.colors, primary=primary,
                             fill=parent.cget("bg") if subtle else None,
                             ink=self.colors["muted"] if subtle else None)

    def _toggle_reveal(self):
        self.reveal.set(not self.reveal.get())
        self.entry.configure(show="" if self.reveal.get() else "•")
        self.reveal_button.set_text("Hide" if self.reveal.get() else "Show")

    def test(self):
        if self._testing:
            return
        key = self.value.get().strip()
        if not key:
            self.status.set("Paste your API key first.")
            self.entry.focus_set()
            return
        self._testing = True
        self.status.set("Checking connection…")
        self.test_button.configure(state="disabled")
        events = self._events
        def work():
            try:
                from elevenlabs.client import ElevenLabs
                ElevenLabs(api_key=key, timeout=15).user.get()
                result = "Connection successful. Transcription uses your account credits."
            except Exception as exc:
                code = getattr(exc, "status_code", None)
                result = ("API key rejected. Check your key." if code == 401 else
                          "Profile access denied. Check the key permissions; speech-to-text access may differ." if code == 403 else
                          "Could not connect. Check your internet connection and API permissions.")
            events.put(result)
        threading.Thread(target=work, daemon=True).start()

    def _poll(self):
        self._poll_job = None
        if self._closed:
            return
        try:
            self.status.set(self._events.get_nowait())
            self._testing = False
            self.test_button.configure(state="normal")
        except queue.Empty:
            pass
        self._poll_job = self.after(100, self._poll)

    def save(self, event=None):
        try:
            credentials.save_key(self.value.get())
        except Exception:
            self.status.set("Could not save the key. Enter a valid key and try again.")
            self.entry.focus_set()
            return "break"
        return self.close()

    def remove(self):
        try:
            credentials.delete_key()
            self.value.set("")
            self.status.set("Saved API key removed.")
        except Exception:
            self.status.set("Could not remove the saved key. Try again.")

    def close(self, event=None):
        self.destroy()
        return "break"

    def destroy(self):
        if self._closed:
            return
        self._closed = True
        if self._poll_job is not None:
            self.after_cancel(self._poll_job)
            self._poll_job = None
        self.value.set("")
        try:
            if self.grab_current() is self:
                self.grab_release()
            for key, script in self._bindings.items():
                self.parent.bind(key, script or "")
                self.parent.deletecommand(self._binding_ids[key])
            if self._previous_grab is not None and self._previous_grab.winfo_exists():
                self._previous_grab.grab_set()
            if self._previous_focus is not None and self._previous_focus.winfo_exists():
                self._previous_focus.focus_set()
        except tk.TclError:
            pass
        if getattr(self.parent, "_api_settings_panel", None) is self:
            self.parent._api_settings_panel = None
        super().destroy()


def show_settings(parent, theme=None):
    existing = getattr(parent, "_api_settings_panel", None)
    if existing is not None and existing.winfo_exists():
        existing.entry.focus_set()
        return
    panel = ApiSettingsPanel(parent, theme)
    parent._api_settings_panel = panel
    parent.wait_window(panel)
