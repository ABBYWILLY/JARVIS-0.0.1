"""Offline Canvas demo. Uses an isolated temporary profile, never user data."""
import argparse
from pathlib import Path
import tempfile
import tkinter as tk
from tkinter import messagebox
from tkinter import font as tkfont
from types import SimpleNamespace

from jarvis.presence import PresenceView
from jarvis.presence_demo import DemoController
from jarvis.storage import Store


def main():
    parser = argparse.ArgumentParser(description="PRESENCE : démonstration hors ligne, PCM synthétique explicite")
    parser.add_argument("--capture-dir", type=Path, help="Captures PNG des étapes (Pillow facultatif requis)")
    parser.add_argument("--size", default="1000x680", help="Taille Tk, par défaut 1000x680")
    parser.add_argument("--reduced-motion", action="store_true")
    parser.add_argument("--auto-close", action="store_true", help="Fermer après le scénario complet")
    args = parser.parse_args()
    capture = None
    if args.capture_dir:
        try:
            from PIL import ImageGrab
        except ImportError:
            parser.error("Les captures demandent Pillow ; la démonstration seule n'en a pas besoin.")
        args.capture_dir.mkdir(parents=True, exist_ok=True)
        if any(args.capture_dir.iterdir()):
            parser.error("Choisissez un dossier de captures vide pour préserver les fichiers existants.")
        capture = ImageGrab
    with tempfile.TemporaryDirectory(prefix="jarvis-presence-demo-") as temporary:
        root = tk.Tk()
        root.withdraw()
        store = Store(Path(temporary) / "demo.sqlite3")
        def unavailable():
            messagebox.showinfo("Démonstration hors ligne", "Aucun microphone ni moteur vocal n'est démarré.", parent=view.window)
        voice = SimpleNamespace(listening=False, microphone_state="disabled", toggle=unavailable,
                                stop_listening=lambda: None, emergency=lambda: demo.stop())
        families = set(tkfont.families(root))
        family = next((name for name in ("Segoe UI", "DejaVu Sans", "Arial") if name in families),
                      tkfont.nametofont("TkDefaultFont", root=root).actual("family"))
        app = SimpleNamespace(root=root, store=store, voice=voice, operation=None, font_family=family)
        view = PresenceView(app)
        view.show()
        view.window.geometry(args.size)
        view.window.title("PRESENCE · DÉMONSTRATION · PCM SYNTHÉTIQUE")
        if args.reduced_motion:
            from dataclasses import replace
            view.settings = view.model.settings = replace(view.settings, reduced_motion=True)
        def snapshot(index, label):
            if capture is None:
                return
            # Capture after 400ms of the real animation, with the same one demo
            # timer: no extra scheduled callback remains after cancellation.
            pending[0] = (index, label)
        pending = [None]
        demo = DemoController(view, on_stage=snapshot,
                              on_finish=lambda reason: close() if args.auto_close and reason == "completed" else None)
        original_paint = demo._paint
        def paint(index, local, changed):
            original_paint(index, local, changed)
            if pending[0] is not None and local >= .4:
                number, _label = pending[0]
                pending[0] = None
                window = view.window
                window.update_idletasks()
                box = (window.winfo_rootx(), window.winfo_rooty(),
                       window.winfo_rootx() + window.winfo_width(), window.winfo_rooty() + window.winfo_height())
                path = args.capture_dir / f"presence-demo-{number + 1:02d}.png"
                with path.open("xb") as output:
                    capture.grab(bbox=box).save(output, format="PNG")
        demo._paint = paint
        def close():
            demo.cancel("closed")
            view.close()
            root.quit()
        view.window.protocol("WM_DELETE_WINDOW", close)
        view.command_button.configure(command=close, text="Fermer la démo")
        # Escape closes this standalone demonstration; no hidden Tk root lingers.
        view.window.bind("<Escape>", lambda _event: close())
        view.window.bind("<Control-r>", lambda _event: demo.start())
        root.update_idletasks()
        demo.start()
        try:
            root.mainloop()
        finally:
            demo.cancel("closed")
            view.close()
            store.close()
            root.destroy()


if __name__ == "__main__":
    main()
