"""Safe Markdown presentation for Tk; the stored message remains its original text."""
import tkinter as tk
from dataclasses import dataclass
from difflib import SequenceMatcher
from tkinter import font, ttk

from .richtext import parse_text


@dataclass
class AssistantRegion:
    start: str
    end: str
    text: str = ""


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
        families = {name.casefold(): name for name in font.families(widget)}
        self.fixed_family = next((families[name] for name in
            ("cascadia mono", "consolas", "dejavu sans mono", "liberation mono", "courier new")
            if name in families), font.nametofont("TkFixedFont", root=widget).actual("family"))
        styles = {
            "quote": {"foreground": muted, "lmargin1": 18, "lmargin2": 18},
            "list": {"lmargin1": 10, "lmargin2": 24},
            "link": {"foreground": accent, "underline": True},
            "code": {"background": code_background},
            "codeblock": {"background": code_background, "lmargin1": 12,
                          "lmargin2": 12, "spacing1": 5, "spacing3": 5},
            "math": {}, "bold": {}, "italic": {},
        }
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

    def reset(self):
        widget = self.widget
        for name in widget.mark_names():
            if name.startswith("md_region_") or name.startswith("md_selection_"):
                widget.mark_unset(name)
        for tag in self.links.values():
            widget.tag_delete(tag)
            self.tags.discard(tag)
        self.links.clear()

    def close(self):
        # Release Font objects while their Tcl interpreter still exists and on
        # Tk's main thread, even if App cycles are collected by a worker later.
        self.fonts.clear()
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
        return region

    def _font_tag(self, tags):
        heading = next((int(tag[7:]) for tag in tags if tag.startswith("heading")), 0)
        code = "code" in tags or "codeblock" in tags
        key = (code, heading, "bold" in tags or bool(heading), "italic" in tags)
        if key not in self.fonts:
            name = "md_font_" + "_".join(str(int(value)) for value in key)
            face = font.Font(root=self.widget, family=self.fixed_family if code else self.family,
                             size=12 + ({1: 8, 2: 5, 3: 3, 4: 2, 5: 1}.get(heading, 0)),
                             weight="bold" if key[2] else "normal",
                             slant="italic" if key[3] else "roman")
            self.fonts[key] = (name, face)
            self.tags.add(name)
            self.widget.tag_configure(name, font=face)
        return self.fonts[key][0]

    def _link_tag(self, url):
        if url not in self.links:
            self.link_serial += 1
            tag = f"md_url_{self.link_serial}"
            self.links[url] = tag
            self.tags.add(tag)
            self.widget.tag_configure(tag, foreground=self.accent, underline=True)
            self.widget.tag_bind(tag, "<Button-1>", lambda event, address=url: self._preview(address))
            self.widget.tag_bind(tag, "<Enter>", lambda event: self.widget.configure(cursor="hand2"))
            self.widget.tag_bind(tag, "<Leave>", lambda event: self.widget.configure(cursor=""))
        return self.links[url]

    def update(self, region, source, *, final=False):
        document = parse_text(source, final=final)
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
                    names.append(self._link_tag(span.url))
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
        """Display an inert address. Copying is the only action available."""
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
        ttk.Button(actions, text="Fermer", command=dialog.destroy).pack(side="left")
        address.focus_set()
        address.selection_range(0, "end")
        dialog.bind("<Escape>", lambda event: dialog.destroy())
        return "break"
