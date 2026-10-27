"""Bounded local visual transport; importing it opens no window or GPU context.

Only presentation snapshots cross this boundary. Microphone, audio playback,
models, history and the authoritative conversation state remain in JARVIS.
"""
import json
import math


PROTOCOL_VERSION = 1
FRAME_QUEUE_SIZE = 1
EVENT_QUEUE_SIZE = 16
MAX_PACKET_BYTES = 131072
ACTIONS = ("command", "studio", "microphone", "stop")
_FRAME_KEYS = frozenset(("time_s", "reactor", "points", "details", "color", "rms",
                         "reduced_motion", "detail_opacity", "orbit_phase", "core_scale",
                         "audio_bands", "orbit_blend", "surface_family", "surface_amount", "art"))


def _finite(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{label} doit être un nombre fini.")
    return value


def _bounded(value, depth=0):
    if depth > 6:
        raise ValueError("Paquet PRESENCE trop profondément imbriqué.")
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return _finite(value, "Valeur PRESENCE")
    if isinstance(value, str):
        if len(value) > 8192:
            raise ValueError("Texte PRESENCE trop long pour le canal visuel.")
        return value
    if isinstance(value, dict):
        if len(value) > 128 or any(not isinstance(key, str) or len(key) > 80 for key in value):
            raise ValueError("Dictionnaire PRESENCE invalide ou trop grand.")
        return {key: _bounded(item, depth+1) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        if len(value) > 512:
            raise ValueError("Liste PRESENCE trop longue.")
        return tuple(_bounded(item, depth+1) for item in value)
    raise ValueError("Le canal PRESENCE n'accepte que des données visuelles simples.")


def _path(value, maximum):
    if not isinstance(value, (tuple, list)) or not 2 <= len(value) <= maximum:
        raise ValueError("Contour PRESENCE invalide.")
    result = []
    for point in value:
        if not isinstance(point, (tuple, list)) or len(point) != 2:
            raise ValueError("Chaque point PRESENCE attend deux coordonnées.")
        result.append(tuple(_finite(item, "Coordonnée") for item in point))
    return tuple(result)


def validate_packet(packet):
    """Copy and validate a complete bounded snapshot, without GPU imports.

    ``pcm_at`` and ``expression_until`` share the host monotonic clock. They
    allow a child to clear expired audio/expression data if Tk stops sending.
    The original caption is preserved as Unicode; wrapping is presentation only.
    """
    if not isinstance(packet, dict):
        raise ValueError("Le paquet PRESENCE doit être un dictionnaire.")
    allowed = {"version", "seq", "frame", "art", "visible", "hud", "window", "pcm_at", "frame_at", "expression_until"}
    if set(packet)-allowed:
        raise ValueError("Champ de protocole PRESENCE inconnu.")
    if packet.get("version", PROTOCOL_VERSION) != PROTOCOL_VERSION:
        raise ValueError("Version de protocole PRESENCE incompatible.")
    seq = packet.get("seq")
    if isinstance(seq, bool) or not isinstance(seq, int) or not 0 <= seq <= 2**63-1:
        raise ValueError("Séquence PRESENCE invalide.")
    if not isinstance(packet.get("visible", True), bool):
        raise ValueError("La visibilité PRESENCE doit être booléenne.")
    frame = packet.get("frame")
    if not isinstance(frame, dict) or set(frame)-_FRAME_KEYS:
        raise ValueError("Image PRESENCE invalide ou paramètres inconnus.")
    if not {"time_s", "reactor", "points"}.issubset(frame):
        raise ValueError("Image PRESENCE incomplète.")
    frame = dict(frame)
    frame["points"] = _path(frame["points"], 97)
    details = frame.get("details", ())
    if not isinstance(details, (tuple, list)) or len(details) > 8:
        raise ValueError("Trop de détails PRESENCE.")
    frame["details"] = tuple(_path(path, 25) for path in details)
    for key in ("time_s", "reactor", "rms", "detail_opacity", "core_scale", "orbit_blend", "surface_amount"):
        if key in frame:
            _finite(frame[key], key)
    for key in ("color", "orbit_phase", "audio_bands"):
        if key in frame:
            values = frame[key]
            if not isinstance(values, (tuple, list)) or len(values) != 3:
                raise ValueError(f"{key} attend trois valeurs.")
            frame[key] = tuple(_finite(value, key) for value in values)
    result = {"version": PROTOCOL_VERSION, "seq": seq, "frame": frame,
              "visible": packet.get("visible", True)}
    for key in ("art", "hud", "window"):
        value = packet.get(key, {})
        if not isinstance(value, dict):
            raise ValueError(f"{key} attend un dictionnaire.")
        result[key] = _bounded(value)
    for key in ("pcm_at", "frame_at", "expression_until"):
        if packet.get(key) is not None:
            result[key] = _finite(packet[key], key)
    result["frame"] = _bounded(result["frame"])
    if len(json.dumps(result, ensure_ascii=False, allow_nan=False).encode("utf-8")) > MAX_PACKET_BYTES:
        raise ValueError("Le paquet visuel PRESENCE dépasse sa limite de taille.")
    return result
