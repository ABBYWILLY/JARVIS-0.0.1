"""Safe Markdown presentation for Tk; the stored message remains its original text."""
import tkinter as tk
import webbrowser
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
from tkinter import font, messagebox, ttk

from .richtext import parse_text, safe_url


@dataclass(frozen=True)
class ConversationTypography:
    family: str = ""
    size: int = 12
    scale: int = 100
    spacing: str = "comfortable"
    accent_intensity: int = 65
    code_family: str = ""

    @classmethod
    def from_dict(cls, value, families=(), code_families=()):
        value = value if isinstance(value, dict) else {}
        installed = {name.casefold(): name for name in families}
        family = value.get("family")
        family = installed.get(family.casefold(), "") if isinstance(family, str) else ""
        fixed = {name.casefold(): name for name in code_families}
        code_family = value.get("code_family")
        code_family = fixed.get(code_family.casefold(), "") if isinstance(code_family, str) else ""
        options = {"family": family, "code_family": code_family}
        for key, low, high in (("size", 9, 24), ("scale", 75, 175), ("accent_intensity", 0, 100)):
            number = value.get(key)
            if type(number) is int and low <= number <= high:
                options[key] = number
        if value.get("spacing") in ("compact", "comfortable"):
            options["spacing"] = value["spacing"]
        return cls(**options)

    def to_dict(self):
        return asdict(self)


@dataclass
class AssistantRegion:
    start: str
    end: str
    text: str = ""
    original: str = ""


class MarkdownView:
    """Render only the assistant region being streamed, on Tk's main thread.

    Relative Tk character offsets count Unicode code points, even when Tk 8.6
    reports UTF-16 column numbers. Never use Tcl string length for +Nc offsets.
    No HTML widget, browser, network request, or interpreter handles message text.
    """

    def __init__(self, widget, family, foreground, muted, accent, code_background):
        self.widget = widget
        self.family = (font.nametofont(family, root=widget).actual("family")
                       if family in font.names(widget) else family)
        self.foreground, self.muted, self.accent = foreground, muted, accent
        self.serial = 0
        self.tags = set()
        self.fonts = {}
        self.links = {}
        self.link_serial = 0
        self.regions = []
        self._source_index = None
        self.typography = ConversationTypography(family=self.family)
        self.body_font = font.Font(root=widget, family=self.family, size=12)
        families = {name.casefold(): name for name in font.families(widget)}
        self.fixed_family = next((families[name] for name in
            ("cascadia mono", "consolas", "dejavu sans mono", "liberation mono", "courier new")
            if name in families), font.nametofont("TkFixedFont", root=widget).actual("family"))
        # Resolve installed fixed-width faces once, outside streaming/animation.
        # Tk's measured 'fixed' metric also handles local fonts not in our list.
        fixed = {self.fixed_family}
        for family_name in families.values():
            face = font.Font(root=widget, family=family_name, size=12)
            if face.metrics("fixed"):
                fixed.add(face.actual("family"))
            del face
        self.code_families = tuple(sorted(fixed, key=str.casefold))
        self.highlight_background = "#544a21" if sum(widget.winfo_rgb(foreground)) > 90000 else "#fff0a0"
        styles = {
            "quote": {"foreground": muted, "lmargin1": 18, "lmargin2": 18},
            "list": {"lmargin1": 10, "lmargin2": 24},
            "link": {"foreground": accent, "underline": True},
            "code": {"background": code_background},
            "codeblock": {"background": code_background, "lmargin1": 12,
                          "lmargin2": 12, "spacing1": 5, "spacing3": 5},
            "math": {}, "bold": {}, "italic": {}, "strike": {}, "underline": {"underline": True},
            "highlight": {"background": self.highlight_background},
            "separator": {"foreground": muted, "spacing1": 8, "spacing3": 8},
            "table": {"spacing1": 1, "spacing3": 1}, "tableheader": {},
        }
        styles.update({f"list_depth_{depth}": {"lmargin1": 10 + depth * 22,
                                             "lmargin2": 24 + depth * 22} for depth in range(7)})
        styles.update({f"heading{level}": {"spacing1": 12, "spacing3": 6}
                       for level in range(1, 7)})
        for name, options in styles.items():
            tag = "md_" + name
            self.tags.add(tag)
            widget.tag_configure(tag, **options)
        widget.bind("<Return>", self._return_link, add="+")
        widget.bind("<Tab>", self._next_link, add="+")
        widget.bind("<Shift-Tab>", lambda event: self._next_link(event, reverse=True), add="+")
        widget.bind("<ISO_Left_Tab>", lambda event: self._next_link(event, reverse=True), add="+")
        self.source_menu = tk.Menu(widget, tearoff=False)
        self.source_menu.add_command(label="Copier la sélection affichée", command=lambda: widget.event_generate("<<Copy>>"))
        self.source_menu.add_command(label="Copier la réponse originale", command=self.copy_original)
        widget.bind("<Button-3>", self._source_context, add="+")
        widget.bind("<Control-Shift-C>", self.copy_original, add="+")
        self.configure_typography(self.typography)

    def reset(self):
        widget = self.widget
        for name in widget.mark_names():
            if name.startswith("md_region_") or name.startswith("md_selection_"):
                widget.mark_unset(name)
        for tag in self.links.values():
            widget.tag_delete(tag)
            self.tags.discard(tag)
        self.links.clear()
        self.regions.clear()
        self._source_index = None

    def close(self):
        # Release Font objects while their Tcl interpreter still exists and on
        # Tk's main thread, even if App cycles are collected by a worker later.
        if self.widget is None:
            return
        self.fonts.clear()
        self.body_font = None
        self.regions.clear()
        self.source_menu.destroy()
        self.links.clear()
        self.tags.clear()
        self.widget = None

    def units(self, text):
        return len(text)

    def offset(self, start, text):
        return self.widget.index(f"{start}+{self.units(text)}c")

    def append(self, source, *, final=True):
        self.serial += 1
        prefix = f"md_region_{self.serial}"
        region = AssistantRegion(prefix + "_start", prefix + "_end")
        widget = self.widget
        widget.mark_set(region.start, "end-1c")
        widget.mark_gravity(region.start, "left")
        widget.mark_set(region.end, region.start)
        widget.mark_gravity(region.end, "left")
        self.update(region, source, final=final)
        self.regions.append(region)
        return region

    def configure_typography(self, settings):
        """Update the bounded font cache in place, without reparsing messages."""
        self.typography = settings
        widget = self.widget
        viewport = widget.index("@0,0")
        top = widget.dlineinfo(viewport)
        family = settings.family or self.family
        size = round(settings.size * settings.scale / 100)
        self.body_font.configure(family=family, size=size)
        gap = max(1, round(size * (.09 if settings.spacing == "compact" else .3)))
        widget.configure(font=self.body_font, spacing1=gap, spacing2=gap, spacing3=gap)
        for key, (_name, face) in self.fonts.items():
            code, heading, _bold, _italic, _strike = key
            face.configure(family=self.code_family if code else family,
                           size=self._point_size(code, heading))
        indent = max(8, round(size * .9))
        widget.tag_configure("md_quote", lmargin1=indent * 2, lmargin2=indent * 2)
        widget.tag_configure("md_list", lmargin1=indent, lmargin2=indent * 2)
        for depth in range(7):
            widget.tag_configure(f"md_list_depth_{depth}", lmargin1=indent + depth * indent * 2,
                                 lmargin2=indent * 2 + depth * indent * 2)
        for level in range(1, 7):
            widget.tag_configure(f"md_heading{level}", spacing1=max(gap, round(size * .8)), spacing3=gap)
        widget.tag_configure("md_codeblock", lmargin1=indent, lmargin2=indent, spacing1=gap, spacing3=gap)
        self._configure_accents(settings.accent_intensity)
        # Font changes preserve the selected characters and visible text anchor.
        widget.update_idletasks()
        widget.yview(viewport)
        restored = widget.dlineinfo(viewport)
        if top is not None and restored is not None:
            widget.yview_scroll(restored[1] - top[1], "pixels")

    @property
    def code_family(self):
        selected = self.typography.code_family
        return selected if selected in self.code_families else self.fixed_family

    def _blend(self, start, end, amount):
        first, last = self.widget.winfo_rgb(start), self.widget.winfo_rgb(end)
        return "#" + "".join(f"{round((a + (b - a) * amount) / 257):02x}"
                              for a, b in zip(first, last))

    def _configure_accents(self, intensity):
        amount = max(0, min(100, intensity)) / 100
        self.display_accent = self._blend(self.foreground, self.accent, amount)
        self.widget.tag_configure("md_link", foreground=self.display_accent)
        for tag in self.links.values():
            self.widget.tag_configure(tag, foreground=self.display_accent)
        for level in range(1, 7):
            self.widget.tag_configure(f"md_heading{level}",
                foreground=self._blend(self.foreground, self.accent, amount * .55))
        self.widget.tag_configure("md_highlight", background=self._blend(
            self.widget.cget("background"), self.highlight_background, amount))

    def _point_size(self, code, heading):
        base = self.typography.size - (1 if code else 0)
        return max(8, round((base + {1: 8, 2: 5, 3: 3, 4: 2, 5: 1}.get(heading, 0))
                            * self.typography.scale / 100))

    def _font_tag(self, tags):
        heading = next((int(tag[7:]) for tag in tags if tag.startswith("heading")), 0)
        code = "code" in tags or "codeblock" in tags or "table" in tags
        key = (code, heading, "bold" in tags or "tableheader" in tags or bool(heading), "italic" in tags,
               "strike" in tags)
        if key not in self.fonts:
            name = "md_font_" + "_".join(str(int(value)) for value in key)
            face = font.Font(root=self.widget, family=self.code_family if code else self.typography.family or self.family,
                             size=self._point_size(code, heading),
                             weight="bold" if key[2] else "normal",
                             slant="italic" if key[3] else "roman", overstrike=key[4])
            self.fonts[key] = (name, face)
            self.tags.add(name)
            self.widget.tag_configure(name, font=face)
        return self.fonts[key][0]

    def _link_tag(self, url):
        if url not in self.links:
            # Large archives retain their text without creating unlimited Tcl
            # tags and callback commands. Ordinary conversations stay clickable.
            if len(self.links) >= 256:
                return None
            self.link_serial += 1
            tag = f"md_url_{self.link_serial}"
            self.links[url] = tag
            self.tags.add(tag)
            self.widget.tag_configure(tag, foreground=self.display_accent, underline=True)
            self.widget.tag_bind(tag, "<Button-1>", lambda event, address=url: self._preview(address))
            self.widget.tag_bind(tag, "<Enter>", lambda event: self.widget.configure(cursor="hand2"))
            self.widget.tag_bind(tag, "<Leave>", lambda event: self.widget.configure(cursor=""))
        return self.links[url]

    def update(self, region, source, *, final=False):
        document = parse_text(source, final=final)
        region.original = source
        widget = self.widget
        at_bottom = widget.yview()[1] >= 0.98
        widget.mark_set("md_viewport", "@0,0")
        widget.mark_gravity("md_viewport", "left")
        top_line = widget.dlineinfo("md_viewport")
        top_y = top_line[1] if top_line else None
        viewport_content = None
        if widget.compare("md_viewport", ">=", region.start) and widget.compare("md_viewport", "<", region.end):
            viewport_offset = len(widget.get(region.start, "md_viewport"))
            viewport_content = (region.text[viewport_offset:viewport_offset + 160], viewport_offset)
        selection = widget.tag_ranges("sel")
        selected_content = {}
        for index in range(0, len(selection), 2):
            start, end = selection[index:index + 2]
            if widget.compare(start, ">=", region.start) and widget.compare(end, "<=", region.end):
                selected_content[index] = (widget.get(start, end), len(widget.get(region.start, start)))
        # Temporary marks keep an existing selection attached to unchanged text.
        for index, position in enumerate(selection):
            mark = f"md_selection_{index}"
            widget.mark_set(mark, position)
            widget.mark_gravity(mark, "right" if index % 2 == 0 else "left")
        old, new = region.text, document.text
        prefix = 0
        limit = min(len(old), len(new))
        while prefix < limit and old[prefix] == new[prefix]:
            prefix += 1
        suffix = 0
        while suffix < limit - prefix and old[-suffix - 1] == new[-suffix - 1]:
            suffix += 1
        widget.configure(state="normal")
        try:
            if old != new:
                widget.mark_gravity(region.end, "right")
                old_middle = old[prefix:len(old) - suffix]
                new_middle = new[prefix:len(new) - suffix]
                # Closing a delimiter may reveal formatting while adding a new
                # phrase. Keep the unchanged words (and their selection marks)
                # in place; cap diff work for large model outputs.
                if len(old_middle) + len(new_middle) <= 8192:
                    changes = SequenceMatcher(None, old_middle, new_middle).get_opcodes()
                else:
                    changes = [("replace", 0, len(old_middle), 0, len(new_middle))]
                base = self.offset(region.start, old[:prefix])
                for operation, a, b, c, d in reversed(changes):
                    if operation == "equal":
                        continue
                    first = self.offset(base, old_middle[:a])
                    last = self.offset(base, old_middle[:b])
                    widget.delete(first, last)
                    widget.insert(first, new_middle[c:d], ())
                widget.mark_gravity(region.end, "left")
            region.text = new
            if viewport_content:
                context, old_offset = viewport_content
                if widget.get("md_viewport", self.offset("md_viewport", context)) != context:
                    position = self._nearest_match(new, context, old_offset)
                    if position is not None:
                        widget.mark_set("md_viewport", self.offset(region.start, new[:position]))
            for tag in self.tags:
                widget.tag_remove(tag, region.start, region.end)
            current = widget.index(region.start)
            for span in document.spans:
                end = self.offset(current, span.text)
                names = ["md_" + tag for tag in span.tags if "md_" + tag in self.tags]
                names.append(self._font_tag(span.tags))
                if span.url:
                    link_tag = self._link_tag(span.url)
                    if link_tag is not None:
                        names.append(link_tag)
                for tag in names:
                    widget.tag_add(tag, current, end)
                current = end
            for url, tag in tuple(self.links.items()):
                if not widget.tag_ranges(tag):
                    widget.tag_delete(tag)
                    self.tags.discard(tag)
                    del self.links[url]
            # Font tags have final priority so bold+italic compose correctly.
            for name, _face in self.fonts.values():
                widget.tag_raise(name)
            widget.tag_raise("sel")
            if selection:
                widget.tag_remove("sel", "1.0", "end")
                for index in range(0, len(selection), 2):
                    start, end = f"md_selection_{index}", f"md_selection_{index + 1}"
                    if index in selected_content:
                        selected, old_offset = selected_content[index]
                        if widget.get(start, end) != selected:
                            # A large delimiter reinterpretation can replace a
                            # whole block. Preserve selected words if present.
                            position = self._nearest_match(new, selected, old_offset)
                            if position is not None:
                                widget.mark_set(start, self.offset(region.start, new[:position]))
                                widget.mark_set(end, self.offset(start, selected))
                    if widget.compare(start, "<", end):
                        widget.tag_add("sel", start, end)
        finally:
            widget.configure(state="disabled")
            for index in range(len(selection)):
                widget.mark_unset(f"md_selection_{index}")
        if at_bottom:
            widget.see("end")
        else:
            widget.yview("md_viewport")
            restored = widget.dlineinfo("md_viewport")
            if restored is not None and top_y is not None:
                widget.yview_scroll(restored[1] - top_y, "pixels")
        widget.mark_unset("md_viewport")
        return document

    def _region_at(self, position):
        return next((region for region in self.regions
                     if self.widget.compare(position, ">=", region.start)
                     and self.widget.compare(position, "<=", region.end)), None)

    def _source_context(self, event):
        self._source_index = self.widget.index(f"@{event.x},{event.y}")
        region = self._region_at(self._source_index)
        self.source_menu.entryconfigure(1, state="normal" if region else "disabled")
        try:
            self.source_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.source_menu.grab_release()
        return "break"

    def copy_original(self, _event=None):
        """Copy the raw assistant source; normal Ctrl+C still copies selection."""
        widget = self.widget
        selected = widget.tag_ranges("sel")
        position = (self._source_index if _event is None else None) or (selected[0] if selected else "insert")
        region = self._region_at(position)
        self._source_index = None
        if region is not None:
            widget.clipboard_clear()
            widget.clipboard_append(region.original)
        return "break"

    @staticmethod
    def _nearest_match(text, fragment, offset):
        if not fragment:
            return None
        before = text.rfind(fragment, 0, offset + len(fragment))
        after = text.find(fragment, offset)
        matches = [position for position in (before, after) if position >= 0]
        return min(matches, key=lambda value: abs(value - offset)) if matches else None

    def _url_at(self, index):
        names = self.widget.tag_names(index)
        return next((url for url, tag in self.links.items() if tag in names), None)

    def _return_link(self, _event=None):
        url = self._url_at("insert")
        if url:
            return self._preview(url)

    def _next_link(self, _event=None, reverse=False):
        widget = self.widget
        ranges = [(widget.index(start), url) for url, tag in self.links.items()
                  for start in widget.tag_ranges(tag)[::2]]
        if not ranges:
            return None
        ranges.sort(key=lambda item: tuple(map(int, item[0].split("."))))
        candidates = [item for item in ranges if widget.compare(item[0], "<" if reverse else ">", "insert")]
        position, _url = (candidates[-1] if reverse else candidates[0]) if candidates else (ranges[-1] if reverse else ranges[0])
        widget.mark_set("insert", position)
        widget.see(position)
        return "break"

    def _preview(self, url):
        """An inert preview precedes any explicit, confirmed browser action."""
        if safe_url(url) is None:
            return "break"
        widget = self.widget
        widget.focus_set()
        dialog = tk.Toplevel(widget)
        dialog.title("Aperçu du lien")
        dialog.transient(widget.winfo_toplevel())
        dialog.columnconfigure(0, weight=1)
        ttk.Label(dialog, text="Adresse HTTPS — aucun site ouvert automatiquement.",
                  padding=12).grid(row=0, column=0, sticky="w")
        address = ttk.Entry(dialog, width=76)
        address.insert(0, url)
        address.configure(state="readonly")
        address.grid(row=1, column=0, padx=12, pady=(0, 12), sticky="ew")
        actions = ttk.Frame(dialog, padding=(12, 0, 12, 12))
        actions.grid(row=2, column=0, sticky="e")

        def copy():
            widget.clipboard_clear()
            widget.clipboard_append(url)

        ttk.Button(actions, text="Copier l’adresse", command=copy).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Ouvrir dans le navigateur", command=lambda: self.open_link(url, dialog)).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Fermer", command=dialog.destroy).pack(side="left")
        address.focus_set()
        address.selection_range(0, "end")
        dialog.bind("<Escape>", lambda event: dialog.destroy())
        return "break"

    def open_link(self, url, parent=None):
        if safe_url(url) is None:
            return False
        parent = parent or self.widget.winfo_toplevel()
        if not messagebox.askyesno("Ouvrir le lien", "Ouvrir cette adresse dans votre navigateur ?\n\n" + url,
                                   parent=parent):
            return False
        try:
            return bool(webbrowser.open(url, new=2))
        except (OSError, webbrowser.Error) as exc:
            messagebox.showerror("Lien indisponible", str(exc), parent=parent)
            return False
