"""Desktop entry point; freeze_support must precede UI startup on Windows."""
import multiprocessing
import sys


def main():
    if "--gpu-smoke-test" in sys.argv:
        from jarvis.config import data_directory
        from jarvis.gpu_smoke import run_smoke
        return run_smoke(data_directory())
    import tkinter as tk
    from tkinter import messagebox
    from jarvis.config import data_directory
    from jarvis.storage import Store
    from jarvis.ui import App
    from dataclasses import replace
    import time

    smoke = "--smoke-test" in sys.argv or "--voice-smoke-test" in sys.argv

    root = tk.Tk()
    root.withdraw()
    try:
        store = Store(data_directory() / "jarvis.sqlite3")
        app = App(root, store, refresh=not smoke)
    except Exception:
        if not smoke:
            messagebox.showerror("JARVIS — démarrage impossible", "Impossible d’ouvrir les données locales. Vérifiez les droits du dossier et l’espace disque. Ne supprimez pas votre base ; sauvegardez-la avant toute réparation.", parent=root)
        root.destroy()
        return 1
    root.deiconify()
    result = [0]
    if smoke:
        # Exercise frozen multiprocessing as well as Tk/SQLite, without Ollama.
        app.settings = replace(app.settings, endpoint="http://127.0.0.1:1")
        app.refresh_models()
        diagnostics = None
        diagnostics_ok = "--voice-smoke-test" not in sys.argv
        if not diagnostics_ok:
            from jarvis.voice_runtime import AudioProcess
            diagnostics = AudioProcess()
            diagnostics.start("diagnostics", app.voice.settings)
        deadline = time.monotonic() + 40

        def check():
            nonlocal diagnostics_ok
            if diagnostics is not None:
                for event in diagnostics.poll():
                    if event.kind == "diagnostics_done":
                        diagnostics_ok = True
                        diagnostics.stop()
                    elif event.kind == "error":
                        result[0] = 1
                        diagnostics.stop()
                        app.close()
                        return
            if not app.operation and diagnostics_ok:
                result[0] = 0 if "Connexion Ollama impossible" in app.status.get() else 1
                app.close()
            elif time.monotonic() > deadline:
                result[0] = 1
                if diagnostics is not None:
                    diagnostics.stop()
                app.close()
            else:
                root.after(50, check)
        root.after(100, check)
    root.mainloop()
    return result[0]


if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(main())
