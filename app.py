"""Frozen GUI entry: home, Resolve form, and Resolve alert dialogs.

Every window is WebView2 (pywebview); see web_ui.py."""
import os
import runpy
import sys
from app_runtime import resources, prepare_environment


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
            import notices
            import web_notice
            web_notice.tell(dict(notices.describe(str(exc)), kind="error",
                                 kicker="One more step", button="Got it"))
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
    show_home()


def show_home():
    """The WebView2 home window, or a notice saying why it cannot open."""
    import web_notice
    import web_ui
    if not web_ui.available():
        web_notice.tell(web_notice.MISSING_RUNTIME)
        return
    import web_home
    try:
        if not web_home.run():
            raise FileNotFoundError("ui/home.html is missing from this installation.")
    except Exception:
        import traceback
        import notices
        web_notice.tell(dict(notices.describe("Could not start the Srutilekha window.\n" + traceback.format_exc()),
                             kind="error", kicker="One more step", button="Got it"))


if __name__ == "__main__":
    main()
