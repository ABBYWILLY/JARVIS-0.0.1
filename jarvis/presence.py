"""One audio-driven mesh, shared by PRESENCE's line, wave and core forms."""
import math
import re
import time
import tkinter as tk
from collections import deque
from dataclasses import asdict, dataclass, replace
from tkinter import colorchooser, messagebox, ttk
from tkinter import font as tkfont

from .spectrum import CYAN, OPERATIONAL, FieldEvent, MoodTracker, Tone, ToneAnalyzer, analyze_passages
from .captions import CaptionPlan, CaptionWindow, prepare_caption
from .expressions import expression_family
from .morphing import FAMILIES, MorphController
from .richtext import parse_text
from .presence_motion import MICRO_LABELS, MicroExpression


STATES = {"silent", "listening", "user_speaking", "thinking", "jarvis_speaking", "dormant"}
PROFILES = {"eco": (16, 2), "balanced": (30, 3), "cinematic": (45, 4)}
PROFILE_LABELS = {"eco": "Éco", "balanced": "Équilibré", "cinematic": "Cinématique"}
ACCENT_LABELS = {"adaptive": "Spectre adaptatif", "cyan": "Cyan fixe",
                 "fixed": "Couleur personnalisée", "none": "Aucun accent émotionnel"}
SPECTRUM_LABELS = {"expression": "Émotion exprimée", "thematic": "Ambiance du sujet",
                   "neutral": "Neutre · cyan"}
STATE_LABELS = {"silent": "SILENCE", "listening": "ÉCOUTE LOCALE",
                "user_speaking": "VOUS PARLEZ", "thinking": "TRAITEMENT LOCAL",
                "jarvis_speaking": "JARVIS PARLE", "dormant": "EN SOMMEIL"}
POINT_COUNT = 97
SIGNAL_LIFETIME = 0.18
FLUIDITY_LABELS = {"reactive": "Réactive", "cinematic": "Cinématique", "calm": "Apaisée"}
COLORING_LABELS = {"discreet": "Discrète", "normal": "Normale", "expressive": "Expressive"}
MIC_LABELS = {"disabled": "MICRO DÉSACTIVÉ", "starting": "MICRO · INITIALISATION",
              "open": "MICRO OUVERT", "voice": "MICRO · VOIX DÉTECTÉE", "stt": "MICRO · STT LOCAL",
              "suspended": "MICRO SUSPENDU · LECTURE", "error": "MICRO · ERREUR"}
EXPRESSION_LABELS = dict(zip(FAMILIES, ("Sourire", "Rire", "Affection", "Tristesse",
                                       "Colère", "Surprise", "Réflexion", "Complicité")))
MORPH_INTENSITY_LABELS = {"discreet": "Discrète", "normal": "Normale", "expressive": "Expressive"}
AMBIENCE_LABELS = {"conversation": "Conversation", "explanation": "Explication",
                   "story": "Récit", "focus": "Concentration"}
PALETTE_LABELS = {"original": "Spectre original", "soft": "Pastel holographique", "warm": "Ambre holographique"}
# Pure visual policies: pace, curvature and halo. They never affect TTS/LLM/permissions.
AMBIENCES = {"conversation": (1., 1., 1.), "explanation": (.82, .75, .90),
             "story": (.85, 1.12, 1.05), "focus": (.65, .55, .75)}
_POSITIONS = tuple(i / (POINT_COUNT - 1) for i in range(POINT_COUNT))
_ANGLES = tuple(-math.pi / 2 + math.tau * t for t in _POSITIONS)
_WINDOW = tuple(math.sin(math.pi * t) ** 2 for t in _POSITIONS)
_ZERO_WAVE = (0.0,) * POINT_COUNT


@dataclass(frozen=True)
class PresenceSettings:
    background: str = "#000000"
    profile: str = "balanced"
    reduced_motion: bool = False
    subtitles: bool = True
    accent_mode: str = "adaptive"
    fixed_color: str = "#69edf5"
    wave_expressivity: int = 75
    timing_monitor: bool = True
    spectrum_mode: str = "thematic"
    spectrum_intensity: int = 65
    visualizer_thickness: int = 6
    halos: bool = True
    animations: bool = True
    fluidity: str = "cinematic"
    emotional_subtitles: bool = True
    subtitle_coloring: str = "normal"
    subtitle_size: int = 18
    diagnostic_mode: bool = True
    semantic_morphing: bool = True
    morph_intensity: str = "normal"
    halo_intensity: int = 100
    thinking_size: int = 100
    ambience: str = "conversation"
    emotional_palette: str = "original"
    microexpressions: bool = True
    mini_mode: bool = False

    @classmethod
    def from_dict(cls, values):
        """Optional visual preferences must never prevent the text app starting."""
        defaults = cls()
        if not isinstance(values, dict):
            return defaults
        valid = {}
        color = values.get("background")
        if isinstance(color, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", color):
            valid["background"] = color.lower()
        if isinstance(values.get("profile"), str) and values["profile"] in PROFILES:
            valid["profile"] = values["profile"]
        for key in ("reduced_motion", "subtitles", "timing_monitor", "halos", "animations",
                    "emotional_subtitles", "diagnostic_mode", "semantic_morphing", "microexpressions", "mini_mode"):
            if isinstance(values.get(key), bool):
                valid[key] = values[key]
        if isinstance(values.get("accent_mode"), str) and values["accent_mode"] in ACCENT_LABELS:
            valid["accent_mode"] = values["accent_mode"]
        color = values.get("fixed_color")
        if isinstance(color, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", color):
            valid["fixed_color"] = color.lower()
        if isinstance(values.get("spectrum_mode"), str) and values["spectrum_mode"] in SPECTRUM_LABELS:
            valid["spectrum_mode"] = values["spectrum_mode"]
        for key in ("wave_expressivity", "spectrum_intensity", "halo_intensity"):
            value = values.get(key)
            if (isinstance(value, (int, float)) and not isinstance(value, bool)
                    and 0 <= value <= 100 and math.isfinite(value)):
                valid[key] = round(value)
        value = values.get("visualizer_thickness")
        if (isinstance(value, (int, float)) and not isinstance(value, bool)
                and 1 <= value <= 10 and math.isfinite(value)):
            valid["visualizer_thickness"] = round(value)
        for key, choices in (("fluidity", FLUIDITY_LABELS), ("subtitle_coloring", COLORING_LABELS),
                             ("morph_intensity", MORPH_INTENSITY_LABELS), ("ambience", AMBIENCE_LABELS),
                             ("emotional_palette", PALETTE_LABELS)):
            if isinstance(values.get(key), str) and values[key] in choices:
                valid[key] = values[key]
        value = values.get("thinking_size")
        if type(value) is int and 70 <= value <= 130:
            valid["thinking_size"] = value
        value = values.get("subtitle_size")
        if isinstance(value, int) and not isinstance(value, bool) and 12 <= value <= 32:
            valid["subtitle_size"] = value
        return replace(defaults, **valid)


@dataclass(frozen=True)
class ExpressionCue:
    response_id: int
    segment_id: int
    start: int
    end: int
    family: str
    fraction: float
    terminal: bool


def _rgb(color):
    return tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))


def mix(background, foreground, amount):
    return "#" + "".join(f"{round(a + (b - a) * amount):02x}"
                         for a, b in zip(_rgb(background), _rgb(foreground)))


class AccentTransition:
    """Time-based interpolation; retargeting always starts at the visible colour."""
    duration = 0.45

    def __init__(self, color=CYAN):
        self.source = self.target = color
        self.started = float("-inf")

    def color(self, now):
        if self.source == self.target or now >= self.started + self.duration:
            return self.target
        fraction = max(0.0, min(1.0, (now - self.started) / self.duration))
        return mix(self.source, self.target, fraction * fraction * (3 - 2 * fraction))

    def retarget(self, color, now):
        if color != self.target:
            self.source, self.target, self.started = self.color(now), color, now

    def active(self, now):
        return self.source != self.target and now < self.started + self.duration


def luminance(color):
    channels = [value / 255 for value in _rgb(color)]
    linear = [value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4
              for value in channels]
    return sum(value * weight for value, weight in zip(linear, (0.2126, 0.7152, 0.0722)))


def contrast(a, b):
    light, dark = sorted((luminance(a), luminance(b)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


def palette(background):
    foreground = max(("#f2f6fa", "#101820"), key=lambda color: contrast(background, color))
    muted = mix(background, foreground, 0.72)
    if contrast(background, muted) < 4.5:
        muted = foreground
    accent = max(("#69edf5", "#005367"), key=lambda color: contrast(background, color))
    button_shade = "#000000" if foreground == "#f2f6fa" else "#ffffff"
    return {"background": background, "foreground": foreground, "muted": muted,
            "accent": accent, "button": mix(background, button_shade, 0.08)}


def readable_accent(color, background):
    """Keep even dark semantic accents visible against a custom background."""
    if contrast(color, background) >= 3:
        return color
    destination = palette(background)["foreground"]
    for step in range(1, 21):
        candidate = mix(color, destination, step / 20)
        if contrast(candidate, background) >= 3:
            return candidate
    return destination


def core_radius(width, height):
    small = max(1.0, min(width, height))
    # Reference radius shared by the speaking core and the THINKING lens.
    return small * 0.145


def dpi_scale(tk_scaling):
    """Tk scaling is pixels/point: 96 DPI on Windows is 96/72, not 1."""
    return max(0.75, min(4.0, _finite(tk_scaling, 96 / 72) / (96 / 72)))


def stroke_widths(thickness, scale=1.0):
    """Outer halo → inner halo → envelope → clear central stroke, in pixels."""
    amount = (max(1, min(10, thickness)) - 1) / 9
    edge = 2.5 + 6.3 * amount
    halo = 15.0 + 22.0 * amount
    return tuple(width * scale for width in (halo, halo * 0.68, edge + 6.5, edge))


def render_quality(settings, width, height, scale=1.0, overloaded=False):
    """Bound Canvas work for the profile, pixel area, DPI and measured frame cost."""
    fps, layers = PROFILES[settings.profile]
    if width * height > 2_500_000 or scale >= 1.75:
        fps, layers = min(fps, 30), min(layers, 3)
    if width * height > 6_000_000 or overloaded:
        fps, layers = min(fps, 16), min(layers, 2)
    if settings.reduced_motion or not settings.animations:
        fps = min(fps, 16)
    if not settings.halos or settings.halo_intensity == 0:
        layers = 1
    arcs = min(3, layers - 1)
    return fps, layers, arcs


def _finite(value, default=0.0):
    try:
        value = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return value if math.isfinite(value) else default


def _signal(signal):
    if not isinstance(signal, dict):
        return {"rms": 0.0, "wave": []}
    wave = signal.get("wave", [])
    if not isinstance(wave, (list, tuple)):
        wave = []
    return {"rms": max(0.0, min(1.0, _finite(signal.get("rms", 0)))),
            "wave": [max(-1.0, min(1.0, _finite(value))) for value in wave[:192]]}


def _smooth_wave(samples, count=POINT_COUNT):
    if not samples or not any(samples):
        return [0.0] * count
    values = list(samples)
    # A short spatial filter plus Canvas splines removes angular microphone peaks.
    for _ in range(2):
        padded = [values[0]] * 2 + values + [values[-1]] * 2
        values = [sum(padded[i + j] * weight for j, weight in enumerate((1, 4, 6, 4, 1))) / 16
                  for i in range(len(values))]
    mean = sum(values) / len(values)
    values = [value - mean for value in values]
    peak = max(abs(value) for value in values)
    if peak < 1e-9:
        return [0.0] * count
    result = []
    for i in range(count):
        position = i * (len(values) - 1) / (count - 1)
        left = int(position)
        right = min(len(values) - 1, left + 1)
        value = values[left] + (values[right] - values[left]) * (position - left)
        result.append(value / peak)
    return result


def _center(points, width, height):
    xs, ys = zip(*points)
    dx, dy = width / 2 - (min(xs) + max(xs)) / 2, height / 2 - (min(ys) + max(ys)) / 2
    return [(x + dx, y + dy) for x, y in points]


def _mesh_arc(points, start, length):
    """A circulating highlight cut from the current mesh, including its morph."""
    size = len(points) - 1
    steps = max(2, round(length * size))
    result = []
    for index in range(steps + 1):
        position = ((start + length * index / steps) % 1) * size
        left = int(position)
        fraction = position - left
        x, y = points[left]
        tx, ty = points[left + 1]
        result.extend((x + (tx - x) * fraction, y + (ty - y) * fraction))
    return result


class PresenceModel:
    """The sole state machine and reversible mesh; independent of Tk and audio I/O."""
    def __init__(self, settings=None):
        self.settings = settings or PresenceSettings()
        self.state = "silent"
        self.signal = _signal(None)
        self.signal_at = self.state_since = 0.0
        self.points = []
        self.size = None
        self.last_frame = None
        self.morphing = False
        self._wave = self._wave_line = _ZERO_WAVE
        self._signal_version = 0
        self._geometry_key = self._geometry = None
        self.emotional_inertia = self.emotional_curve = 1.0
        self.micro = MicroExpression()

    @property
    def motion_allowed(self):
        return self.settings.animations and not self.settings.reduced_motion

    def update_event(self, state, signal=None, now=None):
        if state not in STATES:
            raise ValueError("État PRESENCE inconnu.")
        now = time.monotonic() if now is None else now
        if state != self.state:
            self.state_since = now
        self.state = state
        if state in {"silent", "listening", "user_speaking", "dormant"}:
            self.micro.cancel()
        self.signal = _signal(signal)
        self.signal_at = now
        self._signal_version += 1
        # Only the latest bounded PCM summary is retained. Filtering belongs to
        # signal arrival, never to the animation loop or an invented carrier.
        if self.signal["rms"] > 0:
            self._wave = tuple(_smooth_wave(self.signal["wave"]))
            windowed = tuple(value * weight for value, weight in zip(self._wave, _WINDOW))
            positive, negative = max(windowed), -min(windowed)
            self._wave_line = (tuple(value / (positive if value >= 0 else negative)
                                     for value in windowed)
                               if positive > 1e-9 and negative > 1e-9 else _ZERO_WAVE)
        else:
            self._wave = self._wave_line = _ZERO_WAVE

    def has_signal(self, now):
        return self.signal["rms"] > 0 and 0 <= now - self.signal_at <= SIGNAL_LIFETIME

    def target_geometry(self, width, height, now=None):
        now = time.monotonic() if now is None else now
        width, height = max(1, width), max(1, height)
        cx, cy = width / 2, height / 2
        span = max(1.0, width - 2 * max(18, width * 0.08))
        active = self.has_signal(now)
        orbital = self.state == "thinking" or self.state == "jarvis_speaking" and active
        moving = self.state == "thinking" and self.motion_allowed
        micro_active = (self.settings.microexpressions and self.motion_allowed and self.micro.active(now)
                        and (self.state == "thinking" or self.state == "jarvis_speaking" and active))
        micro_radius, micro_curve, micro_speed = self.micro.factors(now) if micro_active else (1., 1., 1.)
        pace, curvature, _halo = AMBIENCES[self.settings.ambience]
        key = (width, height, self.state, self.settings.wave_expressivity,
               self.settings.reduced_motion, self.motion_allowed, self.settings.thinking_size, self.settings.ambience,
               self.settings.mini_mode,
               self._signal_version if active and self.state in {"listening", "user_speaking", "jarvis_speaking"} else None)
        if not moving and not micro_active and key == self._geometry_key:
            return self._geometry
        energy = min(1.0, math.sqrt(self.signal["rms"]) * 1.6) if active else 0.0
        expressivity = self.settings.wave_expressivity / 100
        # Display compression only: retain quiet real variations without changing
        # microphone PCM, VAD thresholds, or the signal driving the speaking core.
        wave_energy = ((1 - math.exp(-self.signal["rms"] * (10 + 35 * expressivity))) ** 0.8
                       if active else 0.0)
        amplitude = min(220, height * 0.24) * (0.18 + 0.82 * expressivity) * wave_energy
        wave, wave_line = self._wave, self._wave_line
        points = []
        phase = (now - self.state_since) * 1.35 * pace if moving else 0.0
        if moving and micro_active:
            # A short bounded phase nuance, independent of how long THINKING
            # has already lasted. Multiplying the entire age would cause jumps.
            phase += (micro_speed - 1) * (now - self.micro.started) * 1.35
        for i, t in enumerate(_POSITIONS):
            if self.state == "dormant":
                x, y = cx + 2.5 * math.cos(_ANGLES[i]), cy + 2.5 * math.sin(_ANGLES[i])
            elif orbital:
                angle = _ANGLES[i]
                radius = core_radius(width, height)
                if self.settings.mini_mode:
                    radius = min(radius, min(width, height) * .09)
                if self.state == "thinking":
                    radius *= self.settings.thinking_size / 100 * micro_radius
                if moving:
                    # Smooth, low-frequency deformations of this same closed mesh.
                    # This indicates active processing, never fictitious audio.
                    radius *= (1 + 0.035 * math.sin(phase * 0.7)
                               + 0.10 * self.emotional_curve * curvature * micro_curve * math.sin(2 * angle + phase)
                               + 0.045 * math.sin(3 * angle - phase * 0.65))
                    angle += 0.07 * math.sin(phase * 0.55)
                elif self.state == "jarvis_speaking" and active:
                    # Opposite radii share data, so speech never moves the core's centre.
                    j = (i + (POINT_COUNT - 1) // 2) % (POINT_COUNT - 1)
                    modulation = (wave[i % (POINT_COUNT - 1)] + wave[j]) / 2
                    radius *= 1 + energy * (0.25 + 0.14 * modulation)
                    # A bounded nuance of the real speaking core, gated by PCM.
                    # Microphone waves and zero/expired PCM are never animated.
                    radius *= 1 + (micro_radius - 1) * energy * .5
                if self.state == "thinking":
                    # A lenticular, softly pinched singularity remains distinct
                    # from the round PCM core even when motion is disabled.
                    radius *= 1 + .055 * math.cos(4 * angle)
                    x, y = cx + 1.08 * radius * math.cos(angle), cy + .76 * radius * math.sin(angle)
                else:
                    x, y = cx + radius * math.cos(angle), cy + radius * math.sin(angle)
            else:
                x, y = cx + (t - 0.5) * span, cy
                if self.state in {"listening", "user_speaking"} and active:
                    # The sine is an endpoint window, never an invented audio carrier.
                    y += wave_line[i] * amplitude * (0.55 if self.settings.reduced_motion else 1)
            points.append((x, y))
        points = _center(points, width, height)
        if orbital or self.state == "dormant":
            points[-1] = points[0]  # Exact closure enables Tk's continuous closed spline.
        # A one-entry cache: silence and fixed forms allocate no new mesh per frame.
        self._geometry_key, self._geometry = (None if moving or micro_active else key), points
        return points

    def frame(self, width, height, now=None):
        now = time.monotonic() if now is None else now
        target = self.target_geometry(width, height, now)
        speaking_without_signal = self.state in {"listening", "user_speaking", "jarvis_speaking"} and not self.has_signal(now)
        if (not self.points or self.size != (width, height) or not self.motion_allowed
                or self.state in {"dormant", "silent"} or speaking_without_signal):
            self.points = target
        else:
            delta = max(0, min(0.1, now - self.last_frame))
            duration = {"reactive": 0.045, "cinematic": 0.065, "calm": 0.11}[self.settings.fluidity]
            duration *= self.emotional_inertia
            if self.state in {"listening", "user_speaking"}:
                extent = lambda points: max(y for _, y in points) - min(y for _, y in points)
                duration = 0.022 if extent(target) >= extent(self.points) else 0.095
            amount = 1 - math.exp(-delta / duration)
            self.points = [(x + (tx - x) * amount, y + (ty - y) * amount)
                           for (x, y), (tx, ty) in zip(self.points, target)]
            if self.state in {"thinking", "jarvis_speaking"} and math.dist(self.points[0], self.points[-1]) < 1:
                self.points[-1] = self.points[0]
            self.points = _center(self.points, width, height)
            if max(math.dist(point, goal) for point, goal in zip(self.points, target)) < 0.15:
                self.points = target
        self.size, self.last_frame = (width, height), now
        self.morphing = any(math.dist(point, goal) > 0.15 for point, goal in zip(self.points, target))
        return self.points

    def needs_animation(self, now=None):
        now = time.monotonic() if now is None else now
        if self.state == "dormant":
            return False
        return (self.morphing and self.motion_allowed or self.state == "thinking" and self.motion_allowed
                or self.state in {"listening", "user_speaking", "jarvis_speaking"} and self.has_signal(now))


class PresenceView:
    """Lazy, optional window. It never owns the microphone, inference or playback."""
    def __init__(self, app):
        self.app = app
        try:
            raw = app.store.get_preference("presence", {})
        except Exception:
            raw = {}
        self._saved_preferences = dict(raw) if isinstance(raw, dict) else {}
        self.settings = PresenceSettings.from_dict(raw)
        self.model = PresenceModel(self.settings)
        self.analyzer = ToneAnalyzer(mode=self.settings.spectrum_mode, hold_seconds=0)
        self.tone = self.analyzer.current
        self._last_text = None
        self._last_estimate = Tone()
        self._preview_text = None
        self._segment_key = None
        self._segment_fraction = 0.0
        self._segment_events = []
        self.dominant_tone = Tone()
        self.mood_tracker = MoodTracker(mode=self.settings.spectrum_mode)
        self._caption_plan = None
        self._caption_window = CaptionWindow("", ())
        self._caption_layout_key = None
        self._caption_font = None
        self._caption_fit_key = None
        self._caption_top = None
        self._caption_footer_visible = True
        self._preview_id = None
        self._scenario_index = None
        self.microphone_state = "disabled"
        self.microphone_detail = ""
        self._accent = AccentTransition(self._target_accent())
        self.operation = "inactive"
        self.operation_detail = ""
        self._operation_explicit = False
        self.window = self.canvas = None
        self.after_id = None
        self.caption_text = ""
        self.caption_data = None
        self._rendered_caption = None
        self.paths = []
        self.orbital_paths = []
        self.settings_dialog = None
        self._slow_until = 0.0
        self.timings = {}
        self.timing_history = []
        self._timing_recorded = False
        self._timing_render_key = None
        self._overlay_key = None
        self.semantic = MorphController()
        self.semantic_paths = []
        self._semantic_response = -1
        self._semantic_closed = False
        self._semantic_cues = deque(maxlen=64)
        self._semantic_completed = deque(maxlen=64)
        self._semantic_playing = None
        self._semantic_plans = {}
        self._prepared_semantic_caption = None
        self._semantic_last_trigger = float("-inf")
        self._semantic_preview = False
        self._semantic_drawn = False
        self._semantic_trace = deque(maxlen=48)
        self._workshop_preview = False
        self._normal_geometry = None
        self._window_mode = None
        self._controls_layout = None

    @property
    def state(self):
        return self.model.state

    def show(self):
        if self.window is not None and self.window.winfo_exists():
            self.window.deiconify()
            self.window.lift()
            self._render()
            return
        window = self.window = tk.Toplevel(self.app.root)
        self._window_mode = self._controls_layout = None
        self._overlay_key = self._timing_render_key = self._rendered_caption = None
        window.title("JARVIS · PRESENCE")
        sw, sh = window.winfo_screenwidth(), window.winfo_screenheight()
        width, height = min(1100, max(420, sw - 80)), min(760, max(340, sh - 100))
        window.geometry(f"{width}x{height}")
        window.minsize(min(620, width), min(440, height))
        window.protocol("WM_DELETE_WINDOW", self.close)
        window.bind("<F11>", self.toggle_fullscreen)
        window.bind("<Escape>", self.exit_fullscreen)
        window.bind("<F9>", self.toggle_diagnostic)
        window.bind("<F10>", self.toggle_mini)
        window.bind("<Control-space>", lambda _event: self.toggle_listening())
        window.bind("<Map>", self._on_map)
        window.bind("<Unmap>", self._on_unmap)
        window.bind("<Destroy>", self._on_destroy)
        self.canvas = tk.Canvas(window, highlightthickness=0, borderwidth=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", self._on_resize)
        self.paths = [self.canvas.create_line(0, 0, 1, 0, smooth=True, splinesteps=16,
                                             capstyle="round", joinstyle="round") for _ in range(4)]
        self.orbital_paths = [self.canvas.create_line(0, 0, 1, 0, smooth=True, splinesteps=12,
                                                     capstyle="round", joinstyle="round", state="hidden")
                              for _ in range(3)]
        # Secondary facial strokes belong to the same morphing entity, and are
        # permanently pooled. No image, extra avatar, or new Canvas is created.
        self.semantic_paths = [tuple(self.canvas.create_line(0, 0, 1, 0, smooth=True,
                               splinesteps=12, capstyle="round", joinstyle="round", state="hidden")
                               for _ in range(2)) for _ in range(8)]
        family = getattr(self.app, "font_family", "Segoe UI")
        self.identity = tk.Label(window, text="J A R V I S", font=(family, 18, "bold"))
        self.identity.place(relx=0.045, rely=0.045, anchor="nw")
        self.state_label = tk.Label(window, font=(family, 10), anchor="w")
        self.state_label.place(relx=0.045, rely=0.105, anchor="nw")
        self.mic_label = tk.Label(window, font=(family, 9), anchor="w")
        self.mic_label.place(relx=0.045, rely=0.15, anchor="nw")
        self.tone_label = tk.Label(window, font=(family, 9), anchor="w")
        self.tone_label.place(relx=0.045, rely=0.195, anchor="nw")
        self.operation_label = tk.Label(window, font=(family, 9), anchor="ne", justify="right")
        self.operation_label.place(relx=0.955, rely=0.15, anchor="ne", relwidth=0.43)
        self.header_controls = tk.Frame(window)
        self.header_controls.place(relx=0.955, rely=0.045, anchor="ne")
        self.buttons = []
        for label, command in (("F9 · Mode", self.toggle_diagnostic), ("Fond", self.choose_background), ("Chrono", self.toggle_timing),
                               ("Atelier", self.open_settings)):
            self._button(self.header_controls, label, command).pack(side="left", padx=4)
        self.mini_button = self._button(self.header_controls, "Mini", self.toggle_mini)
        self.mini_button.pack(side="left", padx=4)
        self.header_buttons = tuple(self.header_controls.winfo_children())
        self.controls = tk.Frame(window)
        self.controls.place(relx=0.5, rely=0.92, anchor="center")
        self.listen_button = self._button(self.controls, "Activer l’écoute", self.toggle_listening)
        self.listen_button.pack(side="left", padx=4)
        self._button(self.controls, "Arrêt", self.emergency).pack(side="left", padx=4)
        self.sleep_button = self._button(self.controls, "Sommeil", self.toggle_sleep)
        self.sleep_button.pack(side="left", padx=4)
        self.command_button = self._button(self.controls, "COMMAND OS", self.return_to_command)
        self.command_button.pack(side="left", padx=4)
        self.control_buttons = tuple(self.controls.winfo_children())
        # Overlays use place: their requested size never participates in core layout.
        self._caption_font = tkfont.Font(root=window, family=family, size=self.settings.subtitle_size)
        self.caption_label = tk.Text(window, font=self._caption_font, wrap="word", height=2,
                                     state="disabled", borderwidth=0, highlightthickness=0,
                                     padx=8, pady=0, takefocus=True)
        self.caption_label.tag_configure("center", justify="center")
        self.caption_footer = tk.Frame(window)
        self.caption_note = tk.Label(self.caption_footer, font=(family, 8),
                                     text="Synchronisation estimée par phrase / bloc audio Piper")
        self.caption_note.pack(side="left", padx=6)
        self._button(self.caption_footer, "Copier l’extrait", self.copy_caption).pack(side="left", padx=6)
        self.timing_panel = tk.Frame(window, padx=10, pady=8, highlightthickness=1)
        self.timing_title = tk.Label(self.timing_panel, text="CHRONO · LOCAL / ms", anchor="w", font=(family, 9, "bold"))
        self.timing_title.pack(fill="x")
        self.timing_values = tk.Label(self.timing_panel, anchor="w", justify="left", font=(family, 9))
        self.timing_values.pack(fill="x", pady=4)
        self.timing_chart = tk.Canvas(self.timing_panel, height=45, highlightthickness=0)
        self.timing_chart.pack(fill="x")
        self.timing_note = tk.Label(self.timing_panel, anchor="w", justify="left", font=(family, 8),
                                   text="≈ DAC PortAudio · Bluetooth acoustique inconnu\nCourbe : derniers échanges, aucune donnée biologique")
        self.timing_note.pack(fill="x", pady=(4, 0))
        self._timing_render_key = None
        self._rendered_caption = None
        self._apply_colors()
        window.update_idletasks()
        self._apply_window_mode()
        self.canvas.focus_set()
        self._render()

    def _button(self, parent, text, command):
        button = tk.Button(parent, text=text, command=command, relief="flat", borderwidth=1,
                           padx=12, pady=8, takefocus=True,
                           font=(getattr(self.app, "font_family", "Segoe UI"), 10))
        self.buttons.append(button)
        return button

    def update_event(self, state, signal=None, caption=None):
        if state not in STATES or self.state == "dormant" and state != "dormant":
            return
        if self._workshop_preview:
            self._workshop_preview = False
            self.model.micro.cancel()
        # Actual functional events cancel the offline scenario before any drawing.
        self._cancel_scenario()
        # Repeated waiting notifications are idempotent: text may already be
        # queued while the first PCM is still being synthesized. A real state
        # transition or user interruption still invalidates that response.
        if (state in {"user_speaking", "dormant"} or self._semantic_preview
                or state == "thinking" and (self.state != "thinking" or self.semantic.active)):
            self._cancel_semantics("state:" + state)
        elif state == "jarvis_speaking":
            # Any new real audio pre-empts a held symbol immediately. Future
            # events in the response remain available; no audio is delayed.
            incoming = (caption.get("response_id", -1), caption.get("segment_id", -1)) if isinstance(caption, dict) else None
            if incoming != self._semantic_playing or _finite((signal or {}).get("rms")) > .008:
                if self.semantic.active:
                    self._trace_semantic("cancelled", "pcm_resumed", self._semantic_playing,
                                         self.semantic.family)
                self.semantic.cancel()
        # Real voice/state events always take priority over an optional local preview.
        if self._preview_text is not None:
            self._preview_text = None
            self._set_tone(Tone())
        self.model.update_event(state, signal)
        if not self._operation_explicit:
            self.operation = "inactive" if state in {"silent", "dormant"} else "info"
        if isinstance(caption, dict) and state == "jarvis_speaking":
            semantic_key = (caption.get("response_id", -1), caption.get("segment_id", -1))
            self._semantic_playing = semantic_key
            self.caption_data = dict(caption)
            text = str(caption.get("text", ""))
            key = ("segment", caption.get("response_id"), caption["segment_id"]) if "segment_id" in caption else ("text", text)
            fraction = max(0.0, min(1.0, _finite(caption.get("fraction"))))
            if key != self._segment_key:
                self._segment_key, self._segment_fraction = key, fraction
                self._segment_events = self._events_for_caption(caption)
                plan = caption.get("caption_plan")
                self._caption_plan = self._semantic_plans.get(semantic_key)
                if self._caption_plan is None:
                    self._caption_plan = (CaptionPlan.from_dict(plan) if isinstance(plan, dict)
                                          else prepare_caption(text, mode=self.settings.spectrum_mode))
            else:
                # Piper may restart its fraction at each PCM block. This is only a
                # phrase/block estimate: never regress within the same segment.
                self._segment_fraction = max(self._segment_fraction, fraction)
            self._update_playback_tone()
            self._layout_caption()
            self._advance_expressions(semantic_key, self._segment_fraction, signal)
        elif state != "jarvis_speaking":
            self._clear_playback()
            if not self.semantic.active:
                self._set_tone(Tone())
        if self._visible():
            self._render()

    def interpret_text(self, text, render=True):
        """Estimate text without changing the displayed tone ahead of playback."""
        text = str(text)
        if text != self._last_text:
            self._last_estimate = self.analyzer.update(text)
            self._last_text = text
        return self._last_estimate

    def begin_response(self):
        self._cancel_semantics("new_response")
        self.model.micro.cancel()
        self.mood_tracker = MoodTracker(mode=self.settings.spectrum_mode)
        self._clear_playback()
        self._set_tone(Tone())

    def prepare_segment(self, original, display, start):
        """Text-arrival work only; PCM and paint callbacks never classify text."""
        mode = self.settings.spectrum_mode
        if self.mood_tracker.mode != mode:
            self.mood_tracker = MoodTracker(mode=mode)
        # Visual work is bounded even for an unusually large indivisible Markdown
        # block. Speech and SQLite retain the full original; an unanalysed tail
        # is explicitly neutral rather than inventing a mood for unseen text.
        passages = analyze_passages(original[:4000], mode=mode, start=start)[:64]
        events = self.mood_tracker.feed(passages)
        last = events[-1].end if events else start
        if last < start + len(original):
            events += (FieldEvent(last, start + len(original), "", Tone(), Tone()),)
        plan = prepare_caption(display, mode=mode)
        self._prepared_semantic_caption = plan
        return events, plan

    def _trace_semantic(self, stage, reason, key=None, family=None):
        # No answer text or PCM is retained. These are bounded UI-thread events,
        # never per-sample logging in an audio or paint callback.
        key = key if key is not None else (self._semantic_response, "—")
        entry = f"{stage} · {reason} · réponse {key[0]} / segment {key[1]}"
        if family is not None:
            entry += " · " + family
        if not self._semantic_trace or self._semantic_trace[-1] != entry:
            self._semantic_trace.append(entry)

    def semantic_diagnostics(self):
        return ("Semantic Morphing · trace locale (48 étapes maximum)\n"
                + ("\n".join(self._semantic_trace) or "Aucune expression reçue"))

    def _cancel_semantics(self, reason="reset"):
        if self.semantic.active or self._semantic_cues:
            self._trace_semantic("cancelled", reason, self._semantic_playing, self.semantic.family)
        self.semantic.cancel()
        self._semantic_cues.clear()
        self._semantic_completed.clear()
        self._semantic_plans.clear()
        self._semantic_playing = None
        self._semantic_closed = True
        self._semantic_preview = False

    def queue_expressions(self, response_id, segment_id, original, start, end, events):
        """Prepare a bounded timeline on text arrival, never on paint/PCM threads."""
        if (type(response_id) is not int or type(segment_id) is not int
                or response_id < self._semantic_response or segment_id <= 0):
            self._trace_semantic("ignored", "invalid_or_stale_response")
            return
        if response_id > self._semantic_response:
            self._cancel_semantics("newer_response")
            self._semantic_response, self._semantic_closed = response_id, False
            self._semantic_last_trigger = float("-inf")
        if self._semantic_closed:
            self._trace_semantic("ignored", "closed_response", (response_id, segment_id))
            return
        key = (response_id, segment_id)
        source = str(original)[:4000]
        document = parse_text(source)
        visual_only = not any(char.isalnum() for char in document.speech)
        if visual_only and key in self._semantic_plans:
            previous = self._semantic_plans[key]
            self._semantic_plans[key] = prepare_caption(previous.text + document.text,
                                                       mode=self.settings.spectrum_mode)
            if key == self._semantic_playing:
                self._caption_plan = self._semantic_plans[key]
                self._caption_layout_key = None
                self._layout_caption()
        elif not visual_only and self._prepared_semantic_caption is not None:
            self._semantic_plans[key] = self._prepared_semantic_caption
        while len(self._semantic_plans) > 64:
            del self._semantic_plans[next(iter(self._semantic_plans))]
        if not self.settings.semantic_morphing:
            self._trace_semantic("ignored", "disabled", key)
            return  # Caption preservation is independent of the optional effect.
        candidates = []
        for event in events[:64]:
            if event.kind != "expression" or not start <= event.start < event.end <= min(end, start + len(source)):
                continue
            family = expression_family(event.value)
            if family is None:
                self._trace_semantic("ignored", "unsupported_symbol", key)
                continue
            self._trace_semantic("detected", "expression", key, family)
            tail = source[max(0, event.end - start):]
            terminal = not any(char.isalnum() for char in parse_text(tail).speech)
            cue = ExpressionCue(response_id, segment_id, event.start, event.end, family,
                                min(1., max(0., (event.start - start) / max(1, end - start))), terminal)
            if candidates:
                gap = source[max(0, candidates[-1].end - start):event.start - start]
                if len(gap) <= 8 and not any(char.isalnum() for char in gap):
                    prior = candidates[-1]
                    candidates[-1] = replace(prior, end=cue.end, terminal=cue.terminal)
                    continue
            candidates.append(cue)
        existing = {(cue.response_id, cue.segment_id, cue.start, cue.end) for cue in self._semantic_cues}
        for cue in candidates:
            if (cue.response_id, cue.segment_id, cue.start, cue.end) not in existing:
                self._semantic_cues.append(cue)
                self._trace_semantic("scheduled", "segment_end" if cue.terminal else "quiet_pcm",
                                     key, cue.family)
        if not candidates:
            self._trace_semantic("ignored", "no_supported_expression", key)
        if key in self._semantic_completed and self.state in {"silent", "listening"}:
            self._start_expression(key, final=True)
        if self._visible():
            self._render()

    def _advance_expressions(self, key, fraction, signal):
        ready = any((cue.response_id, cue.segment_id) == key and not cue.terminal
                    and cue.fraction <= fraction for cue in self._semantic_cues)
        if ready and isinstance(signal, dict) and _finite(signal.get("rms")) <= .008:
            # A middle-of-phrase cue uses an actual quiet PCM interval. It yields
            # immediately to the next nonquiet callback; this is approximate.
            self._start_expression(key, fraction=fraction)

    def _start_expression(self, key, *, fraction=1., final=False):
        reason = ("disabled" if not self.settings.semantic_morphing else
                  "closed_response" if self._semantic_closed else
                  "hidden" if not self._visible() else
                  "state:" + self.state if self.state in {"user_speaking", "thinking", "dormant"} else None)
        if reason is not None:
            self._trace_semantic("ignored", reason, key)
            return
        now = time.monotonic()
        eligible = [cue for cue in self._semantic_cues
                    if (cue.response_id, cue.segment_id) == key
                    and (final or not cue.terminal and cue.fraction <= fraction)]
        if not eligible:
            return
        # One shape at a time, and no rapid sequence of decorative transformations.
        selected = eligible[0]
        for cue in eligible:
            self._semantic_cues.remove(cue)
        if now - self._semantic_last_trigger < 1.25:
            self._trace_semantic("ignored", "cooldown", key, selected.family)
            return
        if self._trigger_morph(selected.family, now):
            self._trace_semantic("triggered", "segment_end" if final else "quiet_pcm", key, selected.family)
            self._semantic_last_trigger = now
            self._render()

    def complete_segment(self, payload):
        """Actual worker completion, after its PCM callbacks; never an audio timer."""
        key = (payload.get("response_id"), payload.get("segment_id"))
        if (type(key[0]) is not int or type(key[1]) is not int or key[1] <= 0
                or self._semantic_closed or key[0] != self._semantic_response):
            self._trace_semantic("ignored", "closed_or_stale_completion", key)
            return
        if key in self._semantic_completed:
            self._trace_semantic("ignored", "duplicate_completion", key)
            return
        self._semantic_completed.append(key)
        if self._semantic_playing is not None and key < self._semantic_playing:
            self._semantic_cues = deque((cue for cue in self._semantic_cues
                                        if (cue.response_id, cue.segment_id) != key), maxlen=64)
            self._trace_semantic("ignored", "newer_pcm_segment", key)
            return  # A newer segment already owns the real speaking visualizer.
        # PCM display callbacks are deliberately lossy. The reliable worker
        # boundary can still finish its prepared timeline if none of its played
        # callbacks reached Tk; it never invents PCM or delays audio playback.
        self._semantic_playing = key
        self._segment_fraction = 1.
        self._update_playback_tone()
        self._layout_caption()
        self.model.update_event("silent")
        self._start_expression(key, final=True)
        if self._visible():
            self._render()

    def preview_expression(self, family):
        if self._workshop_preview:
            self.clear_preview()
        if family not in FAMILIES or self.state != "silent" or self.app.voice.listening or not self._visible():
            return False
        self.clear_preview()
        self._semantic_preview = True
        self._preview_text = "Expression : " + EXPRESSION_LABELS[family]
        self._trigger_morph(family, time.monotonic())
        if self._visible():
            self._render()
        return True

    def _trigger_morph(self, family, now):
        coords = self.canvas.coords(self.paths[-1])
        origin = tuple(zip(coords[::2], coords[1::2]))
        return self.semantic.trigger(family, now, intensity=self.settings.morph_intensity,
            reduced_motion=self.settings.reduced_motion or not self.settings.animations,
            origin=origin, viewport=(self.canvas.winfo_width(), self.canvas.winfo_height()))

    def _set_tone(self, tone, dominant=None):
        self.tone = tone
        self.dominant_tone = tone if dominant is None else dominant
        mood = self.dominant_tone.name
        if self.settings.microexpressions and self.model.motion_allowed:
            self.model.micro.trigger(mood, time.monotonic())
        self.model.emotional_inertia = {"colère": .85, "peur": .9, "attachement": 1.1,
                                        "apaisement": 1.2, "deuil": 1.15}.get(mood, 1.0)
        self.model.emotional_curve = {"colère": 1.12, "peur": 1.05,
                                     "attachement": .88, "apaisement": .8}.get(mood, 1.0)
        self._accent.duration = {"reactive": .22, "cinematic": .45, "calm": .8}[self.settings.fluidity]
        self._accent.retarget(self._target_accent(), time.monotonic())

    def _clear_playback(self):
        self.caption_text, self.caption_data = "", None
        self._segment_key, self._segment_fraction, self._segment_events = None, 0.0, []
        self._caption_plan = None
        self._caption_window = CaptionWindow("", ())
        self._caption_layout_key = None

    def _layout_caption(self):
        if self._caption_plan is None:
            return
        if self._visible():
            width_px, height_px = self.canvas.winfo_width(), self.canvas.winfo_height()
            fit_key = (width_px, height_px, self.settings.subtitle_size,
                       float(self.canvas.tk.call("tk", "scaling")),
                       self.caption_footer.winfo_reqheight(), self.controls.winfo_reqheight())
            if fit_key != self._caption_fit_key:
                self._caption_fit_key = fit_key
                footer_top = min(height_px * .855 - self.caption_footer.winfo_reqheight() / 2,
                                 height_px * .92 - self.controls.winfo_reqheight() / 2
                                 - self.caption_footer.winfo_reqheight() - 8)
                core_bottom = height_px / 2 + core_radius(width_px, height_px) * 1.4 + 8
                room = max(24, footer_top - core_bottom - 8)
                self._caption_font.configure(size=-12)
                minimum_rows = self._caption_font.metrics("linespace") * 2
                self._caption_footer_visible = room >= minimum_rows
                if not self._caption_footer_visible:
                    footer_top = height_px * .92 - self.controls.winfo_reqheight() / 2 - 8
                    room = max(minimum_rows, footer_top - core_bottom - 8)
                self._caption_font.configure(size=self.settings.subtitle_size)
                if self._caption_font.metrics("linespace") * 2 > room:
                    # Keep the saved preference. A tiny window has less physical
                    # space: fit two readable rows rather than covering Stop.
                    pixels = max(12, int(room / 2) - 2)
                    self._caption_font.configure(size=-pixels)
                    while self._caption_font.metrics("linespace") * 2 > room and pixels > 12:
                        pixels -= 1
                        self._caption_font.configure(size=-pixels)
                self._caption_top = max(core_bottom, footer_top - self._caption_font.metrics("linespace") * 2 - 6)
        width = max(40, self.canvas.winfo_width() * .82 - 20) if self._visible() else None
        measure = self._caption_font.measure if width is not None else None
        key = (id(self._caption_plan), self._segment_fraction, width, self.settings.subtitle_size)
        if key != self._caption_layout_key:
            self._caption_layout_key = key
            self._caption_window = self._caption_plan.window(self._segment_fraction, measure=measure, width=width)
            self.caption_text = self._caption_window.text

    def _events_for_caption(self, caption):
        events = caption.get("spectrum_events")
        result = []
        if isinstance(events, (list, tuple)):
            for event in events:
                if not isinstance(event, dict):
                    continue
                start, end = _finite(event.get("start"), -1), _finite(event.get("end"), -1)
                if start < 0 or end <= start:
                    continue
                text = str(event.get("text", ""))
                raw = event.get("tone")
                if (caption.get("spectrum_mode", self.settings.spectrum_mode) == self.settings.spectrum_mode
                        and isinstance(raw, dict) and isinstance(raw.get("name"), str)
                        and isinstance(raw.get("color"), str)
                        and re.fullmatch(r"#[0-9a-fA-F]{6}", raw["color"])):
                    words = raw.get("words", ())
                    tone = Tone(raw["name"], raw["color"],
                                tuple(word for word in words if isinstance(word, str))
                                if isinstance(words, (list, tuple)) else (),
                                max(0.0, min(1.0, _finite(raw.get("confidence")))))
                else:
                    tone = self.interpret_text(text, render=False)
                # A stale or malformed event must never override an explicit neutral mode.
                dominant = tone
                raw_dominant = event.get("dominant")
                if (caption.get("spectrum_mode", self.settings.spectrum_mode) == self.settings.spectrum_mode
                        and isinstance(raw_dominant, dict) and isinstance(raw_dominant.get("name"), str)
                        and isinstance(raw_dominant.get("color"), str)
                        and re.fullmatch(r"#[0-9a-fA-F]{6}", raw_dominant["color"])):
                    dominant = Tone(raw_dominant["name"], raw_dominant["color"])
                if self.settings.spectrum_mode == "neutral":
                    tone = dominant = Tone()
                result.append((start, end, tone, dominant))
        if not result:
            text = str(caption.get("text", ""))
            tone = self.interpret_text(text, render=False)
            result = [(0, max(1, len(text)), tone, tone)]
        return sorted(result, key=lambda event: event[0])

    def _update_playback_tone(self):
        if not self._segment_events or self.caption_data is None:
            return
        events = self._segment_events
        start = _finite(self.caption_data.get("original_start"), events[0][0])
        end = _finite(self.caption_data.get("original_end"), events[-1][1])
        position = start + self._segment_fraction * max(0, end - start)
        chosen = events[0]
        for event in events[1:]:
            if event[0] > position:
                break
            chosen = event
        self._set_tone(chosen[2], chosen[3])

    def preview_text(self, text):
        """Explicit visual-only preview; never starts capture, inference or speech."""
        if self._workshop_preview:
            self.clear_preview()
        if self.state not in {"silent", "dormant"} or self.app.voice.listening:
            return None
        self._cancel_semantics()
        self._cancel_scenario()
        self._preview_text = str(text)
        tone = self.interpret_text(self._preview_text, render=False)
        self._set_tone(tone)
        if self._visible():
            self._render()
        return tone

    def clear_preview(self):
        if self._semantic_preview:
            self._cancel_semantics()
        scenario = self._scenario_index is not None
        self._cancel_scenario()
        if self._preview_text is not None:
            self._preview_text = None
            if scenario or self._workshop_preview:
                self.model.update_event("silent")
            self._workshop_preview = False
            self.model.micro.cancel()
            self._set_tone(Tone())
            if self._visible():
                self._render()

    def _cancel_scenario(self):
        if self._preview_id is not None:
            self.app.root.after_cancel(self._preview_id)
            self._preview_id = None
        self._scenario_index = None

    def preview_workshop(self, family=None):
        """The existing mesh previews appearance, never a fabricated audio wave."""
        if family not in {None, "line", *MICRO_LABELS}:
            return False
        if self.app.voice.listening or (self.state not in {"silent", "dormant"} and not self._workshop_preview):
            return False
        self.clear_preview()
        self._cancel_semantics()
        self._workshop_preview = True
        self._preview_text = "Noyau hors ligne" if family is None else MICRO_LABELS.get(family, "Ligne sans signal")
        self.model.update_event("silent" if family == "line" else "thinking")
        self._set_tone(Tone())
        self.model.micro = MicroExpression()
        if family in MICRO_LABELS:
            self.model.micro.trigger(family, time.monotonic())
        self._render()
        return True

    def preview_scenario(self):
        """Offline symbolic forms/colors only. It never invents an audio signal."""
        if self._workshop_preview:
            self.clear_preview()
        if self.app.voice.listening or self.state not in {"silent", "dormant"}:
            return False
        self._cancel_semantics()
        self._cancel_scenario()
        self._scenario_index = 0
        self._scenario_step()
        return True

    def _scenario_step(self):
        self._preview_id = None
        index = self._scenario_index
        if index is None:
            return
        phrases = ("J'ai confiance et espoir pour demain.",
                   "Maintenant je ressens de la tendresse et de l'affection.",
                   "Je suis inquiet face au danger.", "Désormais je suis calme et serein.")
        if index >= len(phrases):
            self._scenario_index = None
            self._preview_text = None
            self.model.update_event("silent")
            self._set_tone(Tone())
            self._render()
            return
        self._preview_text = phrases[index]
        self.model.update_event("thinking")
        self._set_tone(self.interpret_text(phrases[index], render=False))
        self._scenario_index = index + 1
        self._render()
        self._preview_id = self.app.root.after(2500, self._scenario_step)

    def _target_accent(self):
        mode = self.settings.accent_mode
        if mode == "none":
            return palette(self.settings.background)["muted"]
        dominant = getattr(self, "dominant_tone", self.tone)
        field_color = (dominant.color if self.tone.name == "neutralité" else
                       mix(dominant.color, self.tone.color, .22))
        emotional = dominant.name != "neutralité" or self.tone.name != "neutralité"
        if emotional and self.settings.emotional_palette == "soft":
            field_color = mix(field_color, "#d5efff", .18)
        elif emotional and self.settings.emotional_palette == "warm":
            field_color = mix(field_color, "#ffbc82", .18)
        color = (self.settings.fixed_color if mode == "fixed" else
                 CYAN if mode == "cyan" or self.settings.spectrum_mode == "neutral" else mix(CYAN, field_color,
                                                 self.settings.spectrum_intensity / 100))
        return readable_accent(color, self.settings.background)

    def mesh_accent(self, now=None):
        return self._accent.color(time.monotonic() if now is None else now)

    def update_operation(self, key, detail=""):
        if key not in OPERATIONAL:
            return
        self.operation = key
        self.operation_detail = str(detail)
        self._operation_explicit = True
        if key in {"error", "inactive"}:
            self._workshop_preview = False
            self.model.micro.cancel()
            self._cancel_semantics("operation:" + key)
            self._cancel_scenario()
            self._cancel_animation()
            self._preview_text = None
            self._clear_playback()
            self._set_tone(Tone())
            self._accent = AccentTransition(self._target_accent())
            if self.state != "dormant":
                self.model.update_event("silent")
        if self._visible():
            self._render()

    def update_timing(self, values, new_turn=False, complete=False):
        """Measured durations only; missing stages stay absent, never simulated."""
        if new_turn:
            self.timings = {}
            self._timing_recorded = False
        for key in ("vad_silence_ms", "stt_ms", "llm_wait_ms", "token_to_audio_ms",
                    "turn_to_audio_ms", "speech_to_audio_ms"):
            value = values.get(key) if isinstance(values, dict) else None
            if isinstance(value, (int, float)) and not isinstance(value, bool) and _finite(value, -1) >= 0:
                self.timings[key] = round(value)
        if complete and not self._timing_recorded and "speech_to_audio_ms" in self.timings:
            self.timing_history = (self.timing_history + [self.timings["speech_to_audio_ms"]])[-12:]
            self._timing_recorded = True
        if self._visible():
            self._render_timing(self.canvas.winfo_width(), self.canvas.winfo_height())

    def toggle_timing(self):
        self.set_options(timing_monitor=not self.settings.timing_monitor)

    def toggle_diagnostic(self, _event=None):
        self.set_options(diagnostic_mode=not self.settings.diagnostic_mode)
        return "break"

    def update_microphone(self, state, detail=""):
        if state not in MIC_LABELS:
            raise ValueError("État du microphone inconnu.")
        self.microphone_state, self.microphone_detail = state, str(detail)[:256]
        if state in {"disabled", "error", "starting", "voice", "stt"}:
            self._cancel_semantics("microphone:" + state)
            self.model.micro.cancel()
        if state in {"disabled", "error"}:
            self._workshop_preview = False
            self._cancel_scenario()
            self._preview_text = None
            self._clear_playback()
            self._set_tone(Tone())
            self._accent = AccentTransition(self._target_accent())
            if self.state != "dormant":
                self.model.update_event("silent")
            self._cancel_animation()
        if self._visible():
            if state in {"disabled", "error"}:
                self._render()
            else:
                self._update_overlays(self.canvas.winfo_width())

    def _render_timing(self, width, height):
        key = (width, height, self.settings, tuple(sorted(self.timings.items())),
               tuple(self.timing_history), self.state == "dormant")
        if key == self._timing_render_key:
            return
        self._timing_render_key = key
        if self.settings.mini_mode or not self.settings.timing_monitor or not self.settings.diagnostic_mode or self.state == "dormant":
            self.timing_panel.place_forget()
            return
        # An overlay in the side gutter: never changes the canvas or mesh centre.
        available = width / 2 - core_radius(width, height) - width * 0.045 - 14
        panel_width = max(100, min(300, round(available)))
        self.timing_panel.place(relx=0.955, rely=0.28, anchor="ne", width=panel_width)
        rows = (("vad_silence_ms", "Silence VAD"), ("stt_ms", "STT"),
                ("llm_wait_ms", "Attente LLM"), ("token_to_audio_ms", "Texte → son ≈"),
                ("turn_to_audio_ms", "Fin tour → son ≈"), ("speech_to_audio_ms", "Parole → son ≈"))
        self.timing_values.configure(text="\n".join(
            f"{label}  {self.timings[key]}" if key in self.timings else f"{label}  —" for key, label in rows))
        self.timing_note.configure(wraplength=max(80, panel_width - 20))
        chart = self.timing_chart
        chart.delete("all")
        chart_width = max(60, panel_width - 20)
        colors = palette(self.settings.background)
        grid = mix(colors["background"], colors["foreground"], 0.13)
        for y in (9, 22, 35):
            chart.create_line(0, y, chart_width, y, fill=grid)
        for x in range(0, chart_width, 30):
            chart.create_line(x, 0, x, 44, fill=grid)
        if self.timing_history:
            maximum = max(1, max(self.timing_history))
            points = [(5 + i * (chart_width - 10) / 11, 40 - value / maximum * 34)
                      for i, value in enumerate(self.timing_history)]
            if len(points) > 1:
                chart.create_line(*[v for point in points for v in point], fill=colors["accent"],
                                  width=2, smooth=True, splinesteps=12)
            x, y = points[-1]
            chart.create_oval(x - 2, y - 2, x + 2, y + 2, fill=colors["accent"], outline="")

    def _visible(self):
        return self.window is not None and bool(self.window.winfo_exists() and self.window.winfo_viewable())

    def _cancel_animation(self):
        if self.after_id is not None:
            self.app.root.after_cancel(self.after_id)
            self.after_id = None

    def _render(self):
        self._cancel_animation()
        if not self._visible():
            return
        started = time.monotonic()
        width, height = self.canvas.winfo_width(), self.canvas.winfo_height()
        points = self.model.frame(width, height, started)
        was_semantic = self.semantic.active
        semantic_frame = self.semantic.frame(points, width, height, started, profile=self.settings.profile)
        if semantic_frame is not None:
            points = semantic_frame.contour
        elif was_semantic:
            self._semantic_preview = False
            self._preview_text = None
            if self.state in {"silent", "listening"}:
                self._set_tone(Tone())
        coords = [coordinate for point in points for coordinate in point]
        scale = dpi_scale(self.canvas.tk.call("tk", "scaling"))
        fps, count, arc_count = render_quality(self.settings, width, height, scale,
                                               started < self._slow_until)
        if self.state == "dormant":
            count, arc_count = 1, 0
        selected = ({3}, {2, 3}, {0, 2, 3}, {0, 1, 2, 3})[count - 1]
        widths = stroke_widths(self.settings.visualizer_thickness, scale)
        accent = self.mesh_accent(started)
        # Local mood changes the halo/inertia and symbolic thinking curves only.
        # Speech displacement and amplitude still come exclusively from PCM.
        mood_halo = {"colère": 1.15, "peur": 1.08, "apaisement": .85,
                     "attachement": 1.1}.get(self.dominant_tone.name, 1.0)
        strength = 1.0 if semantic_frame is not None else 0.25 if self.state == "dormant" else 0.72 if self.state == "silent" else 1.0
        breath = 0.0
        if self.state == "thinking" and self.model.motion_allowed:
            breath = math.sin((started - self.model.state_since) * 1.1)
            strength = 0.9 + breath * 0.08
        # Every halo uses precisely the same coordinates, never another visualizer.
        for index, path in enumerate(self.paths):
            opacity = min(1, (0.14, 0.22, 0.42, 0.96)[index] * strength *
                          (mood_halo if index != 3 else 1))
            if index != 3:
                opacity *= self.settings.halo_intensity / 100 * AMBIENCES[self.settings.ambience][2]
            self.canvas.coords(path, *coords)
            self.canvas.itemconfigure(path, state="normal" if index in selected else "hidden",
                                      width=widths[index],
                                      fill=mix(self.settings.background, accent, opacity))
        phase = (started - self.model.state_since) * 0.055 if self.model.motion_allowed else 0.0
        highlight = mix(accent, self._colors["foreground"], .32)
        for index, (path, offset, length) in enumerate(zip(self.orbital_paths,
                                                         (0.03, 0.43, 0.72), (0.20, 0.12, 0.16))):
            visible = semantic_frame is None and self.state == "thinking" and index < arc_count
            if visible:
                self.canvas.coords(path, *_mesh_arc(points, offset + phase, length))
            self.canvas.itemconfigure(path, state="normal" if visible else "hidden",
                                      width=widths[3] * (0.72 + index * 0.09),
                                      fill=mix(self.settings.background, highlight, 0.98 - index * 0.07))
        detail_paths = self.semantic_paths if semantic_frame is not None or self._semantic_drawn else ()
        for index, paths in enumerate(detail_paths):
            detail = (semantic_frame.details[index] if semantic_frame is not None
                      and index < len(semantic_frame.details) else ())
            for layer, path in enumerate(paths):
                visible = bool(detail) and (layer == 1 or self.settings.halos and count > 1)
                if visible:
                    self.canvas.coords(path, *[coordinate for point in detail for coordinate in point])
                    opacity = semantic_frame.detail_opacity * (.18 if layer == 0 else .96)
                    self.canvas.itemconfigure(path, width=widths[1 if layer == 0 else 3] * .65,
                                              fill=mix(self.settings.background, accent, opacity))
                self.canvas.itemconfigure(path, state="normal" if visible else "hidden")
        self._semantic_drawn = semantic_frame is not None
        self._update_overlays(width)
        elapsed = time.monotonic() - started
        if elapsed > 0.012:
            self._slow_until = started + 3
        normal_animation = (self.model.needs_animation(started) or self.state != "dormant"
                            and self.settings.animations and self._accent.active(started))
        delay = round(1000 / fps)
        if self.semantic.active:
            semantic_delay = self.semantic.next_delay_ms(started, delay)
            if semantic_delay is not None:
                delay = min(delay, semantic_delay) if normal_animation else semantic_delay
        if normal_animation or self.semantic.active:
            self.after_id = self.app.root.after(delay, self._tick)

    def _tick(self):
        self.after_id = None
        self._render()

    def toggle_mini(self, _event=None):
        self.set_options(mini_mode=not self.settings.mini_mode)
        return "break"

    def _apply_window_mode(self):
        if self.window is None or self._window_mode == self.settings.mini_mode:
            return
        mini = self.settings.mini_mode
        self._window_mode = mini
        self._controls_layout = self._overlay_key = self._timing_render_key = None
        if mini:
            self._normal_geometry = self.window.geometry()
            self.window.attributes("-fullscreen", False)
            self.window.minsize(320, 240)
            self.window.geometry("420x300")
        else:
            self.window.minsize(min(620, max(320, self.window.winfo_screenwidth() - 80)),
                                min(440, max(240, self.window.winfo_screenheight() - 100)))
            if self._normal_geometry:
                self.window.geometry(self._normal_geometry)

    def _layout_controls(self, width, height):
        key = (width, height, self.settings.mini_mode)
        if key == self._controls_layout:
            return
        self._controls_layout = key
        mini = self.settings.mini_mode
        family = getattr(self.app, "font_family", "Segoe UI")
        for button in self.buttons:
            button.configure(font=(family, -12 if mini else 10), padx=8 if mini else 12,
                             pady=6 if mini else 8)
        for button in self.header_buttons:
            button.pack_forget()
            if not mini or button is self.mini_button:
                button.pack(side="left", padx=4)
        self.mini_button.configure(text="Étendre" if mini else "Mini")
        for button in self.control_buttons:
            button.pack_forget()
            if not mini or button is not self.sleep_button:
                button.pack(side="left", padx=3 if mini else 4)
        self.header_controls.place(relx=.97 if mini else .955, y=10 if mini else 0,
                                   rely=0 if mini else .045, anchor="ne")
        self.controls.place(relx=.5, rely=.92, anchor="center")
        if mini:
            self.identity.place_forget()
            self.mic_label.configure(font=(family, -12), wraplength=max(160, width - 24), justify="left")
            self.state_label.configure(font=(family, -11))
            self.operation_label.configure(font=(family, -11), justify="center")
            self.mic_label.place(x=12, y=44, relx=0, rely=0, anchor="nw")
            self.state_label.place(x=12, y=12, relx=0, rely=0, anchor="nw")
            self.operation_label.place_forget()
            self.tone_label.place_forget()
        else:
            self.identity.place(relx=.045, rely=.045, anchor="nw")
            self.mic_label.configure(font=(family, 9), wraplength=0)
            self.state_label.configure(font=(family, 10))
            self.operation_label.configure(font=(family, 9), justify="right")
            self.mic_label.place(x=0, y=0, relx=.045, rely=.15, anchor="nw")
            self.state_label.place(x=0, y=0, relx=.045, rely=.105, anchor="nw")
            self.operation_label.place(relx=.955, rely=.15, relwidth=.43, anchor="ne")

    def _update_overlays(self, width):
        self._layout_controls(width, self.canvas.winfo_height())
        listening = bool(self.app.voice.listening)
        mic = getattr(self.app.voice, "microphone_state", self.microphone_state)
        if not isinstance(mic, str) or mic not in MIC_LABELS:
            mic = "open" if listening else "disabled"
        if mic == "disabled" and listening and not hasattr(self.app.voice, "microphone_state"):
            mic = "open"
        key = (width, self.state, listening, mic, self.settings, self.tone.name,
               self.dominant_tone.name, self._preview_text, self.operation, self.operation_detail)
        if key != self._overlay_key:
            self._overlay_key = key
            self.state_label.configure(text=("APERÇU HORS LIGNE · " if self._preview_text is not None else "")
                                       + STATE_LABELS[self.state] + (" · SOUS-TITRES ≈" if self.state == "jarvis_speaking" else ""))
            self.mic_label.configure(text=MIC_LABELS[mic] + (" · écoute maintenue" if mic == "error" and listening else " · LOCAL"),
                                     fg=readable_accent(OPERATIONAL["error"]["color"], self.settings.background)
                                     if mic == "error" else palette(self.settings.background)["muted"])
            self.listen_button.configure(text=("Couper micro" if listening else "Micro") if self.settings.mini_mode
                                         else "Désactiver l’écoute" if listening else "Activer l’écoute")
            self.sleep_button.configure(text="Réveiller" if self.state == "dormant" else "Sommeil")
            mode = self.settings.accent_mode
            self.tone_label.configure(text=(("Aperçu local : " if self._preview_text is not None else
                                            SPECTRUM_LABELS[self.settings.spectrum_mode] + " · estimation : ")
                                           + self.dominant_tone.name if mode == "adaptive" else ACCENT_LABELS[mode]))
            if self.settings.diagnostic_mode and not self.settings.mini_mode:
                self.tone_label.place(relx=.045, rely=.195, anchor="nw")
            else:
                self.tone_label.place_forget()
            operational = OPERATIONAL[self.operation]
            symbol = {"allowed": "✓", "info": "●", "caution": "!", "confirm": "?", "error": "!", "inactive": "○"}[self.operation]
            detail = self.operation_detail.strip()
            if self.settings.mini_mode:
                detail = detail[:60] if self.operation in {"error", "confirm", "caution"} else ""
            if len(detail) > 140:
                detail = detail[:137] + "…"
            label = symbol + " " + operational["label"] + ("\n" + detail if detail else "")
            self.operation_label.configure(text=label, wraplength=max(180, round(width * (.90 if self.settings.mini_mode else .40))),
                                           fg=readable_accent(operational["color"], self.settings.background))
            if self.settings.mini_mode:
                if self.operation in {"error", "confirm", "caution", "allowed"}:
                    self.operation_label.place(relx=.5, rely=.73, relwidth=.92, anchor="center")
                else:
                    self.operation_label.place_forget()
        self._render_caption()
        self._render_timing(width, self.canvas.winfo_height())
        if not self.settings.mini_mode and self.settings.subtitles and self.caption_text and self.state == "jarvis_speaking":
            self.caption_label.place(relx=0.5, y=self._caption_top or self.canvas.winfo_height() * .70,
                                     relwidth=0.82, anchor="n")
            if self._caption_footer_visible:
                self.caption_footer.place(relx=0.5, rely=0.855, anchor="center")
            else:
                self.caption_footer.place_forget()
        else:
            self.caption_label.place_forget()
            self.caption_footer.place_forget()

    def _render_caption(self):
        # This is paint only: all classification/tokenization/positions were
        # prepared at text arrival; PCM selected the already prepared window.
        enabled = (self.settings.emotional_subtitles and self.settings.accent_mode != "none"
                   and self.settings.spectrum_mode != "neutral")
        marks = tuple(mark for mark in self._caption_window.marks
                      if enabled and mark.tone in {self.tone.name, self.dominant_tone.name})
        key = (self.caption_text, marks, self.settings.emotional_subtitles, self.settings.accent_mode)
        if key != self._rendered_caption:
            self._rendered_caption = key
            self.caption_label.configure(state="normal")
            self.caption_label.delete("1.0", "end")
            self.caption_label.insert("1.0", self.caption_text, "center")
            for mark in marks:
                self.caption_label.tag_add("keyword", f"1.0+{mark.start}c", f"1.0+{mark.end}c")
            self.caption_label.configure(state="disabled")
        if not marks:
            return
        color_key = (self.mesh_accent(), self.settings.subtitle_coloring, self.settings.background)
        if color_key == getattr(self, "_caption_color_key", None):
            return
        self._caption_color_key = color_key
        colors = self._colors
        amount = {"discreet": .45, "normal": .75, "expressive": 1}[self.settings.subtitle_coloring]
        color = readable_accent(mix(colors["foreground"], self.mesh_accent(), amount), self.settings.background)
        if color != getattr(self, "_caption_color", None):
            self._caption_color = color
            self.caption_label.tag_configure("keyword", foreground=color)

    def copy_caption(self):
        if self.caption_text:
            self.app.root.clipboard_clear()
            self.app.root.clipboard_append(self.caption_text)

    def _apply_colors(self):
        if self.window is None:
            return
        colors = palette(self.settings.background)
        self._colors = colors
        self._overlay_key = None
        self._caption_color = None
        self._caption_color_key = None
        bg, fg = colors["background"], colors["foreground"]
        self.window.configure(bg=bg)
        self.canvas.configure(bg=bg)
        self.timing_panel.configure(bg=bg, highlightbackground=mix(bg, fg, 0.2))
        self.timing_chart.configure(bg=bg)
        for widget in (self.timing_title, self.timing_values, self.timing_note):
            widget.configure(bg=bg, fg=colors["muted"])
        self.timing_title.configure(fg=colors["accent"])
        for widget in (self.controls, self.header_controls, self.caption_footer):
            widget.configure(bg=bg)
        for widget in (self.identity, self.state_label, self.mic_label, self.tone_label,
                       self.operation_label, self.caption_label, self.caption_note):
            widget.configure(bg=bg, fg=fg)
        self.state_label.configure(fg=colors["accent"])
        self.mic_label.configure(fg=colors["muted"])
        self.tone_label.configure(fg=colors["muted"])
        self.caption_note.configure(fg=colors["muted"])
        caption_foreground = mix(bg, fg, .86)
        self.caption_label.configure(fg=caption_foreground if contrast(bg, caption_foreground) >= 4.5 else fg)
        self._caption_fit_key = None
        for button in self.buttons:
            button.configure(bg=colors["button"], fg=fg,
                             activebackground=mix(bg, fg, 0.15), activeforeground=fg,
                             highlightbackground=bg, highlightcolor=colors["accent"])

    def set_options(self, **changes):
        candidate = PresenceSettings.from_dict({**asdict(self.settings), **changes})
        values = {**self._saved_preferences, **asdict(candidate)}
        try:
            self.app.store.set_preference("presence", values)
        except Exception:
            messagebox.showerror("Préférences PRESENCE", "Impossible d’enregistrer les préférences locales. Vérifiez les droits et l’espace disque.", parent=self.window or self.app.root)
            return False
        self._saved_preferences = values
        old_mode = self.settings.spectrum_mode
        self.settings = self.model.settings = candidate
        if not candidate.microexpressions or candidate.reduced_motion or not candidate.animations:
            self.model.micro.cancel()
        self._apply_window_mode()
        if not candidate.semantic_morphing:
            self.semantic.cancel()
            self._semantic_cues.clear()
            if self._semantic_preview:
                self._semantic_preview, self._preview_text = False, None
        elif self.semantic.active and (candidate.reduced_motion or not candidate.animations):
            self._trigger_morph(self.semantic.family, time.monotonic())
        if candidate.spectrum_mode != old_mode:
            self.analyzer = ToneAnalyzer(mode=candidate.spectrum_mode, hold_seconds=0)
            self.mood_tracker = MoodTracker(mode=candidate.spectrum_mode)
            self._last_text = None
            if self.caption_data is not None and self.state == "jarvis_speaking":
                self._segment_events = self._events_for_caption(self.caption_data)
                self._caption_plan = prepare_caption(str(self.caption_data.get("text", "")), mode=candidate.spectrum_mode)
                self._caption_layout_key = None
                self._update_playback_tone()
            elif self._preview_text is not None:
                self._set_tone(self.interpret_text(self._preview_text, render=False))
            if candidate.spectrum_mode == "neutral":
                self._set_tone(Tone())
        self._accent.retarget(self._target_accent(), time.monotonic())
        self._apply_colors()
        self._layout_caption()
        self._render()
        return True

    def set_background(self, color):
        if not isinstance(color, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
            return False
        return self.set_options(background=color.lower())

    def reset_background(self):
        return self.set_background("#000000")

    def choose_background(self):
        _rgb_value, color = colorchooser.askcolor(self.settings.background, title="Fond PRESENCE",
                                                parent=self.window or self.app.root)
        if color:
            self.set_background(color)

    def open_settings(self):
        if self.settings_dialog is not None and self.settings_dialog.winfo_exists():
            self.settings_dialog.lift()
            return
        dialog = self.settings_dialog = tk.Toplevel(self.window)
        dialog.title("PRESENCE · atelier")
        dialog.transient(self.window)
        colors = palette(self.settings.background)
        dialog.configure(bg=colors["background"], padx=20, pady=18)
        screen_w, screen_h = dialog.winfo_screenwidth(), dialog.winfo_screenheight()
        dialog.maxsize(max(320, screen_w - 40), max(300, screen_h - 60))
        # Reserve the close control before the expandable notebook. Each page
        # scrolls independently when large Windows fonts need more height.
        ttk.Button(dialog, text="Fermer", command=dialog.destroy).pack(side="bottom", fill="x", pady=(12, 0))
        notebook = ttk.Notebook(dialog)
        notebook.pack(fill="both", expand=True)
        def page(title):
            outer = tk.Frame(notebook, bg=colors["background"])
            notebook.add(outer, text=title)
            canvas = tk.Canvas(outer, bg=colors["background"], highlightthickness=0,
                               width=min(600, screen_w - 120), height=min(660, screen_h - 240))
            scroll = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
            scroll.pack(side="right", fill="y")
            canvas.pack(side="left", fill="both", expand=True)
            canvas.configure(yscrollcommand=scroll.set)
            inner = tk.Frame(canvas, bg=colors["background"], padx=12, pady=10)
            item = canvas.create_window(0, 0, anchor="nw", window=inner)
            inner.bind("<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all")))
            canvas.bind("<Configure>", lambda event: canvas.itemconfigure(item, width=event.width))
            def reveal(event):
                if event.widget is inner:
                    return
                y = event.widget.winfo_rooty() - inner.winfo_rooty()
                bottom = y + event.widget.winfo_height()
                top = canvas.canvasy(0)
                if y < top or bottom > top + canvas.winfo_height():
                    canvas.yview_moveto(max(0, bottom - canvas.winfo_height()) / max(1, inner.winfo_height()))
            inner.bind("<FocusIn>", reveal)
            # FocusIn propagates through the toplevel bindtag; only reveal
            # descendants of this page, without changing global mouse bindings.
            dialog.bind("<FocusIn>", lambda event: reveal(event) if str(event.widget).startswith(str(inner) + ".") else None, add="+")
            def wheel(event):
                if (str(event.widget).startswith(str(inner))
                        and not isinstance(event.widget, (ttk.Combobox, tk.Scale))):
                    direction = -1 if getattr(event, "num", None) == 4 or getattr(event, "delta", 0) > 0 else 1
                    canvas.yview_scroll(direction * 3, "units")
                    return "break"
            for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
                dialog.bind(sequence, wheel, add="+")
            return inner
        workshop = page("Atelier")
        visual = page("Visualiseur")
        spectrum_page = page("Spectre et aperçu")
        captions_page = page("Sous-titres")
        expressions_page = page("Expressions")
        tk.Label(workshop, text="Un seul visualiseur · aperçu hors ligne sans micro ni modèle",
                 bg=colors["background"], fg=colors["muted"], wraplength=420,
                 justify="left").pack(anchor="w", pady=(0, 10))
        for key, label, choices in (("ambience", "Ambiance visuelle", AMBIENCE_LABELS),
                                     ("emotional_palette", "Palette émotionnelle", PALETTE_LABELS)):
            tk.Label(workshop, text=label, bg=colors["background"], fg=colors["foreground"]).pack(anchor="w")
            variable = tk.StringVar(value=choices[getattr(self.settings, key)])
            choice = ttk.Combobox(workshop, name=key, state="readonly", textvariable=variable,
                                  values=list(choices.values()))
            choice.pack(fill="x", pady=(4, 10))
            choice.bind("<<ComboboxSelected>>", lambda _event, k=key, v=variable, c=choices:
                        self.set_options(**{k: next(option for option, label in c.items() if label == v.get())}))
        for key, label, low, high in (("halo_intensity", "Intensité du halo (%)", 0, 100),
                                       ("thinking_size", "Taille du noyau THINKING (%)", 70, 130)):
            tk.Label(workshop, text=label, bg=colors["background"], fg=colors["foreground"]).pack(anchor="w")
            variable = tk.IntVar(value=getattr(self.settings, key))
            tk.Scale(workshop, name=key, from_=low, to=high, resolution=1, orient="horizontal", variable=variable,
                     bg=colors["background"], fg=colors["foreground"], troughcolor=colors["button"],
                     highlightthickness=0, command=lambda value, k=key:
                     self.set_options(**{k: round(float(value))})).pack(fill="x", pady=(0, 10))
        micro_enabled = tk.BooleanVar(value=self.settings.microexpressions)
        tk.Checkbutton(workshop, text="Microexpressions contextuelles", variable=micro_enabled,
                       bg=colors["background"], fg=colors["foreground"], selectcolor=colors["button"],
                       command=lambda: self.set_options(microexpressions=micro_enabled.get())).pack(anchor="w", pady=6)
        micro_family = tk.StringVar(value=MICRO_LABELS["surprise"])
        ttk.Combobox(workshop, name="micro_family", state="readonly", textvariable=micro_family,
                     values=list(MICRO_LABELS.values())).pack(fill="x", pady=4)
        ttk.Button(workshop, text="Prévisualiser la microexpression", command=lambda:
                   self.preview_workshop(next(key for key, label in MICRO_LABELS.items() if label == micro_family.get()))).pack(fill="x", pady=4)
        ttk.Button(workshop, text="Prévisualiser le noyau THINKING", command=self.preview_workshop).pack(fill="x", pady=4)
        ttk.Button(workshop, text="Prévisualiser la ligne sans signal", command=lambda: self.preview_workshop("line")).pack(fill="x", pady=4)
        ttk.Button(workshop, text="Arrêter l’aperçu", command=self.clear_preview).pack(fill="x", pady=4)
        ttk.Button(workshop, text="Mini-PRESENCE / fenêtre normale (F10)", command=self.toggle_mini).pack(fill="x", pady=(12, 4))
        tk.Label(workshop, text="Épaisseur, fluidité et qualité : onglet Visualiseur. Morphing : Expressions.\n"
                 "Ces ambiances sont visuelles ; elles ne modifient ni voix, ni permissions, ni capacités.",
                 wraplength=420, justify="left", bg=colors["background"], fg=colors["muted"]).pack(anchor="w", pady=8)
        morph_enabled = tk.BooleanVar(value=self.settings.semantic_morphing)
        ttk.Checkbutton(expressions_page, text="Semantic Morphing", variable=morph_enabled,
                        command=lambda: self.set_options(semantic_morphing=morph_enabled.get())).pack(anchor="w", pady=8)
        tk.Label(expressions_page, text="Intensité de l’expression", bg=colors["background"],
                 fg=colors["foreground"]).pack(anchor="w")
        morph_intensity = tk.StringVar(value=MORPH_INTENSITY_LABELS[self.settings.morph_intensity])
        morph_choice = ttk.Combobox(expressions_page, state="readonly", textvariable=morph_intensity,
                                    values=list(MORPH_INTENSITY_LABELS.values()))
        morph_choice.pack(fill="x", pady=8)
        morph_choice.bind("<<ComboboxSelected>>", lambda _event: self.set_options(
            morph_intensity=next(key for key, label in MORPH_INTENSITY_LABELS.items() if label == morph_intensity.get())))
        tk.Label(expressions_page, text="Aperçu vectoriel local · huit familles", bg=colors["background"],
                 fg=colors["foreground"]).pack(anchor="w", pady=(12, 4))
        morph_family = tk.StringVar(value=EXPRESSION_LABELS["smile"])
        ttk.Combobox(expressions_page, state="readonly", textvariable=morph_family,
                     values=list(EXPRESSION_LABELS.values())).pack(fill="x", pady=4)
        morph_status = tk.StringVar(value="Au repos, sans Ollama ni Piper")
        def preview_morph():
            family = next(key for key, label in EXPRESSION_LABELS.items() if label == morph_family.get())
            available = self.preview_expression(family)
            morph_status.set("Aperçu hors ligne : " + EXPRESSION_LABELS[family] if available
                             else "Désactivez l’écoute et attendez le repos pour cet aperçu.")
        ttk.Button(expressions_page, text="Prévisualiser l’expression", command=preview_morph).pack(fill="x", pady=6)
        ttk.Button(expressions_page, text="Arrêter l’aperçu", command=self.clear_preview).pack(fill="x", pady=4)
        tk.Label(expressions_page, textvariable=morph_status, bg=colors["background"],
                 fg=colors["muted"], wraplength=360).pack(anchor="w", pady=8)
        tk.Label(expressions_page, text="Réduction des mouvements / animations désactivées : symbole statique.\n"
                 "Synchronisation estimée par segment PCM. Au milieu d’une phrase, un creux audio est prioritaire ;\n"
                 "sinon l’expression attend la fin du segment. Toute reprise audio ou parole micro annule le symbole.",
                 bg=colors["background"], fg=colors["muted"], wraplength=360, justify="left").pack(anchor="w", pady=8)
        tk.Label(visual, text="Profil graphique", bg=colors["background"], fg=colors["foreground"]).pack(anchor="w")
        profile = tk.StringVar(value=PROFILE_LABELS[self.settings.profile])
        choice = ttk.Combobox(visual, state="readonly", values=list(PROFILE_LABELS.values()), textvariable=profile)
        choice.pack(fill="x", pady=(6, 12))
        choice.bind("<<ComboboxSelected>>", lambda _event: self.set_options(
            profile=next(key for key, label in PROFILE_LABELS.items() if label == profile.get())))
        tk.Label(visual, text="Fluidité", bg=colors["background"], fg=colors["foreground"]).pack(anchor="w")
        fluidity = tk.StringVar(value=FLUIDITY_LABELS[self.settings.fluidity])
        flow = ttk.Combobox(visual, state="readonly", values=list(FLUIDITY_LABELS.values()), textvariable=fluidity)
        flow.pack(fill="x", pady=(4, 8))
        flow.bind("<<ComboboxSelected>>", lambda _event: self.set_options(
            fluidity=next(key for key, label in FLUIDITY_LABELS.items() if label == fluidity.get())))
        tk.Label(visual, text="Expressivité de l’onde (%)", bg=colors["background"],
                 fg=colors["foreground"]).pack(anchor="w")
        expressivity = tk.IntVar(value=self.settings.wave_expressivity)
        tk.Scale(visual, name="wave_expressivity", from_=0, to=100, resolution=1, orient="horizontal", variable=expressivity,
                 bg=colors["background"], fg=colors["foreground"], highlightthickness=0,
                 troughcolor=colors["button"],
                 command=lambda value: self.set_options(wave_expressivity=round(float(value)))).pack(fill="x")
        tk.Label(visual, text="Affichage uniquement · aucun effet sur le micro ou la détection vocale",
                 wraplength=360, justify="left", bg=colors["background"],
                 fg=colors["muted"]).pack(anchor="w", pady=(0, 8))
        tk.Label(visual, text="Épaisseur du visualiseur", bg=colors["background"],
                 fg=colors["foreground"]).pack(anchor="w", pady=(8, 0))
        thickness = tk.IntVar(value=self.settings.visualizer_thickness)
        tk.Scale(visual, from_=1, to=10, resolution=1, orient="horizontal", variable=thickness,
                 bg=colors["background"], fg=colors["foreground"], highlightthickness=0,
                 troughcolor=colors["button"],
                 command=lambda value: self.set_options(visualizer_thickness=round(float(value)))).pack(fill="x")
        reduced = tk.BooleanVar(value=self.settings.reduced_motion)
        subtitles = tk.BooleanVar(value=self.settings.subtitles)
        halos = tk.BooleanVar(value=self.settings.halos)
        animations = tk.BooleanVar(value=self.settings.animations)
        for label, variable, key in (("Réduire les mouvements", reduced, "reduced_motion"),
                                     ("Afficher les sous-titres", subtitles, "subtitles"),
                                     ("Halos lumineux", halos, "halos"),
                                     ("Animations visuelles", animations, "animations")):
            tk.Checkbutton(visual, text=label, variable=variable, bg=colors["background"],
                           fg=colors["foreground"], selectcolor=colors["button"],
                           activebackground=colors["background"], activeforeground=colors["foreground"],
                           command=lambda v=variable, k=key: self.set_options(**{k: v.get()})).pack(anchor="w", pady=5)
        tk.Label(spectrum_page, text="Accents de tonalité (estimation, sans effet sur les permissions)",
                 wraplength=360, justify="left", bg=colors["background"],
                 fg=colors["foreground"]).pack(anchor="w", pady=(12, 4))
        accent = tk.StringVar(value=ACCENT_LABELS[self.settings.accent_mode])
        accent_choice = ttk.Combobox(spectrum_page, state="readonly", values=list(ACCENT_LABELS.values()), textvariable=accent, width=35)
        accent_choice.pack(fill="x", pady=4)
        accent_choice.bind("<<ComboboxSelected>>", lambda _event: self.set_options(
            accent_mode=next(key for key, label in ACCENT_LABELS.items() if label == accent.get())))
        tk.Label(spectrum_page, text="Interprétation du spectre", bg=colors["background"],
                 fg=colors["foreground"]).pack(anchor="w", pady=(10, 4))
        spectrum = tk.StringVar(value=SPECTRUM_LABELS[self.settings.spectrum_mode])
        spectrum_choice = ttk.Combobox(spectrum_page, state="readonly", values=list(SPECTRUM_LABELS.values()),
                                       textvariable=spectrum, width=35)
        spectrum_choice.pack(fill="x", pady=4)
        spectrum_choice.bind("<<ComboboxSelected>>", lambda _event: self.set_options(
            spectrum_mode=next(key for key, label in SPECTRUM_LABELS.items() if label == spectrum.get())))
        tk.Label(spectrum_page, text="Intensité du spectre (%)", bg=colors["background"],
                 fg=colors["foreground"]).pack(anchor="w")
        intensity = tk.IntVar(value=self.settings.spectrum_intensity)
        tk.Scale(spectrum_page, name="spectrum_intensity", from_=0, to=100, resolution=1, orient="horizontal", variable=intensity,
                 bg=colors["background"], fg=colors["foreground"], highlightthickness=0,
                 troughcolor=colors["button"],
                 command=lambda value: self.set_options(spectrum_intensity=round(float(value)))).pack(fill="x")
        tk.Label(spectrum_page, text="Aperçu local · phrase au choix", bg=colors["background"],
                 fg=colors["muted"]).pack(anchor="w", pady=(10, 4))
        preview_phrase = tk.StringVar(value="Je suis heureux et ravi.")
        ttk.Entry(spectrum_page, textvariable=preview_phrase).pack(fill="x")
        preview_result = tk.Label(spectrum_page, text="Sans micro, modèle ni réseau", anchor="w",
                                  bg=colors["background"], fg=colors["muted"])
        preview_result.pack(fill="x", pady=4)

        def preview():
            tone = self.preview_text(preview_phrase.get())
            preview_result.configure(text=("Aperçu : " + tone.name if tone is not None else
                                           "Aperçu disponible lorsque la voix est au repos"),
                                     fg=self._target_accent() if tone is not None else colors["muted"])

        ttk.Button(spectrum_page, text="Prévisualiser la phrase", command=preview).pack(fill="x", pady=4)
        ttk.Button(spectrum_page, text="Scénario hors ligne · espoir → affection → tension → apaisement",
                   command=self.preview_scenario).pack(fill="x", pady=4)
        ttk.Button(spectrum_page, text="Arrêter l’aperçu", command=self.clear_preview).pack(fill="x", pady=4)
        emotion_caps = tk.BooleanVar(value=self.settings.emotional_subtitles)
        ttk.Checkbutton(captions_page, text="Sous-titres émotionnels", variable=emotion_caps,
                        command=lambda: self.set_options(emotional_subtitles=emotion_caps.get())).pack(anchor="w", pady=8)
        tk.Label(captions_page, text="Colorisation", bg=colors["background"], fg=colors["foreground"]).pack(anchor="w")
        coloring = tk.StringVar(value=COLORING_LABELS[self.settings.subtitle_coloring])
        color_choice = ttk.Combobox(captions_page, textvariable=coloring,
                                    values=list(COLORING_LABELS.values()), state="readonly")
        color_choice.pack(fill="x", pady=8)
        color_choice.bind("<<ComboboxSelected>>", lambda _event: self.set_options(
            subtitle_coloring=next(key for key, label in COLORING_LABELS.items() if label == coloring.get())))
        tk.Label(captions_page, text="Taille préférée · ajustée dans les petites fenêtres", bg=colors["background"], fg=colors["foreground"], wraplength=360).pack(anchor="w")
        size = tk.IntVar(value=self.settings.subtitle_size)
        tk.Scale(captions_page, from_=12, to=32, variable=size, orient="horizontal", resolution=1,
                 bg=colors["background"], fg=colors["foreground"], highlightthickness=0,
                 command=lambda value: self.set_options(subtitle_size=round(float(value)))).pack(fill="x")
        ttk.Button(captions_page, text="Immersion / Diagnostic (F9)", command=self.toggle_diagnostic).pack(fill="x", pady=12)
        tk.Label(captions_page, text="Deux lignes maximum. Synchronisation estimée par groupes de mots / bloc PCM.\nLes indicateurs micro, arrêt et sécurité restent visibles en Immersion.",
                 wraplength=360, justify="left", bg=colors["background"], fg=colors["muted"]).pack(fill="x", pady=8)

        def closed(event):
            if event.widget is dialog:
                self.clear_preview()
                self.settings_dialog = None

        dialog.bind("<Destroy>", closed)

        def choose_accent():
            _rgb_value, color = colorchooser.askcolor(self.settings.fixed_color,
                                                    title="Accent personnalisé", parent=dialog)
            if color:
                self.set_options(fixed_color=color, accent_mode="fixed")
                accent.set(ACCENT_LABELS["fixed"])

        ttk.Button(spectrum_page, text="Choisir la couleur d’accent…", command=choose_accent).pack(fill="x", pady=4)
        ttk.Button(visual, text="Choisir le fond…", command=self.choose_background).pack(fill="x", pady=(12, 4))
        ttk.Button(visual, text="Rétablir le noir", command=self.reset_background).pack(fill="x", pady=4)

    def toggle_listening(self):
        if self.state == "dormant":
            self.wake()
        self.app.voice.toggle()
        return "break"

    def emergency(self):
        self.app.voice.emergency()
        if self.state != "dormant":
            self.update_event("silent")
        self.update_operation("error", "Arrêt demandé : microphone, génération et lecture arrêtés.")

    def toggle_sleep(self):
        if self.state == "dormant":
            self.wake()
        else:
            self.sleep()

    def sleep(self):
        # Stop real audio/inference first; no visual transition delays cancellation.
        self.app.voice.emergency()
        self.update_event("dormant")
        self.update_operation("inactive", "Microphone, génération et lecture arrêtés.")

    def wake(self):
        self.app.voice.stop_listening()
        self.model.update_event("silent")
        self._preview_text = None
        self._clear_playback()
        self._set_tone(Tone())
        self.update_operation("inactive", "Microphone désactivé. Activez l’écoute pour parler.")
        self._render()

    def toggle_fullscreen(self, _event=None):
        if self.window is not None:
            self.window.attributes("-fullscreen", not bool(self.window.attributes("-fullscreen")))
        return "break"

    def exit_fullscreen(self, _event=None):
        if self.window is not None:
            self.window.attributes("-fullscreen", False)
        return "break"

    def return_to_command(self):
        self._cancel_semantics("return_to_command")
        self.clear_preview()
        if self.window is not None:
            self.window.withdraw()
        self._cancel_animation()
        self.app.root.deiconify()
        self.app.root.lift()
        self.app.root.focus_set()

    def _on_resize(self, _event=None):
        if self._visible():
            self._layout_caption()
            self._render()

    def _on_map(self, event):
        if event.widget is self.window:
            self._render()

    def _on_unmap(self, event):
        if event.widget is self.window:
            self._cancel_semantics("hidden")
            self.clear_preview()
            self._cancel_animation()

    def _on_destroy(self, event):
        if event.widget is self.window:
            self._cancel_semantics()
            self._cancel_scenario()
            self._caption_font = None
            self._cancel_animation()
            self.window = self.canvas = None
            self.settings_dialog = None

    def close(self):
        self._cancel_semantics("closed")
        self.clear_preview()
        self._cancel_scenario()
        self._cancel_animation()
        window = self.window
        self._caption_font = None
        self.window = self.canvas = None
        self._window_mode = self._controls_layout = None
        self.settings_dialog = None
        if window is not None and window.winfo_exists():
            window.destroy()
