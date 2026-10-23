"""Bounded cosmetic microexpressions from already classified mood labels.

No text analysis, audio gain or operational state belongs here. The caller only
applies these factors to THINKING or a small PCM-gated nuance of the speaking core.
The actual microphone wave is never changed by these factors.
"""
import math


MICRO_DURATION = 1.4
MICRO_COOLDOWN = 3.0
MICRO_LABELS = {"surprise": "Surprise", "comfort": "Réconfort",
                "enthusiasm": "Enthousiasme", "gravity": "Gravité"}
_MOODS = {
    "surprise": "surprise",
    "comfort": "comfort", "réconfort": "comfort", "reconfort": "comfort",
    "attachement": "comfort", "apaisement": "comfort", "compassion": "comfort",
    "enthusiasm": "enthusiasm", "enthousiasme": "enthusiasm",
    "joie": "enthusiasm", "espoir": "enthusiasm", "volonté": "enthusiasm",
    "désir": "enthusiasm", "renouveau": "enthusiasm",
    "gravity": "gravity", "gravité": "gravity", "gravite": "gravity",
    "deuil": "gravity", "peur": "gravity", "colère": "gravity",
}
_IDENTITY = (1.0, 1.0, 1.0)


def _valid_time(value):
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


class MicroExpression:
    """A single short pulse, with no queue or recurring timer.

    Repeated labels within one family do not retrigger a pulse. A different family
    must also wait for the cooldown. Explicit cancellation clears the family but
    retains the cooldown, so interruptions never produce rapid restart flashes.
    """
    def __init__(self):
        self.family = None
        self.started = float("-inf")
        self._last_family = None
        self._last_trigger_at = float("-inf")

    def trigger(self, mood, now):
        family = _MOODS.get(mood.strip().casefold()) if isinstance(mood, str) else None
        if (family is None or not _valid_time(now) or family == self._last_family
                or now - self._last_trigger_at < MICRO_COOLDOWN):
            return False
        self.family = self._last_family = family
        self.started = self._last_trigger_at = now
        return True

    def cancel(self):
        self.family = self._last_family = None
        self.started = float("-inf")

    def active(self, now):
        return (self.family is not None and _valid_time(now)
                and 0 <= now - self.started < MICRO_DURATION)

    def factors(self, now):
        """Return radius, curve and speed multipliers, each within 8% of one."""
        if not self.active(now):
            return _IDENTITY
        progress = (now - self.started) / MICRO_DURATION
        envelope = math.sin(math.pi * progress) ** 2
        if self.family == "surprise":
            # Smooth contraction then expansion; both endpoints have zero slope.
            return (1 - .07 * math.sin(math.tau * progress) * envelope,
                    1 + .04 * envelope, 1 + .03 * envelope)
        if self.family == "comfort":
            return (1 + .015 * envelope, 1 - .06 * envelope, 1 - .05 * envelope)
        if self.family == "enthusiasm":
            return (1 + .05 * envelope, 1 + .045 * envelope, 1 + .06 * envelope)
        return (1 - .035 * envelope, 1 - .04 * envelope, 1 - .075 * envelope)
