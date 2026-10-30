"""Fresh, deterministic OS-clock observations and conservative French routing.

The local timezone is the operating system's choice, never a France default.
Future/past day requests describe a calendar DATE, not an invented wall-clock
instant with today's UTC offset. IANA conversions use Python's zoneinfo data;
there is no network access or timezone/model download in this module.
"""
from datetime import date, datetime, timedelta, timezone
import re
import unicodedata
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


KINDS = frozenset(("datetime", "time", "date", "weekday"))
MAX_DAYS = 36600
WEEKDAYS = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")
MONTHS = ("janvier", "février", "mars", "avril", "mai", "juin", "juillet",
          "août", "septembre", "octobre", "novembre", "décembre")
_ACCENTS = str.maketrans("àâäéèêëîïôöùûüç", "aaaeeeeiioouuuc")
_ZONE_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_+\-]*(?:/[A-Za-z0-9_+\-]+){0,3}\Z")
# Explicit spoken city names are aliases, not a default local timezone. Keep
# this first vocabulary small; arbitrary cities must use their exact IANA key.
_SPOKEN_ZONES = {
    "paris": "Europe/Paris", "londres": "Europe/London", "new york": "America/New_York",
    "montreal": "America/Toronto", "tokyo": "Asia/Tokyo", "sydney": "Australia/Sydney",
    "utc": "UTC",
}
_CANONICAL_ZONES = {value.casefold(): value for value in _SPOKEN_ZONES.values()}


def validate_datetime_arguments(arguments=None):
    if arguments is None:
        arguments = {}
    if not isinstance(arguments, dict) or set(arguments) - {"kind", "timezone", "days"}:
        raise ValueError("Arguments d'horloge attendus : kind, timezone et days uniquement.")
    kind = arguments.get("kind", "datetime")
    days = arguments.get("days", 0)
    zone = arguments.get("timezone")
    if not isinstance(kind, str) or kind not in KINDS:
        raise ValueError("Choisissez datetime, time, date ou weekday pour l'horloge.")
    if type(days) is not int or not -MAX_DAYS <= days <= MAX_DAYS:
        raise ValueError("Le décalage de date doit être un entier compris entre -36600 et 36600 jours.")
    if "timezone" in arguments and (not isinstance(zone, str) or not 1 <= len(zone) <= 128
                                    or not _ZONE_PATTERN.fullmatch(zone)):
        raise ValueError("Indiquez un fuseau IANA valide, par exemple Europe/Paris ou UTC.")
    if days and kind == "time":
        raise ValueError("Une heure future n'est pas déduite de l'horloge actuelle ; demandez une date.")
    return {"kind": kind, "days": days, **({"timezone": zone} if zone is not None else {})}


def _local_now(instant):
    # astimezone(None) delegates to the OS local-time/DST rules at this instant.
    # The resulting fixed offset must NOT be reused for a future day.
    return instant.astimezone()


def _observation(instant, arguments):
    zone_key = arguments.get("timezone")
    try:
        local = instant.astimezone(ZoneInfo(zone_key)) if zone_key else _local_now(instant)
        target = local.date() + timedelta(days=arguments["days"])
    except ZoneInfoNotFoundError as error:
        raise ValueError("Fuseau IANA introuvable. Vérifiez son nom et les données tzdata de l'installation.") from error
    except (OverflowError, OSError) as error:
        raise ValueError("Cette date est hors de la plage prise en charge par l'horloge locale.") from error
    return {
        "source": "system_clock", "captured_at_utc": instant.isoformat(),
        "local_now": local.isoformat(), "timezone": zone_key or "system_local",
        "timezone_name": local.tzname() or "", "utc_offset_seconds": int(local.utcoffset().total_seconds()),
        "target_date": target.isoformat(), "weekday_fr": WEEKDAYS[target.weekday()],
        "time_hms": local.strftime("%H:%M:%S"), "day_offset": arguments["days"], "kind": arguments["kind"],
    }


def get_datetime(arguments=None, *, clock=None):
    """Read once at execution; ``clock`` only provides deterministic test input.

    The injectable clock must yield an aware datetime. Production uses the OS
    clock in UTC and converts that same instant to the OS local zone or IANA.
    """
    arguments = validate_datetime_arguments(arguments)
    instant = (clock or (lambda: datetime.now(timezone.utc)))()
    if not isinstance(instant, datetime) or instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError("L'horloge doit fournir un instant datetime avec fuseau explicite.")
    return _observation(instant.astimezone(timezone.utc), arguments)


def verify_datetime_result(result):
    """Check internal consistency against the observed instant, never a new now.

    Freshness/cancellation are the task owner's responsibility: this does not
    turn an archived observation into the current system time.
    """
    if not isinstance(result, dict):
        return False
    try:
        string_fields = ("source", "captured_at_utc", "local_now", "timezone", "timezone_name",
                         "target_date", "weekday_fr", "time_hms", "kind")
        if (any(not isinstance(result.get(key), str) for key in string_fields)
                or type(result.get("utc_offset_seconds")) is not int
                or type(result.get("day_offset")) is not int):
            return False
        args = {"kind": result["kind"], "days": result["day_offset"]}
        if result["timezone"] != "system_local":
            args["timezone"] = result["timezone"]
        args = validate_datetime_arguments(args)
        instant = datetime.fromisoformat(result["captured_at_utc"])
        if instant.tzinfo is None or instant.utcoffset() != timedelta(0):
            return False
        return result == _observation(instant.astimezone(timezone.utc), args)
    except (KeyError, TypeError, ValueError, OverflowError):
        return False


def format_datetime(result):
    """French presentation of verified data; no LLM or archived-date guessing."""
    if not verify_datetime_result(result):
        raise ValueError("Le résultat d'horloge n'a pas pu être vérifié.")
    target = date.fromisoformat(result["target_date"])
    written_date = (f"{result['weekday_fr']} {target.day} {MONTHS[target.month - 1]} {target.year}")
    days, kind = result["day_offset"], result["kind"]
    suffix = "" if result["timezone"] == "system_local" else f" Fuseau : {result['timezone']}."
    if days:
        prefix = "Demain" if days == 1 else "Hier" if days == -1 else (
            f"Dans {days} jours" if days > 0 else f"Il y a {-days} jours")
        verb = "nous serons" if days > 0 else "nous étions"
        content = result["weekday_fr"] if kind == "weekday" else written_date
        return f"{prefix}, {verb} {content}.{suffix}"
    if kind == "weekday":
        return f"Nous sommes {result['weekday_fr']}.{suffix}"
    if kind == "date":
        return f"Nous sommes le {written_date}.{suffix}"
    hour, minute, _second = result["time_hms"].split(":")
    spoken_time = f"{int(hour)} h {minute}"
    if kind == "time":
        return f"Il est {spoken_time}.{suffix}"
    return f"Nous sommes le {written_date}, il est {spoken_time}.{suffix}"


def _spoken_day_count(value):
    if re.fullmatch(r"[0-9]{1,12}", value):
        return int(value)
    # Reuse the shipped French numeral vocabulary. Only 0..100 spoken days
    # belong to this narrow first router; arbitrary text remains conversation.
    from .speech_normalization import french_integer
    normalized = value.replace("-", " ")
    for count in range(101):
        spoken = french_integer(count).translate(_ACCENTS).replace("-", " ")
        if normalized == spoken:
            return count
    return None


def recognize_datetime_request(text):
    """Recognize complete unambiguous French questions, leaving all else alone.

    Quotations, code, reminders, compound requests and prose mentioning a date
    are not commands. Unknown explicit IANA keys remain an attempted clock
    request so execution reports the error instead of asking the LLM to guess.
    """
    if not isinstance(text, str) or not 1 <= len(text) <= 256:
        return None
    value = unicodedata.normalize("NFC", text).strip(" \t\u00a0\u202f")
    if any(unicodedata.category(char).startswith("C") for char in value):
        return None
    value = re.sub(r"[ \u00a0\u202f]+", " ", value)
    value = re.sub(r"[?!.]+$", "", value).rstrip(" ")
    value = re.sub(r"^jarvis(?:, ?| )", "", value, count=1, flags=re.IGNORECASE)
    # Preserve the case of an explicit IANA key while matching French accents.
    zone = None
    zone_match = re.search(r" (?:dans le fuseau(?: horaire)?|dans la zone|dans) ([A-Za-z][A-Za-z0-9_+\-/]*)$", value,
                           flags=re.IGNORECASE)
    if zone_match:
        zone = zone_match.group(1)
        zone = _CANONICAL_ZONES.get(zone.casefold(), zone)
        value = value[:zone_match.start()]
    else:
        city_match = re.search(r" (?:à|a) (.+)$", value, flags=re.IGNORECASE)
        if city_match:
            city = city_match.group(1).casefold().translate(_ACCENTS)
            zone = _SPOKEN_ZONES.get(city)
            if zone:
                value = value[:city_match.start()]
    value = value.casefold().translate(_ACCENTS).replace("’", "'").replace("‐", "-")
    value = value.replace("‑", "-")
    questions = {
        "quelle heure est-il": "time", "quelle heure est il": "time", "il est quelle heure": "time",
        "quelle est l'heure": "time", "peux-tu me donner l'heure": "time",
        "peux tu me donner l'heure": "time", "donne-moi l'heure": "time", "donne moi l'heure": "time",
        "quel jour sommes-nous": "date", "quel jour sommes nous": "date", "on est quel jour": "date",
        "quelle est la date d'aujourd'hui": "date", "quelle est la date aujourd'hui": "date",
        "quelle est la date": "date", "quelle date sommes-nous": "date", "quelle date sommes nous": "date",
        "quel est le jour d'aujourd'hui": "date", "quel est le jour aujourd'hui": "date",
        "quel jour de la semaine sommes-nous": "weekday", "quel jour de la semaine sommes nous": "weekday",
        "donne-moi la date et l'heure": "datetime", "donne moi la date et l'heure": "datetime",
        "quelle est la date et l'heure": "datetime",
    }
    if value in questions:
        return {"kind": questions[value], **({"timezone": zone} if zone is not None else {})}
    relative = re.fullmatch(r"(?:quelle date sera-t-on|quelle date serons-nous|quelle sera la date|"
                            r"quel jour sera-t-on|quel jour serons-nous|on sera quel jour|"
                            r"quel jour de la semaine serons-nous) "
                            r"(demain|apres-demain|dans ([a-z0-9 -]{1,48}) jours?)", value)
    if relative:
        days = (1 if relative[1] == "demain" else 2 if relative[1] == "apres-demain"
                else _spoken_day_count(relative[2]))
        kind = "weekday" if value.startswith("quel jour de la semaine") else "date"
        if days is not None:
            return {"kind": kind, "days": days, **({"timezone": zone} if zone is not None else {})}
    return None
