"""GPU artistic preferences: bounded migration, independent controls and timing.

These tests need no OpenGL context, Tk window, voice backend or model weights.
"""
from dataclasses import FrozenInstanceError, fields
import json
import math
import subprocess
import sys
import unittest

from jarvis.gpu_config import FIELD_SPECS, RENDER_SCALES, UNIFORM_KEYS, GpuSettings
from jarvis import morphing
from jarvis.morphing import ENTER_SECONDS, HOLD_SECONDS, RETURN_SECONDS


class GpuSettingsTests(unittest.TestCase):
    def test_empty_and_legacy_preferences_keep_the_approved_style_defaults(self):
        defaults = GpuSettings()
        self.assertEqual(defaults.profile, "balanced")
        for key in ("core_size", "halo_intensity", "halo_radius",
                    "particle_size", "particle_density", "ring_speed"):
            with self.subTest(key=key):
                self.assertEqual(getattr(defaults, key), 100)
        self.assertEqual(defaults.expression_transition_ms, 360)
        self.assertEqual(defaults.expression_hold_ms, 650)
        for raw in ({}, None, [], False, "old invalid value", 14):
            with self.subTest(kind=type(raw).__name__):
                self.assertEqual(GpuSettings.from_dict(raw), defaults)

    def test_roundtrip_does_not_mutate_the_source_or_retain_unknown_fields(self):
        raw = {"halo_intensity": 145, "halo_radius": 80,
               "particle_size": 175, "profile": "eco", "future_shader_key": {"keep": True}}
        source = json.loads(json.dumps(raw))
        candidate = GpuSettings.from_dict(raw)
        self.assertEqual(raw, source)
        self.assertEqual(candidate.halo_intensity, 145)
        self.assertEqual(candidate.halo_radius, 80)
        self.assertEqual(candidate.profile, "eco")
        self.assertNotIn("future_shader_key", candidate.to_dict())
        self.assertEqual(GpuSettings.from_dict(json.loads(json.dumps(candidate.to_dict()))), candidate)
        exported = candidate.to_dict()
        exported["halo_intensity"] = 0
        self.assertEqual(candidate.halo_intensity, 145)

    def test_every_slider_has_a_bounded_default_and_a_documented_category(self):
        defaults = GpuSettings()
        numeric = {entry.name for entry in fields(defaults) if isinstance(entry.default, int)}
        self.assertEqual(set(FIELD_SPECS), numeric)
        for key, spec in FIELD_SPECS.items():
            with self.subTest(key=key):
                value = getattr(defaults, key)
                self.assertEqual(value, spec.default)
                self.assertLessEqual(spec.low, value)
                self.assertLessEqual(value, spec.high)
                self.assertGreater(spec.high, spec.low)
                self.assertGreater(spec.step, 0)
                self.assertTrue(spec.label.strip())
                self.assertTrue(spec.section.strip())
                self.assertIn(spec.level, {"essential", "personalize", "advanced"})
                self.assertTrue(spec.help.strip())

    def test_all_numeric_preferences_reject_nonfinite_and_non_numeric_values(self):
        defaults = GpuSettings()
        invalid = (True, False, None, "100", [], {}, math.nan, math.inf, -math.inf, 10 ** 1000)
        for key in FIELD_SPECS:
            for value in invalid:
                with self.subTest(key=key, kind=type(value).__name__):
                    settings = GpuSettings.from_dict({key: value})
                    self.assertEqual(getattr(settings, key), getattr(defaults, key))

    def test_finite_slider_values_are_clamped_without_escaping_gpu_limits(self):
        for key, spec in FIELD_SPECS.items():
            with self.subTest(key=key):
                below = GpuSettings.from_dict({key: spec.low - 10000})
                above = GpuSettings.from_dict({key: spec.high + 10000})
                self.assertEqual(getattr(below, key), spec.low)
                self.assertEqual(getattr(above, key), spec.high)
                rounded = getattr(GpuSettings.from_dict({key: spec.default + .2}), key)
                self.assertIsInstance(rounded, int)
                self.assertLessEqual(spec.low, rounded)
                self.assertLessEqual(rounded, spec.high)

    def test_halo_size_brightness_and_particle_size_density_are_independent(self):
        defaults = GpuSettings().to_dict()
        controls = ("halo_intensity", "halo_radius", "particle_size", "particle_density")
        for key in controls:
            spec = FIELD_SPECS[key]
            value = spec.low if defaults[key] != spec.low else spec.high
            settings = GpuSettings.from_dict({key: value}).to_dict()
            with self.subTest(key=key):
                self.assertEqual(settings[key], value)
                self.assertEqual({name for name in settings if settings[name] != defaults[name]}, {key})

    def test_quality_profiles_are_validated_and_settings_are_immutable(self):
        for profile in ("eco", "balanced", "cinematic"):
            self.assertEqual(GpuSettings.from_dict({"profile": profile}).profile, profile)
        for profile in (None, True, [], {}, "ultra", "GPU"):
            with self.subTest(kind=type(profile).__name__):
                self.assertEqual(GpuSettings.from_dict({"profile": profile}).profile, "balanced")
        with self.assertRaises(FrozenInstanceError):
            GpuSettings().halo_intensity = 0

    def test_render_scale_is_a_validated_independent_enum_and_migrates_safely(self):
        self.assertEqual(GpuSettings.from_dict({}).render_scale, "auto")
        for scale in RENDER_SCALES:
            with self.subTest(scale=scale):
                candidate = GpuSettings.from_dict({"render_scale": scale, "halo_radius": 160})
                self.assertEqual(candidate.render_scale, scale)
                self.assertEqual(candidate.halo_radius, 160)
                self.assertNotIn("render_scale", UNIFORM_KEYS)
                self.assertEqual(candidate, GpuSettings.from_dict(candidate.to_dict()))
        self.assertEqual(GpuSettings.from_dict({"render_scale": 125}).render_scale, "125")
        for scale in (True, None, "150%", "999", 1.25, [], {}):
            with self.subTest(scale=scale):
                self.assertEqual(GpuSettings.from_dict({"render_scale": scale}).render_scale, "auto")

    def test_animated_nominal_budget_is_sixty_except_explicit_eco_or_lower_limit(self):
        for profile, nominal in (("eco", 15), ("balanced", 60), ("cinematic", 60)):
            for limit in (15, 30, 60):
                self.assertEqual(GpuSettings(profile=profile, fps_limit=limit).frames_per_second,
                                 min(limit, nominal))

    def test_uniform_payload_is_finite_bounded_and_has_no_optional_import_side_effect(self):
        self.assertEqual(len(UNIFORM_KEYS), len(set(UNIFORM_KEYS)))
        for raw in ({}, {key: spec.high for key, spec in FIELD_SPECS.items()},
                    {key: spec.low for key, spec in FIELD_SPECS.items()}):
            payload = GpuSettings.from_dict(raw).uniforms()
            self.assertGreaterEqual(len(payload), len(UNIFORM_KEYS))
            self.assertEqual(len(payload) % 4, 0)
            self.assertTrue(all(math.isfinite(value) and abs(value) < 10000 for value in payload))
        code = ("import sys; import jarvis.gpu_config; "
                "assert not any(name in sys.modules for name in "
                "('tkinter','moderngl','glfw','numpy','sounddevice','piper'))")
        subprocess.run([sys.executable, "-c", code], check=True, capture_output=True)

    def test_custom_expression_times_map_to_existing_controller_without_jumps(self):
        original = (ENTER_SECONDS, HOLD_SECONDS, RETURN_SECONDS)
        settings = GpuSettings.from_dict({"expression_transition_ms": 700, "expression_hold_ms": 1400})
        start, enter, hold = 17., .7, 1.4
        total = 2 * enter + hold
        limits = ((0., 0.), (enter, ENTER_SECONDS),
                  (enter + hold, ENTER_SECONDS + HOLD_SECONDS),
                  (total, sum(original)))
        for elapsed, expected in limits:
            with self.subTest(elapsed=elapsed):
                self.assertAlmostEqual(settings.morph_clock(start + elapsed, start), start + expected, places=6)
        values = [settings.morph_clock(start + total * index / 1000, start) for index in range(1001)]
        self.assertTrue(all(a <= b for a, b in zip(values, values[1:])))
        for elapsed, _ in limits:
            if elapsed:
                before = settings.morph_clock(start + elapsed - 1e-6, start)
                after = settings.morph_clock(start + elapsed + 1e-6, start)
                self.assertLess(abs(after - before), 1e-4)
        self.assertGreaterEqual(settings.morph_clock(start + total + .1, start), start + sum(original))
        self.assertEqual((morphing.ENTER_SECONDS, morphing.HOLD_SECONDS,
                          morphing.RETURN_SECONDS), original)

    def test_reduced_motion_uses_only_the_configured_static_hold(self):
        settings = GpuSettings.from_dict({"expression_transition_ms": 700, "expression_hold_ms": 1400})
        start = 22.
        for fraction in (0., .25, .5, 1.):
            self.assertAlmostEqual(settings.morph_clock(start + 1.4 * fraction, start, reduced_motion=True),
                                   start + HOLD_SECONDS * fraction, places=6)


if __name__ == "__main__":
    unittest.main()
