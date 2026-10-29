"""Conservative whole-utterance commands from an accepted microphone turn.

This parser cannot identify acoustic echo. The caller must retain the existing
speaker mute/settling guard and only confirm a current VAD/STT user turn. Text
from the editor, history, a model response or a playback callback is never an
eligible command source. Unknown phrases stay ordinary conversational text.
"""
import re
import unicodedata
from itertools import islice


_PHRASES = {
    "stop": "stop",
    "arrete": "stop",
    "repete": "repeat",
    "repete la reponse": "repeat",
    "reprends": "resume",
    "reprends la lecture": "resume",
    "continue": "continue",
    "continue la reponse": "continue",
    "plus lentement": "slower",
    "parle moins vite": "slower",
    "ralentis": "slower",
    "developpe ce passage": "expand",
}
COMMANDS = frozenset(_PHRASES.values())
_FRENCH_ACCENTS = str.maketrans("àâäéèêëîïôöùûüç", "aaaeeeeiioouuuc")


def recognize_command(text, *, source="microphone", confirmed_user_turn=False):
    """Return an action name or None; never remove quoted/dictated wrappers.

    Only the allowlisted complete imperative, optionally addressed to JARVIS,
    is accepted. A question mark deliberately leaves an ambiguous question in
    the conversation. NFC/NFD French accents are equivalent for matching only;
    the caller's original text is never changed.
    """
    if source != "microphone" or confirmed_user_turn is not True:
        return None
    if not isinstance(text, str) or not 0 < len(text) <= 120:
        return None
    value = unicodedata.normalize("NFC", text).strip(" \t\r\n\u00a0\u202f")
    if any(unicodedata.category(char).startswith("C") and char != "\t"
           for char in value):
        return None
    value = re.sub(r"[ \t\u00a0\u202f]+", " ", value).casefold()
    # Do not strip quotes, Markdown, colons, question marks or arbitrary symbols.
    value = re.sub(r"[.!]+$", "", value).rstrip(" ")
    value = re.sub(r"^jarvis(?:, ?| )", "", value, count=1)
    value = value.translate(_FRENCH_ACCENTS)
    return _PHRASES.get(value)


def command_echo(text, spoken_texts):
    """Conservatively flag words also present in recently played output.

    Call only for an already recognized command during the playback/settling
    window. This is a textual echo guard, not acoustic echo cancellation: a
    deliberate matching user command can also be refused during that window.
    The caller can combine eight PCM-played segments and eight submitted ones
    when callbacks are pending; examine at most sixteen segments and 8192
    characters per segment to bound work on malformed input.
    """
    if not isinstance(text, str) or not 0 < len(text) <= 120:
        return False

    def words(value):
        value = unicodedata.normalize("NFC", value).casefold().translate(_FRENCH_ACCENTS)
        return re.findall(r"[^\W\d_]+", value)

    candidate = words(text)
    if candidate[:1] == ["jarvis"]:
        candidate = candidate[1:]
    if not candidate or spoken_texts is None:
        return False
    # A single segment is convenient for callers and must not iterate letters.
    segments = (spoken_texts,) if isinstance(spoken_texts, str) else spoken_texts
    for segment in islice(segments, 16):
        if not isinstance(segment, str):
            continue
        spoken = words(segment[:8192])
        size = len(candidate)
        if any(spoken[start:start + size] == candidate
               for start in range(len(spoken) - size + 1)):
            return True
    return False
