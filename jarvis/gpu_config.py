"""Validated, model-free artistic preferences for the optional GPU renderer.

This is a value object, not a second persistence layer. The application stores
its dictionary in the existing SQLite preference store, separately from the
Canvas artwork. Defaults preserve the approved GPU 3.0 composition.
"""
from dataclasses import asdict, dataclass, field, fields
import math
from types import MappingProxyType


PROFILES = ("eco", "balanced", "cinematic")
RENDER_SCALES = ("auto", "100", "125", "150", "200")
SECTIONS = ("Noyau", "Halo et lumière", "Anneaux", "Particules", "Animations et états", "Expressions", "Performances")
LEVELS = ("essential", "personalize", "advanced")


def _setting(default, label, section, level, low, high, help="", unit="percent", step=1):
    return field(default=default, metadata=dict(label=label, section=section, level=level,
                 low=low, high=high, step=step, help=help or label, unit=unit))


@dataclass(frozen=True)
class GpuSettings:
    profile: str = "balanced"
    render_scale: str = "auto"
    core_size: int = _setting(100, "Taille du noyau (%)", "Noyau", "essential", 70, 125,
                             "Rayon de la sphère ; les traits et l'occlusion suivent ce même rayon.")
    core_brightness: int = _setting(100, "Luminosité du noyau (%)", "Noyau", "personalize", 0, 200)
    core_opacity: int = _setting(100, "Opacité du noyau (%)", "Noyau", "personalize", 10, 100)
    core_translucency: int = _setting(100, "Translucidité optique (%)", "Noyau", "advanced", 0, 200,
                                     "Transmission optique simulée, sans réfraction d'un environnement.")
    core_fresnel: int = _setting(100, "Liseré iridescent (%)", "Noyau", "personalize", 0, 200)
    color_hue: int = _setting(0, "Nuance de la matière (°)", "Noyau", "personalize", -180, 180, unit="degrees")
    color_saturation: int = _setting(100, "Saturation (%)", "Noyau", "personalize", 0, 200)
    core_reflections: int = _setting(100, "Reflets (%)", "Noyau", "personalize", 0, 200)
    surface_speed: int = _setting(100, "Vitesse de la matière (%)", "Noyau", "advanced", 0, 200)
    plasma_intensity: int = _setting(100, "Plasma intérieur (%)", "Noyau", "personalize", 0, 200)
    plasma_speed: int = _setting(100, "Vitesse du plasma (%)", "Noyau", "advanced", 0, 200)
    breathing: int = _setting(100, "Respiration symbolique (%)", "Noyau", "personalize", 0, 200,
                             "Mouvement visuel d'état, distinct de l'activité audio réelle.")
    halo_intensity: int = _setting(100, "Luminosité du halo (%)", "Halo et lumière", "essential", 0, 200,
                                  "Intensité indépendante du rayon de diffusion.")
    halo_radius: int = _setting(100, "Taille du halo (%)", "Halo et lumière", "essential", 25, 250,
                               "Étend la diffusion sans multiplier sa luminosité.")
    halo_opacity: int = _setting(100, "Opacité du halo (%)", "Halo et lumière", "personalize", 0, 100)
    halo_softness: int = _setting(100, "Douceur de diffusion (%)", "Halo et lumière", "personalize", 40, 200)
    bloom_intensity: int = _setting(100, "Bloom HDR (%)", "Halo et lumière", "personalize", 0, 200)
    bloom_threshold: int = _setting(80, "Seuil du bloom (%)", "Halo et lumière", "advanced", 20, 200,
                                   "Seules les hautes lumières dépassant ce seuil alimentent le bloom.")
    bloom_radius: int = _setting(100, "Diffusion du bloom (%)", "Halo et lumière", "advanced", 25, 200)
    audio_reactivity: int = _setting(100, "Réactivité visuelle à la voix (%)", "Halo et lumière", "personalize", 0, 200,
                                    "Modifie l'affichage seulement, jamais le PCM, le gain ou le VAD.")
    pulse_amplitude: int = _setting(100, "Amplitude des pulsations (%)", "Halo et lumière", "personalize", 0, 200)
    pulse_radius: int = _setting(100, "Rayon de pulsation vocale (%)", "Halo et lumière", "personalize", 0, 200,
                                "Expansion de l'aura pilotée par le PCM joué ; indépendante du rayon statique du halo.")
    audio_attack_ms: int = _setting(55, "Attaque audio (ms)", "Halo et lumière", "advanced", 20, 250, unit="milliseconds")
    audio_release_ms: int = _setting(240, "Retour au calme (ms)", "Halo et lumière", "personalize", 80, 1000, unit="milliseconds")
    bass_contribution: int = _setting(100, "Contribution des graves (%)", "Halo et lumière", "advanced", 0, 200)
    mid_contribution: int = _setting(100, "Contribution des médiums (%)", "Halo et lumière", "advanced", 0, 200)
    treble_contribution: int = _setting(100, "Contribution des aigus (%)", "Halo et lumière", "advanced", 0, 200)
    ring_radius: int = _setting(100, "Rayon des orbites (%)", "Anneaux", "personalize", 80, 140)
    ring_thickness: int = _setting(100, "Épaisseur des anneaux (%)", "Anneaux", "personalize", 40, 250)
    ring_brightness: int = _setting(100, "Luminosité des anneaux (%)", "Anneaux", "personalize", 0, 200)
    ring_opacity: int = _setting(100, "Opacité des anneaux (%)", "Anneaux", "personalize", 0, 100)
    ring_count: int = _setting(3, "Nombre d'anneaux", "Anneaux", "personalize", 1, 3, unit="count")
    ring_spacing: int = _setting(100, "Espacement des anneaux (%)", "Anneaux", "personalize", 40, 160)
    ring_speed: int = _setting(100, "Vitesse des anneaux (%)", "Anneaux", "essential", 0, 200)
    ring_trails: int = _setting(100, "Traînées lumineuses (%)", "Anneaux", "advanced", 0, 200)
    ring_1_tilt: int = _setting(0, "Inclinaison de l'anneau 1 (°)", "Anneaux", "advanced", -35, 35, unit="degrees")
    ring_2_tilt: int = _setting(0, "Inclinaison de l'anneau 2 (°)", "Anneaux", "advanced", -35, 35, unit="degrees")
    ring_3_tilt: int = _setting(0, "Inclinaison de l'anneau 3 (°)", "Anneaux", "advanced", -35, 35, unit="degrees")
    ring_orientation: int = _setting(0, "Orientation générale (°)", "Anneaux", "advanced", -90, 90, unit="degrees")
    particle_density: int = _setting(100, "Quantité de particules (%)", "Particules", "essential", 0, 200,
                                    "Nombre borné selon le profil, sans allocation de géométrie supplémentaire.")
    particle_size: int = _setting(100, "Taille des particules (%)", "Particules", "essential", 25, 300)
    particle_variation: int = _setting(100, "Variation de taille (%)", "Particules", "personalize", 0, 200)
    particle_brightness: int = _setting(100, "Luminosité des particules (%)", "Particules", "personalize", 0, 200)
    particle_opacity: int = _setting(100, "Opacité des particules (%)", "Particules", "personalize", 0, 100)
    particle_speed: int = _setting(100, "Vitesse des particules (%)", "Particules", "personalize", 0, 200)
    particle_dispersion: int = _setting(100, "Dispersion des particules (%)", "Particules", "advanced", 0, 200)
    particle_distance: int = _setting(100, "Distance de distribution (%)", "Particules", "advanced", 60, 140)
    particle_lifetime: int = _setting(100, "Durée de l'enveloppe lumineuse (%)", "Particules", "advanced", 40, 250,
                                     "Apparitions et disparitions déterministes, sans clignotement aléatoire.")
    particle_trails: int = _setting(100, "Traînées des particules (%)", "Particules", "advanced", 0, 200)
    particle_colors: int = _setting(0, "Variation des couleurs (%)", "Particules", "advanced", 0, 100)
    particle_audio: int = _setting(100, "Réaction des particules à la voix (%)", "Particules", "personalize", 0, 200)
    thinking_contraction: int = _setting(8, "Contraction THINKING (%)", "Animations et états", "personalize", 0, 15)
    thinking_speed: int = _setting(100, "Vitesse THINKING (%)", "Animations et états", "personalize", 0, 250)
    speaking_speed: int = _setting(100, "Vitesse pendant la parole (%)", "Animations et états", "personalize", 0, 250)
    listening_speed: int = _setting(100, "Vitesse pendant l'écoute (%)", "Animations et états", "personalize", 0, 250)
    idle_speed: int = _setting(0, "Rotation au repos (%)", "Animations et états", "advanced", 0, 100,
                              "Zéro conserve le repos statique et sa consommation minimale.")
    transition_ms: int = _setting(300, "Transition du noyau (ms)", "Animations et états", "personalize", 80, 1200, unit="milliseconds")
    ring_acceleration_ms: int = _setting(450, "Inertie des anneaux (ms)", "Animations et états", "advanced", 100, 1500, unit="milliseconds")
    converging_intensity: int = _setting(100, "Réception de la parole (%)", "Animations et états", "personalize", 0, 200,
                                       "Énergie convergente lors de la parole réellement détectée ; aucun effet sur le VAD.")
    radiating_intensity: int = _setting(100, "Émission de la voix (%)", "Animations et états", "personalize", 0, 200,
                                      "Énergie rayonnante pendant le PCM Piper, sans modifier le volume ni la voix.")
    expression_brightness: int = _setting(100, "Luminosité des traits (%)", "Expressions", "personalize", 0, 200)
    expression_thickness: int = _setting(100, "Épaisseur des traits (%)", "Expressions", "personalize", 40, 200)
    expression_opacity: int = _setting(100, "Opacité des traits (%)", "Expressions", "personalize", 0, 100)
    expression_size: int = _setting(100, "Taille du visage / symbole (%)", "Expressions", "personalize", 60, 115)
    expression_transition_ms: int = _setting(360, "Transition de l'expression (ms)", "Expressions", "advanced", 120, 1000, unit="milliseconds")
    expression_hold_ms: int = _setting(650, "Maintien de l'expression (ms)", "Expressions", "personalize", 250, 2500, unit="milliseconds")
    expression_ring_speed: int = _setting(100, "Réorganisation des couronnes (%)", "Expressions", "advanced", 40, 200)
    expression_core_light: int = _setting(0, "Illumination du noyau pendant l'expression (%)", "Expressions", "advanced", 0, 100)
    fps_limit: int = _setting(60, "Limite globale d'images/s", "Performances", "advanced", 15, 60, unit="count")

    @classmethod
    def from_dict(cls, values):
        values = values if isinstance(values, dict) else {}
        clean = {}
        for key, spec in FIELD_SPECS.items():
            value = values.get(key, spec.default)
            try:
                valid = (not isinstance(value, bool) and isinstance(value, (int, float))
                         and math.isfinite(value))
            except OverflowError:
                valid = False
            if not valid:
                value = spec.default
            clean[key] = max(spec.low, min(spec.high, round(value)))
        profile = values.get("profile", "balanced")
        clean["profile"] = profile if isinstance(profile, str) and profile in PROFILES else "balanced"
        scale = values.get("render_scale", "auto")
        if type(scale) is int and scale in (100, 125, 150, 200):
            scale = str(scale)
        clean["render_scale"] = scale if isinstance(scale, str) and scale in RENDER_SCALES else "auto"
        return cls(**clean)

    def to_dict(self):
        return asdict(self)

    @classmethod
    def reference_30(cls, profile="balanced"):
        """The approved artwork, with the optional 3.1 energy layers disabled."""
        return cls.from_dict({"profile": profile, "pulse_radius": 0,
                              "converging_intensity": 0, "radiating_intensity": 0})

    @property
    def frames_per_second(self):
        return min(self.fps_limit, {"eco": 15, "balanced": 60, "cinematic": 60}[self.profile])

    def uniforms(self):
        """Packed numeric shader values. The same mapping drives Studio metadata."""
        result = []
        for key in UNIFORM_KEYS:
            value, unit = getattr(self, key), FIELD_SPECS[key].unit
            result.append(value * math.pi / 180 if unit == "degrees" else
                          value / 1000 if unit == "milliseconds" else
                          float(value) if unit == "count" else value / 100)
        result.extend([0.] * ((-len(result)) % 4))
        return tuple(result)

    def morph_clock(self, now, started, *, reduced_motion=False):
        """Map GPU-only durations onto the shared controller's unchanged clock."""
        from .morphing import ENTER_SECONDS, HOLD_SECONDS, RETURN_SECONDS
        if not all(math.isfinite(value) for value in (now, started)):
            raise ValueError("L'horloge d'expression doit être finie.")
        elapsed = max(0., now - started)
        enter, hold = self.expression_transition_ms / 1000, self.expression_hold_ms / 1000
        if reduced_motion:
            logical = elapsed / hold * HOLD_SECONDS
        elif elapsed < enter:
            logical = elapsed / enter * ENTER_SECONDS
        elif elapsed < enter + hold:
            logical = ENTER_SECONDS + (elapsed - enter) / hold * HOLD_SECONDS
        else:
            logical = ENTER_SECONDS + HOLD_SECONDS + (elapsed - enter - hold) / enter * RETURN_SECONDS
        return started + logical


@dataclass(frozen=True)
class SettingSpec:
    key: str
    label: str
    section: str
    level: str
    low: int
    high: int
    step: int
    default: int
    help: str
    unit: str


FIELD_SPECS = MappingProxyType({item.name: SettingSpec(key=item.name, default=item.default, **item.metadata)
                              for item in fields(GpuSettings) if item.metadata})
UNIFORM_KEYS = tuple(FIELD_SPECS)
UNIFORM_VECTORS = (len(UNIFORM_KEYS) + 3) // 4
