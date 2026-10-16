"""Conservative lexical tone estimate, separate from operational status/permissions."""
import math
import re
import time
import unicodedata
from dataclasses import dataclass

CYAN = "#69edf5"
OPERATIONAL = {
    "allowed": {"color": "#70dca0", "label": "AUTORISÉ"},
    "info": {"color": "#65b6ff", "label": "INFORMATION"},
    "caution": {"color": "#f4d56a", "label": "VIGILANCE"},
    "confirm": {"color": "#ffb575", "label": "CONFIRMATION"},
    "error": {"color": "#ff9c9c", "label": "ARRÊT / ERREUR"},
    "inactive": {"color": "#a6b0be", "label": "INACTIF"},
}

# Intentionally narrow: two distinct cues, a clear majority and temporal inertia.
# No claim of reading human emotion; ambiguous language stays neutral.
TONES = {
    "colère": ("#ff717a", {"rage", "colere", "furieux", "furieuse", "enerve", "enervee"}),
    "désir": ("#ffb16b", {"ambition", "desir", "ambitieux", "convoitise", "avarice"}),
    "peur": ("#f4d56a", {"peur", "angoisse", "inquiet", "inquiete", "crainte"}),
    "volonté": ("#70dca0", {"volonte", "determination", "perseverance", "resolu", "determine"}),
    "espoir": ("#73bfff", {"espoir", "confiance", "optimisme", "esperance"}),
    "compassion": ("#b4a0ff", {"compassion", "empathie", "sollicitude", "bienveillance"}),
    "attachement": ("#f6a0d7", {"amour", "affection", "tendresse", "attachement"}),
    "renouveau": ("#f3f8ff", {"renaissance", "renouveau", "vitalite", "vie"}),
    "deuil": ("#526a74", {"mort", "deuil", "deces", "funerailles"}),
}


def normalized(word):
    return ''.join(c for c in unicodedata.normalize("NFD", word.casefold())
                   if unicodedata.category(c) != "Mn")


@dataclass(frozen=True)
class Tone:
    name: str = "neutralité"
    color: str = CYAN
    words: tuple = ()
    confidence: float = 0.0


class ToneAnalyzer:
    def __init__(self, hold_seconds=3):
        self.current = Tone()
        self.changed_at = float('-inf')
        self.hold_seconds = hold_seconds
        self.last_text = None

    def update(self, text, now=None):
        now = time.monotonic() if now is None else now
        sequence = [normalized(word) for word in re.findall(r"[^\W\d_]+", text, flags=re.UNICODE)]
        negations = {"pas", "sans", "aucun", "aucune", "ni", "jamais"}
        tokens = {word for i, word in enumerate(sequence)
                  if not negations.intersection(sequence[max(0, i - 3):i])}
        hits = [(name, color, words & tokens) for name, (color, words) in TONES.items()]
        hits.sort(key=lambda item: len(item[2]), reverse=True)
        name, color, matched = hits[0]
        total = sum(len(item[2]) for item in hits)
        confidence = len(matched) / total if total else 0.0
        chosen = Tone(name, color, tuple(sorted(matched)), confidence) if len(matched) >= 2 and confidence >= 0.67 else Tone()
        if chosen.name != self.current.name and now - self.changed_at < self.hold_seconds:
            return self.current
        if chosen.name != self.current.name:
            self.changed_at = now
        self.current = chosen
        self.last_text = text
        return chosen


def keyword_spans(text, words):
    wanted = set(words)
    return [(match.start(), match.end()) for match in re.finditer(r"[^\W\d_]+", text, flags=re.UNICODE)
            if normalized(match.group()) in wanted]


def caption_group(text, fraction):
    """PCM-duration approximation, in groups of three words; never a timing claim."""
    words = str(text).split()
    try:
        value = float(fraction)
    except (ValueError, TypeError):
        value = 0
    fraction = max(0.0, min(1.0, value)) if math.isfinite(value) else 0
    if not words or fraction <= 0:
        return ""
    spoken = min(len(words), max(1, math.ceil(fraction * len(words))))
    visible = min(len(words), 3 * math.ceil(spoken / 3))
    # Keep at most four groups on screen. The full reply remains in SQLite/chat.
    return ' '.join(words[max(0, visible - 12):visible])
