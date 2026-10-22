"""Prepared text, real playback boundaries and accessible PRESENCE controls.

PCM dictionaries below are explicit test doubles; no microphone, model, audio
device or network is started by these checks.
"""
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
import tempfile
import tkinter as tk
from tkinter import font as tkfont, ttk
import unittest
from unittest.mock import Mock, patch

from jarvis.captions import CaptionPlan
from jarvis.presence import MIC_LABELS, PresenceSettings, PresenceView
from jarvis.spectrum import CYAN, OPERATIONAL, Tone, analyze_passages
from jarvis.storage import Store


PCM_DOUBLE = {"rms": .12, "wave": [.2, -.1, .05, -.3, .1]}


def available_display():
    try:
        root = tk.Tk()
        root.destroy()
        return True
    except tk.TclError:
        return False


class FieldPreferenceTests(unittest.TestCase):
    def test_new_defaults_and_explicit_legacy_choices_are_preserved(self):
        current = PresenceSettings.from_dict({})
        self.assertEqual((current.spectrum_mode, current.wave_expressivity, current.fluidity),
                         ("thematic", 75, "cinematic"))
        legacy = PresenceSettings.from_dict({"wave_expressivity": 65, "spectrum_mode": "expression"})
        self.assertEqual((legacy.wave_expressivity, legacy.spectrum_mode), (65, "expression"))
        self.assertTrue(current.emotional_subtitles)
        self.assertEqual(current.subtitle_coloring, "normal")

    def test_malformed_new_preferences_fall_back_without_enabling_invalid_modes(self):
        defaults = PresenceSettings()
        for key, values in {
            "fluidity": (None, [], "fast"),
            "subtitle_coloring": (True, {}, "rainbow"),
            "subtitle_size": (11, 33, True, "18", 18.5, float("nan")),
            "emotional_subtitles": (1, "yes", None),
            "diagnostic_mode": (0, "false", []),
        }.items():
            for value in values:
                with self.subTest(key=key, value=value):
                    self.assertEqual(getattr(PresenceSettings.from_dict({key: value}), key),
                                     getattr(defaults, key))


@unittest.skipUnless(available_display(), "Écran graphique indisponible")
class EmotionalFieldTkTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = tk.Tk()
        self.addCleanup(self.root.destroy)
        self.store = Store(Path(self.temp.name) / "field.sqlite3")
        self.addCleanup(self.store.close)
        self.voice = SimpleNamespace(listening=False, toggle=Mock(), emergency=Mock(), stop_listening=Mock())
        self.app = SimpleNamespace(root=self.root, store=self.store, voice=self.voice, font_family="DejaVu Sans")
        self.view = PresenceView(self.app)
        self.addCleanup(self.view.close)
        self.view.show()
        self.root.update()

    def prepared(self, text, *, start=0, segment_id=1, fraction=.5):
        events, plan = self.view.prepare_segment(text, text, start)
        return {"text": text, "segment_id": segment_id, "fraction": fraction,
                "original_start": start, "original_end": start + len(text),
                "spectrum_mode": self.view.settings.spectrum_mode,
                "spectrum_events": [asdict(event) for event in events], "caption_plan": asdict(plan)}

    def tagged_words(self):
        ranges = self.view.caption_label.tag_ranges("keyword")
        return tuple(self.view.caption_label.get(left, right)
                     for left, right in zip(ranges[::2], ranges[1::2]))

    def assert_no_scenario(self):
        self.assertIsNone(self.view._preview_id)
        self.assertIsNone(self.view._scenario_index)

    def test_visual_caption_and_fluidity_preferences_survive_restart_without_changing_voice(self):
        self.store.set_preference("voice", {"vad_threshold": .6, "silence_ms": 800})
        for fluidity in ("reactive", "cinematic", "calm"):
            for coloring in ("discreet", "normal", "expressive"):
                self.assertTrue(self.view.set_options(fluidity=fluidity, subtitle_coloring=coloring,
                                                       subtitle_size=26, emotional_subtitles=False,
                                                       visualizer_thickness=8, halos=False, animations=False))
                reopened = PresenceView(self.app)
                self.addCleanup(reopened.close)
                self.assertEqual((reopened.settings.fluidity, reopened.settings.subtitle_coloring),
                                 (fluidity, coloring))
                self.assertEqual(reopened.settings.subtitle_size, 26)
                self.assertFalse(reopened.settings.emotional_subtitles)
                self.assertFalse(reopened.settings.halos)
                self.assertFalse(reopened.settings.animations)
                self.assertEqual(reopened.settings.visualizer_thickness, 8)
        self.assertEqual(self.store.get_preference("voice"), {"vad_threshold": .6, "silence_ms": 800})

    def test_adding_new_preferences_does_not_migrate_away_explicit_legacy_choices(self):
        raw = {"wave_expressivity": 65, "spectrum_mode": "expression", "future_preference": "preserve"}
        self.store.set_preference("presence", raw)
        legacy = PresenceView(self.app)
        self.addCleanup(legacy.close)
        self.assertEqual(self.store.get_preference("presence"), raw)
        self.assertTrue(legacy.set_options(fluidity="calm", subtitle_size=24))
        reopened = PresenceView(self.app)
        self.addCleanup(reopened.close)
        self.assertEqual((reopened.settings.wave_expressivity, reopened.settings.spectrum_mode),
                         (65, "expression"))
        self.assertEqual(self.store.get_preference("presence")["future_preference"], "preserve")

    def test_preparation_does_not_anticipate_pcm_and_passages_keep_a_stable_dominant(self):
        self.view.begin_response()
        first = self.prepared("J'ai confiance et espoir pour demain.", fraction=1)
        second = self.prepared("Une affection et une tendresse accompagnent ce souvenir.",
                               start=100, segment_id=2, fraction=1)
        self.assertEqual(self.view.tone, Tone())
        self.assertEqual(self.view.dominant_tone, Tone())
        self.assertEqual(self.view.mesh_accent(), CYAN)
        self.view.update_event("thinking")
        self.assertEqual(self.view.tone, Tone())
        self.view.update_event("jarvis_speaking", PCM_DOUBLE, first)
        self.assertEqual((self.view.tone.name, self.view.dominant_tone.name), ("espoir", "espoir"))
        hope_target = self.view._target_accent()
        self.view.update_event("jarvis_speaking", PCM_DOUBLE, second)
        self.assertEqual((self.view.tone.name, self.view.dominant_tone.name), ("attachement", "espoir"))
        self.assertNotEqual(self.view._target_accent(), hope_target)
        self.view.begin_response()
        third = self.prepared("Je suis calme et serein.", segment_id=3, fraction=1)
        self.view.update_event("jarvis_speaking", PCM_DOUBLE, third)
        self.assertEqual(self.view.dominant_tone.name, "apaisement")

    def test_prepared_source_is_not_reclassified_at_pcm_repeats_or_fade_frames(self):
        self.view.begin_response()
        with patch("jarvis.presence.analyze_passages", wraps=analyze_passages) as source_analysis:
            payload = self.prepared("J'ai confiance et espoir pour demain.", fraction=.3)
            source_analysis.assert_called_once()
            with patch("jarvis.presence.prepare_caption", side_effect=AssertionError("caption reclassified")), \
                 patch("jarvis.captions.analyze_passages", side_effect=AssertionError("caption reclassified")), \
                 patch.object(self.view.analyzer, "update", side_effect=AssertionError("text reclassified")):
                for fraction in (.3, .6, .2, 1):
                    self.view.update_event("jarvis_speaking", PCM_DOUBLE, {**payload, "fraction": fraction})
                    for _ in range(3):
                        self.view._render()
                self.assertEqual(self.view._segment_fraction, 1)
            source_analysis.assert_called_once()

    def test_caption_payload_keeps_future_emotional_words_neutral_until_estimated_pronunciation(self):
        text = "Bonjour espoir demain."
        payload = self.prepared(text, fraction=.1)
        self.assertIsInstance(CaptionPlan.from_dict(payload["caption_plan"]), CaptionPlan)
        self.view.update_event("jarvis_speaking", PCM_DOUBLE, payload)
        self.assertIn("espoir", self.view.caption_text)
        self.assertEqual(self.tagged_words(), ())
        self.view.update_event("jarvis_speaking", PCM_DOUBLE, {**payload, "fraction": .7})
        self.assertEqual(self.tagged_words(), ("espoir",))
        self.assertNotIn("Bonjour", self.tagged_words())
        self.assertNotIn("demain.", self.tagged_words())

    def test_caption_negation_unicode_and_emoji_do_not_color_neutral_words(self):
        for text, expected in (("Je ne suis pas triste. Je suis calme 🫶🏽.", "calme"),
                               ("Je suis apaise\u0301 et serein 👨‍👩‍👧‍👦.", "apaise\u0301")):
            with self.subTest(text=text):
                self.view.begin_response()
                payload = self.prepared(text, segment_id=text, fraction=1)
                self.view.update_event("jarvis_speaking", PCM_DOUBLE, payload)
                self.assertIn(expected, " ".join(self.tagged_words()))
                for neutral in ("triste", "Je", "suis", "🫶🏽", "👨‍👩‍👧‍👦"):
                    self.assertNotIn(neutral, self.tagged_words())
                self.assertLessEqual(len(self.view.caption_text.splitlines()), 2)

    def test_caption_font_changes_reflow_to_two_lines_and_disable_only_emotional_marks(self):
        self.view.window.geometry("620x440")
        self.root.update()
        text = "Je suis calme et serein dans cette pièce paisible, la fenêtre laisse entrer une lumière douce."
        payload = self.prepared(text, fraction=.5)
        for size in (12, 22, 32):
            self.view.set_options(subtitle_size=size)
            self.view.update_event("jarvis_speaking", PCM_DOUBLE, payload)
            self.assertLessEqual(len(self.view.caption_text.splitlines()), 2)
            self.assertEqual(self.view.settings.subtitle_size, size)
            self.assertGreater(self.view._caption_font.metrics("linespace"), 0)
            available = self.view.canvas.winfo_width() * .82 - 20
            self.assertTrue(all(self.view._caption_font.measure(line) <= available
                                for line in self.view.caption_text.splitlines()))
        before = self.view.caption_text
        self.view.set_options(emotional_subtitles=False)
        self.assertEqual(self.tagged_words(), ())
        self.assertEqual(self.view.caption_text, before)
        self.assertEqual(self.view.caption_label.winfo_manager(), "place")
        self.voice.emergency.assert_not_called()

    def test_large_subtitles_fit_above_footer_and_controls_at_windows_dpi_scales(self):
        original_scaling = self.root.tk.call("tk", "scaling")
        self.addCleanup(lambda: self.root.tk.call("tk", "scaling", original_scaling))
        text = "Je suis calme et serein dans cette pièce paisible, la fenêtre laisse entrer une lumière douce."
        for scale in (1, 2, 2.5):
            with self.subTest(scale=scale):
                self.view.close()
                self.root.tk.call("tk", "scaling", 96 / 72 * scale)
                self.view.show()
                self.view.window.geometry("620x440")
                self.view.set_options(subtitle_size=32, diagnostic_mode=False)
                self.root.update()
                payload = self.prepared(text, segment_id=scale, fraction=.5)
                self.view.update_event("jarvis_speaking", PCM_DOUBLE, payload)
                self.root.update()
                self.assertLessEqual(len(self.view.caption_text.splitlines()), 2)
                bottom = self.view.caption_label.winfo_y() + self.view.caption_label.winfo_height()
                if self.view.caption_footer.winfo_manager():
                    self.assertLessEqual(bottom, self.view.caption_footer.winfo_y())
                self.assertLessEqual(bottom, self.view.controls.winfo_y())
                self.assertGreaterEqual(self.view._caption_font.metrics("linespace"), 12)
                self.assertEqual(self.view.settings.subtitle_size, 32)

    def test_unusually_large_segments_have_a_bounded_neutral_visual_tail(self):
        original = "La peur est le sujet. " * 300
        events, plan = self.view.prepare_segment(original, original, 17)
        self.assertLessEqual(len(events), 65)
        self.assertLessEqual(len(plan.text), 4000)
        self.assertEqual(events[-1].end, 17 + len(original))
        self.assertEqual(events[-1].tone.name, "neutralité")
        self.assertEqual(events[-1].dominant.name, "neutralité")

    def test_settings_tabs_and_close_control_stay_on_screen_at_windows_dpi_scales(self):
        original_scaling = self.root.tk.call("tk", "scaling")
        self.addCleanup(lambda: self.root.tk.call("tk", "scaling", original_scaling))
        for scale in (1, 2, 2.5):
            with self.subTest(scale=scale):
                self.view.close()
                self.root.tk.call("tk", "scaling", 96 / 72 * scale)
                # Recalculate named default fonts just as a new DPI-aware Tk
                # process does, including installations with limited fonts.
                tkfont.nametofont("TkDefaultFont", root=self.root).configure(size=10)
                tkfont.nametofont("TkTextFont", root=self.root).configure(size=10)
                self.view.show()
                self.view.open_settings()
                self.root.update()
                dialog = self.view.settings_dialog
                close = next(widget for widget in dialog.winfo_children()
                             if isinstance(widget, ttk.Button) and widget.cget("text") == "Fermer")
                notebook = next(widget for widget in dialog.winfo_children() if isinstance(widget, ttk.Notebook))
                self.assertLessEqual(close.winfo_rooty() + close.winfo_height(), self.root.winfo_screenheight())
                for tab in notebook.tabs():
                    notebook.select(tab)
                    self.root.update()
                    self.assertTrue(self.root.nametowidget(tab).winfo_viewable())
                    self.assertLessEqual(close.winfo_y() + close.winfo_height(), dialog.winfo_height())

    def test_immersion_binding_hides_diagnostics_but_keeps_microphone_error_and_stop_visible(self):
        binding = self.view.window.bind("<F9>")
        self.assertTrue(binding)
        # Invoke the registered key callback through Tcl, without changing the
        # desktop focus or generating a real keyboard event on the CI display.
        key_callback = binding.split("[", 1)[1].split()[0]
        self.view.update_microphone("suspended")
        self.view.update_operation("error", "Arrêt explicite")
        self.root.tk.call(key_callback)
        self.root.update()
        self.assertFalse(self.view.settings.diagnostic_mode)
        self.assertEqual(self.view.timing_panel.winfo_manager(), "")
        self.assertEqual(self.view.tone_label.winfo_manager(), "")
        self.assertIn("SUSPENDU", self.view.mic_label.cget("text"))
        self.assertEqual(self.view.mic_label.winfo_manager(), "place")
        self.assertIn(OPERATIONAL["error"]["label"], self.view.operation_label.cget("text"))
        self.assertEqual(self.view.operation_label.winfo_manager(), "place")
        stop = next(button for button in self.view.buttons if button.cget("text") == "Arrêt")
        self.assertEqual(stop.winfo_manager(), "pack")
        stop.invoke()
        self.voice.emergency.assert_called_once()
        self.root.tk.call(key_callback)
        self.assertEqual(self.view.timing_panel.winfo_manager(), "place")

    def test_microphone_labels_are_explicit_and_do_not_change_with_emotional_palette(self):
        self.view.set_options(spectrum_intensity=100)
        self.view.preview_text("Je suis furieux et en colère.")
        for state, label in MIC_LABELS.items():
            self.view.update_microphone(state, "détail technique")
            self.assertIn(label, self.view.mic_label.cget("text"))
            self.assertEqual(self.view.microphone_state, state)
            if state == "error":
                self.assertNotEqual(self.view.mic_label.cget("foreground"), self.view._target_accent())
        with self.assertRaises(ValueError):
            self.view.update_microphone("invented")
        self.voice.toggle.assert_not_called()

    def test_offline_scenario_has_four_reproducible_moods_and_no_audio_or_inference(self):
        self.view.set_options(animations=False)
        with patch("threading.Thread.start", side_effect=AssertionError("unexpected worker")), \
             patch("subprocess.Popen", side_effect=AssertionError("unexpected process")):
            self.assertTrue(self.view.preview_scenario())
            moods = []
            for _ in range(4):
                moods.append(self.view.tone.name)
                self.assertEqual(self.view.state, "thinking")
                self.assertEqual(self.view.model.signal["rms"], 0)
                self.assertIn("APERÇU HORS LIGNE", self.view.state_label.cget("text"))
                self.root.after_cancel(self.view._preview_id)
                self.view._scenario_step()
        self.assertEqual(moods, ["espoir", "attachement", "peur", "apaisement"])
        self.assert_no_scenario()
        self.assertEqual(self.view.state, "silent")
        self.assertIsNone(self.view.after_id)
        self.voice.toggle.assert_not_called()
        self.voice.emergency.assert_not_called()
        self.voice.stop_listening.assert_not_called()

    def test_voice_error_hide_and_close_cancel_the_scenario_without_late_resurrection(self):
        self.view.set_options(animations=False)
        actions = (lambda: self.view.update_event("user_speaking", PCM_DOUBLE),
                   lambda: self.view.update_operation("error", "Erreur fonctionnelle"),
                   lambda: self.view.update_microphone("disabled"),
                   lambda: self.view.update_microphone("error"),
                   self.view.return_to_command, self.view.emergency, self.view.close)
        for action in actions:
            with self.subTest(action=action):
                self.view.show()
                self.view.update_event("silent")
                self.assertTrue(self.view.preview_scenario())
                preview_id = self.view._preview_id
                action()
                self.assert_no_scenario()
                self.assertNotIn(preview_id, self.root.tk.call("after", "info"))
                state = self.view.state
                self.view._scenario_step()
                self.assertEqual(self.view.state, state)


if __name__ == "__main__":
    unittest.main()
