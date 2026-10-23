"""Scrollable voice settings use real Tk/SQLite, with no physical audio device."""
from dataclasses import fields, replace
from pathlib import Path
import tempfile
import tkinter as tk
from tkinter import ttk
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from jarvis.config import Settings
from jarvis.storage import Store
from jarvis.voice_config import VoiceSettings
from jarvis.voice_ui import VoiceControls
from tests.test_jarvis import display_available


@unittest.skipUnless(display_available(), "Écran graphique indisponible")
class VoiceSettingsDesktopTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.store = Store(Path(temp.name) / "voice-settings.sqlite3")
        self.addCleanup(self.store.close)
        self.root = tk.Tk()
        self.addCleanup(self.root.destroy)
        self.app = SimpleNamespace(root=self.root, store=self.store, operation=None,
                                   settings=Settings(), font_family="DejaVu Sans")
        self.parent = ttk.Frame(self.root)
        self.parent.pack(fill="both", expand=True)
        with patch("jarvis.voice_ui.AudioProcess"):
            self.voice = VoiceControls(self.app, self.parent)
        self.voice.cancel_speech = Mock()
        self.voice.preview = Mock()
        inventory = patch("jarvis.audio.device_inventory", return_value={
            "input": [{"key": "USB · MME"}], "output": [{"key": "Bluetooth · MME"}]})
        self.inventory = inventory.start()
        self.addCleanup(inventory.stop)

    def open_dialog(self, focus_key=None):
        dialog = self.voice.open_settings(focus_key=focus_key)
        self.root.update()
        return dialog

    def set_value(self, dialog, key, value):
        self.root.setvar(dialog.controls[key].cget("textvariable"), value)

    def assert_inside(self, widget, dialog):
        self.assertTrue(widget.winfo_viewable())
        x, y = widget.winfo_rootx() - dialog.winfo_rootx(), widget.winfo_rooty() - dialog.winfo_rooty()
        self.assertGreaterEqual(x, 0)
        self.assertGreaterEqual(y, 0)
        self.assertLessEqual(x + widget.winfo_width(), dialog.winfo_width())
        self.assertLessEqual(y + widget.winfo_height(), dialog.winfo_height())

    def test_editor_is_unique_and_exposes_every_existing_profile_key_without_persisting(self):
        dialog = self.open_dialog()
        self.assertEqual(set(dialog.controls), {field.name for field in fields(VoiceSettings)})
        self.assertIs(self.voice.open_settings(), dialog)
        self.assertEqual(self.inventory.call_count, 1)
        self.assertFalse(dialog.controls["vad_threshold"].winfo_viewable())
        self.assertIsNone(self.store.get_preference("voice"))
        self.voice.cancel_speech.assert_not_called()
        self.voice.preview.assert_not_called()
        dialog.cancel_button.invoke()
        self.assertIsNone(self.voice.settings_dialog)
        self.assertIsNone(self.store.get_preference("voice"))

    def test_fixed_actions_and_keyboard_target_remain_accessible_at_small_sizes_and_dpi(self):
        for scaling in (1., 2.5):
            with self.subTest(scaling=scaling):
                self.root.tk.call("tk", "scaling", 96 / 72 * scaling)
                dialog = self.open_dialog()
                for geometry in ("360x340", "580x380", "380x620"):
                    with self.subTest(geometry=geometry):
                        dialog.geometry(geometry)
                        self.root.update()
                        for action in (dialog.save_button, dialog.cancel_button):
                            self.assert_inside(action, dialog)
                        self.assertTrue(dialog.focus_control("cpu_threads"))
                        self.root.update()
                        self.assertTrue(dialog.controls["cpu_threads"].winfo_viewable())
                        canvas = dialog.settings_canvas
                        control = dialog.controls["cpu_threads"]
                        relative_y = control.winfo_rooty() - canvas.winfo_rooty()
                        self.assertGreaterEqual(relative_y, 0)
                        self.assertLessEqual(relative_y + control.winfo_height(), canvas.winfo_height())
                        dialog.focus_force()
                        dialog.focus_control("input_device")
                        self.root.update()
                        self.assertIs(dialog.focus_get(), dialog.controls["input_device"])
                        self.assertLessEqual(dialog.controls["input_device"].winfo_width(), canvas.winfo_width())
                        self.assertGreaterEqual(dialog.controls["input_device"].winfo_rooty(), canvas.winfo_rooty())
                dialog.destroy()

    def test_cancel_and_escape_discard_drafts_including_hidden_advanced_settings(self):
        original = replace(self.voice.settings, vad_threshold=.72, cpu_threads=3)
        self.voice.settings = original
        self.store.set_preference("voice", original.to_dict())
        for use_escape in (False, True):
            with self.subTest(escape=use_escape):
                dialog = self.open_dialog("vad_threshold")
                self.set_value(dialog, "vad_threshold", ".4")
                self.set_value(dialog, "cpu_threads", "7")
                self.set_value(dialog, "speed", "1.4")
                if use_escape:
                    dialog.focus_force()
                    self.root.update()
                    dialog.event_generate("<Escape>")
                    self.root.update()
                else:
                    dialog.cancel_button.invoke()
                self.assertIsNone(self.voice.settings_dialog)
                self.assertEqual(self.voice.settings, original)
                self.assertEqual(self.store.get_preference("voice"), original.to_dict())
        self.voice.preview.assert_not_called()
        self.voice.cancel_speech.assert_not_called()

    def test_save_validates_advanced_values_before_persistence_and_preserves_devices(self):
        original = replace(self.voice.settings, input_device="USB · MME", output_device="Bluetooth · MME")
        self.voice.settings = original
        self.store.set_preference("voice", original.to_dict())
        dialog = self.open_dialog("vad_threshold")
        for key, invalid in (("vad_threshold", ".1"), ("cpu_threads", "9")):
            with self.subTest(key=key):
                self.set_value(dialog, "vad_threshold", str(original.vad_threshold))
                self.set_value(dialog, "cpu_threads", str(original.cpu_threads))
                self.set_value(dialog, key, invalid)
                with patch("jarvis.voice_ui.messagebox.showerror") as error:
                    dialog.save_button.invoke()
                error.assert_called_once()
                self.assertEqual(self.voice.settings, original)
                self.assertEqual(self.store.get_preference("voice"), original.to_dict())
                self.assertTrue(dialog.winfo_exists())
        self.set_value(dialog, "vad_threshold", ".72")
        self.set_value(dialog, "cpu_threads", "3")
        self.set_value(dialog, "speed", "1.25")
        dialog.save_button.invoke()
        saved = self.store.get_preference("voice")
        self.assertEqual((saved["vad_threshold"], saved["cpu_threads"], saved["speed"]), (.72, 3, 1.25))
        self.assertEqual((saved["input_device"], saved["output_device"]), (original.input_device, original.output_device))
        self.assertEqual(self.voice.settings.to_dict(), saved)
        self.assertFalse(self.voice.listening)
        self.voice.cancel_speech.assert_called_once()
        self.voice.preview.assert_not_called()

    def test_preview_explicitly_retains_existing_save_then_preview_contract(self):
        dialog = self.open_dialog()
        self.set_value(dialog, "speed", "1.2")
        preview = next(widget for widget in dialog.controls["speed"].master.winfo_children()
                       if widget.winfo_name() == "preview_voice")
        preview.invoke()
        self.assertEqual(self.store.get_preference("voice")["speed"], 1.2)
        self.voice.preview.assert_called_once()
        self.assertTrue(dialog.winfo_exists())

    def test_listening_or_generation_blocks_editor_without_enumerating_devices(self):
        for listening, operation in ((True, None), (False, "chat")):
            with self.subTest(listening=listening, operation=operation):
                self.voice.listening, self.app.operation = listening, operation
                with patch("jarvis.voice_ui.messagebox.showinfo") as info:
                    self.assertIsNone(self.voice.open_settings())
                info.assert_called_once()
        self.inventory.assert_not_called()
