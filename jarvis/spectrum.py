"""Conservative lexical tone estimate, separate from operational status/permissions."""
import math
import re
import time
import unicodedata
from dataclasses import dataclass

from .richtext import parse_text

CYAN = "#69edf5"
OPERATIONAL = {
    "allowed": {"color": "#70dca0", "label": "AUTORISÉ"},
    "info": {"color": "#65b6ff", "label": "INFORMATION"},
    "caution": {"color": "#f4d56a", "label": "VIGILANCE"},
    "confirm": {"color": "#ffb575", "label": "CONFIRMATION"},
    "error": {"color": "#ff9c9c", "label": "ARRÊT / ERREUR"},
    "inactive": {"color": "#a6b0be", "label": "INACTIF"},
}

# Small local lexicons: an estimate of the text, never an operational status.
# Expression mode requires an affirmed feeling; uncertain language stays cyan.
TONES = {
    "surprise": ("#a9e8ff", {"surprise", "surpris", "surprisee", "etonne", "etonnee", "etonnement", "stupefait", "stupefaite"}),
    "joie": ("#ffe28a", {"joie", "plaisir", "heureux", "heureuse", "ravi", "ravie", "content", "contente", "joyeux", "joyeuse"}),
    "colère": ("#ff717a", {"rage", "colere", "furieux", "furieuse", "enerve", "enervee", "enrage", "exaspere", "exasperee"}),
    "désir": ("#ffb16b", {"ambition", "desir", "ambitieux", "convoitise", "avarice", "envie", "desire"}),
    "peur": ("#f4d56a", {"peur", "angoisse", "inquiet", "inquiete", "crainte", "crains", "panique", "effraye", "effrayee"}),
    "volonté": ("#70dca0", {"volonte", "determination", "perseverance", "resolu", "resolue", "determine", "determinee"}),
    "espoir": ("#73bfff", {"espoir", "confiance", "optimisme", "esperance", "optimiste", "confiant", "confiante", "espere"}),
    "compassion": ("#b4a0ff", {"compassion", "empathie", "sollicitude", "bienveillance", "compatis"}),
    "attachement": ("#f6a0d7", {"amour", "affection", "tendresse", "attachement", "aime", "adore"}),
    "renouveau": ("#f3f8ff", {"renaissance", "renouveau", "vitalite", "vie", "renais"}),
    "deuil": ("#526a74", {"mort", "deuil", "deces", "funerailles", "endeuille", "endeuillee", "chagrin", "triste", "tristesse"}),
    "apaisement": ("#8fd9ca", {"calme", "serein", "sereine", "serenite", "apaisement", "apaise", "apaisee", "tranquille", "soulage", "soulagee", "soulagement"}),
}


def normalized(word):
    return ''.join(c for c in unicodedata.normalize("NFD", word.casefold())
                   if unicodedata.category(c) != "Mn").replace("œ", "oe").replace("æ", "ae")


@dataclass(frozen=True)
class Tone:
    name: str = "neutralité"
    color: str = CYAN
    words: tuple = ()
    confidence: float = 0.0


@dataclass(frozen=True)
class ToneEvent:
    """One raw source passage, with absolute Python string offsets."""
    start: int
    end: int
    text: str
    tone: Tone


@dataclass(frozen=True)
class FieldEvent:
    """A passage's local estimate and the stable response mood at its arrival."""
    start: int
    end: int
    text: str
    tone: Tone
    dominant: Tone


_MODES = {"thematic", "expression", "neutral"}
_WORD = re.compile(r"[^\W\d_](?:[^\W\d_]|[\u0300-\u036f])*", re.UNICODE)
_NEGATIONS = {"ne", "n", "pas", "sans", "aucun", "aucune", "ni", "jamais", "rien", "nullement", "guere"}
_MODIFIERS = (
    "vraiment tres tellement si profondement sincerement actuellement encore deja "
    "completement absolument totalement assez un une de du des la le les l en "
    "plein pleine rempli remplie beaucoup immense grande grand forte fort mon ma mes "
    "desormais maintenant enfin"
).split()
_CUES = set().union(*(words for _, words in TONES.values()))
_CONTINUATION = set(_MODIFIERS) | _CUES | {"et", "ou", "aussi"}
_FRAME = re.compile(
    r"(?:\bje (?:suis|ressens|eprouve|garde)|\bje me sens|\bj (?:ai|eprouve)|"
    r"\bnous (?:sommes|ressentons|eprouvons|gardons)|\bnous nous sentons) "
    r"(?:(?:" + "|".join(sorted(_CONTINUATION)) + r") ){0,9}$"
)
_POSSESSIVE = re.compile(r"\b(?:ma|mon|notre) (?:(?:vraie|vrai|profonde|profond|grande|grand) ){0,2}$")
_DIRECT = {"rage", "desire", "crains", "espere", "compatis", "aime", "adore", "renais", "angoisse"}
_UNCERTAIN = re.compile(r"\b(?:si (?=je\b|j['’]|nous\b|tu\b|vous\b|il\b|elle\b|on\b)|peut[- ‐‑]etre|peutetre|probablement|pas seulement|pourrais|pourrions|serais|serions|aurais|aurions|hypothese|supposons)\b")
_CLAUSE = re.compile(r"[,;:]|\b(?:mais|cependant|pourtant|toutefois)\b|\bet (?=(?:je|j|nous)\b)", re.I)
_PHRASES = {
    "apaisement": (("tout", "va", "bien"), ("ca", "va", "aller")),
    "compassion": (("de", "tout", "coeur"),),
}
_INTENSIFIERS = {"vraiment", "tres", "tellement", "profondement", "sincerement",
                 "completement", "absolument", "totalement", "immense"}
_PIVOT = re.compile(
    r"(?:^|[.!?;:]\s*)(?:mais\s+)?(?:desormais|maintenant|enfin)\b|"
    r"\b(?:je suis|je me sens|nous sommes|nous nous sentons)\s+(?:desormais|maintenant|enfin)\b"
)


def _mask(source, start, end):
    source[start:end] = " " * (end - start)


def _analysis_source(text):
    """Mask opaque syntax without changing a single source position."""
    visible = list(text)
    opaque = []
    for event in parse_text(text).events:
        if event.kind in {"code", "math"}:
            opaque.append((event.start, event.end))
            _mask(visible, event.start, event.end)
        elif event.kind == "link":
            # The label is natural language; the destination is never evidence.
            raw = text[event.start:event.end]
            if raw.startswith("[") and "](" in raw:
                destination = event.start + raw.rfind("](")
                _mask(visible, destination, event.end)
                _mask(visible, event.start, event.start + 1)
            else:
                _mask(visible, event.start, event.end)
        elif event.kind == "markup":
            _mask(visible, event.start, event.end)
    # Raw HTML remains inert text in the renderer and contributes no feeling.
    html = re.compile(r"<!--[\s\S]*?(?:-->|$)|<([A-Za-z][\w:-]*)\b[^>]*>[\s\S]*?</\1\s*>|</?[A-Za-z][^>]*>|<![^>]*>", re.I)
    void_tags = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
    for match in html.finditer(text):
        left, right = match.span()
        raw = match.group()
        opening = re.fullmatch(r"<([A-Za-z][\w:-]*)\b[^>]*>", raw)
        if opening and opening[1].lower() not in void_tags and not raw.endswith("/>"):
            right = len(text)  # An unclosed HTML element stays opaque.
        opaque.append((left, right))
        _mask(visible, left, right)
    # Reported speech, definitions in quotes and Markdown block quotes are not
    # an assertion of the narrator's own feeling. Apostrophes remain readable.
    for pattern in (r'«[^»]*(?:»|$)', r'“[^”]*(?:”|$)', r'"[^"\n]*(?:"|$)',
                    r"(?<!\w)'[^'\n]+'(?!\w)", r"(?m)^ {0,3}>[^\n]*"):
        for match in re.finditer(pattern, text):
            _mask(visible, *match.span())
    return "".join(visible), opaque


def _negated(words, index):
    before = words[max(0, index - 7):index]
    # A new asserted subject starts a new scope, including after "et".
    subjects = [i for i, word in enumerate(before) if word in {"je", "j", "nous"}]
    if subjects:
        before = before[subjects[-1]:]
    after = words[index + 1:index + 3]
    following_negation = bool(after and (after[0] in {"ne", "n", "pas", "jamais", "guere"} or
                              after[0] in {"vraiment", "absolument"} and "pas" in after))
    return bool(_NEGATIONS.intersection(before) or following_negation)


def _expressed(words, index):
    cue = words[index]
    # These common nouns usually describe a fact, rather than an expression.
    if cue in {"vie", "mort"}:
        return False
    if cue in {"joie", "plaisir"} and words[:index] in (["avec"], ["quelle"]):
        return True
    prefix = " ".join(words[max(0, index - 12):index]) + " "
    if _FRAME.search(prefix) or _POSSESSIVE.search(prefix):
        return True
    if cue in _DIRECT:
        return bool(re.search(r"\b(?:je|j|nous) (?:(?:t|te|vous|l|le|la|les|m|me) )?$", prefix))
    # "Cela m'angoisse" and "ça m'énerve" express a reaction directly.
    return cue in {"angoisse", "enerve", "exaspere"} and bool(
        re.search(r"\b(?:cela|ca) m $", prefix))


def _intensified(words, index):
    modifiers = []
    for word in reversed(words[max(0, index - 3):index]):
        if word not in _MODIFIERS:
            break
        modifiers.append(word)
    return bool(_INTENSIFIERS.intersection(modifiers))


def _evidence(visible, mode):
    """Reuse the lexical estimator's scopes, retaining source offsets for words."""
    if mode == "neutral" or _UNCERTAIN.search(normalized(visible)) or mode == "expression" and "?" in visible:
        return ()
    evidence = []
    prior_expression = False
    previous = 0
    boundaries = [(match.start(), match.end()) for match in _CLAUSE.finditer(visible)]
    boundaries.append((len(visible), len(visible)))
    for end, following in boundaries:
        clause = visible[previous:end]
        tokens = tuple(_WORD.finditer(clause))
        words = [normalized(token.group()) for token in tokens]
        continuation = prior_expression and bool(words) and set(words) <= _CONTINUATION
        for index, word in enumerate(words):
            if word not in _CUES or _negated(words, index):
                continue
            if mode == "expression" and not (continuation or _expressed(words, index)):
                continue
            for name, (_, lexicon) in TONES.items():
                if word in lexicon:
                    token = tokens[index]
                    strong = _intensified(words, index)
                    evidence.append((name, word, previous + token.start(), previous + token.end(), strong))
                    prior_expression = True
        # A small set of common reassuring/supportive expressions supplements
        # the same conservative word estimator; quoted/negated mentions remain
        # masked. Tokens preserve accents, Markdown gaps and Python offsets.
        for name, phrases in _PHRASES.items():
            for phrase in phrases:
                for index in range(len(words) - len(phrase) + 1):
                    if tuple(words[index:index + len(phrase)]) != phrase or _negated(words, index):
                        continue
                    if any(not clause[tokens[i].end():tokens[i + 1].start()].isspace()
                           for i in range(index, index + len(phrase) - 1)):
                        continue
                    if {"expression", "phrase", "mot", "signifie", "exemple"}.intersection(words):
                        continue
                    if "?" in visible or _UNCERTAIN.search(normalized(visible)):
                        continue
                    if name == "compassion":
                        context = " ".join(words[max(0, index - 7):index + len(phrase) + 4])
                        if not re.search(r"\b(?:avec|pour) (?:toi|vous)\b|\b(?:compatis|soutiens|soutenons|accompagne|accompagnons)\b", context):
                            continue
                    left, right = tokens[index].start(), tokens[index + len(phrase) - 1].end()
                    strong = _intensified(words, index)
                    evidence.append((name, " ".join(phrase), previous + left, previous + right, strong))
                    prior_expression = True
        previous = following
    return tuple(evidence)


def _classify(visible, mode):
    evidence = _evidence(visible, mode)
    hits = {name: set() for name in TONES}
    for name, word, *_ in evidence:
        hits[name].add(word)
    active = [(name, words) for name, words in hits.items() if words]
    # Conflicting affirmed categories stay cyan, even with repeated synonyms.
    if len(active) != 1:
        return Tone()
    name, words = active[0]
    confidence = 1.0 if any(hit[4] for hit in evidence) else 0.85
    return Tone(name, TONES[name][0], tuple(sorted(words)), confidence)


def analyze_passages(text, mode="expression", start=0):
    """Estimate each sentence/paragraph locally, retaining raw Markdown/emoji.

    Neutral passages are explicit so a following factual sentence returns cyan.
    No model, network call, or clock is involved in this analysis.
    """
    if mode not in _MODES:
        raise ValueError("unknown spectrum mode: " + str(mode))
    if not text:
        return ()
    visible, opaque = _analysis_source(text)
    boundaries = {0, len(text)}
    for left, right in opaque:
        boundaries.update((left, right))
    for match in re.finditer(r"[.!?]+[*_`\\]*[\"”»')\]]*\s*|\n+", text):
        position = match.start()
        if visible[position] != text[position]:
            continue
        if text[position] == "." and position and text[position - 1].isdigit() and position + 1 < len(text) and text[position + 1].isdigit():
            continue
        boundaries.add(match.end())
    result = []
    previous = 0
    for end in sorted(boundaries - {0}):
        raw = text[previous:end]
        if raw.isspace() and result:
            last = result.pop()
            result.append(ToneEvent(last.start, start + end, last.text + raw, last.tone))
        else:
            result.append(ToneEvent(start + previous, start + end, raw, _classify(visible[previous:end], mode)))
        previous = end
    return tuple(result)


class ToneAnalyzer:
    def __init__(self, mode="expression", hold_seconds=0):
        if mode not in _MODES:
            raise ValueError("unknown spectrum mode: " + str(mode))
        self.mode = mode
        self.current = Tone()
        self.changed_at = float('-inf')
        # Retained for callers/settings from the former clock-based estimator.
        # Passage changes, including a return to cyan, are always immediate.
        self.hold_seconds = hold_seconds
        self.last_text = None

    def update(self, text, now=None):
        now = time.monotonic() if now is None else now
        passages = analyze_passages(text, mode=self.mode)
        chosen = passages[-1].tone if passages else Tone()
        if chosen.name != self.current.name:
            self.changed_at = now
        self.current = chosen
        self.last_text = text
        return chosen


class MoodTracker:
    """Keep a response mood stable while retaining each passage's own nuance.

    Feed each newly classified source passage once, before audio/rendering.
    Reset at a response boundary or interruption. State is constant in size:
    no response text, audio samples or event history is retained. This is a
    lexical presentation estimate, not a measurement of anyone's emotions.
    """

    def __init__(self, mode="thematic"):
        if mode not in _MODES:
            raise ValueError("unknown spectrum mode: " + str(mode))
        self.mode = mode
        self.reset()

    def reset(self):
        self.dominant = Tone()
        self._candidate = None
        self._candidate_count = 0

    def feed(self, events):
        result = []
        for event in events:
            tone = Tone() if self.mode == "neutral" else event.tone
            reliable = tone.name in TONES and tone.confidence >= 0.65
            if not reliable:
                self._candidate = None
                self._candidate_count = 0
            elif self.dominant.name == "neutralité" or tone.name == self.dominant.name:
                self.dominant = tone
                self._candidate = None
                self._candidate_count = 0
            else:
                visible, _ = _analysis_source(event.text)
                folded = normalized(visible).strip()
                explicit = bool(_PIVOT.search(folded)) and "?" not in visible and not _UNCERTAIN.search(folded)
                if self._candidate == tone.name:
                    self._candidate_count += 1
                else:
                    self._candidate, self._candidate_count = tone.name, 1
                if explicit or self._candidate_count >= 2:
                    self.dominant = tone
                    self._candidate = None
                    self._candidate_count = 0
            if self.mode == "neutral":
                self.dominant = Tone()
            result.append(FieldEvent(event.start, event.end, event.text, tone, self.dominant))
        return tuple(result)


def emotional_spans(text, tone, mode="thematic"):
    """Return contextually affirmed words/phrases in this local tone only.

    Source Python offsets include combining accents. Opaque syntax, quotes,
    negations and ambiguous competing categories never supply highlights.
    No passage reclassification, model or timing calculation is performed.
    """
    if mode not in _MODES:
        raise ValueError("unknown spectrum mode: " + str(mode))
    if mode == "neutral" or tone.name not in TONES:
        return ()
    visible, _ = _analysis_source(text)
    evidence = _evidence(visible, mode)
    if {hit[0] for hit in evidence} != {tone.name}:
        return ()
    spans = sorted({(hit[2], hit[3]) for hit in evidence if hit[0] == tone.name})
    return tuple(spans)


def keyword_spans(text, words):
    wanted = set(words)
    return [(match.start(), match.end()) for match in _WORD.finditer(text)
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
