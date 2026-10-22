"""Small local expression vocabulary; never infer a drawing for an unknown emoji.

Positions are Python Unicode offsets in the unmodified source. Context masks
are deliberately conservative for quoted literals, paths and technical prose.
The Markdown scanner supplies code/link/math protection separately.
"""
from bisect import bisect_left
from operator import itemgetter
import re


FAMILY_SYMBOLS = {
    "smile": (":)", ":-)", "🙂", "😊", "☺", "😀", "😃", "😄"),
    "laughter": (":D", ":-D", "😂", "🤣", "😆"),
    "affection": ("❤", "♥", "💕", "💖", "💗", "💘", "💞", "💓", "💝", "🥰", "😍", "😘", "🫶", "❤‍🔥", "❤‍🩹"),
    "sadness": (":(", ":-(", "😢", "😭", "🙁", "☹", "😞", "💔"),
    "anger": ("😠", "😡", "🤬", "😤"),
    "surprise": ("😮", "😲", "😯", "😳"),
    "thinking": ("🤔", "🧐"),
    "wink": (";)", ";-)", "😉"),
}
_FAMILIES = {symbol: family for family, symbols in FAMILY_SYMBOLS.items() for symbol in symbols}
_ASCII = re.compile(r":-?[)(D]|;-?\)")
_QUOTED = re.compile(r'"[^"\n]*(?:"|$)|«[^»]*(?:»|$)|“[^”]*(?:”|$)|‘[^’\n]*(?:’|$)|(?<!\w)\x27[^\x27\n]*(?:\x27|$)', re.M)
_PATH = re.compile(r"(?<!\w)(?:[a-zA-Z]:[\\/]|\\\\|~?/|\.{1,2}[\\/])[^\s<>\"']*")
_FILENAME = re.compile(r"(?<!\S)[^\s<>\"'/:\\]{1,240}\.(?:py|txt|json|exe|dll|md|png|jpe?g|svg|wav|mp3|sqlite3?)(?!\w)", re.I)
_TECHNICAL = re.compile(r"(?im)^.*(?:\b(?:regex|regexp|ascii|litt[ée]ral|[ée]motic[ôo]ne|expression r[ée]guli[èe]re)\b|^\s*(?:[\w.]+\s*=|(?:def|class|return|import|from|function|if|while|for|select)\b)).*$")
_CARD = re.compile(r"(?i)\b(?:as|roi|dame|valet|[2-9]|10)(?:\s+de)?\s*♥[\ufe0e\ufe0f]?")


def expression_family(symbol):
    if not isinstance(symbol, str):
        return None
    # Presentation selectors and supported skin variants do not define a new
    # expression. Preserve ZWJ: an unknown compound must not match its prefix.
    normalized = "".join(char for char in symbol if char not in "\ufe0e\ufe0f"
                         and not 0x1F3FB <= ord(char) <= 0x1F3FF)
    return _FAMILIES.get(normalized)


def merge_ranges(ranges):
    merged = []
    for start, end in sorted(ranges):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return tuple(merged)


def context_exclusions(text):
    return merge_ranges((match.start(), match.end()) for pattern in
                        (_QUOTED, _PATH, _FILENAME, _TECHNICAL, _CARD) for match in pattern.finditer(text))


def overlaps(start, end, ranges):
    """Logarithmic lookup in sorted, merged intervals prepared once per text."""
    position = bisect_left(ranges, end, key=itemgetter(0)) - 1
    return position >= 0 and ranges[position][1] > start


def ascii_expressions(text, excluded=()):
    excluded = merge_ranges(excluded)
    previous_end = -1
    for match in _ASCII.finditer(text):
        start, end = match.span()
        before = text[start - 1] if start else " "
        after = text[end] if end < len(text) else " "
        emoji_boundary = ord(before) >= 0x2600
        if (start and not before.isspace() and start != previous_end and not emoji_boundary
                or after.isalnum() or after in "/\\"
                or overlaps(start, end, excluded)):
            continue
        previous_end = end
        yield start, end, match.group()


def spoken_context_symbols(text):
    """A playing-card heart is a suit, not a silent expression."""
    return _CARD.sub(lambda match: re.sub(r"♥[\ufe0e\ufe0f]?", "cœur", match.group()), text)
