"""Geometry and real Tk rendering contracts; no simulated audio is called live."""
import math
import tempfile
import time
import tkinter as tk
import unittest
from pathlib import Path
from tkinter import ttk
from types import SimpleNamespace
from unittest.mock import Mock, patch

from jarvis.presence import (POINT_COUNT, PROFILES, AccentTransition, PresenceModel, PresenceSettings,
                             PresenceView, _mesh_arc, _smooth_wave, contrast, core_radius,
                             dpi_scale, mix, palette, readable_accent, render_quality, stroke_widths)
from jarvis.spectrum import CYAN, OPERATIONAL, Tone, caption_group
from jarvis.storage import Store


SIGNAL = {"rms": 0.12, "wave": [0.05, -0.2, 0.15, 0.08, -0.13, 0.3, -0.08, 0.02]}


def bounds(points):
    xs, ys = zip(*points)
    return min(xs), min(ys), max(xs), max(ys)


def widgets(parent):
    return [widget for child in parent.winfo_children()
            for widget in [child, *widgets(child)]]


class PlaybackSpectrumTests(unittest.TestCase):
    def setUp(self):
        self.app = SimpleNamespace(root=Mock(), store=Mock(), voice=Mock(listening=False))
        self.app.store.get_preference.return_value = {}
        self.view = PresenceView(self.app)

    def event(self, name, color, start=0, end=10):
        return {"start": start, "end": end, "text": "texte source",
                "tone": {"name": name, "color": color, "words": [], "confidence": 1}}

    def test_new_spectrum_preferences_are_validated(self):
        self.assertEqual(PresenceSettings().spectrum_mode, "expression")
        self.assertEqual(PresenceSettings().spectrum_intensity, 65)
        for mode in ("expression", "thematic", "neutral"):
            self.assertEqual(PresenceSettings.from_dict({"spectrum_mode": mode}).spectrum_mode, mode)
        for value in (-1, 101, True, "90", float("nan"), float("inf"), None):
            self.assertEqual(PresenceSettings.from_dict({"spectrum_intensity": value}).spectrum_intensity, 65)
        self.assertEqual(PresenceSettings.from_dict({"spectrum_mode": []}).spectrum_mode, "expression")

    def test_color_transition_is_smooth_and_retargets_without_a_flash(self):
        transition = AccentTransition()
        transition.retarget("#ff717a", 10)
        self.assertEqual(transition.color(10), CYAN)
        middle = transition.color(10.2)
        self.assertNotIn(middle, (CYAN, "#ff717a"))
        transition.retarget("#70dca0", 10.2)
        self.assertEqual(transition.color(10.2), middle)
        self.assertEqual(transition.color(11), "#70dca0")
        self.assertFalse(transition.active(11))

    def test_text_estimation_never_changes_visible_tone_before_pcm(self):
        self.view.set_options(spectrum_mode="thematic")
        self.assertEqual(self.view.interpret_text("colère et rage").name, "colère")
        self.assertEqual(self.view.tone, Tone())
        self.assertEqual(self.view.mesh_accent(), CYAN)
        self.view.update_event("thinking", caption={"text": "colère et rage"})
        self.assertEqual(self.view.tone, Tone())
        self.view.update_event("jarvis_speaking", SIGNAL, {"text": "colère et rage", "fraction": 0})
        self.assertEqual(self.view.tone.name, "colère")
        self.assertEqual(self.view.caption_text, "")

    def test_passage_offsets_are_monotone_when_piper_block_fraction_restarts(self):
        caption = {"text": "Un premier passage puis un deuxième passage.", "segment_id": 1,
                   "original_start": 100, "original_end": 120,
                   "spectrum_events": [self.event("colère", "#ff717a", 100, 110),
                                       self.event("espoir", "#73bfff", 110, 120)]}
        with patch.object(self.view.analyzer, "update", wraps=self.view.analyzer.update) as analyze:
            self.view.update_event("jarvis_speaking", SIGNAL, {**caption, "fraction": 0})
            self.assertEqual(self.view.tone.name, "colère")
            self.view.update_event("jarvis_speaking", SIGNAL, {**caption, "fraction": 0.8})
            self.assertEqual(self.view.tone.name, "espoir")
            text = self.view.caption_text
            self.view.update_event("jarvis_speaking", SIGNAL, {**caption, "fraction": 0.1})
            self.assertEqual(self.view.tone.name, "espoir")
            self.assertEqual(self.view.caption_text, text)
            self.view.update_event("jarvis_speaking", SIGNAL, {**caption, "segment_id": 2, "fraction": 0})
            self.assertEqual(self.view.tone.name, "colère")
        analyze.assert_not_called()

    def test_neutral_passage_and_interruption_clear_tone_without_semantic_hold(self):
        with patch("jarvis.presence.time.monotonic", return_value=10):
            self.view.update_event("jarvis_speaking", SIGNAL,
                                   {"text": "colère", "fraction": 1, "segment_id": 1,
                                    "spectrum_events": [self.event("colère", "#ff717a")]})
        self.assertNotEqual(self.view.mesh_accent(11), CYAN)
        with patch("jarvis.presence.time.monotonic", return_value=11):
            self.view.update_event("jarvis_speaking", SIGNAL,
                                   {"text": "Fait ordinaire.", "fraction": 1, "segment_id": 2,
                                    "spectrum_events": [self.event("neutralité", CYAN)]})
        self.assertEqual(self.view.tone, Tone(confidence=1))
        self.assertNotEqual(self.view.mesh_accent(11), CYAN)
        self.assertEqual(self.view.mesh_accent(12), CYAN)
        self.view.update_event("listening")
        self.assertEqual(self.view.state, "listening")
        self.assertEqual(self.view.caption_text, "")
        self.assertIsNone(self.view.caption_data)
        self.assertIsNone(self.view._segment_key)
        self.assertEqual(self.view._segment_events, [])

    def test_preview_is_local_and_real_voice_events_take_priority(self):
        self.view.set_options(spectrum_mode="thematic", spectrum_intensity=100)
        self.assertEqual(self.view.preview_text("colère et rage").name, "colère")
        self.assertEqual(self.view.mesh_accent(time.monotonic() + 1), self.view.tone.color)
        self.view.set_options(spectrum_intensity=0)
        self.assertEqual(self.view.tone.name, "colère")
        self.assertEqual(self.view.mesh_accent(time.monotonic() + 1), CYAN)
        self.view.set_options(spectrum_intensity=65)
        self.assertEqual(self.view.mesh_accent(time.monotonic() + 1), mix(CYAN, self.view.tone.color, 0.65))
        self.view.update_event("listening")
        self.assertIsNone(self.view._preview_text)
        self.assertEqual(self.view.tone, Tone())
        self.assertIsNone(self.view.preview_text("colère et rage"))
        self.app.voice.toggle.assert_not_called()
        self.app.voice.emergency.assert_not_called()
        self.view.set_options(spectrum_mode="neutral", spectrum_intensity=0)
        self.view.update_event("jarvis_speaking", SIGNAL,
                               {"text": "colère", "fraction": 1,
                                "spectrum_events": [self.event("colère", "#ff717a")]})
        self.assertEqual(self.view.tone, Tone())
        self.assertEqual(self.view.mesh_accent(time.monotonic() + 1), CYAN)


class GeometryTests(unittest.TestCase):
    def test_thickness_is_validated_and_independent_of_audio_expressivity(self):
        self.assertEqual(PresenceSettings().visualizer_thickness, 6)
        for value in (-1, 0, 11, True, "6", None, float("nan"), float("inf")):
            self.assertEqual(PresenceSettings.from_dict({"visualizer_thickness": value}).visualizer_thickness, 6)
        for value in (1, 6, 10):
            self.assertEqual(PresenceSettings.from_dict({"visualizer_thickness": value}).visualizer_thickness, value)
        models = [PresenceModel(PresenceSettings(visualizer_thickness=value)) for value in (1, 6, 10)]
        for model in models:
            model.update_event("user_speaking", SIGNAL, now=1)
        self.assertTrue(all(model.target_geometry(1000, 700, now=1) ==
                            models[0].target_geometry(1000, 700, now=1) for model in models))
        widths = stroke_widths(6)
        self.assertTrue(3 <= widths[-1] <= 4)
        self.assertTrue(8 <= widths[0] <= 14)
        self.assertAlmostEqual(dpi_scale(96 / 72), 1)
        self.assertAlmostEqual(dpi_scale(144 / 72), 1.5)
        self.assertEqual(stroke_widths(6, 1.5), tuple(width * 1.5 for width in widths))

    def test_processing_core_diameter_and_real_pcm_expansion_are_bounded(self):
        model = PresenceModel(PresenceSettings(reduced_motion=True))
        for width, height in ((620, 440), (480, 840), (1920, 1080), (3440, 1440), (10000, 10000)):
            model.update_event("thinking", now=1)
            core = model.frame(width, height, now=1)
            self.assert_centered(core, width, height)
            diameter = bounds(core)[2] - bounds(core)[0]
            self.assertTrue(0.25 <= diameter / min(width, height) <= 0.35)
            model.update_event("jarvis_speaking", SIGNAL, now=2)
            speaking = model.frame(width, height, now=2)
            self.assertGreater(bounds(speaking)[2] - bounds(speaking)[0], diameter)
            self.assertEqual(len(speaking), len(core))
            model.update_event("jarvis_speaking", {"rms": 0, "wave": [1, -1]}, now=2.1)
            self.assertTrue(all(y == height / 2 for _, y in model.frame(width, height, now=2.1)))

    def test_reduced_motion_and_disabled_animations_freeze_orbital_geometry(self):
        for settings in (PresenceSettings(reduced_motion=True), PresenceSettings(animations=False)):
            model = PresenceModel(settings)
            model.update_event("thinking", now=1)
            self.assertEqual(model.frame(1000, 700, now=1), model.frame(1000, 700, now=90))
            self.assertFalse(model.needs_animation(now=90))
            model.update_event("silent", now=91)
            self.assertTrue(all(y == 350 for _, y in model.frame(1000, 700, now=91)))

    def test_pcm_filter_is_cached_at_event_arrival_and_static_mesh_cache_is_bounded(self):
        model = PresenceModel()
        with patch("jarvis.presence._smooth_wave", wraps=_smooth_wave) as smooth:
            model.update_event("user_speaking", SIGNAL, now=1)
            for index in range(5):
                model.frame(1000, 700, now=1 + index * 0.02)
            smooth.assert_called_once()
            model.update_event("user_speaking", SIGNAL, now=2)
            self.assertEqual(smooth.call_count, 2)
        self.assertEqual(len(model._wave), POINT_COUNT)
        model.update_event("silent", now=3)
        first = model.target_geometry(1000, 700, now=3)
        self.assertIs(first, model.target_geometry(1000, 700, now=4))
        self.assertIsNot(first, model.target_geometry(900, 700, now=5))

    def test_quality_profiles_cap_layers_fps_for_dpi_pixel_area_and_load(self):
        for profile in PROFILES:
            settings = PresenceSettings(profile=profile)
            base = render_quality(settings, 1000, 700)
            self.assertEqual(base[:2], PROFILES[profile])
            for quality in (render_quality(settings, 3840, 2160, 2),
                            render_quality(settings, 1000, 700, overloaded=True)):
                self.assertLessEqual(quality[0], 16)
                self.assertLessEqual(quality[1], 2)
                self.assertLessEqual(quality[2], 1)
            self.assertEqual(render_quality(PresenceSettings(profile=profile, halos=False), 1000, 700)[1:], (1, 0))

    def test_circulating_arcs_are_interpolated_subsets_of_the_current_mesh(self):
        model = PresenceModel()
        model.update_event("thinking", now=1)
        points = model.target_geometry(1000, 700, now=1.8)
        arc = _mesh_arc(points, 0.95, 0.2)  # Wrap through the mesh seam.
        for x, y in zip(arc[::2], arc[1::2]):
            self.assertTrue(any(abs(math.dist(a, (x, y)) + math.dist((x, y), b) - math.dist(a, b)) < 1e-6
                                for a, b in zip(points, points[1:])))
        self.assertLess(len(arc), POINT_COUNT)

    def test_thinking_has_visible_organic_deformation_on_the_same_closed_mesh(self):
        model = PresenceModel()
        model.update_event("thinking", now=1)
        first = model.target_geometry(1000, 700, now=1)
        later = model.target_geometry(1000, 700, now=2.2)
        self.assertEqual(len(first), POINT_COUNT)
        self.assertGreater(max(math.dist(a, b) for a, b in zip(first, later)), core_radius(1000, 700) * 0.12)
        self.assertEqual(first[0], first[-1])
        self.assert_centered(first, 1000, 700)
        self.assert_centered(later, 1000, 700)

    def test_expressivity_is_nonlinear_bounded_and_uses_only_real_audio(self):
        heights = []
        for expressivity in (0, 65, 100):
            model = PresenceModel(PresenceSettings(wave_expressivity=expressivity))
            model.update_event("user_speaking", {**SIGNAL, "rms": 0.02}, now=1)
            points = model.frame(1000, 700, now=1)
            self.assert_centered(points, 1000, 700)
            heights.append(bounds(points)[3] - bounds(points)[1])
            model.update_event("user_speaking", {"rms": 0, "wave": SIGNAL["wave"]}, now=2)
            self.assertTrue(all(y == 350 for _, y in model.frame(1000, 700, now=2)))
        self.assertLess(heights[0], heights[1])
        self.assertLess(heights[1], heights[2])
        self.assertGreater(heights[1], 100)  # Quiet PCM now has visible dynamic range.
        model = PresenceModel()
        excursions = []
        for rms in (0.01, 0.02, 0.04, 1):
            model.update_event("user_speaking", {**SIGNAL, "rms": rms}, now=1)
            points = model.target_geometry(1000, 700, now=1)
            self.assert_centered(points, 1000, 700)
            excursions.append(bounds(points)[3] - bounds(points)[1])
        self.assertEqual(excursions, sorted(excursions))
        self.assertLess(excursions[1], 2 * excursions[0])  # Compression, not fixed gain.

    def test_wave_attack_is_fast_and_release_is_softer_without_idle_motion(self):
        model = PresenceModel()
        model.update_event("user_speaking", {**SIGNAL, "rms": 0.001}, now=1)
        low = model.frame(1000, 700, now=1)
        model.update_event("user_speaking", {**SIGNAL, "rms": 0.12}, now=1.03)
        high_target = model.target_geometry(1000, 700, now=1.03)
        rise = model.frame(1000, 700, now=1.03)
        extent = lambda points: bounds(points)[3] - bounds(points)[1]
        attack = (extent(rise) - extent(low)) / (extent(high_target) - extent(low))
        model.update_event("user_speaking", {**SIGNAL, "rms": 0.001}, now=1.06)
        fall = model.frame(1000, 700, now=1.06)
        release = (extent(rise) - extent(fall)) / (extent(rise) - extent(low))
        self.assertGreater(attack, 0.7)
        self.assertLess(release, 0.3)
        flat = model.frame(1000, 700, now=2)
        self.assertTrue(all(y == 350 for _, y in flat))
        self.assertFalse(model.needs_animation(now=2))

    def test_expressivity_defaults_and_invalid_preferences(self):
        self.assertEqual(PresenceSettings().wave_expressivity, 65)
        for value in (-1, 101, float("nan"), float("inf"), True, "high", None):
            self.assertEqual(PresenceSettings.from_dict({"wave_expressivity": value}).wave_expressivity, 65)
        for value in (0, 65, 100):
            self.assertEqual(PresenceSettings.from_dict({"wave_expressivity": value}).wave_expressivity, value)

    def assert_centered(self, points, width, height):
        left, top, right, bottom = bounds(points)
        self.assertAlmostEqual((left + right) / 2, width / 2, places=6)
        self.assertAlmostEqual((top + bottom) / 2, height / 2, places=6)
        self.assertGreaterEqual(left, 0)
        self.assertLessEqual(right, width)
        self.assertGreaterEqual(top, 0)
        self.assertLessEqual(bottom, height)

    def test_silent_and_listening_are_exact_flat_lines_without_fake_motion(self):
        model = PresenceModel()
        for state in ("silent", "listening"):
            model.update_event(state, SIGNAL, now=0)
            first = model.frame(1000, 700, now=0.01)
            self.assertTrue(all(y == 350 for _, y in first))
            self.assertGreater(first[-1][0] - first[0][0], 800)
            self.assertEqual(first, model.frame(1000, 700, now=50))
            self.assertFalse(model.needs_animation(now=50))

    def test_microphone_wave_uses_real_signal_and_joins_the_baseline(self):
        model = PresenceModel()
        model.update_event("user_speaking", SIGNAL, now=1)
        points = model.frame(1000, 700, now=1.01)
        self.assertEqual(len(points), POINT_COUNT)
        self.assertGreater(max(y for _, y in points), 350)
        self.assertLess(min(y for _, y in points), 350)
        self.assertAlmostEqual(points[0][1], 350)
        self.assertAlmostEqual(points[-1][1], 350)
        self.assert_centered(points, 1000, 700)
        model.update_event("user_speaking", {"rms": 0, "wave": [1, -1]}, now=1.05)
        self.assertTrue(all(y == 350 for _, y in model.frame(1000, 700, now=1.06)))

    def test_expired_or_missing_signal_never_keeps_audio_motion_alive(self):
        model = PresenceModel()
        model.update_event("user_speaking", SIGNAL, now=1)
        self.assertTrue(model.needs_animation(now=1.01))
        model.frame(1000, 700, now=1.01)
        flat = model.frame(1000, 700, now=1.3)
        self.assertTrue(all(y == 350 for _, y in flat))
        self.assertFalse(model.needs_animation(now=1.3))
        model.update_event("jarvis_speaking", now=2)
        core = model.frame(1000, 700, now=2.01)
        self.assertEqual(core, model.frame(1000, 700, now=5))
        self.assertFalse(model.needs_animation(now=5))
        model.update_event("jarvis_speaking", SIGNAL, now=6)
        self.assertNotEqual(core, model.target_geometry(1000, 700, now=6.01))

    def test_core_is_circular_and_centred_in_multiple_aspect_ratios(self):
        model = PresenceModel(PresenceSettings(reduced_motion=True))
        for width, height in ((620, 440), (480, 840), (1920, 1080), (3440, 1440), (900, 600)):
            for signal in (None, SIGNAL):
                model.update_event("thinking" if signal is None else "jarvis_speaking", signal, now=0)
                points = model.frame(width, height, now=0.01)
                self.assert_centered(points, width, height)
                if signal is None:
                    radius = core_radius(width, height)
                    for x, y in points:
                        self.assertAlmostEqual(math.hypot(x - width / 2, y - height / 2), radius, places=6)
                    self.assertAlmostEqual(bounds(points)[2] - bounds(points)[0], 2 * radius)
        self.assertAlmostEqual(core_radius(1000, 700), 101.5)

    def test_one_mesh_morphs_reversibly_and_interrupts_without_waiting(self):
        model = PresenceModel()
        line = model.frame(1000, 700, now=0)
        model.update_event("thinking", now=0.01)
        middle = model.frame(1000, 700, now=0.04)
        self.assertNotEqual(middle, line)
        self.assertNotEqual(middle, model.target_geometry(1000, 700, now=0.04))
        self.assertTrue(model.morphing)
        model.update_event("user_speaking", SIGNAL, now=0.05)
        interrupted = model.frame(1000, 700, now=0.08)
        self.assertEqual(model.state, "user_speaking")
        self.assertEqual(len(interrupted), len(line))
        self.assert_centered(interrupted, 1000, 700)
        model.update_event("silent", now=0.09)
        for index in range(1, 31):
            model.frame(1000, 700, now=0.09 + index * 0.03)
        self.assertEqual(model.points, line)
        self.assertFalse(model.needs_animation(now=2))

    def test_thinking_animates_only_actual_state_and_reduced_motion_disables_it(self):
        model = PresenceModel()
        model.update_event("thinking", now=1)
        self.assertNotEqual(model.target_geometry(1000, 700, now=1),
                            model.target_geometry(1000, 700, now=4))
        model.settings = PresenceSettings(reduced_motion=True)
        first = model.frame(1000, 700, now=5)
        self.assertEqual(first, model.frame(1000, 700, now=9))
        self.assertFalse(model.needs_animation(now=9))
        model.update_event("dormant", now=10)
        dormant = model.frame(1000, 700, now=10)
        self.assertLessEqual(bounds(dormant)[2] - bounds(dormant)[0], 5)
        self.assertFalse(model.needs_animation(now=10))

    def test_malformed_preferences_and_signal_are_safe(self):
        for raw in (None, [], "invalid", {"profile": [], "background": "white",
                                         "reduced_motion": "yes", "subtitles": 1,
                                         "accent_mode": [], "fixed_color": "invisible"}):
            self.assertEqual(PresenceSettings.from_dict(raw), PresenceSettings())
        model = PresenceModel()
        model.update_event("user_speaking", {"rms": float("nan"), "wave": [None, float("inf")]}, now=0)
        self.assertTrue(all(y == 350 for _, y in model.frame(1000, 700, now=0.01)))
        with self.assertRaises(ValueError):
            model.update_event("invented")

    def test_text_contrast_adapts_to_user_background(self):
        for background in ("#000000", "#ffffff", "#ffcc00", "#00ffff", "#808080", "#aa0077"):
            colors = palette(background)
            self.assertGreaterEqual(contrast(background, colors["foreground"]), 4.5)
            self.assertGreaterEqual(contrast(background, colors["muted"]), 4.5)
        self.assertEqual(set(PROFILES), {"eco", "balanced", "cinematic"})


def display_available():
    try:
        root = tk.Tk()
        root.destroy()
        return True
    except tk.TclError:
        return False


@unittest.skipUnless(display_available(), "Écran graphique indisponible")
class PresenceTkTests(unittest.TestCase):
    def test_thickness_halos_and_animations_controls_persist_and_fit_the_screen(self):
        self.view.show()
        self.view.open_settings()
        self.root.update()
        children = widgets(self.view.settings_dialog)
        thickness = next(widget for widget in children if isinstance(widget, tk.Scale)
                         and float(widget.cget("from")) == 1)
        self.assertEqual(thickness.get(), 6)
        thickness.set(9)
        for text in ("Halos lumineux", "Animations visuelles"):
            next(widget for widget in children if isinstance(widget, tk.Checkbutton)
                 and widget.cget("text") == text).invoke()
        self.root.update()
        reopened = PresenceView(self.app)
        self.addCleanup(reopened.close)
        self.assertEqual(reopened.settings.visualizer_thickness, 9)
        self.assertFalse(reopened.settings.halos)
        self.assertFalse(reopened.settings.animations)
        self.assertLessEqual(self.view.settings_dialog.winfo_height(), self.root.winfo_screenheight())

    def test_layers_use_scaled_widths_and_orbital_highlights_reuse_canvas_items(self):
        old_scaling = self.root.tk.call("tk", "scaling")
        self.addCleanup(lambda: self.root.tk.call("tk", "scaling", old_scaling))
        self.root.tk.call("tk", "scaling", 96 / 72)
        self.view.set_options(profile="cinematic", reduced_motion=True)
        self.view.show()
        self.view.update_event("thinking")
        self.root.update()
        items = self.view.canvas.find_all()
        coords = self.view.canvas.coords(self.view.paths[-1])
        widths = stroke_widths(6, dpi_scale(self.root.tk.call("tk", "scaling")))
        for path, expected in zip(self.view.paths, widths):
            self.assertEqual(self.view.canvas.coords(path), coords)
            self.assertAlmostEqual(float(self.view.canvas.itemcget(path, "width")), expected)
            self.assertEqual(self.view.canvas.itemcget(path, "capstyle"), "round")
        for path in self.view.orbital_paths:
            self.assertEqual(self.view.canvas.itemcget(path, "state"), "normal")
            self.assertLess(len(self.view.canvas.coords(path)), len(coords))
        for _ in range(5):
            self.view._render()
        self.assertEqual(self.view.canvas.find_all(), items)
        self.assertIsNone(self.view.after_id)
        self.view.set_options(halos=False)
        self.assertEqual([self.view.canvas.itemcget(path, "state") for path in self.view.paths],
                         ["hidden", "hidden", "hidden", "normal"])
        self.assertTrue(all(self.view.canvas.itemcget(path, "state") == "hidden"
                            for path in self.view.orbital_paths))

    def test_disabled_motion_profiles_and_hidden_window_leave_no_orbital_callbacks(self):
        self.view.show()
        self.root.update()
        for profile in PROFILES:
            self.view.set_options(profile=profile, animations=False)
            self.view.update_event("thinking")
            before = self.view.canvas.coords(self.view.paths[-1])
            self.view._render()
            self.assertEqual(self.view.canvas.coords(self.view.paths[-1]), before)
            self.assertIsNone(self.view.after_id)
        self.view.set_options(animations=True)
        self.assertIsNotNone(self.view.after_id)
        self.view.return_to_command()
        self.assertIsNone(self.view.after_id)
        self.view.update_event("thinking")
        self.assertIsNone(self.view.after_id)

    def test_error_and_microphone_off_operations_immediately_clear_pending_morph_and_caption(self):
        self.view.show()
        self.root.update()
        for operation in ("error", "inactive"):
            self.view.update_event("jarvis_speaking", SIGNAL, {"text": "Phrase en cours", "fraction": 1})
            self.assertTrue(self.view.caption_text)
            self.view.update_event("thinking")
            self.assertIsNotNone(self.view.after_id)
            self.view.update_operation(operation, "Arrêt fonctionnel")
            self.assertEqual(self.view.state, "silent")
            self.assertTrue(all(y == self.view.canvas.winfo_height() / 2 for _, y in self.view.model.points))
            self.assertEqual(self.view.caption_text, "")
            self.assertIsNone(self.view.caption_data)
            self.assertIsNone(self.view.after_id)
            self.assertTrue(all(self.view.canvas.itemcget(path, "state") == "hidden"
                                for path in self.view.orbital_paths))

    def test_timing_monitor_uses_measured_history_hides_and_preserves_core_centre(self):
        self.view.set_options(reduced_motion=True)
        self.view.show()
        self.view.update_event("thinking")
        self.root.update()
        canvas_size = (self.view.canvas.winfo_width(), self.view.canvas.winfo_height())
        core = list(self.view.canvas.coords(self.view.paths[0]))
        self.view.update_timing({"stt_ms": 250, "llm_wait_ms": 700, "token_to_audio_ms": 400,
                                 "turn_to_audio_ms": 1500, "speech_to_audio_ms": 2300}, new_turn=True, complete=True)
        self.root.update()
        self.assertIn("STT  250", self.view.timing_values.cget("text"))
        self.assertIn("Silence VAD  —", self.view.timing_values.cget("text"))
        self.assertIn("Bluetooth", self.view.timing_note.cget("text"))
        self.assertEqual(self.view.timing_history, [2300])
        self.view.update_timing({}, complete=True)
        self.assertEqual(self.view.timing_history, [2300])
        self.view.toggle_timing()
        self.root.update()
        self.assertEqual(self.view.timing_panel.winfo_manager(), "")
        self.assertFalse(self.store.get_preference("presence")["timing_monitor"])
        self.assertEqual(self.view.canvas.coords(self.view.paths[0]), core)
        self.assertEqual((self.view.canvas.winfo_width(), self.view.canvas.winfo_height()), canvas_size)
        self.view.toggle_timing()
        self.root.update()
        self.assertEqual(self.view.timing_panel.winfo_manager(), "place")
        reopened = PresenceView(self.app)
        self.addCleanup(reopened.close)
        self.assertTrue(reopened.settings.timing_monitor)
        self.view.update_timing({"stt_ms": float("nan"), "llm_wait_ms": -5}, new_turn=True)
        self.assertEqual(self.view.timings, {})
        for i in range(20):
            self.view.update_timing({"speech_to_audio_ms": i * 100}, new_turn=True, complete=True)
        self.assertEqual(len(self.view.timing_history), 12)
        self.view.update_event("dormant")
        self.assertEqual(self.view.timing_panel.winfo_manager(), "")

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = tk.Tk()
        self.addCleanup(self.root.destroy)
        self.store = Store(Path(self.temp.name) / "presence.sqlite3")
        self.addCleanup(self.store.close)
        voice = SimpleNamespace(listening=False, toggle=Mock(), emergency=Mock(), stop_listening=Mock())
        self.app = SimpleNamespace(root=self.root, store=self.store, voice=voice, font_family="DejaVu Sans")
        self.view = PresenceView(self.app)
        self.addCleanup(self.view.close)

    def test_lazy_window_reopens_and_all_layers_share_one_spline(self):
        self.assertEqual(self.root.winfo_children(), [])
        self.view.update_event("thinking")
        self.assertIsNone(self.view.window)
        self.assertIsNone(self.view.after_id)
        self.view.show()
        self.root.update()
        original = self.view.window
        self.assertIsNotNone(self.view.after_id)
        self.assertEqual(self.view.canvas.cget("background"), "#000000")
        coordinates = self.view.canvas.coords(self.view.paths[0])
        for path in self.view.paths:
            self.assertEqual(self.view.canvas.coords(path), coordinates)
            self.assertIn(str(self.view.canvas.itemcget(path, "smooth")), {"true", "1"})
        self.view.close()
        self.assertIsNone(self.view.after_id)
        self.assertFalse(self.root.tk.call("after", "info"))
        self.view.show()
        self.assertIsNot(self.view.window, original)
        self.assertEqual(self.view.state, "thinking")
        self.root.update()
        self.assertEqual(self.view.state_label.cget("text"), "TRAITEMENT LOCAL")
        self.assertEqual(self.view.timing_panel.winfo_manager(), "place")

    def test_expressivity_slider_persists_without_touching_voice_preferences(self):
        self.store.set_preference("voice", {"vad_threshold": 0.6, "silence_ms": 800})
        self.view.show()
        self.view.open_settings()
        slider = next(child for child in widgets(self.view.settings_dialog) if isinstance(child, tk.Scale))
        self.assertEqual(slider.get(), 65)
        self.root.update()
        slider.set(90)
        self.root.update()
        self.assertEqual(self.store.get_preference("presence")["wave_expressivity"], 90)
        reopened = PresenceView(self.app)
        self.addCleanup(reopened.close)
        self.assertEqual(reopened.settings.wave_expressivity, 90)
        self.assertEqual(self.store.get_preference("voice"), {"vad_threshold": 0.6, "silence_ms": 800})

    def test_spectrum_controls_persist_and_preview_never_starts_voice(self):
        self.view.show()
        self.view.set_options(reduced_motion=True)
        self.root.update()
        size = (self.view.canvas.winfo_width(), self.view.canvas.winfo_height())
        self.view.open_settings()
        next(widget for widget in self.view.settings_dialog.winfo_children()
             if isinstance(widget, ttk.Notebook)).select(1)
        self.root.update()
        children = widgets(self.view.settings_dialog)
        mode = [widget for widget in children if isinstance(widget, ttk.Combobox)][2]
        self.assertEqual(mode.get(), "Émotion exprimée")
        mode.set("Ambiance du sujet")
        mode.event_generate("<<ComboboxSelected>>")
        slider = [widget for widget in children if isinstance(widget, tk.Scale) and float(widget.cget("from")) == 0][1]
        self.assertEqual(slider.get(), 65)
        slider.set(85)
        entry = next(widget for widget in children if type(widget) is ttk.Entry)
        entry.delete(0, "end")
        entry.insert(0, "colère et rage")
        button = next(widget for widget in children if isinstance(widget, ttk.Button)
                      and widget.cget("text") == "Prévisualiser la phrase")
        self.root.update()
        button.invoke()
        self.assertEqual(self.view.tone.name, "colère")
        self.assertEqual(self.view.caption_text, "")
        self.assertEqual((self.view.canvas.winfo_width(), self.view.canvas.winfo_height()), size)
        self.assertEqual(self.view.state, "silent")
        reopened = PresenceView(self.app)
        self.addCleanup(reopened.close)
        self.assertEqual(reopened.settings.spectrum_mode, "thematic")
        self.assertEqual(reopened.settings.spectrum_intensity, 85)
        self.view.update_event("listening")
        self.assertIsNone(self.view._preview_text)
        self.assertEqual(self.view.tone, Tone())
        self.app.voice.toggle.assert_not_called()
        self.app.voice.emergency.assert_not_called()

    def test_caption_overlay_never_changes_canvas_or_core_centre(self):
        self.view.show()
        self.view.set_options(reduced_motion=True)
        self.root.update()
        width, height = self.view.canvas.winfo_width(), self.view.canvas.winfo_height()
        self.view.update_event("jarvis_speaking", SIGNAL, {"text": "Phrase courte", "fraction": 0.5})
        self.root.update()
        before = bounds(self.view.model.points)
        self.view.update_event("jarvis_speaking", SIGNAL, {"text": "Une transcription très longue " * 30, "fraction": 1})
        self.root.update()
        self.assertEqual((self.view.canvas.winfo_width(), self.view.canvas.winfo_height()), (width, height))
        self.assertEqual(before, bounds(self.view.model.points))
        self.assertEqual(self.view.caption_label.winfo_manager(), "place")
        left, top, right, bottom = bounds(self.view.model.points)
        self.assertAlmostEqual((left + right) / 2, width / 2)
        self.assertAlmostEqual((top + bottom) / 2, height / 2)
        self.view.set_options(subtitles=False)
        self.assertEqual(self.view.caption_label.winfo_manager(), "")

    def test_preferences_persist_and_bad_saved_values_are_not_overwritten_on_load(self):
        raw = {"background": "invalid", "profile": [], "future": "preserve"}
        self.store.set_preference("presence", raw)
        view = PresenceView(self.app)
        self.addCleanup(view.close)
        self.assertEqual(view.settings, PresenceSettings())
        self.assertEqual(self.store.get_preference("presence"), raw)
        self.assertTrue(view.set_background("#FfFfFf"))
        self.assertFalse(view.set_background("arbitrary"))
        self.assertTrue(view.set_options(profile="eco", reduced_motion=True, subtitles=False))
        reopened = PresenceView(self.app)
        self.assertEqual(reopened.settings, PresenceSettings("#ffffff", "eco", True, False))
        self.assertEqual(self.store.get_preference("presence")["future"], "preserve")
        reopened.reset_background()
        self.assertEqual(self.store.get_preference("presence")["background"], "#000000")

    def test_background_picker_applies_real_selection_and_cancellation_is_inert(self):
        with patch("jarvis.presence.colorchooser.askcolor", return_value=((255, 255, 255), "#ffffff")):
            self.view.choose_background()
        self.assertEqual(self.view.settings.background, "#ffffff")
        with patch("jarvis.presence.colorchooser.askcolor", return_value=(None, None)):
            self.view.choose_background()
        self.assertEqual(self.view.settings.background, "#ffffff")

    def test_dormant_stops_real_activity_first_and_wake_never_enables_microphone(self):
        self.view.show()
        self.view.update_event("thinking")
        states_at_stop = []
        self.app.voice.emergency.side_effect = lambda: states_at_stop.append(self.view.state)
        self.view.sleep()
        self.assertEqual(states_at_stop, ["thinking"])
        self.assertEqual(self.view.state, "dormant")
        self.assertIsNone(self.view.after_id)
        self.view.update_event("jarvis_speaking", SIGNAL)
        self.assertEqual(self.view.state, "dormant")
        self.view.wake()
        self.assertEqual(self.view.state, "silent")
        self.app.voice.stop_listening.assert_called_once()
        self.app.voice.toggle.assert_not_called()

    def test_hidden_and_closed_windows_cancel_all_animation_callbacks(self):
        self.view.show()
        self.view.update_event("thinking")
        self.assertIsNotNone(self.view.after_id)
        self.view.return_to_command()
        self.assertIsNone(self.view.after_id)
        self.view.update_event("user_speaking", SIGNAL)
        self.assertIsNone(self.view.after_id)
        self.view.show()
        self.root.update()
        self.assertIsNotNone(self.view.after_id)
        self.view.close()
        self.assertFalse(self.root.tk.call("after", "info"))

    def test_resize_is_responsive_and_reduced_motion_uses_no_thinking_timer(self):
        self.view.show()
        self.view.set_options(reduced_motion=True)
        self.view.update_event("thinking")
        for width, height in ((800, 500), (700, 900), (1200, 650)):
            self.view.window.geometry(f"{width}x{height}")
            self.root.update()
            actual_width, actual_height = self.view.canvas.winfo_width(), self.view.canvas.winfo_height()
            left, top, right, bottom = bounds(self.view.model.points)
            self.assertAlmostEqual((left + right) / 2, actual_width / 2)
            self.assertAlmostEqual((top + bottom) / 2, actual_height / 2)
            self.assertAlmostEqual(right - left, bottom - top)
            self.assertIsNone(self.view.after_id)

    def test_emotional_modes_persist_and_never_recolor_operational_controls(self):
        self.view.show()
        self.view.set_options(spectrum_mode="thematic")
        self.view.update_operation("error", "Arrêt explicite")
        old_operation_color = self.view.operation_label.cget("foreground")
        old_background = self.view.canvas.cget("background")
        old_button_color = self.view.listen_button.cget("foreground")
        old_identity_color = self.view.identity.cget("foreground")
        self.assertEqual(self.view.preview_text("Une colère et une rage explicites.").name, "colère")
        self.assertEqual(self.view.mesh_accent(time.monotonic() + 1), mix(CYAN, self.view.tone.color, 0.65))
        self.assertEqual(self.view.operation, "error")
        self.assertEqual(self.view.operation_label.cget("foreground"), old_operation_color)
        self.assertIn(OPERATIONAL["error"]["label"], self.view.operation_label.cget("text"))
        self.assertEqual(self.view.canvas.cget("background"), old_background)
        self.assertEqual(self.view.listen_button.cget("foreground"), old_button_color)
        self.assertEqual(self.view.identity.cget("foreground"), old_identity_color)
        for mode in ("cyan", "fixed", "none", "adaptive"):
            self.assertTrue(self.view.set_options(accent_mode=mode, fixed_color="#AB78EF"))
            self.assertEqual(self.store.get_preference("presence")["accent_mode"], mode)
            self.assertEqual(self.view.operation_label.cget("foreground"), old_operation_color)
            reopened = PresenceView(self.app)
            self.assertEqual(reopened.settings.accent_mode, mode)
            self.assertEqual(reopened.settings.fixed_color, "#ab78ef")
            if mode == "cyan":
                self.assertEqual(self.view.mesh_accent(time.monotonic() + 1), "#69edf5")
            elif mode == "fixed":
                self.assertEqual(self.view.mesh_accent(time.monotonic() + 1), "#ab78ef")
            elif mode == "none":
                self.assertEqual(self.view.mesh_accent(time.monotonic() + 1), palette("#000000")["muted"])
        self.app.voice.toggle.assert_not_called()
        self.app.voice.emergency.assert_not_called()

    def test_captions_follow_played_fraction_and_only_keywords_receive_accents(self):
        self.view.show()
        self.view.set_options(spectrum_mode="thematic")
        text = "La colère et la rage, le reste demeure une simple phrase ordinaire."
        self.view.interpret_text(text)
        self.assertEqual(self.view.caption_label.winfo_manager(), "")
        self.view.update_event("jarvis_speaking", SIGNAL, {"text": text, "fraction": 0})
        self.assertEqual(self.view.caption_label.winfo_manager(), "")
        self.view.update_event("jarvis_speaking", SIGNAL, {"text": text, "fraction": 0.4})
        self.assertEqual(self.view.caption_label.get("1.0", "end-1c"), caption_group(text, 0.4))
        self.assertEqual(self.view.caption_label.winfo_manager(), "place")
        self.assertIn("estimée", self.view.caption_note.cget("text"))
        self.assertEqual(self.view.caption_footer.winfo_manager(), "place")
        ranges = self.view.caption_label.tag_ranges("keyword")
        emphasized = [self.view.caption_label.get(start, end) for start, end in zip(ranges[::2], ranges[1::2])]
        self.assertEqual(emphasized, ["colère", "rage"])
        self.assertEqual(self.view.caption_label.cget("foreground"), palette("#000000")["foreground"])
        with patch("jarvis.presence.time.monotonic", return_value=time.monotonic() + 1):
            self.view._render_caption()
        self.assertEqual(self.view.caption_label.tag_cget("keyword", "foreground"),
                         mix(CYAN, self.view.tone.color, 0.65))
        self.view.copy_caption()
        self.assertEqual(self.root.clipboard_get(), caption_group(text, 0.4))
        self.view.update_event("jarvis_speaking", SIGNAL, {"text": text, "fraction": 1})
        self.assertEqual(self.view.caption_text, caption_group(text, 1))
        self.assertLessEqual(len(self.view.caption_text.split()), 12)
        self.view.update_event("thinking")
        self.assertEqual(self.view.caption_text, "")
        self.assertEqual(self.view.caption_label.winfo_manager(), "")

    def test_none_mode_removes_keyword_tags_without_affecting_audio_or_text(self):
        self.view.show()
        self.view.set_options(spectrum_mode="thematic")
        self.view.update_event("jarvis_speaking", SIGNAL,
                               {"text": "Une colère et une rage explicites", "fraction": 1})
        self.assertTrue(self.view.caption_label.tag_ranges("keyword"))
        text = self.view.caption_label.get("1.0", "end-1c")
        self.view.set_options(accent_mode="none")
        self.assertEqual(self.view.caption_label.tag_ranges("keyword"), ())
        self.assertEqual(self.view.caption_label.get("1.0", "end-1c"), text)
        self.assertEqual(self.view.state, "jarvis_speaking")
        self.app.voice.emergency.assert_not_called()

    def test_dark_emotional_and_fixed_colors_retain_visible_contours(self):
        self.view.set_options(spectrum_mode="thematic")
        self.assertEqual(self.view.preview_text("La mort et le deuil.").name, "deuil")
        self.assertGreaterEqual(contrast(self.view.mesh_accent(time.monotonic() + 1), "#000000"), 3)
        self.view.set_options(accent_mode="fixed", fixed_color="#000000")
        self.assertNotEqual(self.view.mesh_accent(time.monotonic() + 1), "#000000")
        self.assertGreaterEqual(contrast(self.view.mesh_accent(time.monotonic() + 1), "#000000"), 3)
        for background in ("#000000", "#ffffff", "#ffcc00", "#808080"):
            self.assertGreaterEqual(contrast(readable_accent(background, background), background), 3)

    def test_repeated_playback_text_does_not_repeat_tone_analysis(self):
        self.view.show()
        text = "Une colère et une rage explicites."
        with patch.object(self.view.analyzer, "update", wraps=self.view.analyzer.update) as analyze:
            self.view.update_event("jarvis_speaking", SIGNAL, {"text": text, "fraction": 0.2})
            self.view.update_event("jarvis_speaking", SIGNAL, {"text": text, "fraction": 0.4})
            self.view.update_event("jarvis_speaking", SIGNAL, {"text": text, "fraction": 0.8})
        analyze.assert_called_once_with(text)

    def test_ambiguous_caption_has_no_semantic_hold_and_returns_smoothly_to_cyan(self):
        self.view.set_options(spectrum_mode="thematic")
        self.view.update_event("jarvis_speaking", SIGNAL, {"text": "colère et rage", "fraction": 1})
        self.assertEqual(self.view.tone.name, "colère")
        self.view.update_event("jarvis_speaking", SIGNAL, {"text": "Une réponse ambiguë", "fraction": 1})
        self.assertEqual(self.view.tone.name, "neutralité")
        self.assertEqual(self.view.mesh_accent(time.monotonic() + 1), CYAN)


if __name__ == "__main__":
    unittest.main()
