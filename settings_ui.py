"""Key settings shared by the standalone home screen and Resolve form."""
import queue
import threading
import tkinter as tk
from tkinter import ttk, messagebox
import credentials


def show_settings(parent):
    win = tk.Toplevel(parent)
    win.title("Srutilekha — API settings")
    win.geometry("530x310")
    win.resizable(False, False)
    win.transient(parent)
    win.attributes("-topmost", True)
    win.grab_set()
    body = ttk.Frame(win, padding=22)
    body.pack(fill="both", expand=True)
    ttk.Label(body, text="Your ElevenLabs API key", font=("Segoe UI", 13)).pack(anchor="w")
    ttk.Label(body, text="Transcription uses your own ElevenLabs account and credits.").pack(anchor="w", pady=(6, 12))
    value = tk.StringVar()
    try:
        value.set(credentials.get_key())
    except Exception:
        pass
    entry = ttk.Entry(body, textvariable=value, show="•")
    entry.pack(fill="x")
    reveal = tk.BooleanVar()
    ttk.Checkbutton(body, text="Show key", variable=reveal,
                    command=lambda: entry.configure(show="" if reveal.get() else "•")).pack(anchor="w", pady=8)
    status = tk.StringVar(value="Stored encrypted for your Windows user. Updates keep this key.")
    ttk.Label(body, textvariable=status, wraplength=475).pack(anchor="w", pady=8)
    events = queue.Queue()
    testing = False

    def test():
        nonlocal testing
        if testing:
            return
        key = value.get().strip()
        if not key:
            status.set("Paste your API key first.")
            return
        testing = True
        status.set("Checking connection…")
        test_button.configure(state="disabled")

        def work():
            try:
                from elevenlabs.client import ElevenLabs
                ElevenLabs(api_key=key, timeout=15).user.get()
                result = "Connection successful. Speech-to-text usage is billed to your account."
            except Exception as exc:
                code = getattr(exc, "status_code", None)
                result = ("API key rejected. Check your key." if code == 401 else
                          "User-profile access denied. Check the key permissions; speech-to-text access may differ." if code == 403 else
                          "Could not connect. Check your internet connection and API permissions.")
            events.put(result)
        threading.Thread(target=work, daemon=True).start()

    def poll():
        nonlocal testing
        if not win.winfo_exists():
            return
        try:
            status.set(events.get_nowait())
            testing = False
            test_button.configure(state="normal")
        except queue.Empty:
            pass
        win.after(100, poll)

    def save():
        try:
            credentials.save_key(value.get())
        except Exception as exc:
            messagebox.showerror("API settings", str(exc), parent=win)
            return
        win.destroy()

    def remove():
        try:
            credentials.delete_key()
            value.set("")
            status.set("Saved API key removed.")
        except Exception:
            status.set("Could not remove the saved key.")

    buttons = ttk.Frame(body)
    buttons.pack(fill="x", pady=(12, 0))
    test_button = ttk.Button(buttons, text="Test connection", command=test)
    test_button.pack(side="left")
    ttk.Button(buttons, text="Remove key", command=remove).pack(side="left", padx=8)
    ttk.Button(buttons, text="Save", command=save).pack(side="right")
    ttk.Button(buttons, text="Cancel", command=win.destroy).pack(side="right", padx=8)
    win.after(100, poll)
    entry.focus_set()
    parent.wait_window(win)
