"""The cognitive projection changes peripheral text, never visual/audio state."""
import unittest
from unittest.mock import patch

from jarvis.gpu_session import validate_packet
from jarvis.presence import STATE_LABELS
from jarvis.presence_host import IntegratedPresence
from tests import test_presence as canvas_tests
from tests import test_presence_integration as integration_tests
from tests import test_presence_host as host_tests
from tests.test_gpu_session import packet
from tests.test_jarvis import display_available


class CognitiveTransportTests(unittest.TestCase):
    def test_cognitive_summary_is_bounded_single_line_and_never_changes_frame(self):
        source = packet()
        baseline_frame = validate_packet(source)["frame"]
        source["hud"]["cognitive"] = "Transcription locale · français · ≈ PCM"
        received = validate_packet(source)
        self.assertEqual(received["frame"], baseline_frame)
        self.assertEqual(received["hud"]["cognitive"], source["hud"]["cognitive"])
        for invalid in (None, 3, False, ["Repos"], "x" * 301, "Repos\nsecret", "Repos\tsecret"):
            with self.subTest(invalid=repr(invalid)[:40]):
                source["hud"]["cognitive"] = invalid
                with self.assertRaisesRegex(ValueError, "cognitif"):
                    validate_packet(source)


@unittest.skipUnless(display_available(), "Écran graphique indisponible")
class CognitiveCanvasTests(unittest.TestCase):
    setUp = canvas_tests.PresenceTkTests.setUp

    def test_hidden_summary_creates_no_window_callback_device_or_persistence(self):
        callbacks = self.root.tk.call("after", "info")
        with patch.object(self.store, "set_preference") as save:
            self.assertTrue(self.view.update_cognitive("Contexte préparé"))
            self.assertFalse(self.view.update_cognitive("Contexte préparé"))
            self.assertTrue(self.view.update_cognitive("Repos\n  local"))
        self.assertEqual(self.view.cognitive_text, "Repos local")
        self.assertEqual(self.root.winfo_children(), [])
        self.assertEqual(self.root.tk.call("after", "info"), callbacks)
        self.assertEqual(self.view.state, "silent")
        save.assert_not_called()
        self.app.voice.toggle.assert_not_called()
        with self.assertRaisesRegex(ValueError, "texte"):
            self.view.update_cognitive({"status": "Repos"})

    def test_visible_summary_reuses_status_label_without_changing_the_mesh(self):
        self.view.show()
        self.root.update()
        self.view._cancel_animation()
        items = self.view.canvas.find_all()
        mesh = [self.view.canvas.coords(path) for path in self.view.paths]
        callbacks = self.root.tk.call("after", "info")
        self.view.update_cognitive("Contexte préparé · modèle local")
        self.assertEqual(self.view.state_label.cget("text"), "Contexte préparé · modèle local")
        self.assertEqual(self.view.canvas.find_all(), items)
        self.assertEqual([self.view.canvas.coords(path) for path in self.view.paths], mesh)
        self.assertEqual(self.root.tk.call("after", "info"), callbacks)
        self.view.update_cognitive("")
        self.assertEqual(self.view.state_label.cget("text"), STATE_LABELS["silent"])

    def test_long_status_is_one_line_within_free_mini_space_at_different_dpi(self):
        self.view.close()
        self.view = IntegratedPresence(self.app)
        self.addCleanup(self.view.close)
        original_scaling = self.root.tk.call("tk", "scaling")
        self.addCleanup(lambda: self.root.tk.call("tk", "scaling", original_scaling))
        for scaling in (1., 2.):
            self.root.tk.call("tk", "scaling", 96 / 72 * scaling)
            self.view.set_options(mini_mode=True)
            self.view.show()
            for geometry in ("400x260", "680x360", "480x640"):
                with self.subTest(scaling=scaling, geometry=geometry):
                    self.view.window.geometry(geometry)
                    self.root.update()
                    self.view.update_cognitive("Génération locale · Qwen · mode rapide · " + "modèle " * 45)
                    self.root.update_idletasks()
                    label = self.view.state_label
                    self.assertLessEqual(len(self.view.cognitive_text), 300)
                    self.assertIn("…", label.cget("text"))
                    self.assertNotIn("\n", label.cget("text"))
                    right = label.winfo_x() + label.winfo_reqwidth()
                    self.assertLessEqual(right, self.view.header_controls.winfo_x())
                    self.assertLess(label.winfo_y() + label.winfo_reqheight(), self.view.mic_label.winfo_y())
                    self.view.update_cognitive("")


@unittest.skipUnless(display_available(), "Écran graphique indisponible")
class CognitiveIntegratedTests(unittest.TestCase):
    setUp = integration_tests.PresenceIntegrationTests.setUp
    pump_until = integration_tests.PresenceIntegrationTests.pump_until
    ready_gpu = host_tests.DualEngineTests.ready_gpu

    def test_same_parent_text_survives_engine_switch_and_hidden_gpu_gets_no_updates(self):
        self.presence.session_factory = host_tests.RendererDouble
        self.app.cognitive.update("context")
        self.app.cognitive_view.refresh(force=True)
        child = self.ready_gpu()
        self.assertEqual(child.frames[-1]["hud"]["cognitive"], "Préparation du contexte")
        starts = (list(self.voice.capture.starts), list(self.voice.speech.starts))
        self.presence._gpu_visible = True
        self.app.cognitive.update("context", False)
        self.app.cognitive.update("generating")
        self.app.cognitive_view.refresh(force=True)
        self.assertEqual(child.frames[-1]["hud"]["cognitive"], "Génération locale")
        packets = len(child.frames)
        self.app.cognitive_view.refresh(force=True)
        self.assertEqual(len(child.frames), packets)
        self.presence._gpu_visible = False
        callbacks = self.root.tk.call("after", "info")
        self.app.cognitive.update("idle")
        self.app.cognitive_view.refresh(force=True)
        self.assertEqual(len(child.frames), packets)
        self.assertEqual(self.root.tk.call("after", "info"), callbacks)
        self.presence.set_engine("canvas")
        self.root.update_idletasks()
        self.assertEqual(self.presence.state_label.cget("text"), "Repos")
        self.assertEqual(starts, (self.voice.capture.starts, self.voice.speech.starts))
        self.assertEqual(self.presence.state, "silent")


if __name__ == "__main__":
    unittest.main()
