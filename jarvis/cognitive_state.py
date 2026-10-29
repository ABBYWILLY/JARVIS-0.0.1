"""Small observable activity contract, owned and fed by the conversation owner.

This module observes application events; it does not infer a model's thoughts,
read SQLite, query a device, or create a timer. Only bounded, non-content
diagnostics are retained. Views receive copies and never determine activity.
"""
from collections import deque
from dataclasses import asdict, dataclass
import math
import re
import time

from .metrics import generation_metrics


ACTIVITIES = ("speaking", "synthesis", "generating", "waiting", "context",
              "audio_loading", "transcribing", "user_speaking", "listening")
TERMINALS = frozenset({"error", "interrupted", "cancelled"})
LABELS = {
    "idle": "Repos", "listening": "J’écoute", "user_speaking": "Voix détectée",
    "transcribing": "Transcription en cours", "context": "Préparation du contexte",
    "waiting": "Attente d’Ollama", "generating": "Génération locale",
    "synthesis": "Préparation de la voix", "speaking": "JARVIS parle",
    "audio_loading": "Chargement audio local",
    "interrupted": "Réponse interrompue", "cancelled": "Réponse annulée",
    "error": "Erreur · diagnostic disponible",
}
_POLICIES = {"fast": "Rapide", "deep": "Approfondi", "creative": "Créatif",
             "manual": "Manuel", "auto": "Automatique local",
             "model_default": "Choix du modèle"}
_LOCAL_METRICS = frozenset({"stt_ms", "context_ms", "piper_ms", "tts_first_pcm_ms",
                          "end_to_pcm_estimate_ms", "silence_ms", "audio_start_estimate_ms"})
_SAFE_DETAIL = re.compile(r"[A-Za-z0-9_.:-]{1,80}\Z")


def _label(value, limit):
    return "".join(char for char in value if char.isprintable())[:limit] if isinstance(value, str) else ""


def _valid_number(value):
    try:
        return (isinstance(value, (int, float)) and not isinstance(value, bool)
                and math.isfinite(value) and value >= 0)
    except OverflowError:
        return False


@dataclass(frozen=True)
class CognitiveHudSettings:
    enabled: bool = True
    level: str = "minimal"
    show_durations: bool = True
    show_model: bool = True
    show_policy: bool = True
    show_provenance: bool = False
    show_actions: bool = True

    @classmethod
    def from_dict(cls, values):
        values = values if isinstance(values, dict) else {}
        options = {key: values[key] for key in ("enabled", "show_durations", "show_model",
                   "show_policy", "show_provenance", "show_actions") if type(values.get(key)) is bool}
        if isinstance(values.get("level"), str) and values["level"] in {"minimal", "standard", "diagnostic"}:
            options["level"] = values["level"]
        return cls(**options)

    def to_dict(self):
        return asdict(self)


class CognitiveState:
    """Record only events accepted for the owner's current turn/generation.

    ``update`` returns whether state changed, or False for a stale/idempotent
    event. ``snapshot`` exposes no source excerpts, paths, or instruction text.
    Error details belong to the existing explicitly opened local diagnostics;
    this journal retains an optional identifier such as ``stt_error`` only.
    """
    HISTORY_LIMIT = 64
    HISTORY_TTL = 900.

    def __init__(self, *, clock=time.monotonic):
        self._clock = clock
        now = self._now()
        self.generation = 0
        self.turn_id = None
        self.model = self.policy = ""
        self.budget = None
        self.source_count = 0
        self.metrics = {}
        self.started_at = self.changed_at = now
        self.revision = 0
        self._begun = False
        self._terminal = self._error = ""
        self._active = {}
        self._events = deque(maxlen=self.HISTORY_LIMIT)

    def _now(self, now=None):
        value = self._clock() if now is None else now
        if not _valid_number(value):
            raise ValueError("Horodatage monotone positif ou nul requis.")
        return max(float(value), getattr(self, "changed_at", 0.))

    @staticmethod
    def _turn(value):
        if value is None or type(value) is int and value >= 0:
            return value
        # SQLite uses integer message IDs. Short external IDs remain possible,
        # but a response/selection's content is never an acceptable identifier.
        if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,64}", value):
            return value
        raise ValueError("Identifiant de tour invalide.")

    def _accept(self, generation, turn_id):
        return ((generation is None or type(generation) is int and generation == self.generation)
                and (turn_id is None or turn_id == self.turn_id and type(turn_id) is type(self.turn_id)))

    def _prune(self, now):
        while self._events and now - self._events[0]["at"] > self.HISTORY_TTL:
            self._events.popleft()

    def _record(self, activity, active, now, detail=""):
        self._prune(now)
        code = detail if isinstance(detail, str) and _SAFE_DETAIL.fullmatch(detail) else ""
        self._events.append({"at": now, "turn_id": self.turn_id, "generation": self.generation,
                             "activity": activity, "active": active, "detail": code})
        self.changed_at = now
        self.revision += 1

    def begin(self, turn_id, generation, model="", policy="", budget=None, sources=(), now=None):
        turn_id = self._turn(turn_id)
        if type(generation) is not int or generation < 0:
            raise ValueError("Identifiant de génération entier positif ou nul requis.")
        stamp = self._now(now)
        if self._begun and generation <= self.generation:
            return self.snapshot(now=stamp)
        self.turn_id, self.generation = turn_id, generation
        self._begun = True
        self.model, self.policy = _label(model, 128), _label(policy, 64)
        self.budget = budget if type(budget) is int and 0 < budget <= 1_000_000 else None
        self.source_count = len(sources) if isinstance(sources, (list, tuple)) else 0
        self.metrics.clear()
        # Listening is a distinct, concurrent, user-permitted operation. A new
        # inference turn must not fabricate its suspension or open a device.
        self._active = {key: started for key, started in self._active.items() if key == "listening"}
        self._terminal = self._error = ""
        self.started_at = stamp
        self._record("begin", True, stamp)
        return self.snapshot(now=stamp)

    def update(self, activity, active=True, *, generation=None, turn_id=None, now=None, detail=""):
        if not isinstance(activity, str) or activity not in {*ACTIVITIES, *TERMINALS, "idle"} or type(active) is not bool:
            raise ValueError("Activité cognitive observable invalide.")
        if not self._accept(generation, turn_id):
            return False
        stamp = self._now(now)
        if activity == "idle":
            if not active or not self._active and not self._terminal:
                return False
            self._active.clear()
            self._terminal = self._error = ""
        elif activity in TERMINALS:
            if active:
                code = detail if isinstance(detail, str) and _SAFE_DETAIL.fullmatch(detail) else ""
                if self._terminal == activity and (activity != "error" or self._error == code):
                    return False
                self._active = {key: value for key, value in self._active.items() if key == "listening"}
                self._terminal, self._error = activity, code if activity == "error" else ""
            elif self._terminal == activity:
                self._terminal = self._error = ""
            else:
                return False
        elif active:
            if activity in self._active:
                return False
            self._active[activity] = stamp
            self._terminal = self._error = ""
        else:
            if activity not in self._active:
                return False
            del self._active[activity]
        self._record(activity, active, stamp, detail)
        return True

    def attach_context(self, turn_id, *, generation=None, policy="", budget=None, sources=(), now=None):
        """Bind a prepared request to its newly created archive row, without a new turn."""
        if not self._accept(generation, None):
            return False
        self.turn_id = self._turn(turn_id)
        self.policy = _label(policy, 64)
        self.budget = budget if type(budget) is int and 0 < budget <= 1_000_000 else None
        self.source_count = len(sources) if isinstance(sources, (list, tuple)) else 0
        self._record("context_bound", True, self._now(now))
        return True

    def observe_metrics(self, values, *, generation=None, turn_id=None, now=None):
        if not self._accept(generation, turn_id) or not isinstance(values, dict):
            return False
        accepted = generation_metrics(values)
        accepted.update({key: float(values[key]) for key in _LOCAL_METRICS
                         if key in values and _valid_number(values[key])})
        accepted = {key: _label(value, 128) if isinstance(value, str) else value
                    for key, value in accepted.items()}
        if not any(self.metrics.get(key) != value for key, value in accepted.items()):
            return False
        self.metrics.update(accepted)
        self._record("metrics", True, self._now(now))
        return True

    def snapshot(self, now=None):
        stamp = self._now(now)
        self._prune(stamp)
        active = tuple(key for key in ACTIVITIES if key in self._active)
        primary = self._terminal or next(iter(active), "idle")
        return {"turn_id": self.turn_id, "generation": self.generation,
                "primary": primary, "activities": active,
                "started_at": self.started_at, "changed_at": self.changed_at,
                "activity_started": dict(self._active), "observed_at": stamp,
                "model": self.model, "policy": self.policy, "budget": self.budget,
                "source_count": self.source_count, "metrics": dict(self.metrics),
                "error": self._error if primary == "error" else "",
                "cancelled": primary == "cancelled", "interrupted": primary == "interrupted",
                "revision": self.revision}

    def events(self, now=None):
        self._prune(self._now(now))
        return tuple(dict(event) for event in self._events)


def summary(snapshot, settings=None, now=None):
    """Safe peripheral text shared by COMMAND OS, Canvas and the GPU HUD.

    Rich provenance, system instructions and diagnostic error text deliberately
    have no place in this projection. Counts mean inclusion, never model use.
    """
    settings = settings or CognitiveHudSettings()
    if not settings.enabled:
        return ""
    primary = snapshot.get("primary", "idle")
    parts = [LABELS.get(primary, LABELS["idle"])]
    if settings.level == "minimal":
        return parts[0]
    if settings.show_model and snapshot.get("model"):
        parts.append(_label(snapshot["model"], 128))
    if settings.show_policy and snapshot.get("policy"):
        parts.append(_POLICIES.get(snapshot["policy"], _label(snapshot["policy"], 64)))
    if settings.show_policy and type(snapshot.get("budget")) is int:
        parts.append(f"≤ {snapshot['budget']} tokens")
    stamp = snapshot.get("observed_at", 0.) if now is None else now
    started = snapshot.get("activity_started", {}).get(primary)
    if settings.show_durations and _valid_number(stamp) and _valid_number(started):
        parts.append(f"{max(0., stamp - started):.1f} s")
    if settings.show_provenance and type(snapshot.get("source_count")) is int:
        parts.append(f"{snapshot['source_count']} source(s) dans le contexte")
    if settings.level == "diagnostic":
        secondary = [LABELS[key] for key in snapshot.get("activities", ())
                     if key in LABELS and key != primary]
        if secondary:
            parts.append(" + ".join(secondary))
        metrics = snapshot.get("metrics", {})
        for key, label in (("stt_ms", "STT"), ("context_ms", "Contexte"), ("piper_ms", "Piper")):
            if _valid_number(metrics.get(key)):
                parts.append(f"{label} {metrics[key]:.0f} ms")
        if _valid_number(metrics.get("ttft_seconds")):
            parts.append(f"TTFT reçu {metrics['ttft_seconds'] * 1000:.0f} ms")
        if _valid_number(metrics.get("tokens_per_second")):
            parts.append(f"{metrics['tokens_per_second']:.1f} tokens/s")
    return " · ".join(parts)[:512]
