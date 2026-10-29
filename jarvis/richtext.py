"""Inert Markdown display and French speech, with offsets into the raw answer.

This module never interprets HTML, performs network requests, or changes the
source text. Display, speech and stream segmentation share the same scanner.
"""
from dataclasses import dataclass
import ipaddress
import re
from urllib.parse import urlsplit

from .expressions import (ascii_expressions, context_exclusions, expression_family,
                          merge_ranges, overlaps, spoken_context_symbols)
from .speech_normalization import expand_dollar_symbols, sentence_boundary, speech_atom_spans


@dataclass(frozen=True)
class Span:
    text: str
    tags: tuple = ()
    url: str | None = None


@dataclass(frozen=True)
class TextEvent:
    kind: str
    start: int
    end: int
    value: str


@dataclass(frozen=True)
class RichDocument:
    original: str
    spans: tuple
    speech: str
    events: tuple

    @property
    def text(self):
        return "".join(span.text for span in self.spans)


@dataclass(frozen=True)
class SpeechSegment:
    text: str
    original: str
    start: int
    end: int
    events: tuple = ()
    visual_only: bool = False


def safe_url(value):
    """Allow only syntactically public HTTPS destinations, without credentials.

    No DNS lookup is made: following the link remains an explicit UI action.
    """
    if not value or re.search(r"[\s\x00-\x20\x7f\\]", value):
        return None
    try:
        parsed = urlsplit(value)
        host = (parsed.hostname or "").rstrip(".").lower()
        if parsed.scheme.lower() != "https" or parsed.username is not None or parsed.password is not None:
            return None
        if not host or parsed.port is not None and not 0 < parsed.port < 65536:
            return None
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            host = host.encode("idna").decode("ascii")
            labels = host.split(".")
            if len(labels) < 2 or not re.fullmatch(r"[a-z][a-z0-9-]*", labels[-1]):
                return None
            if any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", part) for part in labels):
                return None
            if labels[-1] in {"localhost", "local", "internal", "lan", "home", "onion", "invalid", "test"}:
                return None
        else:
            if not address.is_global:
                return None
    except (ValueError, UnicodeError):
        return None
    return value


def _emoji_base(char):
    n = ord(char)
    return (0x1F000 <= n <= 0x1FAFF or 0x2600 <= n <= 0x27BF
            or 0x2194 <= n <= 0x2199 or 0x21A9 <= n <= 0x21AA
            or 0x23E9 <= n <= 0x23F3 or 0x23F8 <= n <= 0x23FA
            or 0x25FB <= n <= 0x25FE or 0x2934 <= n <= 0x2935
            or 0x2B05 <= n <= 0x2B07
            or n in {0xA9, 0xAE, 0x203C, 0x2049, 0x2122, 0x2139,
                     0x231A, 0x231B, 0x2328, 0x23CF, 0x24C2, 0x25AA,
                     0x25AB, 0x25B6, 0x25C0, 0x2B1B, 0x2B1C, 0x2B50,
                     0x2B55, 0x3030, 0x303D, 0x3297, 0x3299})


def _emoji_ranges(text):
    i = 0
    while i < len(text):
        start = i
        char = text[i]
        keycap = char in "0123456789#*" and re.compile("[\ufe0e\ufe0f]?\u20e3").match(text, i + 1)
        if keycap:
            i = keycap.end()
        elif _emoji_base(char):
            i += 1
            if 0x1F1E6 <= ord(char) <= 0x1F1FF and i < len(text) and 0x1F1E6 <= ord(text[i]) <= 0x1F1FF:
                i += 1
            while i < len(text):
                n = ord(text[i])
                if text[i] in "\ufe0e\ufe0f\u20e3" or 0x1F3FB <= n <= 0x1F3FF or 0xE0020 <= n <= 0xE007F:
                    i += 1
                elif text[i] == "\u200d":
                    i += 1
                    if i < len(text) and _emoji_base(text[i]):
                        i += 1
                    else:
                        break
                else:
                    break
        elif char in "\u200d\ufe0e\ufe0f\u20e3" or 0xE0020 <= ord(char) <= 0xE007F:
            i += 1
        else:
            i += 1
            continue
        yield start, i


_GREEK = dict(zip("αβγδεζηθικλμνξοπρστυφχψω", (
    "alpha", "bêta", "gamma", "delta", "epsilon", "zêta", "êta", "thêta", "iota", "kappa", "lambda", "mu",
    "nu", "xi", "omicron", "pi", "rhô", "sigma", "tau", "upsilon", "phi", "khi", "psi", "oméga")))
_COMMANDS = dict(zip(("alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi omicron pi rho sigma tau upsilon phi chi psi omega").split(), _GREEK.values()))
_COMMANDS.update({"le": "inférieur ou égal à", "leq": "inférieur ou égal à", "ge": "supérieur ou égal à",
                  "geq": "supérieur ou égal à", "neq": "différent de", "ne": "différent de", "approx": "environ égal à",
                  "times": "fois", "cdot": "fois", "div": "divisé par", "pm": "plus ou moins", "infty": "infini",
                  "sum": "somme", "prod": "produit", "int": "intégrale", "in": "appartient à", "to": "tend vers"})
_UNITS = {"m/s": "mètres par seconde", "km/h": "kilomètres par heure", "kg": "kilogrammes", "km": "kilomètres",
          "cm": "centimètres", "mm": "millimètres", "ms": "millisecondes", "m": "mètres", "s": "secondes",
          "Hz": "hertz", "°C": "degrés Celsius", "€": "euros", "$": "dollars", "%": "pour cent"}


def _group(text, start):
    """Return a balanced TeX group (or its next single token)."""
    while start < len(text) and text[start].isspace():
        start += 1
    if start >= len(text):
        return "", start
    if text[start] != "{":
        token = re.match(r"\\[A-Za-z]+|.", text[start:], re.S)
        return token.group(), start + token.end()
    depth = 1
    end = start + 1
    while end < len(text) and depth:
        depth += (text[end] == "{") - (text[end] == "}")
        end += 1
    return text[start + 1:end - 1 if depth == 0 else end], end


def verbalize_math(text):
    """A small deterministic verbalizer; unknown names and units stay readable."""
    for start, end in reversed(list(_emoji_ranges(text))):
        text = text[:start] + " " + text[end:]
    result = []
    i = 0
    while i < len(text):
        if text[i] == "\\":
            match = re.match(r"\\([A-Za-z]+|.)", text[i:], re.S)
            if not match:
                i += 1
                continue
            name = match[1]
            i += match.end()
            if name in {"frac", "dfrac", "tfrac"}:
                top, i = _group(text, i)
                bottom, i = _group(text, i)
                result.append(" fraction de " + verbalize_math(top) + " sur " + verbalize_math(bottom) + " ")
            elif name == "sqrt":
                degree = "carrée"
                if i < len(text) and text[i] == "[" and "]" in text[i:]:
                    end = text.index("]", i)
                    degree = "d’ordre " + verbalize_math(text[i + 1:end])
                    i = end + 1
                value, i = _group(text, i)
                result.append(" racine " + degree + " de " + verbalize_math(value) + " ")
            elif name in {"text", "mathrm", "textrm", "operatorname"}:
                value, i = _group(text, i)
                result.append(" " + _UNITS.get(value, value) + " ")
            elif name in {"left", "right"}:
                pass
            elif name in {",", ";", "!", " ", "quad", "qquad"}:
                result.append(" ")
            else:
                result.append(" " + _COMMANDS.get(name.lower(), name) + " ")
        elif text[i] in "^_":
            marker = text[i]
            value, i = _group(text, i + 1)
            if marker == "^" and value in {"2", "3"}:
                result.append(" au carré " if value == "2" else " au cube ")
            else:
                result.append((" puissance " if marker == "^" else " indice ") + verbalize_math(value) + " ")
        else:
            char = text[i]
            if char in _GREEK or char.lower() in _GREEK:
                result.append(" " + _GREEK[char.lower()] + " ")
            else:
                result.append(char)
            i += 1
    value = "".join(result)
    # Expand a numeric unit before replacing division signs.
    unit_pattern = "|".join(re.escape(unit) for unit in sorted(_UNITS, key=len, reverse=True))
    value = re.sub(r"(?<=\d)\s*(" + unit_pattern + r")(?!\w)", lambda m: " " + _UNITS[m[1]] + " ", value)
    symbols = {"≤": "inférieur ou égal à", "≥": "supérieur ou égal à", "≠": "différent de", "≈": "environ égal à",
               "=": "égal à", "<": "inférieur à", ">": "supérieur à", "+": "plus", "−": "moins", "-": "moins",
               "×": "fois", "*": "fois", "÷": "divisé par", "/": "divisé par", "±": "plus ou moins", "∞": "infini"}
    value = "".join(" " + symbols[c] + " " if c in symbols else " " if c in "{}" else c for c in value)
    return " ".join(value.split())


def _speech_text(text):
    text = spoken_context_symbols(text)
    ranges = list(_emoji_ranges(text))
    for start, end in reversed(ranges):
        text = text[:start] + " " + text[end:]
    text = expand_dollar_symbols(text)
    # Unclosed formatting remains readable at end of stream.
    text = re.sub(r"[*_`$]", "", text)
    # A line/paragraph break is an audible pause, even inside emphasis or a list.
    text = re.sub(r"([^\s.!?;:,])(?:[ \t]*\n)+", r"\1. ", text)
    return " ".join(text.split())


class _Scanner:
    def __init__(self, text, final, speak_code, source_map=False):
        self.text, self.final, self.speak_code = text, final, speak_code
        self.spans, self.speech, self.events = [], [], []
        self.protected, self.incomplete = [], []
        # Source projection is built only on explicit selection actions. The
        # ordinary display/stream/speech path allocates no per-character map.
        self.source_map = [] if source_map else None
        self.add = self._add_mapped if source_map else self._add_plain
        self.expression_exclusions = context_exclusions(text)
        self.ascii_expressions = {start: (end, value) for start, end, value in
                                  ascii_expressions(text, self.expression_exclusions)}

    def _add_plain(self, text, tags=(), url=None, speech=None, *, source=None, mapping=None):
        if not text and speech is None:
            return
        tags = tuple(dict.fromkeys(tags))
        if text:
            if self.spans and (self.spans[-1].tags, self.spans[-1].url) == (tags, url):
                previous = self.spans[-1]
                self.spans[-1] = Span(previous.text + text, tags, url)
            else:
                self.spans.append(Span(text, tags, url))
        self.speech.append(text if speech is None else speech)

    def _add_mapped(self, text, tags=(), url=None, speech=None, *, source=None, mapping=None):
        self._add_plain(text, tags, url, speech)
        if mapping is not None:
            self.source_map.extend(mapping)
        elif source is not None:
            left, right = source
            if self.text[left:right] == text:
                self.source_map.extend((index, index + 1) for index in range(left, right))
            else:
                # A synthetic glyph (for example a bullet) has a known source
                # interval, but no character-for-character original substring.
                self.source_map.extend((left, right) for _ in text)
        else:
            self.source_map.extend((None, None) for _ in text)

    def event(self, kind, start, end, value):
        self.events.append(TextEvent(kind, start, end, value))

    def protect(self, start, end, complete=True):
        self.protected.append((start, end))
        if not complete and not self.final:
            self.incomplete.append(start)

    def _cells(self, start, end):
        """Source intervals, respecting escaped pipes and inline code."""
        text = self.text
        while start < end and text[start].isspace():
            start += 1
        while end > start and text[end - 1].isspace():
            end -= 1
        if start < end and text[start] == "|":
            start += 1
        if end > start and text[end - 1] == "|" and (end < 2 or text[end - 2] != "\\"):
            end -= 1
        cells, left, i, code = [], start, start, ""
        while i < end:
            if text[i] == "\\":
                i += 2
                continue
            if text[i] == "`":
                run = re.match(r"`+", text[i:end])[0]
                if code == run:
                    code = ""
                elif not code:
                    code = run
                i += len(run)
                continue
            if text[i] == "|" and not code:
                cells.append((left, i))
                left = i + 1
            i += 1
        cells.append((left, end))
        return tuple((left + len(text[left:right]) - len(text[left:right].lstrip()),
                      right - len(text[left:right]) + len(text[left:right].rstrip()))
                     for left, right in cells)

    def _table(self, start, end, inherited):
        """Render a conventional pipe table through the existing span scanner."""
        text = self.text
        header_end = text.find("\n", start, end)
        if header_end < 0:
            if not self.final and "|" in text[start:end]:
                self.protect(start, end, False)
            return None
        if "|" not in text[start:header_end]:
            return None
        rule_end = text.find("\n", header_end + 1, end)
        rule_end = end if rule_end < 0 else rule_end
        header = self._cells(start, header_end)
        rules = self._cells(header_end + 1, rule_end)
        if not (2 <= len(header) <= 32 and len(rules) == len(header)
                and all(re.fullmatch(r":?-{3,}:?", text[a:b]) for a, b in rules)):
            if not self.final and rule_end == end and re.fullmatch(r"[ \t|:\-]*", text[header_end + 1:end]):
                self.protect(start, end, False)
            return None
        rows, stop = [header], rule_end + (rule_end < end)
        while stop < end:
            right = text.find("\n", stop, end)
            right = end if right < 0 else right
            if "|" not in text[stop:right]:
                break
            cells = self._cells(stop, right)
            if len(cells) != len(header):
                break
            rows.append(cells)
            stop = right + (right < end)
        # A growing table is indivisible for speech: never pronounce a partial
        # separator row or treat the following data row as ordinary prose.
        complete = self.final or stop < end and "\n" in text[stop:end]
        self.protect(start, stop, complete)
        self.event("table", start, stop, "")
        prepared, widths = [], [0] * len(header)
        for row_index, row in enumerate(rows):
            cells = []
            for column, (left, right) in enumerate(row):
                saved_spans, saved_speech, saved_map = self.spans, self.speech, self.source_map
                self.spans, self.speech = [], []
                if saved_map is not None:
                    self.source_map = []
                self.scan(left, right, inherited + ("table",) + (("tableheader",) if row_index == 0 else ()))
                spans, speech = self.spans, "".join(self.speech)
                cell_map = self.source_map
                self.spans, self.speech, self.source_map = saved_spans, saved_speech, saved_map
                width = len("".join(span.text for span in spans))
                widths[column] = max(widths[column], min(40, width))
                cells.append((spans, speech, width, cell_map))
            prepared.append(cells)
        for row in prepared:
            for column, (spans, speech, width, cell_map) in enumerate(row):
                if column:
                    self.add(" │ ", inherited + ("table",), speech=" ; ")
                offset = 0
                for span in spans:
                    self.add(span.text, span.tags, span.url, speech="",
                             mapping=cell_map[offset:offset + len(span.text)] if cell_map is not None else None)
                    offset += len(span.text)
                self.add(" " * max(0, widths[column] - width), inherited + ("table",), speech=speech)
            self.add("\n", inherited + ("table",))
        return stop

    def scan(self, start=0, end=None, inherited=()):
        text = self.text
        end = len(text) if end is None else end
        i, stack, block = start, [], ()
        while i < end:
            tags = inherited + block + tuple(tag for _, tag, _ in stack)
            # Fences and other block markers only exist at line starts.
            if i == 0 or text[i - 1] == "\n":
                fence = re.match(r" {0,3}(`{3,}|~{3,})([^\n]*)\n?", text[i:end])
                if fence:
                    marker = fence[1]
                    content_start = i + fence.end()
                    close = re.search(r"(?m)^ {0,3}" + re.escape(marker[0]) + "{" + str(len(marker)) + r",}[ \t]*(?:\n|$)", text[content_start:end])
                    content_end = content_start + close.start() if close else end
                    stop = content_start + close.end() if close else end
                    content = text[content_start:content_end]
                    speech = " " + content + " " if self.speak_code else " Bloc de code non lu. "
                    self.add(content, inherited + ("codeblock",), speech=speech,
                             source=(content_start, content_end))
                    self.event("code", i, stop, content)
                    self.protect(i, stop, close is not None)
                    if close and stop > content_end and text[stop - 1:stop] == "\n":
                        self.add("\n", inherited, source=(stop - 1, stop))
                    i = stop
                    continue
                table_end = self._table(i, end, inherited)
                if table_end is not None:
                    i = table_end
                    continue
                separator = re.match(r" {0,3}(?:(?:\*[ \t]*){3,}|(?:-[ \t]*){3,}|(?:_[ \t]*){3,})(?:\n|$)", text[i:end])
                if separator:
                    stop = i + separator.end()
                    self.add("────────────────────────\n", inherited + ("separator",), speech="\n", source=(i, stop))
                    self.event("markup", i, stop, text[i:stop])
                    self.protect(i, stop, stop < end or self.final or text[stop - 1:stop] == "\n")
                    i = stop
                    continue
                prefix = re.match(r" {0,3}(#{1,6})[ \t]+", text[i:end])
                quote = re.match(r" {0,3}(?:>[ \t]?)+", text[i:end])
                listing = re.match(r"[ \t]*(?:[-+*]|\d+[.)])[ \t]+", text[i:end])
                match = prefix or quote or listing
                block = (("heading" + str(len(prefix[1])),) if prefix else ("quote",) if quote else ("list",) if listing else ())
                if match:
                    if listing and not prefix and not quote:
                        marker = listing[0].strip()
                        indent = listing[0][:len(listing[0]) - len(listing[0].lstrip())]
                        depth = min(6, len(indent.expandtabs(4)) // 2)
                        block += (f"list_depth_{depth}",)
                        self.add(("•" if marker in "-+*" else marker) + " ",
                                 inherited + block, speech="", source=(i, i + match.end()))
                    self.event("markup", i, i + match.end(), text[i:i + match.end()])
                    i += match.end()
                    continue
                tags = inherited + tuple(tag for _, tag, _ in stack)
            char = text[i]
            expression = self.ascii_expressions.get(i)
            if expression and not {"code", "codeblock", "link", "math"}.intersection(tags):
                stop, value = expression
                self.add(value, tags, speech=" ", source=(i, stop))
                self.event("expression", i, stop, value)
                self.protect(i, stop)
                i = stop
                continue
            keycap = re.match("\\*[\ufe0e\ufe0f]?\u20e3", text[i:i + 3])
            if keycap:
                self.add(keycap[0], tags, source=(i, i + keycap.end()))
                i += keycap.end()
                continue
            if char == "\n":
                self.add(char, inherited, source=(i, i + 1))
                block = ()
                i += 1
                continue
            if char == "\\" and i + 1 < end and text[i + 1] in r"\`*_{}[]<>#$!+=|~":
                self.add(text[i + 1], tags, source=(i, i + 2))
                self.protect(i, i + 2)
                i += 2
                continue
            # Code is opaque: Markdown, URLs and formulas inside stay literal.
            if char == "`":
                run = re.match(r"`+", text[i:end])[0]
                close = text.find(run, i + len(run), end)
                stop = close + len(run) if close >= 0 else end
                value = text[i + len(run):close if close >= 0 else end]
                self.add(value, tags + ("code",), source=(i + len(run), close if close >= 0 else end))
                self.event("code", i, stop, value)
                self.protect(i, stop, close >= 0)
                i = stop
                continue
            # Deliberate non-HTML extensions. A technical equality/increment
            # inside an identifier or an equation is not expressive styling.
            if char in "+=" and text[i:i + 2] == char * 2:
                before = text[i - 1] if i > start else " "
                after = text[i + 2] if i + 2 < end else ""
                if not before.isalnum() and after and not after.isspace():
                    marker = char * 2
                    close = i + 2
                    while True:
                        close = text.find(marker, close, end)
                        if close < 0 or (text[close - 1] != "\\" and not text[close - 1].isspace()):
                            break
                        close += 2
                    if close >= 0:
                        stop = close + 2
                        self.scan(i + 2, close, tags + (("underline" if char == "+" else "highlight"),))
                        self.event("markup", i, stop, marker)
                        self.protect(i, stop)
                        i = stop
                        continue
                    if not self.final:
                        self.add(text[i + 2:end], tags, source=(i + 2, end))
                        self.protect(i, end, False)
                        i = end
                        continue
            # Label and destination are one indivisible source interval.
            if char == "[":
                label_end = self._closing(i, "[", "]", end)
                if label_end is not None and label_end + 1 < end and text[label_end + 1] == "(":
                    destination_end = self._closing(label_end + 1, "(", ")", end)
                    if destination_end is not None:
                        destination = text[label_end + 2:destination_end].strip()
                        if destination.startswith("<") and ">" in destination:
                            destination = destination[1:destination.index(">")]
                        else:
                            destination = re.split(r"\s+[\"']", destination, maxsplit=1)[0]
                        url = safe_url(destination)
                        previous = self.spans
                        self.spans = []
                        self.scan(i + 1, label_end, tags + ("link",))
                        # Nested label spans retain emphasis, with the validated URL.
                        label_spans = self.spans
                        self.spans = previous + [Span(span.text, span.tags, url) for span in label_spans]
                        self.event("link", i, destination_end + 1, destination)
                        self.protect(i, destination_end + 1)
                        i = destination_end + 1
                        continue
                    self.protect(i, end, False)
                    self.scan(i + 1, label_end, tags + ("link",))
                    i = end
                    continue
                if label_end is None or label_end + 1 == end:
                    self.protect(i, end, False)
            math = self._math(i, end)
            if math:
                body_start, body_end, stop, complete = math
                value = text[body_start:body_end]
                self.add(value, tags + ("math",), speech=" " + verbalize_math(value) + " ",
                         source=(body_start, body_end))
                self.event("math", i, stop, verbalize_math(value))
                self.protect(i, stop, complete)
                i = stop
                continue
            url_match = re.match(r"(?:https?://|ftp://|www\.)[^\s<>\[\]`]+", text[i:end], re.I)
            if url_match:
                value = url_match[0].rstrip(".,!?;:")
                stop = i + len(value)
                self.add(value, tags + ("link",), safe_url(value), " lien ", source=(i, stop))
                self.event("link", i, stop, value)
                self.protect(i, stop, i + url_match.end() < end or self.final)
                i = stop
                continue
            if char in "*_~":
                run_end = i + 1
                while run_end < end and text[run_end] == char:
                    run_end += 1
                count = run_end - i
                # Strikethrough is the explicit ~~extension~~, never a single
                # approximation tilde, an inline ~~~run~~~ or intraword code.
                # Fenced code was already handled before entering this branch.
                if char == "~" and count != 2:
                    self.add(char * count, tags, source=(i, run_end))
                    if not self.final and run_end == end:
                        self.protect(i, end, False)
                    i = run_end
                    continue
                before = text[i - 1] if i > start else " "
                after = text[run_end] if run_end < end else ""
                intraword = char in "_~" and before.isalnum() and after.isalnum()
                remaining = count
                if not intraword and not before.isspace():
                    while stack and stack[-1][0][0] == char and len(stack[-1][0]) <= remaining:
                        marker, _, opening = stack.pop()
                        self.protect(opening, run_end)
                        remaining -= len(marker)
                if not intraword and remaining and (after and not after.isspace()):
                    while remaining:
                        length = 2 if remaining >= 2 else 1
                        stack.append((char * length, "strike" if char == "~" else "bold" if length == 2 else "italic", i))
                        remaining -= length
                if intraword or remaining:
                    self.add(char * remaining, tags, source=(run_end - remaining, run_end))
                    if not self.final and run_end == end:
                        self.protect(i, end, False)
                self.event("markup", i, run_end, text[i:run_end])
                i = run_end
                continue
            # Coalesce plain runs rather than processing every character separately.
            stop = i + 1
            while (stop < end and stop not in self.ascii_expressions
                   and text[stop] not in "\n\\`[*_$+=~"
                   and not text.startswith(("http://", "https://", "ftp://", "www."), stop)):
                stop += 1
            self.add(text[i:stop], tags, source=(i, stop))
            i = stop
        for _, _, opening in stack:
            self.protect(opening, end, False)

    def _closing(self, start, opening, closing, end):
        depth, i = 1, start + 1
        while i < end:
            if self.text[i] == "\\":
                i += 2
                continue
            depth += (self.text[i] == opening) - (self.text[i] == closing)
            if depth == 0:
                return i
            i += 1
        return None

    def _math(self, start, end):
        text = self.text
        # A suffix currency sign belongs to the amount, including before a
        # sentence ending (20 $.). It cannot open a LaTeX expression.
        previous = start - 1
        while previous >= 0 and text[previous] in " \t":
            previous -= 1
        if (text[start] == "$" and previous >= 0 and text[previous].isdigit()
                and (start + 1 == end or text[start + 1].isspace()
                     or text[start + 1] in ".,!?;:")):
            return None
        for opening, closing in ((r"\(", r"\)"), (r"\[", r"\]"), ("$$", "$$")):
            if text.startswith(opening, start):
                close = text.find(closing, start + len(opening), end)
                return start + len(opening), close if close >= 0 else end, close + len(closing) if close >= 0 else end, close >= 0
        if text[start] != "$" or start + 1 == end or text[start + 1].isspace():
            if text[start] == "$" and start + 1 == end and not self.final:
                self.protect(start, end, False)
            return None
        close = start + 1
        while True:
            close = text.find("$", close, end)
            if close < 0:
                break
            if text[close - 1] != "\\":
                # '$5+$10' contains two prices; the second sign opens a price
                # rather than closing the first expression.
                if close + 1 < end and text[close + 1].isdigit():
                    break
                body = text[start + 1:close]
                if body and not body[-1].isspace() and "\n" not in body:
                    return start + 1, close, close + 1, True
                break
            close += 1
        # Numeric currency can be spoken once its enclosing phrase is complete;
        # an unfinished algebraic formula waits for its closing delimiter.
        following = text[start + 1:end]
        if not re.match(r"[+-]?\d", following):
            self.protect(start, end, False)
            return start + 1, end, end, False
        # Until the stream ends, '$2.' could still become '$2.14 + x$'.
        # Currency remains visible but cannot force a premature speech boundary.
        self.protect(start, end, False)
        return None

    def document(self):
        self.scan()
        excluded = merge_ranges(self.expression_exclusions + tuple((event.start, event.end)
                                for event in self.events if event.kind in {"code", "link", "math"}))
        for start, end in _emoji_ranges(self.text):
            self.event("emoji", start, end, self.text[start:end])
            if expression_family(self.text[start:end]) and not overlaps(start, end, excluded):
                self.event("expression", start, end, self.text[start:end])
        return RichDocument(self.text, tuple(self.spans), _speech_text("".join(self.speech)),
                            tuple(sorted(self.events, key=lambda event: (event.start, event.end, event.kind))))


def parse_text(text, final=True, speak_code=False):
    return _Scanner(text, final, speak_code).document()


def parse_mapped_text(text, final=True):
    """Return the ordinary document and exact rendered-codepoint source ranges.

    Called on demand by selection tools, never by the streaming/audio loops.
    ``(None, None)`` denotes generated table spacing, which cannot be mistaken
    for user/model source characters.
    """
    scanner = _Scanner(text, final, False, source_map=True)
    document = scanner.document()
    return document, tuple(scanner.source_map)


class SpeechBuffer:
    """Segment only outside balanced constructs; retain every raw source offset."""
    def __init__(self, speak_code=False):
        self.speak_code = speak_code
        self.original = ""
        self._cursor = 0
        self.emitted = False

    @property
    def pending(self):
        return self.original[self._cursor:]

    def feed(self, text, final=False):
        self.original += text
        result = []
        while self.pending:
            source = self.pending
            scanner = _Scanner(source, final, self.speak_code)
            scanner.document()
            available = min(scanner.incomplete, default=len(source))
            limit = 240 if self.emitted else 96
            protected = scanner.protected + (list(speech_atom_spans(source[:available])) if len(source) >= limit else [])

            def safe(end):
                return end <= available and not any(start < end < stop for start, stop in protected)

            sentence = None
            for match in re.finditer(r"[.!?;:\n](?:\s+|$)", source[:available]):
                position = match.start()
                # Titles/initials and numeric fragments are not whole phrases.
                # In particular a streamed 'Dr.' cannot start Piper yet.
                if not sentence_boundary(source, position, final=final):
                    continue
                if safe(match.end()):
                    sentence = match.end()
                    break
            spaces = [match.end() for match in re.finditer(r"\s+", source[:min(available, limit + 1)]) if safe(match.end())]
            clause = next((match.end() for match in re.finditer(r",\s+", source[40:min(available, limit)])
                           if safe(40 + match.end())), None) if not self.emitted else None
            if sentence is not None and sentence <= limit:
                stop = sentence
            elif clause is not None:
                stop = 40 + clause
            elif len(source) >= limit and spaces:
                stop = spaces[-1]
            elif sentence is not None:
                stop = sentence
            elif final:
                # An indivisible construct may exceed the preferred segment length.
                stop = len(source)
            else:
                break
            if stop <= 0:
                break
            raw = source[:stop]
            document = parse_text(raw, speak_code=self.speak_code)
            start = self._cursor
            self._cursor += stop
            events = tuple(TextEvent(event.kind, event.start + start, event.end + start, event.value) for event in document.events)
            expressive = any(event.kind in {"expression", "emoji"} for event in events)
            punctuation_only = not document.speech.strip(" \t\r\n.!?,;:…-–—()[]{}")
            if document.speech and not (expressive and punctuation_only):
                result.append(SpeechSegment(document.speech, raw, start, self._cursor, events))
                self.emitted = True
            elif expressive:
                result.append(SpeechSegment("", raw, start, self._cursor, events, visual_only=True))
        return result
