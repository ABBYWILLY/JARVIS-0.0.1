"""Scrollable native form with a fixed action area and focus revelation."""
import tkinter as tk
from tkinter import ttk


class SettingsForm:
    def __init__(self, dialog, *, background):
        self.dialog = dialog
        width = min(720, dialog.winfo_screenwidth() - 60)
        height = min(660, dialog.winfo_screenheight() - 100)
        dialog.geometry(f"{width}x{height}")
        dialog.minsize(340, 280)
        self.footer = ttk.Frame(dialog)
        self.footer.pack(side="bottom", fill="x", pady=(8, 0))
        body = tk.Frame(dialog, bg=background)
        body.pack(fill="both", expand=True)
        self.canvas = canvas = tk.Canvas(body, bg=background, highlightthickness=0, width=1, height=1)
        scroll = ttk.Scrollbar(body, command=canvas.yview)
        scroll.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        canvas.configure(yscrollcommand=scroll.set)
        self.content = tk.Frame(canvas, bg=background)
        item = canvas.create_window(0, 0, anchor="nw", window=self.content)
        self.content.columnconfigure(0, weight=1)
        self.content.bind("<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(item, width=event.width))
        dialog.bind("<FocusIn>", self.reveal, add="+")
        for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            dialog.bind(sequence, self.wheel, add="+")
        dialog.bind("<Escape>", lambda _event: dialog.destroy())

    def reveal(self, event):
        if not str(event.widget).startswith(str(self.content) + "."):
            return
        y = event.widget.winfo_rooty() - self.content.winfo_rooty()
        bottom = y + event.widget.winfo_height()
        top = self.canvas.canvasy(0)
        if y < top or bottom > top + self.canvas.winfo_height():
            self.canvas.yview_moveto(max(0, bottom - self.canvas.winfo_height()) /
                                    max(1, self.content.winfo_height()))

    def wheel(self, event):
        if (str(event.widget).startswith(str(self.content))
                and not isinstance(event.widget, (ttk.Combobox, tk.Scale, tk.Text))):
            direction = -1 if getattr(event, "num", None) == 4 or getattr(event, "delta", 0) > 0 else 1
            self.canvas.yview_scroll(direction * 3, "units")
            return "break"
