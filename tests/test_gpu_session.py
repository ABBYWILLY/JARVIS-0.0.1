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

from jarvis.gpu_session import ACTIONS, GpuSession, _dispatch_action, _fresh_frame, validate_packet
from jarvis.gpu_session import _release_gpu_resources


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
        for animation in ({"active": 1}, {"unknown": 1}, {"orbit_tau": 0.},
                          {"core_target": float("nan")}, {"orbit_velocity": (1., 2.)},
                          {"orbit_target": (0., 0., 30.)}):
            with self.subTest(animation=animation), self.assertRaises(ValueError):
                validate_packet({**packet(), "animation": animation})

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

    def test_state_language_fields_are_bounded_copied_and_keep_operational_state(self):
        values = {"visual_state": 3, "visual_mix": (.1, .2, .7), "voice_envelopes": (.3, .5, .2),
                  "input_energy": .2, "receipt": .6}
        source = {**packet(), "frame": {**packet()["frame"], **values}}
        original = copy.deepcopy(source)
        validated = validate_packet(source)
        self.assertEqual(source, original)
        for key, value in values.items():
            self.assertEqual(validated["frame"][key], value)
        changes = ({"visual_state": True}, {"visual_state": 3.}, {"visual_state": -1}, {"visual_state": 6},
                   {"visual_mix": (0., 1.)}, {"visual_mix": (0., .5, 1.1)},
                   {"voice_envelopes": (False, 0., 0.)}, {"voice_envelopes": (0., float("nan"), 0.)},
                   {"receipt": -.01}, {"receipt": True}, {"input_energy": 1.01}, {"input_energy": float("inf")})
        for change in changes:
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_packet({**source, "frame": {**source["frame"], **change}})

    def test_stale_voice_input_and_receipt_clear_without_cutting_a_fresh_parent_release(self):
        values = {"visual_state": 3, "visual_mix": (.1, .2, .7), "voice_envelopes": (.3, .5, .2),
                  "input_energy": .2, "receipt": .6}
        source = {**packet(), "frame_at": 10., "pcm_at": 9.,
                  "frame": {**packet()["frame"], **values}}
        original = copy.deepcopy(source)
        release, _ = _fresh_frame(source, 10.05)
        self.assertEqual(release["rms"], 0.)
        for key, value in values.items():
            self.assertEqual(release[key], value)
        stale, _ = _fresh_frame(source, 10.21)
        self.assertEqual(stale["voice_envelopes"], (0., 0., 0.))
        self.assertEqual(stale["input_energy"], 0.)
        self.assertEqual(stale["receipt"], 0.)
        self.assertEqual(stale["visual_state"], 3)
        self.assertEqual(stale["visual_mix"], values["visual_mix"])
        self.assertEqual(source, original)


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


def action_child(_frames, events, quit_event, urgent, options):
    options["heartbeat"].value = time.monotonic()
    events.put({"kind": "ready", "renderer": {"acceleration": "command_transport_test"}})
    for name in ("engine_canvas", "engine_gpu", "toggle_engine", "stop"):
        _dispatch_action(events, urgent, name)
    while not quit_event.wait(.02):
        options["heartbeat"].value = time.monotonic()


def late_cleanup_child(_frames, events, quit_event, _urgent, options):
    options["heartbeat"].value = time.monotonic()
    events.put({"kind": "ready"})
    quit_event.wait(3.)
    events.put({"kind": "error", "message": "Fermeture GPU : renderer: resource lost"})
    events.put({"kind": "closed", "cleanup_errors": ["renderer: resource lost"]})


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
    def test_cleanup_attempts_all_resources_and_reports_deferred_renderer_failures(self):
        calls = []
        class Resource:
            release_errors = ()
            def __init__(self, name, fails=False):
                self.name, self.fails = name, fails
            def shutdown(self):
                calls.append(self.name)
                if self.fails:
                    raise RuntimeError("direct failure")
            release = shutdown
        renderer = Resource("renderer")
        renderer.release_errors = ("RuntimeError: deferred failure",)
        errors = _release_gpu_resources((("hud", Resource("hud", True)),
                                        ("renderer", renderer), ("framebuffer", Resource("framebuffer")),
                                        ("context", Resource("context")), ("missing", None)))
        self.assertEqual(calls, ["hud", "renderer", "framebuffer", "context"])
        self.assertEqual(errors, ["hud: RuntimeError: direct failure",
                                  "renderer: RuntimeError: deferred failure"])

    def test_stop_drains_late_cleanup_evidence_and_idempotent_report_is_copied(self):
        session = GpuSession(target=late_cleanup_child)
        self.addCleanup(session.stop)
        session.start()
        self.wait_until(session, lambda items: any(item["kind"] == "ready" for item in items))
        report = session.stop(timeout=1.)
        self.assertEqual(report["status"], "cleanup_failed")
        self.assertTrue(report["acknowledged"])
        self.assertFalse(report["forced"])
        self.assertEqual(report["cleanup_errors"], ["renderer: resource lost"])
        self.assertIn("resource lost", report["errors"][0]["message"])
        report["cleanup_errors"].clear()
        report["errors"][0]["message"] = "mutated"
        self.assertIn("resource lost", session.stop()["errors"][0]["message"])
        self.assertEqual(session.shutdown_report["cleanup_errors"], ["renderer: resource lost"])
        self.assertIsNone(session._process)
        self.assertIsNone(session._events)

    def test_repeated_spawn_stop_and_forced_kill_leave_no_owned_children_or_pending_frames(self):
        import multiprocessing as mp
        owned = []
        session = GpuSession(target=echo_child)
        self.addCleanup(session.stop)
        for cycle in range(5):
            session.start()
            owned.append(session._process.pid)
            self.wait_until(session, lambda items: any(item["kind"] == "ready" for item in items))
            for seq in range(80):
                session.submit(packet(seq))
            self.wait_until(session, lambda items: any(item.get("rendered_seq") == 79 for item in items))
            report = session.stop(timeout=1.)
            self.assertEqual(report["status"], "complete")
            self.assertTrue(report["acknowledged"])
            self.assertFalse(report["forced"])
            self.assertEqual(report["cleanup_errors"], [])
            self.assertIsNone(session._pending)
            self.assertIsNone(session._frames)
            self.assertIsNone(session._events)
            self.assertFalse(set(owned) & {child.pid for child in mp.active_children()})
        hung = GpuSession(target=hung_child, startup_timeout=.05)
        self.addCleanup(hung.stop)
        for cycle in range(2):
            hung.start()
            owned.append(hung._process.pid)
            report = hung.stop(timeout=.5)
            self.assertEqual(report["status"], "forced")
            self.assertTrue(report["forced"])
            self.assertFalse(report["acknowledged"])
            self.assertFalse(set(owned) & {child.pid for child in mp.active_children()})

    def test_large_abandoned_packets_do_not_leave_queue_feeders_after_forced_shutdown(self):
        import multiprocessing as mp
        feeders, pids = [], []
        session = GpuSession(target=hung_child)
        self.addCleanup(session.stop)
        for cycle in range(3):
            session.start()
            pids.append(session._process.pid)
            value = packet()
            # Valid presentation data above the Linux/Windows pipe capacity.
            # The child deliberately never consumes it.
            value["hud"].update({f"extra{index}": "x"*8192 for index in range(12)})
            self.assertTrue(session.submit(value))
            feeder = session._frames._thread
            feeders.append(feeder)
            self.assertTrue(feeder.is_alive())
            report = session.stop(timeout=.8)
            self.assertTrue(report["forced"])
            self.assertFalse(any(thread.is_alive() for thread in feeders))
            self.assertFalse(set(pids) & {child.pid for child in mp.active_children()})
            self.assertEqual(report["cleanup_errors"], [])
            self.assertIsNone(session._frames)

    def test_unexpected_frame_feeder_error_is_visible_once_but_shutdown_discards_are_not_errors(self):
        session = GpuSession(target=echo_child)
        self.addCleanup(session.stop)
        session.start()
        self.wait_until(session, lambda items: any(item["kind"] == "ready" for item in items))
        session._frames._on_queue_feeder_error(BrokenPipeError("runtime transport failure"), b"unused")
        result = session.poll()
        errors = [item for item in result if item.get("kind") == "error"]
        self.assertEqual(len(errors), 1)
        self.assertIn("runtime transport failure", errors[0]["message"])
        self.assertFalse(any(item.get("kind") == "error" for item in session.poll()))
        callback = session._frames._on_queue_feeder_error
        session.stop()
        callback(BrokenPipeError("expected abandoned packet"), b"unused")
        self.assertEqual(len(session._frame_errors), 1)

    def test_unstoppable_process_retains_channels_for_retry_and_reports_failed_termination(self):
        class Unstoppable:
            def join(self, _timeout): pass
            def is_alive(self): return True
            def terminate(self): pass
            def kill(self): pass
            def close(self): raise AssertionError("must not close a live process handle")
        session = GpuSession()
        process = session._process = Unstoppable()
        frames = session._frames = queue.Queue(1)
        events = session._events = queue.Queue(16)
        session._quit = threading.Event()
        with self.assertRaisesRegex(RuntimeError, "aucun second moteur"):
            session.stop(timeout=.1)
        self.assertIs(session._process, process)
        self.assertIs(session._frames, frames)
        self.assertIs(session._events, events)
        self.assertTrue(session._quit.is_set())
        self.assertEqual(session.shutdown_report["status"], "termination_failed")

    def test_reader_is_closed_before_feeder_sentinel_to_prevent_native_double_close(self):
        import multiprocessing as mp
        class DeadProcess:
            def join(self, _timeout): pass
            def is_alive(self): return False
            def close(self): pass
        class SentinelQueue:
            def __init__(self):
                self._reader, self._writer = mp.Pipe(duplex=False)
                self.native_closed, self.release_close = threading.Event(), threading.Event()
                self._thread = threading.Thread(target=self.consume_sentinel)
                native_close = self._reader._close
                def controlled_native_close():
                    native_close()
                    if threading.current_thread() is self._thread:
                        # Hold the native-close / _handle=None interval open.
                        # Closing this reader after posting the sentinel would
                        # deterministically double-close the same OS handle.
                        self.native_closed.set()
                        self.release_close.wait(1.)
                self._reader._close = controlled_native_close
            def consume_sentinel(self):
                self._reader.close()
                self.native_closed.set()
            def cancel_join_thread(self): pass
            def close(self):
                self._thread.start()
                if not self.native_closed.wait(1.):
                    raise RuntimeError("sentinel fixture did not run")
        channel = SentinelQueue()
        session = GpuSession()
        session._process, session._frames = DeadProcess(), channel
        session._quit = threading.Event()
        try:
            report = session.stop(timeout=.6)
            self.assertEqual(report["status"], "unconfirmed")
            self.assertFalse(channel._thread.is_alive())
            self.assertIsNone(session._process)
            self.assertIsNone(session._frames)
        finally:
            channel.release_close.set()
            if channel._thread.ident is not None:
                channel._thread.join(1.)
            channel._reader.close()
            channel._writer.close()

    def test_channel_cleanup_can_retry_without_joining_an_already_closed_process(self):
        class DeadProcess:
            closed, joins = False, 0
            def join(self, _timeout):
                if self.closed:
                    raise ValueError("process object is closed")
                self.joins += 1
            def is_alive(self): return False
            def close(self): self.closed = True
        class FlakyChannel:
            calls = 0
            def cancel_join_thread(self): pass
            def close(self):
                self.calls += 1
                if self.calls == 1:
                    raise OSError("temporary channel cleanup failure")
        session = GpuSession()
        process = session._process = DeadProcess()
        channel = session._frames = FlakyChannel()
        session._quit = threading.Event()
        with self.assertRaisesRegex(OSError, "temporary channel"):
            session.stop()
        self.assertTrue(process.closed)
        self.assertIsNone(session._process)
        self.assertIs(session._frames, channel)
        report = session.stop()
        self.assertEqual(process.joins, 1)
        self.assertEqual(channel.calls, 2)
        self.assertEqual(report["status"], "unconfirmed")
        self.assertIsNone(session._frames)

    def test_visible_engine_commands_cross_real_spawn_transport_with_stop_priority(self):
        session = GpuSession(target=action_child)
        self.addCleanup(session.stop)
        session.start()
        found = self.wait_until(session, lambda items:
            {item.get("action") for item in items if item.get("kind") == "action"}
            >= {"engine_canvas", "engine_gpu", "toggle_engine", "stop"})
        commands = [item["action"] for item in found if item.get("kind") == "action"]
        self.assertEqual(set(commands), {"engine_canvas", "engine_gpu", "toggle_engine", "stop"})
        self.assertEqual(len(commands), 4)
        self.assertTrue(all(command in ACTIONS for command in commands))

    def test_engine_dispatch_rejects_unknown_commands_and_preserves_bounded_stop_channel(self):
        events, urgent = queue.Queue(2), threading.Event()
        for invalid in ("run_shell", "", None, True, {"engine": "gpu"}, ["engine_gpu"]):
            with self.subTest(command=invalid), self.assertRaises(ValueError):
                _dispatch_action(events, urgent, invalid)
        self.assertTrue(events.empty())
        self.assertFalse(urgent.is_set())
        events.put({"kind": "heartbeat"})
        events.put({"kind": "heartbeat"})
        self.assertTrue(_dispatch_action(events, urgent, "engine_canvas"))
        self.assertEqual(events.qsize(), 2)
        self.assertEqual(events.get_nowait(), {"kind": "heartbeat"})
        self.assertEqual(events.get_nowait(), {"kind": "action", "action": "engine_canvas"})
        events.put({"kind": "heartbeat"})
        events.put({"kind": "heartbeat"})
        self.assertTrue(_dispatch_action(events, urgent, "stop"))
        self.assertTrue(urgent.is_set())
        self.assertEqual(events.qsize(), 2)

    def test_parent_reports_unknown_ipc_action_instead_of_dispatching_it(self):
        session = GpuSession(clock=lambda: 100.)
        session._process = SimpleNamespace(is_alive=lambda: True)
        session._frames = queue.Queue(1)
        session._events = queue.Queue(16)
        session._urgent = threading.Event()
        session._heartbeat = SimpleNamespace(value=100.)
        session._ready, session._last_seen = True, 100.
        session._events.put({"kind": "action", "action": {"run_shell": "anything"}})
        events = session.poll()
        self.assertEqual(events[0]["kind"], "error")
        self.assertIn("inconnue", events[0]["message"])
        self.assertFalse(any(item.get("kind") == "action" for item in events))

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

    def test_animated_child_draws_new_time_frames_between_lower_rate_parent_snapshots(self):
        session = GpuSession(allow_software=True, headless=True, startup_timeout=10.)
        self.addCleanup(session.stop)
        session.start()
        self.wait_until(session, lambda items: any(item["kind"] == "ready" for item in items))
        started, sent, events = time.monotonic(), 0, []
        next_send = started
        while time.monotonic()-started < 1.25:
            now = time.monotonic()
            if now >= next_send:
                session.submit({**packet(sent), "frame_at": now, "pcm_at": started-1,
                    "window": {"width": 480, "height": 360},
                    "frame": {**packet()["frame"], "time_s": now-started,
                              "orbit_phase": (now-started, 0., 0.)},
                    "animation": {"active": True, "orbit_velocity": (1., 0., 0.),
                                  "orbit_target": (1., 0., 0.)}})
                next_send += .08  # Deliberately lower than the audio/IPC 25Hz budget.
                sent += 1
            events.extend(session.poll())
            time.sleep(.003)
        events.extend(self.wait_until(session, lambda items: any(item.get("timing", {}).get("animated_frames_drawn", 0) > 0 for item in items)))
        beats = [item for item in events if item["kind"] == "heartbeat"]
        self.assertGreater(max(item["frames"] for item in beats), sent)
        sampled = [item["timing"] for item in beats if item["timing"]["animated_frames_drawn"] > 0]
        self.assertTrue(sampled)
        self.assertTrue(all(item["swap_calls"] == 0 for item in sampled))  # EGL is not a display.
        self.assertTrue(all(item["physical_vram_bytes"] is None for item in sampled))
        self.assertGreater(max(item["frame_time_s"] for item in sampled), .5)


if __name__ == "__main__":
    unittest.main()
