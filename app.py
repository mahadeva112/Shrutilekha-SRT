"""Frozen GUI entry: home, Resolve form, and Resolve alert dialogs."""
import os
import runpy
import sys
from app_runtime import resources, install_dir, prepare_environment


def main():
    from dpi import enable
    enable()
    prepare_environment()
    # Windowed Python has no standard streams. Modules may still print while
    # rendering previews; discard these rather than failing the GUI.
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")
    if "--resolve" in sys.argv:
        sys.argv.remove("--resolve")
    if "--tray-self-test" in sys.argv:
        from tray_helper import self_test
        self_test(sys.argv[sys.argv.index("--tray-self-test") + 1])
        return
    if "--tray" in sys.argv:
        from tray_helper import run
        run()
        return
    if "--tray-stop" in sys.argv:
        from tray_helper import queue_command
        queue_command('stop')
        return
    if "--bridge-run" in sys.argv:
        from resolve_bridge import run_workflow
        try:
            run_workflow()
        except Exception as exc:
            import tkinter as tk
            from tkinter import messagebox
            root = tk.Tk(); root.withdraw()
            messagebox.showerror("Srutilekha — Resolve connection", str(exc), parent=root)
            root.destroy()
        return
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
    if "--home" not in sys.argv:
        from tray_helper import request_open
        request_open()
        return
    import web_home
    if web_home.run():
        return
    # Classic Tk home: used when WebView2 is missing or SRUTILEKHA_CLASSIC_UI=1.
    import tkinter as tk
    from tkinter import ttk, messagebox
    from settings_ui import show_settings
    import credentials
    import release_updater
    import queue
    import threading
    root = tk.Tk()
    from dpi import attach
    attach(root)
    root.title("Srutilekha")
    root.geometry("620x550")
    try:
        root.iconbitmap(str(resources() / 'icon.ico'))
    except tk.TclError:
        pass
    root.configure(bg="#17191e")
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure("TFrame", background="#17191e")
    style.configure("TLabel", background="#17191e", foreground="#dce1eb", font=("Segoe UI", -14))
    style.configure("TCheckbutton", background="#17191e", foreground="#dce1eb", font=("Segoe UI", -13))
    style.map("TCheckbutton", background=[("active", "#17191e")])
    style.configure("TButton", background="#2b303a", foreground="#f1f2f5",
                    font=("Segoe UI", -14), padding=(12, 8), borderwidth=0)
    style.map("TButton", background=[("active", "#3c424f")],
              foreground=[("disabled", "#8993a3")])
    body = ttk.Frame(root, padding=28)
    body.pack(fill="both", expand=True)
    ttk.Label(body, text="Srutilekha", font=("Segoe UI", -27, "bold")).pack(anchor="w")
    ttk.Label(body, text="Timeline audio → captions", font=("Segoe UI", 12)).pack(anchor="w", pady=8)
    ttk.Label(body, text="Resolve 21.1+: captions open automatically when connected.\nStart Workspace → Scripts → Srutilekha once per Resolve session.\nResolve 21.0 or earlier: launch from the Scripts menu.", wraplength=560).pack(anchor="w", pady=16)
    def connect_resolve():
        import subprocess
        command = [str(install_dir() / "Srutilekha.exe"), "--bridge-run"] if getattr(sys, "frozen", False) else [sys.executable, str(resources() / "app.py"), "--bridge-run"]
        subprocess.Popen(command, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        root.destroy()
    ttk.Button(body, text="Connect to Resolve", command=connect_resolve).pack(anchor="w", pady=(0, 10))
    ttk.Button(body, text="API settings", command=lambda: show_settings(root)).pack(anchor="w")
    from tray_helper import startup_enabled, set_startup
    startup = tk.BooleanVar(value=startup_enabled())
    ttk.Checkbutton(body, text="Start quietly with Windows", variable=startup,
                    command=lambda: set_startup(startup.get())).pack(anchor="w", pady=(10, 0))
    connection_status = tk.StringVar(value="Connecting to Resolve…")
    ttk.Label(body, textvariable=connection_status, wraplength=550).pack(anchor="w", pady=(10, 0))
    status = tk.StringVar(value="v" + release_updater.VERSION)
    ttk.Label(body, textvariable=status, wraplength=520).pack(anchor="w", pady=14)
    events = queue.Queue()
    state = {"info": None, "busy": False, "bridge_checking": False}

    def probe():
        if state["bridge_checking"]:
            return
        if getattr(root, "_api_settings_panel", None) is not None:
            root.after(2000, probe)
            return
        state["bridge_checking"] = True
        def work():
            from resolve_bridge import probe_connection, BridgeError
            try:
                events.put(("bridge_ready", probe_connection()))
            except BridgeError as exc:
                events.put(("bridge_wait", str(exc)))
            except Exception:
                events.put(("bridge_wait", ""))
        threading.Thread(target=work, daemon=True).start()

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
            if kind.startswith("bridge_"):
                state["bridge_checking"] = False
                if kind == "bridge_ready" and getattr(root, "_api_settings_panel", None) is None:
                    connect_resolve()
                    return
                if "Another Srutilekha operation" in str(result):
                    connection_status.set("Your caption window is already open. Close it to reconnect here.")
                else:
                    connection_status.set("Waiting for Resolve. Start Workspace → Scripts → Srutilekha; this app will connect automatically.")
                root.after(2000, probe)
                root.after(100, poll)
                return
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
        if missing or "--api-settings" in sys.argv:
            show_settings(root)
        check()
        if "--home" not in sys.argv:
            probe()
        else:
            connection_status.set("Start the Resolve script; the tray helper will open captions. You can also use Connect here.")
    root.after(200, first_run)
    root.mainloop()


if __name__ == "__main__":
    main()
