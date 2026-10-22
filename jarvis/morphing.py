"""Small vector expressions for PRESENCE's existing mesh, with no audio I/O.

Contours and details are original mathematical paths, prepared once at import.
The controller changes the geometry of the existing main strokes. Its caller
owns PCM timing, priorities, colors and cancellation; no text is parsed here.
"""
from dataclasses import dataclass
import math
from types import MappingProxyType


POINT_COUNT = 97
ENTER_SECONDS = .36
HOLD_SECONDS = .65
RETURN_SECONDS = .36
FAMILIES = ("smile", "laughter", "affection", "sadness", "anger", "surprise", "thinking", "wink")
INTENSITIES = ("discreet", "normal", "expressive")
_SCALES = {"discreet": .88, "normal": 1.0, "expressive": 1.12}
_DETAIL_LIMITS = {"eco": 4, "balanced": 6, "cinematic": 8}


@dataclass(frozen=True)
class Symbol:
    contour: tuple
    details: tuple


@dataclass(frozen=True)
class MorphFrame:
    contour: tuple
    details: tuple
    opacity: float
    detail_opacity: float
    phase: str


def _arc(cx, cy, rx, ry, start=0.0, end=math.tau, count=25):
    points = tuple((cx + rx * math.cos(start + (end - start) * i / (count - 1)),
                    cy + ry * math.sin(start + (end - start) * i / (count - 1)))
                   for i in range(count))
    return points[:-1] + points[:1] if math.isclose(end - start, math.tau) else points


def _curve(*points, count=25):
    """Sample a quadratic/cubic Bézier once; Canvas splines round the stroke."""
    if len(points) not in (3, 4):
        raise ValueError("A curve needs three or four control points.")
    result = []
    for i in range(count):
        t = i / (count - 1)
        work = list(points)
        while len(work) > 1:
            work = [(x + (tx - x) * t, y + (ty - y) * t)
                    for (x, y), (tx, ty) in zip(work, work[1:])]
        result.append(work[0])
    return tuple(result)


def _heart():
    raw = tuple((math.sin(t) ** 3,
                 -(13 * math.cos(t) - 5 * math.cos(2 * t)
                   - 2 * math.cos(3 * t) - math.cos(4 * t)) / 16)
                for t in (math.tau * i / (POINT_COUNT - 1) for i in range(POINT_COUNT)))
    xs, ys = zip(*raw)
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    scale = max(max(xs) - min(xs), max(ys) - min(ys)) / 2
    points = tuple((x / scale - cx / scale, y / scale - cy / scale) for x, y in raw)
    return points[:-1] + points[:1]


def _catalogue():
    face = _arc(0, 0, 1, 1, -math.pi / 2, math.tau - math.pi / 2, POINT_COUNT)
    # Mouth/gesture first: even the economical profile retains the expression's
    # defining detail. Optional eyebrows and second tears come last.
    smile = _curve((-.48, .19), (0, .79), (.48, .19))
    sad = _curve((-.42, .51), (0, -.02), (.42, .51))
    eye_l = _arc(-.34, -.22, .065, .105)
    eye_r = _arc(.34, -.22, .065, .105)
    happy_l = _curve((-.53, -.13), (-.34, -.41), (-.15, -.13))
    happy_r = _curve((.15, -.13), (.34, -.41), (.53, -.13))
    tear_l = _curve((-.62, -.02), (-.94, .31), (-.48, .48), (-.62, -.02))
    tear_r = tuple((-x, y) for x, y in tear_l)
    angry_l = _curve((-.58, -.38), (-.34, -.32), (-.13, -.13))
    angry_r = tuple((-x, y) for x, y in angry_l)
    thoughtful_hand = _curve((.66, .60), (.22, .88), (.04, .55), (.32, .38))
    thoughtful_finger = _curve((.32, .38), (.48, .19), (.53, .30))
    thoughtful_mouth = _curve((-.29, .37), (-.10, .21), (.09, .31))
    result = {
        "smile": Symbol(face, (smile, happy_l, happy_r)),
        "laughter": Symbol(face, (_arc(0, .29, .39, .29, 0, math.pi),
                                  happy_l, happy_r, tear_l, tear_r,
                                  _curve((-.39, .29), (0, .38), (.39, .29)))),
        "affection": Symbol(_heart(), ()),
        "sadness": Symbol(face, (sad, tear_l, eye_l, eye_r,
                                 _curve((-.55, -.43), (-.33, -.61), (-.14, -.46)),
                                 _curve((.14, -.46), (.33, -.61), (.55, -.43)))),
        "anger": Symbol(face, (angry_l, angry_r, eye_l, eye_r,
                               _curve((-.32, .41), (0, .14), (.32, .41)))),
        "surprise": Symbol(face, (_arc(0, .33, .17, .24), eye_l, eye_r,
                                  _arc(-.34, -.28, .22, .26, math.pi, math.tau),
                                  _arc(.34, -.28, .22, .26, math.pi, math.tau))),
        "thinking": Symbol(face, (thoughtful_hand, thoughtful_finger,
                                  thoughtful_mouth, eye_l, eye_r,
                                  _curve((-.55, -.46), (-.33, -.61), (-.14, -.46)))),
        "wink": Symbol(face, (_curve((-.53, -.20), (-.34, -.34), (-.15, -.20)),
                              eye_r, _curve((-.40, .23), (.04, .65), (.48, .08)))),
    }
    return MappingProxyType(result)


CATALOGUE = _catalogue()


def _smooth(value):
    value = max(0.0, min(1.0, value))
    return value * value * (3 - 2 * value)


def _scale_path(path, cx, cy, amount):
    if amount >= 1:
        return tuple(path)
    if amount <= 0:
        return ((cx, cy),) * len(path)
    return tuple((cx + (x - cx) * amount, cy + (y - cy) * amount) for x, y in path)


class MorphController:
    """One cancellable expression, using the caller's real current geometry.

    Incompatible outlines never interpolate directly. They first contract to
    the same center, then the target contour expands from that center. Holding
    a symbol needs a single timer at its end, not continuous frame callbacks.
    An optional pixel origin freezes the actually visible contour for entry;
    resizing preserves its proportions about the viewport center. Return uses
    the caller's current functional geometry, never the frozen origin.
    """
    def __init__(self):
        self._family = None
        self._started = 0.0
        self._intensity = "normal"
        self._reduced = False
        self._cache_key = self._cache = None
        self._origin = self._origin_viewport = self._origin_normalized = None
        self._origin_cache_key = self._origin_cache = None

    @property
    def active(self):
        return self._family is not None

    @property
    def family(self):
        return self._family

    def trigger(self, family, now, *, intensity="normal", reduced_motion=False,
                origin=None, viewport=None):
        if not isinstance(family, str) or family not in CATALOGUE:
            return False
        if intensity not in INTENSITIES:
            raise ValueError("Unknown morphing intensity.")
        if not math.isfinite(now):
            raise ValueError("Invalid morphing time.")
        normalized = original = original_viewport = None
        if origin is not None:
            try:
                original = tuple(tuple(point) for point in origin)
                original_viewport = tuple(viewport)
                if (len(original) != POINT_COUNT or len(original_viewport) != 2
                        or not all(len(point) == 2 and all(math.isfinite(v) for v in point)
                                   for point in original)
                        or not all(math.isfinite(v) and v > 0 for v in original_viewport)):
                    raise ValueError
            except (TypeError, ValueError):
                raise ValueError("Invalid morphing origin or viewport.") from None
            width, height = original_viewport
            scale = min(width, height)
            normalized = tuple(((x - width / 2) / scale, (y - height / 2) / scale)
                               for x, y in original)
        self._family, self._started = family, now
        self._intensity, self._reduced = intensity, bool(reduced_motion)
        self._origin, self._origin_viewport, self._origin_normalized = original, original_viewport, normalized
        self._origin_cache_key = self._origin_cache = None
        return True

    def cancel(self):
        self._family = None
        self._origin = self._origin_viewport = self._origin_normalized = None
        self._origin_cache_key = self._origin_cache = None

    def _enter_origin(self, normal_points, width, height):
        if self._origin is None:
            return normal_points
        if self._origin_viewport == (width, height):
            return self._origin
        key = (width, height)
        if key != self._origin_cache_key:
            scale = min(width, height)
            self._origin_cache = tuple((width / 2 + x * scale, height / 2 + y * scale)
                                       for x, y in self._origin_normalized)
            self._origin_cache_key = key
        return self._origin_cache

    def _geometry(self, width, height):
        key = (self._family, self._intensity, width, height)
        if key != self._cache_key:
            cx, cy = width / 2, height / 2
            radius = min(width, height) * .16 * _SCALES[self._intensity]
            def scale(path):
                return tuple((cx + x * radius, cy + y * radius) for x, y in path)
            symbol = CATALOGUE[self._family]
            self._cache_key = key
            self._cache = Symbol(scale(symbol.contour), tuple(scale(path) for path in symbol.details))
        return self._cache

    def frame(self, normal_points, width, height, now, *, profile="balanced"):
        if not self.active:
            return None
        if profile not in _DETAIL_LIMITS:
            raise ValueError("Unknown visual profile.")
        if len(normal_points) != POINT_COUNT:
            raise ValueError("The main PRESENCE mesh must have 97 points.")
        if not all(math.isfinite(value) for value in (width, height, now)) or min(width, height) <= 0:
            raise ValueError("Invalid morphing viewport or time.")
        elapsed = max(0.0, now - self._started)
        total = HOLD_SECONDS if self._reduced else ENTER_SECONDS + HOLD_SECONDS + RETURN_SECONDS
        if elapsed >= total:
            self.cancel()
            return None
        symbol = self._geometry(width, height)
        details = symbol.details[:_DETAIL_LIMITS[profile]]
        if self._reduced:
            return MorphFrame(symbol.contour, details, 1.0, 1.0, "hold")
        cx, cy = width / 2, height / 2
        if elapsed < ENTER_SECONDS:
            phase = elapsed / ENTER_SECONDS
            if phase <= .5:
                contour = _scale_path(self._enter_origin(normal_points, width, height),
                                      cx, cy, 1 - _smooth(phase * 2))
                return MorphFrame(contour, (), 1.0, 0.0, "enter")
            progress = _smooth((phase - .5) * 2)
            contour = _scale_path(symbol.contour, cx, cy, progress)
            return MorphFrame(contour, details, 1.0, _smooth((progress - .2) / .8), "enter")
        elapsed -= ENTER_SECONDS
        if elapsed < HOLD_SECONDS:
            return MorphFrame(symbol.contour, details, 1.0, 1.0, "hold")
        phase = (elapsed - HOLD_SECONDS) / RETURN_SECONDS
        if phase <= .5:
            progress = 1 - _smooth(phase * 2)
            contour = _scale_path(symbol.contour, cx, cy, progress)
            return MorphFrame(contour, details, 1.0, progress * progress, "return")
        contour = _scale_path(normal_points, cx, cy, _smooth((phase - .5) * 2))
        return MorphFrame(contour, (), 1.0, 0.0, "return")

    def next_delay_ms(self, now, frame_ms):
        """Time until the next useful redraw, including a static hold's end."""
        if not self.active:
            return None
        elapsed = max(0.0, now - self._started)
        if self._reduced:
            return max(1, math.ceil((HOLD_SECONDS - elapsed) * 1000))
        if ENTER_SECONDS <= elapsed < ENTER_SECONDS + HOLD_SECONDS:
            return max(1, math.ceil((ENTER_SECONDS + HOLD_SECONDS - elapsed) * 1000))
        return max(1, round(frame_ms))
