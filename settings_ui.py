"""In-window API settings shared by the home screen and Resolve form."""
import queue
import threading
import tkinter as tk
import credentials


class ApiSettingsPanel(tk.Frame):
    """A modal child panel; the Resolve form stays intact underneath it."""
    def __init__(self, parent, theme=None):
        colors = dict(bg="#212126", card="#28282e", field="#1c1c21",
                      text="#d4d4d6", muted="#9a9a9d", border="#3b3b43",
                      accent="#e8c547", font="Segoe UI")
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
        bar.pack(fill="x", padx=22, pady=(12, 8))
        self._button(bar, "‹  Back to captions", self.close).pack(side="left")
        tk.Label(bar, text="ACCOUNT  /  ELEVENLABS", bg=colors["bg"],
                 fg=colors["muted"], font=(font, 8)).pack(side="right")
        space = tk.Frame(self, bg=colors["bg"])
        space.pack(fill="both", expand=True, padx=22, pady=(0, 14))
        card = tk.Frame(space, bg=colors["card"], highlightthickness=1,
                        highlightbackground=colors["border"])
        card.place(relx=.5, rely=.5, anchor="center", relwidth=1, width=-4)
        # Cap the card width on the large Resolve form, but fit the home window.
        def fit(event):
            card.place_configure(relwidth=0, width=min(550, max(1, event.width-4)))
        space.bind("<Configure>", fit)
        body = tk.Frame(card, bg=colors["card"])
        body.pack(fill="both", expand=True, padx=20, pady=17)
        tk.Label(body, text="Your ElevenLabs API key", bg=colors["card"],
                 fg=colors["text"], font=(font, 15, "bold"), anchor="w").pack(fill="x")
        tk.Label(body, text="Use your own account and transcription credits.",
                 bg=colors["card"], fg=colors["muted"], font=(font, 9),
                 anchor="w").pack(fill="x", pady=(6, 16))
        self.value = tk.StringVar(master=self)
        load_error = False
        try:
            self.value.set(credentials.get_key())
        except Exception:
            load_error = True
        self.entry = tk.Entry(body, textvariable=self.value, show="•",
                              bg=colors["field"], fg=colors["text"],
                              insertbackground=colors["accent"], relief="flat",
                              highlightthickness=1, highlightbackground=colors["border"],
                              highlightcolor=colors["accent"], font=(font, 11))
        self.entry.pack(fill="x", ipady=8)
        self.reveal = tk.BooleanVar(master=self)
        tk.Checkbutton(body, text="Show key", variable=self.reveal,
                       command=self._toggle_reveal, bg=colors["card"],
                       fg=colors["muted"], activebackground=colors["card"],
                       activeforeground=colors["text"], selectcolor=colors["field"],
                       font=(font, 9), bd=0, highlightthickness=0).pack(anchor="w", pady=(8, 8))
        self.status = tk.StringVar(master=self, value=(
            "Saved key could not be read. Paste your key again." if load_error else
            "Encrypted for your Windows user. Updates keep your saved key."))
        status_label = tk.Label(body, textvariable=self.status, bg=colors["card"],
                                fg=colors["muted"], font=(font, 9), anchor="w",
                                justify="left", wraplength=480)
        status_label.pack(fill="x", pady=(0, 15))
        body.bind("<Configure>", lambda event: status_label.configure(wraplength=max(1, event.width)))
        actions = tk.Frame(body, bg=colors["card"])
        actions.pack(fill="x")
        self.test_button = self._button(actions, "Test connection", self.test)
        self.test_button.pack(side="left")
        self._button(actions, "Remove key", self.remove).pack(side="left", padx=(8, 0))
        self._button(actions, "Save key", self.save, primary=True).pack(side="right")
        self._binding_ids["<Return>"] = parent.bind("<Return>", self.save)
        self._binding_ids["<Escape>"] = parent.bind("<Escape>", self.close)
        self.grab_set()
        self.entry.focus_set()
        self._poll_job = self.after(100, self._poll)

    def _button(self, parent, text, command, primary=False):
        c = self.colors
        return tk.Button(parent, text=text, command=command, relief="flat", bd=0,
                         bg=c["accent"] if primary else c["field"],
                         fg="#242016" if primary else c["text"],
                         activebackground="#f0d66d" if primary else c["border"],
                         activeforeground="#242016" if primary else c["text"],
                         disabledforeground=c["muted"], font=(c["font"], 9),
                         padx=12, pady=8, cursor="hand2")

    def _toggle_reveal(self):
        self.entry.configure(show="" if self.reveal.get() else "•")

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
