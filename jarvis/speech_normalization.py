"""Small, deterministic French pronunciation rules; never modify the archive.

Run after Markdown/math/emoji processing, only on the speech branch. Ambiguous
technical identifiers, invalid dates and unsupported magnitudes remain literal.
No language model, dictionary download, or work in an audio callback is needed.
"""
from datetime import date
import re


_SMALL = ("zéro un deux trois quatre cinq six sept huit neuf dix onze douze treize "
          "quatorze quinze seize").split()
_MONTHS = ("janvier février mars avril mai juin juillet août septembre octobre novembre décembre").split()
_ABBREVIATIONS = {"m.": "monsieur", "mme.": "madame", "mmes.": "mesdames",
                  "mlle.": "mademoiselle", "dr.": "docteur", "dre.": "docteure",
                  "pr.": "professeur", "rdv": "rendez-vous", "rdv.": "rendez-vous",
                  "c.-à-d.": "c’est-à-dire", "p. ex.": "par exemple", "etc.": "et cetera"}
# Only known technical initialisms. Ordinary words written in capitals retain
# their spelling instead of being guessed into an acronym.
_INITIALISMS = {"CPU": "cé pé u", "GPU": "gé pé u", "RAM": "ram", "VRAM": "vé ram",
               "USB": "u ès bé", "SSD": "ès ès dé", "IA": "i a", "LLM": "èl èl èm",
               "STT": "ès té té", "TTS": "té té ès", "API": "a pé i", "PDF": "pé dé èf",
               "HTML": "ache té èm èl", "SQL": "ès ku èl"}
_NUMBER = r"[+-]?(?:[0-9]{1,3}(?:[ \u00a0\u202f][0-9]{3})+|[0-9]+)(?:[.,][0-9]+)?"
_CURRENCY = re.compile(rf"(?:([$€£])\s*({_NUMBER})|({_NUMBER})\s*(€|\$|£|euros?|dollars?|livres? sterling))", re.I)
_DATE = re.compile(r"([0-9]{1,2})([/.-])([0-9]{1,2})\2([0-9]{4})")
_ISO_DATE = re.compile(r"([0-9]{4})-([0-9]{2})-([0-9]{2})")
_TIME = re.compile(r"([0-9]{1,2})\s*(h|:)\s*([0-9]{2})(?:\s*:\s*([0-9]{2}))?", re.I)
_HOUR = re.compile(r"([0-9]{1,2})\s*h", re.I)
_SCIENTIFIC = re.compile(r"([+-]?[0-9]+(?:[.,][0-9]+)?)[eE]([+-]?[0-9]+)")
_ABBR_PATTERN = "|".join(re.escape(word) for word in sorted(_ABBREVIATIONS, key=len, reverse=True))
_ABBR_PREFIXES = {word[:index + 1] for word in _ABBREVIATIONS for index, char in enumerate(word) if char == "."}
_SENTENCE_ABBR = re.compile(r"(?<!\w)(?:" + "|".join(re.escape(word) for word in sorted(_ABBR_PREFIXES, key=len, reverse=True)) + r")$", re.I)
# Priority matters: consume an entire technical token before looking for a
# number within it; consume a date/time/price before its individual digits.
_TOKENS = re.compile(
    r"(?P<isodate>(?<![\w])[0-9]{4}-[0-9]{2}-[0-9]{2}(?![\w]))"
    r"|(?P<date>(?<![\w])[0-9]{1,2}[/.-][0-9]{1,2}[/.-][0-9]{4}(?![\w]))"
    rf"|(?P<time>(?<![\w]){_TIME.pattern}(?![\w]))"
    rf"|(?P<hour>(?<![\w]){_HOUR.pattern}(?![\w]))"
    rf"|(?P<currency>(?<![\w]){_CURRENCY.pattern}(?![\w]))"
    rf"|(?P<scientific>(?<![\w]){_SCIENTIFIC.pattern}(?![\w]))"
    r"|(?P<technical>https?://\S+|[A-Za-zÀ-ÿ_]\w*[0-9][\w.+/-]*|[0-9]+(?:\.[0-9]+){2,}|[0-9]+(?:[-/][0-9]+)+)"
    rf"|(?P<abbreviation>(?<![\w])(?:{_ABBR_PATTERN})(?![\w]))"
    rf"|(?P<initialism>\b(?:{'|'.join(_INITIALISMS)})\b)"
    rf"|(?P<number>(?<![\w./]){_NUMBER}(?![\w/]|\.[0-9]))",
    re.I,
)


def _under_hundred(value):
    if value <= 16:
        return _SMALL[value]
    if value < 20:
        return "dix-" + _SMALL[value - 10]
    if value < 70:
        tens = ("", "", "vingt", "trente", "quarante", "cinquante", "soixante")[value // 10]
        unit = value % 10
        return tens + (" et un" if unit == 1 else "-" + _SMALL[unit] if unit else "")
    if value < 80:
        return "soixante" + (" et onze" if value == 71 else "-" + _under_hundred(value - 60))
    return "quatre-vingts" if value == 80 else "quatre-vingt-" + _under_hundred(value - 80)


def french_integer(value):
    """Cardinals through 999,999,999,999; keep larger inputs instead of guessing."""
    if abs(value) > 999_999_999_999:
        return str(value)
    if value < 0:
        return "moins " + french_integer(-value)
    if value < 100:
        return _under_hundred(value)
    if value < 1000:
        hundreds, rest = divmod(value, 100)
        prefix = "cent" if hundreds == 1 else _SMALL[hundreds] + " cent"
        return prefix + (" " + french_integer(rest) if rest else "s" if hundreds > 1 else "")
    for divisor, name in ((1_000_000_000, "milliard"), (1_000_000, "million"), (1000, "mille")):
        if value >= divisor:
            count, rest = divmod(value, divisor)
            # Cent/vingt lose their plural before the numeral 'mille'.
            count_text = french_integer(count)
            if divisor == 1000 and count_text.endswith(("cents", "vingts")):
                count_text = count_text[:-1]
            prefix = "mille" if divisor == 1000 and count == 1 else count_text + " " + name
            if divisor != 1000 and count > 1:
                prefix += "s"
            return prefix + (" " + french_integer(rest) if rest else "")


def _parts(number):
    compact = re.sub(r"[ \u00a0\u202f]", "", number)
    sign = "moins " if compact.startswith("-") else "plus " if compact.startswith("+") else ""
    integer, *fraction = re.split(r"[.,]", compact.lstrip("+-"), maxsplit=1)
    return sign, integer, fraction[0] if fraction else ""


def _spoken_number(number):
    sign, integer, fraction = _parts(number)
    if len(integer) > 12:
        return number
    # A phone number or explicit zero-padded identifier is not a cardinal.
    whole = " ".join(_SMALL[int(digit)] for digit in integer) if len(integer) > 1 and integer[0] == "0" else french_integer(int(integer))
    return sign + whole + (" virgule " + " ".join(_SMALL[int(digit)] for digit in fraction) if fraction else "")


def _spoken_currency(token):
    match = _CURRENCY.fullmatch(token)
    currency, amount = (match[1], match[2]) if match[1] else (match[4], match[3])
    sign, integer, fraction = _parts(amount)
    if len(integer) > 12:
        return token
    unit = "euro" if currency.lower().startswith("euro") or currency == "€" else "dollar" if currency.lower().startswith("dollar") or currency == "$" else "livre sterling"
    plural = "livres sterling" if unit == "livre sterling" else unit + "s"
    unit = unit if int(integer) == 1 else plural
    if len(fraction) == 2 and int(integer) <= 999_999_999_999:
        amount_words = "une" if unit == "livre sterling" and int(integer) == 1 else french_integer(int(integer))
        result = sign + amount_words + " " + unit
        if int(fraction):
            result += " et " + french_integer(int(fraction)) + (" centime" if int(fraction) == 1 else " centimes")
        return result
    amount_words = _spoken_number(amount)
    if unit == "livre sterling" and int(integer) == 1:
        amount_words = re.sub(r"\bun\b", "une", amount_words, count=1)
    return amount_words + " " + unit


def normalize_french_speech(text):
    """Pronounce unambiguous French values after the common rich-text scanner.

    Explicit slash dates are day/month/year. Invalid dates/times, version-like
    dotted sequences and embedded identifiers are deliberately left literal.
    Decimal fractional digits are spoken individually, preserving zeros. The
    transformation is idempotent and leaves the source/display branch alone.
    """
    def convert(match):
        token, kind = match.group(), match.lastgroup
        if kind == "technical":
            return token
        if kind == "scientific":
            parsed = _SCIENTIFIC.fullmatch(token)
            return _spoken_number(parsed[1]) + " fois dix puissance " + _spoken_number(parsed[2])
        if kind in {"date", "isodate"}:
            parsed = (_DATE if kind == "date" else _ISO_DATE).fullmatch(token)
            if parsed is None:
                return token
            day, month, year = ((int(parsed[1]), int(parsed[3]), int(parsed[4])) if kind == "date"
                                else (int(parsed[3]), int(parsed[2]), int(parsed[1])))
            try:
                date(year, month, day)
            except ValueError:
                return token
            return ("premier" if day == 1 else french_integer(day)) + " " + _MONTHS[month - 1] + " " + french_integer(year)
        if kind in {"time", "hour"}:
            parsed = (_TIME if kind == "time" else _HOUR).fullmatch(token)
            hour = int(parsed[1])
            minute = int(parsed[3]) if kind == "time" else 0
            second = int(parsed[4]) if kind == "time" and parsed[4] is not None else 0
            if hour > 23 or minute > 59 or second > 59:
                return token
            result = ("une" if hour == 1 else french_integer(hour)) + (" heure" if hour == 1 else " heures")
            if minute:
                result += " " + french_integer(minute)
            if second:
                result += " et " + french_integer(second) + (" seconde" if second == 1 else " secondes")
            return result
        if kind == "currency":
            return _spoken_currency(token)
        if kind == "abbreviation":
            if token == "m.":
                # A metre abbreviation is not the courtesy title 'M.'.
                previous = re.search(r"([0-9]+)\s*$", match.string[:match.start()])
                return ("mètre." if int(previous[1]) == 1 else "mètres.") if previous and len(previous[1]) <= 12 else token
            spoken = _ABBREVIATIONS[token.lower()]
            # 'etc.' may really finish a sentence. Preserve that prosodic stop
            # before an uppercase following sentence or at the end of speech.
            suffix = match.string[match.end():].lstrip()
            if token.lower() == "etc." and (not suffix or suffix[0].isupper()):
                spoken += "."
            return spoken
        if kind == "initialism":
            # Only uppercase tokens: 'ram' in prose is not an initialism.
            return _INITIALISMS.get(token, token)
        prefix = match.string[max(0, match.start() - 24):match.start()]
        if re.search(r"(?:version|python|qwen|v)\s*$", prefix, re.I) and "." in token:
            return token
        return _spoken_number(token)

    return _TOKENS.sub(convert, str(text))


def sentence_boundary(text, position, *, final=False):
    """Whether a punctuation index may end speech, even in a partial stream."""
    char = text[position]
    if char == ".":
        before = text[:position + 1]
        if _SENTENCE_ABBR.search(before):
            return False
        if re.search(r"(?<!\w)[A-ZÀ-Ý]\.$", before):
            return False
        if position and text[position - 1].isdigit():
            if position + 1 == len(text) and not final or position + 1 < len(text) and text[position + 1].isdigit():
                return False
    if char in ":;" and position + 1 == len(text) and not final:
        return False
    return True


def speech_atom_spans(text):
    """Keep multiword amounts/times in one streaming pronunciation segment."""
    return tuple((match.start(), match.end()) for match in _TOKENS.finditer(text)
                 if match.lastgroup in {"currency", "time", "date", "isodate", "number"})


def expand_dollar_symbols(text):
    """Disambiguate complete dollar amounts while retaining digit strings.

    The rich-text scanner uses this before optional pronunciation rules so
    grouping spaces or a minus sign cannot split one amount into two values.
    """
    text = re.sub(rf"\$\s*({_NUMBER})", r"\1 dollars", text)
    return re.sub(rf"({_NUMBER})\s*\$", r"\1 dollars", text)
