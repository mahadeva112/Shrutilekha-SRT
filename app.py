"""Frozen GUI entry: home, Resolve form, and Resolve alert dialogs."""
import os
import runpy
import sys
from app_runtime import resources, install_dir, prepare_environment


def main():
    prepare_environment()
    # Windowed Python has no standard streams. Modules may still print while
    # rendering previews; discard these rather than failing the GUI.
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")
    if "--resolve" in sys.argv:
        sys.argv.remove("--resolve")
    if "--self-test" in sys.argv:
        from distribution_smoke import run
        output = sys.argv[sys.argv.index("--self-test") + 1]
        try:
            run(output)
        except Exception:
            import traceback
            from pathlib import Path
            Path(output).write_text(traceback.format_exc(), encoding="utf-8")
            sys.exit(1)
        return
    if "--dialog" in sys.argv:
        sys.argv.remove("--dialog")
        import dialog
        dialog.main()
        return
    if "--prompt" in sys.argv:
        runpy.run_path(str(resources() / "loader.pyw"), run_name="__main__")
        return
    import tkinter as tk
    from tkinter import ttk, messagebox
    from settings_ui import show_settings
    import credentials
    import release_updater
    import queue
    import threading
    root = tk.Tk()
    root.title("Srutilekha")
    root.geometry("580x380")
    body = ttk.Frame(root, padding=28)
    body.pack(fill="both", expand=True)
    ttk.Label(body, text="Srutilekha", font=("Segoe UI", 24)).pack(anchor="w")
    ttk.Label(body, text="Timeline audio → captions", font=("Segoe UI", 12)).pack(anchor="w", pady=8)
    ttk.Label(body, text="In DaVinci Resolve, open Workspace → Scripts → Srutilekha.\nChoose your audio track and generate captions.", wraplength=520).pack(anchor="w", pady=16)
    ttk.Button(body, text="API settings", command=lambda: show_settings(root)).pack(anchor="w")
    status = tk.StringVar(value="v" + release_updater.VERSION)
    ttk.Label(body, textvariable=status, wraplength=520).pack(anchor="w", pady=14)
    events = queue.Queue()
    state = {"info": None, "busy": False}

    def check():
        if state["busy"]:
            return
        state["busy"] = True
        status.set("Checking GitHub releases…")
        def work():
            try:
                events.put(("checked", release_updater.check()))
            except Exception:
                events.put(("error", "Update check unavailable. Try again later."))
        threading.Thread(target=work, daemon=True).start()

    def update():
        if state["busy"] or not state["info"]:
            return
        info = state["info"]
        if not messagebox.askokcancel("Install update", "Install v%s?\n\n%s\n\nClose all Srutilekha windows before continuing in Setup." % (info["version"], "\n".join(info["notes"][:6])), parent=root):
            return
        state["busy"] = True
        status.set("Downloading update…")
        def work():
            try:
                release_updater.install(info)
                events.put(("installed", None))
            except Exception:
                events.put(("error", "Update failed. Your installation and API key are unchanged."))
        threading.Thread(target=work, daemon=True).start()

    actions = ttk.Frame(body)
    actions.pack(fill="x")
    ttk.Button(actions, text="Check for updates", command=check).pack(side="left")
    update_button = ttk.Button(actions, text="Install update", command=update, state="disabled")
    update_button.pack(side="left", padx=10)

    def poll():
        try:
            kind, result = events.get_nowait()
            state["busy"] = False
            if kind == "checked":
                state["info"] = result
                update_button.configure(state="normal" if result else "disabled")
                status.set("Update available: v" + result["version"] if result else "Up to date · v" + release_updater.VERSION)
            elif kind == "installed":
                root.destroy()
                return
            else:
                status.set(result)
        except queue.Empty:
            pass
        root.after(100, poll)
    root.after(100, poll)
    def first_run():
        try:
            missing = not credentials.get_key()
        except Exception:
            missing = True
        if missing:
            show_settings(root)
        check()
    root.after(200, first_run)
    root.mainloop()


if __name__ == "__main__":
    main()
