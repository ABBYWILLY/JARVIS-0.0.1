"""Real Tk/SQLite/voice orchestration; renderer transport is an explicit double."""
import copy
import os
import sqlite3
from dataclasses import replace
from functools import partial
import time
import unittest
from unittest.mock import patch

from jarvis.gpu_config import GpuSettings
from jarvis.gpu_session import validate_packet
from jarvis.presence_host import IntegratedPresence
from jarvis.richtext import parse_text
from tests.test_jarvis import display_available
from tests import test_presence_integration


class RendererDouble:
    instances = []

    def __init__(self):
        self.events, self.frames = [], []
        self.running = False
        self.stops = 0
        self.instances.append(self)

    def start(self):
        self.running = True
        return True

    def alive(self):
        return self.running

    def poll(self):
        events, self.events = self.events, []
        return events

    def submit(self, packet):
        self.frames.append(validate_packet(copy.deepcopy(packet)))
        return self.running

    def stop(self):
        self.stops += 1
        self.running = False


@unittest.skipUnless(display_available(), "Écran graphique indisponible")
class DualEngineTests(test_presence_integration.PresenceIntegrationTests):
    def setUp(self):
        super().setUp()
        self.assertIsInstance(self.presence, IntegratedPresence)
        self.presence.session_factory = RendererDouble
        RendererDouble.instances = []
        self.root.update()

    def ready_gpu(self):
        self.assertTrue(self.presence.set_engine("gpu"))
        child = self.presence._gpu
        child.events.append({"kind": "ready", "renderer": {"acceleration": "test_double"}})
        self.pump_until(lambda: self.presence.active_engine == "gpu")
        self.root.update()
        return child

    def test_switch_both_directions_preserves_audio_conversation_and_live_state(self):
        mid, epoch = self.start_audio_contract()
        starts = (list(self.voice.capture.starts), list(self.voice.speech.starts))
        model, semantic = self.presence.model, self.presence.semantic
        saved = self.store.messages(self.app.session_id)
        child = self.ready_gpu()
        self.assertFalse(self.presence.window.winfo_ismapped())
        self.assertEqual(self.presence.state, "jarvis_speaking")
        self.assertEqual(child.frames[-1]["hud"]["caption"], self.presence.caption_text)
        self.assertTrue(child.frames[-1]["visible"])
        self.assertTrue(self.presence.set_engine("canvas"))
        self.root.update()
        self.assertFalse(child.alive())
        self.assertEqual(child.stops, 1)
        self.assertTrue(self.presence.window.winfo_ismapped())
        self.assertIs(self.presence.model, model)
        self.assertIs(self.presence.semantic, semantic)
        self.assertEqual(self.presence.state, "jarvis_speaking")
        self.assertEqual(self.voice.epoch, epoch)
        self.assertEqual(starts, (self.voice.capture.starts, self.voice.speech.starts))
        self.assertTrue(self.voice.capture.alive())
        self.assertTrue(self.voice.speech.alive())
        self.assertEqual(self.store.messages(self.app.session_id), saved)
        self.assertEqual(self.store.messages(self.app.session_id)[1]["id"], mid)

    def test_gpu_animation_clock_and_measured_diagnostics_are_separate_from_audio(self):
        child = self.ready_gpu()
        self.presence.update_event("thinking")
        packet = child.frames[-1]
        self.assertTrue(packet["animation"]["active"])
        self.assertEqual(packet["animation"]["orbit_target"], self.presence._gpu_scene._orbit_targets())
        self.assertEqual(packet["frame"]["rms"], 0.)
        self.assertIn("non mesurés", packet["hud"]["performance"])
        child.events.append({"kind": "heartbeat", "size": (1920, 1080), "visible": True,
            "resolution": {"internal_size": (1920, 1080)},
            "timing": {"actual_draw_fps": 58.4, "frame_p95_ms": 19.2}})
        self.pump_until(lambda: bool(self.presence.gpu_diagnostics))
        self.assertIn("58.4 FPS dessinés", self.presence.gpu_runtime_summary())
        self.assertIn("1920 × 1080", self.presence.gpu_runtime_summary())
        self.assertIn("frame_p95_ms", self.presence.semantic_diagnostics())
        self.presence.set_options(reduced_motion=True)
        self.assertFalse(child.frames[-1]["animation"]["active"])
        self.assertFalse(self.voice.capture.alive())

    def test_visible_engine_buttons_and_gpu_ipc_preserve_playback_and_persist_choice(self):
        self.start_audio_contract()
        starts = (list(self.voice.capture.starts), list(self.voice.speech.starts))
        epoch = self.voice.epoch
        self.assertTrue(self.presence.engine_buttons["canvas"].winfo_viewable())
        self.assertTrue(self.presence.engine_buttons["gpu"].winfo_viewable())
        self.assertEqual(self.presence.engine_choice.get(), "canvas")
        self.presence.engine_buttons["gpu"].invoke()
        child = self.presence._gpu
        self.assertEqual(self.presence.engine_choice.get(), "canvas")  # Actual engine until ready.
        child.events.append({"kind": "ready"})
        self.pump_until(lambda: self.presence.active_engine == "gpu")
        self.assertEqual(self.presence.engine_choice.get(), "gpu")
        child.events.append({"kind": "action", "action": "engine_canvas"})
        self.pump_until(lambda: self.presence.active_engine == "canvas")
        self.root.update()
        self.assertTrue(self.presence.engine_buttons["gpu"].winfo_viewable())
        self.assertFalse(child.alive())
        self.assertEqual(self.store.get_preference("presence_engine")["mode"], "canvas")
        self.assertEqual(starts, (self.voice.capture.starts, self.voice.speech.starts))
        self.assertEqual(self.voice.epoch, epoch)
        self.assertTrue(self.voice.capture.alive() and self.voice.speech.alive())

    def test_engine_controls_remain_top_left_and_keyboard_switches_in_mini_and_high_dpi(self):
        original = self.root.tk.call("tk", "scaling")
        self.addCleanup(lambda: self.root.tk.call("tk", "scaling", original))
        for scale in (1., 2., 2.5):
            for mini in (False, True):
                with self.subTest(scale=scale, mini=mini):
                    self.root.tk.call("tk", "scaling", scale*96/72)
                    self.presence.set_options(mini_mode=mini)
                    self.presence.window.geometry("420x300" if mini else "640x440")
                    self.root.update()
                    for button in self.presence.engine_buttons.values():
                        self.assertTrue(button.winfo_viewable())
                        # Compare client pixels: Windows Toplevel root coordinates
                        # include its native title bar; the Canvas is the client area.
                        x = button.winfo_rootx()-self.presence.canvas.winfo_rootx()
                        y = button.winfo_rooty()-self.presence.canvas.winfo_rooty()
                        self.assertGreaterEqual(x, 0)
                        self.assertGreaterEqual(y, 0)
                        self.assertLessEqual(x+button.winfo_width(), self.presence.canvas.winfo_width())
                        self.assertLessEqual(y+button.winfo_height(), self.presence.canvas.winfo_height())
                        self.assertLessEqual(y+button.winfo_height(), 60*scale)
        self.presence.window.focus_force()
        self.presence.window.event_generate("<Control-F7>")
        self.root.update()
        self.assertEqual(self.presence.engine_preferences.mode, "gpu")
        self.assertIsNotNone(self.presence._gpu)

    def test_failure_falls_back_once_and_manual_retry_preserves_preference(self):
        child = self.ready_gpu()
        child.events.append({"kind": "error", "message": "Shader test failure"})
        self.pump_until(lambda: self.presence.active_engine == "canvas")
        self.assertIn("Shader test failure", self.presence.engine_status.get())
        self.assertTrue(self.presence.window.winfo_ismapped())
        self.assertEqual(self.presence.engine_preferences.mode, "gpu")
        self.assertTrue(self.presence.engine_preferences.gpu_failed)
        self.presence.show()
        self.root.update()
        self.assertEqual(len(RendererDouble.instances), 1)
        self.presence.retry_gpu()
        self.assertEqual(len(RendererDouble.instances), 2)
        self.assertFalse(self.presence.engine_preferences.gpu_failed)

    def test_gpu_failure_stays_latched_when_database_is_unwritable(self):
        child = self.ready_gpu()
        child.events.append({"kind": "error", "message": "Driver stopped"})
        with patch.object(self.store, "set_preference", side_effect=sqlite3.OperationalError("disk full")):
            self.pump_until(lambda: self.presence.active_engine == "canvas")
        self.presence.show()
        self.assertTrue(self.presence.engine_preferences.gpu_failed)
        self.assertEqual(len(RendererDouble.instances), 1)

    def test_failed_preview_restores_hidden_command_and_render_error_keeps_audio_alive(self):
        self.presence.return_to_command()
        self.presence.open_gpu_settings()
        self.presence.gpu_studio.preview()
        child = self.presence._gpu
        child.events.append({"kind": "error", "message": "Unavailable preview"})
        self.pump_until(lambda: self.presence._gpu is None)
        self.assertFalse(self.presence._visible())
        self.assertFalse(self.presence.window.winfo_ismapped())
        self.presence.gpu_studio.cancel()
        self.presence.show()
        self.start_audio_contract()
        child = self.ready_gpu()
        self.presence.return_to_command()
        with patch.object(child, "submit", side_effect=ValueError("Invalid visual packet")):
            self.presence.update_event("jarvis_speaking", {"rms": .1, "wave": [.1]*48})
        self.assertEqual(self.presence.active_engine, "canvas")
        self.assertTrue(self.voice.speech.alive())
        self.assertTrue(self.voice.capture.alive())

    def test_return_while_initializing_stays_hidden_and_closed_child_can_reopen(self):
        self.presence.set_engine("gpu")
        child = self.presence._gpu
        self.presence.return_to_command()
        child.events.append({"kind": "ready"})
        self.pump_until(lambda: self.presence._gpu_ready)
        self.assertFalse(child.frames[-1]["visible"])
        self.assertFalse(self.presence._visible())
        child.events.append({"kind": "closed"})
        self.pump_until(lambda: self.presence._gpu is None)
        self.assertFalse(child.alive())
        self.presence.show()
        self.assertIsNot(self.presence._gpu, child)

    def test_preferences_survive_restart_and_do_not_overwrite_other_engine(self):
        self.store.set_preference("presence_gpu", {"future_gpu": "keep", "halo_radius": 135})
        self.presence.close()
        second = IntegratedPresence(self.app)
        self.addCleanup(second.close)
        second.session_factory = RendererDouble
        self.assertEqual(second.active_engine, "canvas")
        original_2d = copy.deepcopy(self.store.get_preference("presence"))
        second.set_gpu_options(particle_size=180)
        second.set_engine("auto")
        second._gpu.events.append({"kind": "ready"})
        self.pump_until(lambda: second.active_engine == "gpu")
        second.close()
        third = IntegratedPresence(self.app)
        self.addCleanup(third.close)
        self.assertEqual(third.engine_preferences.mode, "auto")
        self.assertEqual(third.engine_preferences.target, "gpu")
        self.assertEqual(third.gpu_settings.particle_size, 180)
        self.assertEqual(third.gpu_settings.halo_radius, 135)
        self.assertEqual(self.store.get_preference("presence_gpu")["future_gpu"], "keep")
        self.assertEqual(self.store.get_preference("presence"), original_2d)
        self.assertIsNone(third._gpu)  # No probe at application initialization.

    def test_draft_gpu_preview_is_reversible_and_preempted_by_real_pcm(self):
        self.presence.return_to_command()
        original = self.presence.gpu_settings
        before = self.store.get_preference("presence_gpu", {})
        self.presence.open_gpu_settings()
        studio = self.presence.gpu_studio
        studio.change(halo_radius=175)
        self.assertTrue(studio.preview())
        child = self.presence._gpu
        child.events.append({"kind": "ready"})
        self.pump_until(lambda: self.presence._gpu_ready)
        self.assertEqual(child.frames[-1]["art"]["halo_radius"], 175)
        self.assertEqual(self.presence.state, "thinking")  # First click resumes once ready.
        self.assertTrue(self.presence._demo.active)
        self.presence.update_event("user_speaking", {"rms": .08, "wave": [.1, -.1]*24})
        self.root.update()
        self.assertFalse(studio.previewing)
        self.assertFalse(self.presence._demo.active)
        self.assertEqual(self.presence.state, "user_speaking")
        self.assertEqual(self.presence.active_engine, "canvas")
        self.assertEqual(self.presence.gpu_settings, original)
        self.assertEqual(self.store.get_preference("presence_gpu", {}), before)
        self.assertEqual(studio.draft.halo_radius, 175)

    def test_terminal_expressions_use_same_pcm_timeline_and_interrupt_immediately(self):
        child = self.ready_gpu()
        for index, text in enumerate(("Heureux de te revoir 😊", "Je t'aime ❤️", "C'est drôle 😂"), 1):
            with self.subTest(text=text):
                self.presence.begin_response()
                self.presence.update_event("silent")
                document = parse_text(text)
                events, plan = self.presence.prepare_segment(text, document.text, 0)
                self.presence.queue_expressions(index, 1, text, 0, len(text), document.events)
                caption = {"text": document.text, "response_id": index, "segment_id": 1, "fraction": 1.}
                self.presence.update_event("jarvis_speaking", {"rms": .1, "wave": [.1]*48,
                    "bands": (.3, .5, .1)}, caption)
                self.presence.complete_segment(caption)
                self.presence._render()
                self.assertIsNotNone(child.frames[-1]["frame"]["surface_family"])
                self.assertTrue(self.presence.semantic.active)
                self.presence.update_event("user_speaking", {"rms": .05, "wave": [.05]*48})
                self.assertIsNone(child.frames[-1]["frame"]["surface_family"])
                self.assertEqual(child.frames[-1]["frame"]["audio_bands"], (0., 0., 0.))
                self.assertFalse(self.presence.semantic.active)
                self.assertFalse(self.presence._semantic_cues)

    def test_real_pcm_deadline_drives_visual_state_and_outgoing_aura_cancels_on_stop(self):
        self.start_audio_contract()
        child = self.ready_gpu()
        epoch = self.voice.epoch
        self.presence.update_event("thinking")
        self.presence.begin_response()
        played = self.played(epoch, delay=.25)
        played.payload.update(bands=(.06, .04, .02), spectrum_status="ready")
        self.voice.speech.events.append(played)
        self.voice.poll()
        self.assertEqual(child.frames[-1]["frame"]["voice_envelopes"], (0., 0., 0.))
        self.assertTrue(self.voice.pending_visuals)
        self.pump_until(lambda: not self.voice.pending_visuals)
        self.pump_until(lambda: max(child.frames[-1]["frame"]["voice_envelopes"]) > .1)
        frame = child.frames[-1]["frame"]
        self.assertEqual(frame["visual_state"], 4)
        self.assertEqual(self.presence.state, "jarvis_speaking")
        self.assertTrue(all(type(channel) is int for channel in child.frames[-1]["hud"]["caption_accent"]))
        self.presence.update_event("user_speaking", {"rms": .07, "wave": [.05]*48})
        frame = child.frames[-1]["frame"]
        self.assertEqual(frame["visual_state"], 2)
        self.assertEqual(frame["voice_envelopes"], (0., 0., 0.))
        self.assertEqual(frame["audio_bands"], (0., 0., 0.))
        self.assertTrue(self.voice.speech.alive())  # Visual changes do not stop the device.
        self.presence.emergency()
        self.assertEqual(child.frames[-1]["frame"]["voice_envelopes"], (0., 0., 0.))
        self.assertFalse(self.voice.speech.alive())  # Explicit stop owns device cancellation.

    def test_real_spawned_renderer_receives_host_state_and_switches_back_cleanly(self):
        try:
            import moderngl
            context = moderngl.create_standalone_context(require=330, backend="egl")
            context.release()
        except Exception as error:
            if os.environ.get("JARVIS_REQUIRE_GPU") == "1":
                raise RuntimeError("Required EGL host integration unavailable") from error
            self.skipTest(f"Optional EGL unavailable: {error}")
        from jarvis.gpu_session import GpuSession
        self.presence.session_factory = partial(GpuSession, headless=True, allow_software=True)
        self.presence.update_event("thinking")
        self.presence.set_engine("gpu")
        self.pump_until(lambda: self.presence.active_engine == "gpu")
        child = self.presence._gpu
        self.presence.update_event("listening", {"rms": .08, "wave": [.1, -.1]*24})
        self.assertEqual(self.presence.model.signal["rms"], .08)
        self.assertTrue(child.alive())
        self.assertIsNone(self.app.operation)
        self.assertFalse(self.voice.capture.alive())  # Synthetic test input, no device.
        self.presence.set_engine("canvas")
        self.assertFalse(child.alive())
        self.assertEqual(self.presence.state, "listening")


if __name__ == "__main__":
    unittest.main()
