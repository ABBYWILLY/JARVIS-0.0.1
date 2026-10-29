"""Exact, bounded source projection for explicit rich-conversation actions.

The renderer supplies the same document and source ranges as the scanner. No
string-search heuristic guesses which repeated word or URL was selected.
"""
from dataclasses import dataclass
from hashlib import sha256
import re

from .richtext import parse_mapped_text


MAX_SOURCE = 65_536
MAX_SELECTION = 8192


@dataclass(frozen=True)
class SelectionResult:
    message_id: int
    session_id: str
    region_key: str
    revision: int
    source_start: int
    source_end: int
    original: str
    display_text: str
    speech_source: str
    source_hash: str


def source_hash(text):
    return sha256(text.encode("utf-8")).hexdigest()


def _literal(text):
    # Reconstruct visible prose as inert Markdown. Useful literal French
    # punctuation remains, while selected model text cannot open new markup.
    escaped = re.sub(r"([\\`*_{}\[\]<>#$!+=|~])", r"\\\1", text)
    # A mid-paragraph excerpt can start with "1. value" or "- value" without
    # being a source list. Inert emphasis guards prevent reinterpreting it as
    # a new list (whose marker would otherwise be omitted from speech).
    return "\n".join("**" + line + "**" if re.match(r"^\s*(?:-\s|[0-9]+[.)]\s|-{3,}\s*$)", line)
                     else line for line in escaped.split("\n"))


def _speech_source(document, start, end):
    parts, offset = [], 0
    for span in document.spans:
        left, right = max(start, offset), min(end, offset + len(span.text))
        if left < right:
            text = span.text[left - offset:right - offset]
            if "codeblock" in span.tags or "code" in span.tags:
                run = max((len(match.group()) for match in re.finditer(r"`+", text)), default=0)
                if "codeblock" in span.tags:
                    fence = "`" * max(3, run + 1)
                    parts.append("\n" + fence + "\n" + text + ("" if text.endswith("\n") else "\n") + fence + "\n")
                else:
                    fence = "`" * max(1, run + 1)
                    parts.append(fence + text + fence)
            elif "math" in span.tags:
                parts.append(r"\(" + text + r"\)")
            elif "separator" in span.tags:
                parts.append("\n")
            elif "table" in span.tags:
                # Column separators/padding are generated layout, not words.
                parts.append(_literal(re.sub(r"[ \t]+", " ", text.replace("│", ";"))))
            elif span.url and text.strip() == span.url:
                parts.append("lien")
            else:
                parts.append(_literal(text))
        offset += len(span.text)
        if offset >= end:
            break
    return "".join(parts)


def project_selection(source, rendered, start, end, *, message_id, session_id,
                      region_key, revision, final=True):
    """Project one rendered range or refuse explicitly; never choose a match.

    Generated table padding may lie between mapped cells. It remains in the
    exact visible selection while source_start/end refer to the enclosing raw
    interval. A selection containing *only* generated decoration is refused.
    """
    if type(message_id) is not int or message_id < 1 or not isinstance(session_id, str) or not session_id:
        raise ValueError("Cette sélection n’est pas rattachée à une réponse archivée.")
    if len(source) > MAX_SOURCE:
        raise ValueError("Réponse trop longue pour une projection sûre ; copiez le passage affiché.")
    if not (type(start) is int and type(end) is int and 0 <= start < end <= len(rendered)):
        raise ValueError("La sélection n’est plus disponible dans cette réponse.")
    if end - start > MAX_SELECTION:
        raise ValueError("Sélection trop longue ; choisissez un passage de 8192 caractères maximum.")
    document, mapping = parse_mapped_text(source, final=final)
    if document.text != rendered or len(mapping) != len(rendered):
        raise ValueError("Le texte affiché a changé ; sélectionnez de nouveau le passage.")
    ranges = [item for item in mapping[start:end] if item[0] is not None]
    literal = any(char.strip() and left is not None and char in source[left:right]
                  for char, (left, right) in zip(rendered[start:end], mapping[start:end]))
    if not ranges or not literal:
        raise ValueError("Cette sélection contient seulement de l’espacement ou de la décoration.")
    left, right = min(item[0] for item in ranges), max(item[1] for item in ranges)
    if start == 0:
        left = 0
    if end == len(rendered):
        right = len(source)
    elif end >= len(rendered.rstrip()):
        # The visible final word may precede hidden closing emphasis/link/code
        # delimiters. Include their exact source tail so continuation recognizes
        # the end of the response, without inventing another visible word.
        right = len(source.rstrip())
    if not 0 <= left < right <= len(source):
        raise ValueError("Correspondance avec le texte original indisponible.")
    # Ordered scanner intervals, including recursive labels/cells, are a
    # monotonic projection. Reject any future renderer emitting reordered text.
    if any(current[0] < previous[0] for previous, current in zip(ranges, ranges[1:])):
        raise ValueError("Ce rendu ne permet pas une sélection source fiable.")
    return SelectionResult(message_id, session_id, region_key, revision, left, right,
                           source[left:right], rendered[start:end],
                           _speech_source(document, start, end), source_hash(source))
