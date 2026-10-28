"""Visual transport bounds and lifecycle; no microphone or model is opened."""
import copy
import subprocess
import sys
import importlib.util
import os
import queue
import time
import threading
from types import SimpleNamespace
import unittest

from jarvis.gpu_session import GpuSession, _fresh_frame, validate_packet


def packet(seq=1):
    return {"seq": seq, "visible": True,
            "frame": {"time_s": 0., "reactor": 1., "points": ((-.8, 0.), (.8, 0.)),
                      "audio_bands": (0., .2, .1)},
            "hud": {"caption": "Heureux de te revoir 😊 — été, cœur et 12 €", "state": "Parole"},
            "art": {}, "window": {"width": 960, "height": 640}}


class GpuPacketTests(unittest.TestCase):
    def test_import_opens_no_gpu_audio_or_gui_backend(self):
        code = ("import sys; import jarvis.gpu_session; "
                "assert not any(k in sys.modules for k in "
                "('moderngl','glfw','tkinter','sounddevice','piper','PIL'))")
        subprocess.run([sys.executable, "-c", code], check=True, capture_output=True)

    def test_complete_unicode_snapshot_is_copied_without_touching_original(self):
        source = packet()
        before = copy.deepcopy(source)
        result = validate_packet(source)
        self.assertEqual(source, before)
        self.assertEqual(result["hud"]["caption"], source["hud"]["caption"])
        result["hud"]["caption"] = "autre"
        self.assertNotEqual(source["hud"]["caption"], result["hud"]["caption"])

    def test_malformed_or_unbounded_snapshots_fail_before_transport(self):
        changes = ({"seq": True}, {"seq": -1}, {"version": 2}, {"visible": "yes"},
                   {"frame": {}}, {"hud": {"caption": "x"*8193}}, {"unknown": 1})
        for change in changes:
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_packet({**packet(), **change})
        for frame in ({"points": [(0., 0.)]*98}, {"rms": float("nan")},
                      {"audio_bands": (1., 2.)}, {"points": [(0., 0.), (float("inf"), 1.)]},
                      {"details": [[(0., 0.), (1., 1.)]]*9}):
            with self.subTest(frame=frame), self.assertRaises(ValueError):
                validate_packet({**packet(), "frame": {**packet()["frame"], **frame}})

    def test_fresh_release_envelope_is_not_cut_when_original_pcm_expires(self):
        value = {**packet(), "frame_at": 10., "pcm_at": 9., "expression_until": 11.}
        fresh, flags = _fresh_frame(value, 10.05)
        self.assertEqual(fresh["rms"], 0.)
        self.assertEqual(fresh["audio_bands"], (0., .2, .1))
        old, flags = _fresh_frame(value, 10.3)
        self.assertEqual(old["audio_bands"], (0., 0., 0.))
        self.assertEqual(value["frame"]["audio_bands"], (0., .2, .1))
        expired, flags = _fresh_frame(value, 12.)
        self.assertIsNone(expired["surface_family"])
        self.assertEqual(expired["surface_amount"], 0.)


def echo_child(frames, events, quit_event, urgent, options):
    options["heartbeat"].value = time.monotonic()
    events.put({"kind": "ready", "renderer": {"acceleration": "test"}})
    while not quit_event.is_set():
        options["heartbeat"].value = time.monotonic()
        try:
            value = frames.get(timeout=.02)
        except queue.Empty:
            continue
        events.put({"kind": "heartbeat", "rendered_seq": value["seq"]})
    events.put({"kind": "closed"})


def crash_child(_frames, _events, _quit, _urgent, _options):
    os._exit(7)


def hung_child(_frames, _events, _quit, _urgent, _options):
    while True:
        time.sleep(.1)


class SessionWaitMixin:
    def wait_until(self, session, predicate, timeout=5.):
        deadline = time.monotonic()+timeout
        found = []
        while time.monotonic() < deadline:
            found.extend(session.poll())
            if predicate(found):
                return found
            time.sleep(.01)
        self.fail(f"Session did not reach expected state: {found}")


class ProcessContractTests(SessionWaitMixin, unittest.TestCase):
    def test_one_process_coalesces_to_final_state_and_restart_has_no_old_frames(self):
        session = GpuSession(target=echo_child)
        self.addCleanup(session.stop)
        self.assertFalse(session.alive())
        self.assertTrue(session.start())
        self.assertFalse(session.start())
        self.wait_until(session, lambda items: any(item["kind"] == "ready" for item in items))
        for index in range(100):
            self.assertTrue(session.submit(packet(index)))
        self.assertFalse(session.submit(packet(90)))
        self.wait_until(session, lambda items: any(item.get("rendered_seq") == 99 for item in items))
        session.stop()
        self.assertFalse(session.alive())
        self.assertFalse(session.submit(packet(101)))
        self.assertTrue(session.start())
        self.wait_until(session, lambda items: any(item["kind"] == "ready" for item in items))
        self.assertTrue(session.submit(packet(0)))
        self.wait_until(session, lambda items: any(item.get("rendered_seq") == 0 for item in items))

    def test_crash_is_reported_once_and_hung_start_can_be_killed_without_orphan(self):
        crash = GpuSession(target=crash_child)
        self.addCleanup(crash.stop)
        crash.start()
        found = self.wait_until(crash, lambda items: any(item["kind"] == "error" for item in items))
        self.assertIn("7", next(item["message"] for item in found if item["kind"] == "error"))
        self.assertFalse(any(item["kind"] == "error" for item in crash.poll()))
        hung = GpuSession(target=hung_child, startup_timeout=.05)
        self.addCleanup(hung.stop)
        hung.start()
        self.wait_until(hung, lambda items: any(item["kind"] == "error" for item in items))
        import multiprocessing as mp
        pid = hung._process.pid
        began = time.monotonic()
        hung.stop(timeout=.5)
        self.assertLess(time.monotonic()-began, 2.)
        self.assertFalse(hung.alive())
        self.assertNotIn(pid, {process.pid for process in mp.active_children()})
        hung.stop()

    def test_feeder_race_retains_latest_locally_and_stop_action_has_priority(self):
        class DeferredQueue(queue.Queue):
            deferred = True
            def put_nowait(self, value):
                if self.deferred:
                    raise queue.Full
                return super().put_nowait(value)
        session = GpuSession(clock=lambda: 100.)
        session._process = SimpleNamespace(is_alive=lambda: True)
        session._frames = DeferredQueue(1)
        session._events = queue.Queue(16)
        session._urgent = threading.Event()
        session._heartbeat = SimpleNamespace(value=100.)
        session._ready = True
        session._last_seen = 100.
        self.assertTrue(session.submit(packet(7)))
        self.assertEqual(session._pending["seq"], 7)
        session._frames.deferred = False
        for index in range(16):
            session._events.put({"kind": "heartbeat", "at": 100.})
        session._urgent.set()
        result = session.poll()
        self.assertEqual(result[0], {"kind": "action", "action": "stop"})
        self.assertEqual(session._frames.get_nowait()["seq"], 7)
        self.assertIsNone(session._pending)

    def test_heartbeat_timeout_is_one_visible_error_and_invalid_policy_fails(self):
        session = GpuSession(clock=lambda: 103.)
        session._process = SimpleNamespace(is_alive=lambda: True)
        session._frames = queue.Queue(1)
        session._events = queue.Queue(16)
        session._urgent = threading.Event()
        session._heartbeat = SimpleNamespace(value=100.)
        session._ready = True
        session._last_seen = 100.
        self.assertEqual(session.poll()[0]["kind"], "error")
        self.assertEqual(session.poll(), [])
        for options in ({"startup_timeout": 0}, {"heartbeat_timeout": float("inf")}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                GpuSession(**options)


class RealGpuSessionTests(SessionWaitMixin, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import moderngl
            context = moderngl.create_standalone_context(require=330, backend="egl")
            context.release()
        except Exception as error:
            if os.environ.get("JARVIS_REQUIRE_GPU") == "1":
                raise RuntimeError("Required actual EGL session unavailable") from error
            raise unittest.SkipTest(f"Optional EGL unavailable: {error}") from error

    def test_real_child_renders_unicode_hud_hides_and_resumes_without_audio(self):
        session = GpuSession(allow_software=True, headless=True, startup_timeout=10.)
        self.addCleanup(session.stop)
        session.start()
        self.wait_until(session, lambda items: any(item["kind"] == "ready" for item in items))
        session.submit(packet(1))
        first = self.wait_until(session, lambda items: any(item.get("frames", 0) >= 1 for item in items))
        count = max(item.get("frames", 0) for item in first)
        session.submit({**packet(2), "visible": False})
        hidden = self.wait_until(session, lambda items: any(item.get("visible") is False for item in items))
        hidden_count = max(item.get("frames", 0) for item in hidden)
        self.assertGreaterEqual(hidden_count, count)
        later = self.wait_until(session, lambda items: any(item.get("visible") is False for item in items))
        self.assertEqual(max(item.get("frames", 0) for item in later), hidden_count)
        session.submit(packet(3))
        self.wait_until(session, lambda items: any(item.get("frames", 0) > hidden_count for item in items))


if __name__ == "__main__":
    unittest.main()
