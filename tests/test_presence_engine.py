"""Renderer preference decisions never start, replace or stop audio services."""
import subprocess
import sys
import unittest

from jarvis.presence_engine import EnginePreferences


class EnginePreferenceTests(unittest.TestCase):
    def test_initial_and_invalid_legacy_preferences_keep_canvas(self):
        for value in (None, [], "gpu", {}, {"mode": []}, {"mode": "unknown"}):
            with self.subTest(value=value):
                self.assertEqual(EnginePreferences.from_dict(value).target, "canvas")

    def test_automatic_choice_is_sticky_and_failure_requires_explicit_retry(self):
        first = EnginePreferences().choose("auto")
        self.assertEqual(first.target, "gpu")
        cached = EnginePreferences.from_dict(first.ready().to_dict())
        self.assertEqual(cached.mode, "auto")
        self.assertEqual(cached.target, "gpu")
        failed = EnginePreferences.from_dict(cached.failed("Pilote OpenGL absent").to_dict())
        self.assertEqual(failed.mode, "auto")
        self.assertEqual(failed.target, "canvas")
        self.assertEqual(failed.reason, "Pilote OpenGL absent")
        self.assertEqual(failed.choose("auto").target, "canvas")
        self.assertEqual(failed.retry().target, "gpu")

    def test_forced_gpu_remains_selected_after_failure_and_canvas_is_always_available(self):
        failed = EnginePreferences().choose("gpu").failed("Erreur shader")
        self.assertEqual((failed.mode, failed.target), ("gpu", "canvas"))
        self.assertEqual(failed.choose("canvas").target, "canvas")
        self.assertEqual(failed.choose("gpu").target, "gpu")
        self.assertEqual(failed.reason, "Erreur shader")
        with self.assertRaises(ValueError):
            failed.choose("other")

    def test_contract_import_needs_no_graphics_audio_or_gui_dependency(self):
        subprocess.run([sys.executable, "-c", "import sys; import jarvis.presence_engine; "
                        "assert not any(n in sys.modules for n in ('tkinter','moderngl','glfw','sounddevice'))"],
                       check=True, capture_output=True)
