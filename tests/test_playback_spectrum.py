"""Real FFT over device-bound PCM; PortAudio is an explicit device double."""
import importlib.util
import multiprocessing as mp
import queue
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from jarvis.audio import AudioEvent
from jarvis.audio_spectrum import PCMSpectrum, ZERO_BANDS
from jarvis.tts import AudioPlayer, PCM, _PlaybackSpectrum
from jarvis.voice_config import VoiceSettings
from jarvis.voice_runtime import AudioProcess, speech_worker
from jarvis.voice_ui import VoiceControls


def observe_shared_policy(value, wake, pipe):
    for _ in range(2):
        if not wake.wait(4):
            return
        wake.clear()
        pipe.send(bool(value.value))
    pipe.close()


class PlaybackPolicyTests(unittest.TestCase):
    def controls(self):
        voice = object.__new__(VoiceControls)
        voice.speech = Mock()
        voice.speech.kind = "speech"
        voice.speech.process = None
        voice.speech.alive.return_value = False
        voice.speech.send.return_value = True
        voice.visual_spectrum_requested = False
        voice.spectrum_diagnostic = ""
        voice.record_diagnostic = Mock()
        voice.settings = VoiceSettings()
        voice.tts_profile = None
        voice.epoch = 8
        return voice

    def test_renderer_switch_changes_live_policy_without_restarting_piper(self):
        voice = self.controls()
        voice.speech.process = object()
        voice.speech.alive.return_value = True
        self.assertTrue(voice.set_visual_spectrum(True))
        self.assertTrue(voice.set_visual_spectrum(True))
        self.assertTrue(voice.set_visual_spectrum(False))
        self.assertEqual(voice.speech.send.call_args_list,
                         [unittest.mock.call({"kind": "visual_spectrum", "enabled": True}),
                          unittest.mock.call({"kind": "visual_spectrum", "enabled": False})])
        voice.speech.start.assert_not_called()
        voice.speech.stop.assert_not_called()
        with self.assertRaises(ValueError):
            voice.set_visual_spectrum("yes")

    def test_policy_survives_worker_start_and_canvas_default_sends_no_control(self):
        voice = self.controls()
        voice.prepare_speech()
        voice.speech.send.assert_not_called()
        self.assertTrue(voice.set_visual_spectrum(True))
        voice.speech.send.assert_not_called()
        voice.prepare_speech()
        voice.speech.send.assert_called_once_with({"kind": "visual_spectrum", "enabled": True})
        self.assertEqual(voice.speech.generation, voice.epoch)
        voice.speech.process = object()
        voice.speech.alive.return_value = True
        voice.speech.reset_mock()
        voice.prepare_speech()
        voice.speech.start.assert_not_called()
        voice.speech.send.assert_not_called()

    def test_visual_errors_are_bounded_deduplicated_and_recover_without_stopping_audio(self):
        voice = self.controls()
        voice._spectrum_diagnostic("erreur" * 200)
        voice._spectrum_diagnostic("erreur" * 200)
        self.assertEqual(len(voice.spectrum_diagnostic), 512)
        self.assertEqual(voice.record_diagnostic.call_count, 1)
        voice._spectrum_diagnostic("")
        self.assertEqual(voice.record_diagnostic.call_count, 2)
        self.assertIn("rétablie", voice.record_diagnostic.call_args.args[1])
        voice.speech.stop.assert_not_called()

    def test_actual_bands_keep_dac_deadline_and_stale_errors_are_rejected(self):
        voice = self.controls()
        voice.capture = Mock()
        voice.capture.poll.return_value = []
        voice.speech.poll.return_value = [
            AudioEvent("spectrum_diagnostic", "old generation", voice.epoch - 1),
            AudioEvent("played", {"bands": (.1, .2, .3), "emitted_at": 100., "delay": .2,
                                  "spectrum_status": "error", "spectrum_error": "FFT unavailable"}, voice.epoch)]
        voice.listening = voice.playing_sample = False
        voice.first_pcm_at = voice.tts_requested_at = None
        voice.pending_visuals, voice.pending_segment_ends = [], []
        voice.visual_end_pending = None
        voice.end_pending = False
        voice.app = SimpleNamespace(operation=None)
        voice._diagnostic_refreshed_at = 0.
        voice.refresh_diagnostics = Mock()
        voice.drain_phrases = Mock()
        voice.notify_presence = Mock()
        with patch("jarvis.voice_ui.time.monotonic", return_value=100.):
            voice.poll()
        voice.record_diagnostic.assert_called_once_with("spectrum_diagnostic", "FFT unavailable")
        voice.notify_presence.assert_not_called()
        self.assertEqual(voice.pending_visuals[0][0], 100.2)
        voice._drain_visuals(100.21)
        signal = voice.notify_presence.call_args.kwargs["signal"]
        self.assertEqual(signal["bands"], (.1, .2, .3))
        voice.speech.start.assert_not_called()
        voice.speech.stop.assert_not_called()

    def test_visual_control_bypasses_full_speech_queue_and_rejects_closed_transport(self):
        process = AudioProcess()
        process.kind, process.commands = "speech", queue.Queue(maxsize=1)
        process.commands.put("existing phrase")
        process.spectrum_control = SimpleNamespace(value=False)
        self.assertTrue(process.send({"kind": "visual_spectrum", "enabled": True}))
        self.assertTrue(process.spectrum_control.value)
        self.assertEqual(process.commands.get_nowait(), "existing phrase")
        self.assertTrue(process.send({"kind": "visual_spectrum", "enabled": False}))
        self.assertFalse(process.spectrum_control.value)
        self.assertFalse(process.send({"kind": "visual_spectrum", "enabled": "yes"}))
        process.commands = None
        self.assertFalse(process.send({"kind": "visual_spectrum", "enabled": True}))

    def test_control_is_really_shared_across_spawn_without_restarting_a_worker(self):
        context = mp.get_context("spawn")
        shared, wake = context.Value("b", False, lock=False), context.Event()
        read, write = context.Pipe(duplex=False)
        child = context.Process(target=observe_shared_policy, args=(shared, wake, write))
        child.start()
        write.close()
        try:
            transport = AudioProcess()
            transport.kind, transport.commands, transport.spectrum_control = "speech", queue.Queue(), shared
            for enabled in (True, False):
                self.assertTrue(transport.send({"kind": "visual_spectrum", "enabled": enabled}))
                wake.set()
                self.assertTrue(read.poll(4))
                self.assertIs(read.recv(), enabled)
            child.join(4)
            self.assertEqual(child.exitcode, 0)
        finally:
            if child.is_alive():
                child.terminate()
                child.join(2)
            child.close()
            read.close()

    def test_direct_worker_accepts_visual_control_without_synthesizing_it(self):
        commands, outbox = queue.Queue(), queue.Queue()
        commands.put({"kind": "visual_spectrum", "enabled": True})
        commands.put("Bonjour")
        commands.put(None)
        with patch("jarvis.tts.PiperSpeech") as piper, patch("jarvis.tts.AudioPlayer") as player:
            piper.return_value.synthesize.return_value = []
            speech_worker(outbox, commands, VoiceSettings().to_dict(), 7)
        self.assertIs(player.return_value.spectrum_enabled, True)
        piper.return_value.synthesize.assert_called_once_with("Bonjour")
        self.assertEqual([event.kind for event in outbox.queue], ["tts_ready", "speech_done"])


@unittest.skipUnless(importlib.util.find_spec("numpy"), "NumPy audio optionnel absent")
class PlaybackSpectrumTests(unittest.TestCase):
    def tone(self, frequency, count=640):
        import numpy as np
        return (.2*np.sin(2*np.pi*frequency*np.arange(count)/16000)).astype("float32")

    def wait_ready(self, worker, offset, count=640):
        deadline = time.monotonic()+2
        while worker.block(offset, count)[1] == "waiting" and time.monotonic() < deadline:
            time.sleep(.001)
        self.assertNotEqual(worker.block(offset, count)[1], "waiting")

    def test_late_bands_never_belong_to_another_pcm_block_and_worker_recovers(self):
        import numpy as np
        entered, release = threading.Event(), threading.Event()
        real = PCMSpectrum()
        calls = []

        class Analyzer:
            def analyze(_self, samples, rate):
                calls.append(threading.current_thread().name)
                if len(calls) == 2:
                    entered.set()
                    release.wait(2)
                return real.analyze(samples, rate)

        worker = _PlaybackSpectrum(np.concatenate([self.tone(f) for f in (200, 3000, 1000)]),
                                   16000, 640, analyzer=Analyzer())
        try:
            self.assertEqual(max(range(3), key=worker.block(0, 640)[0].__getitem__), 0)
            worker.request(640, 640)
            self.assertTrue(entered.wait(2))
            worker.request(1280, 640)
            self.assertEqual(worker.block(1280, 640), (ZERO_BANDS, "waiting", ""))
            release.set()
            self.wait_ready(worker, 1280)
            self.assertEqual(max(range(3), key=worker.block(1280, 640)[0].__getitem__), 1)
            self.assertEqual(worker.block(1280, 128), (ZERO_BANDS, "waiting", ""))
        finally:
            release.set()
            worker.close()
        self.assertFalse(worker._thread.is_alive())
        self.assertIsNone(worker._ready)

    def test_fft_fault_is_visible_does_not_kill_worker_and_next_block_recovers(self):
        import numpy as np
        real, failed = PCMSpectrum(), False

        class Analyzer:
            def analyze(_self, samples, rate):
                nonlocal failed
                if not failed:
                    failed = True
                    raise ValueError("spectral fault")
                return real.analyze(samples, rate)

        worker = _PlaybackSpectrum(np.concatenate([self.tone(200), self.tone(3000)]), 16000, 640,
                                   analyzer=Analyzer())
        try:
            bands, status, error = worker.block(0, 640)
            self.assertEqual((bands, status), (ZERO_BANDS, "error"))
            self.assertIn("spectral fault", error)
            worker.request(640, 640)
            self.wait_ready(worker, 640)
            bands, status, error = worker.block(640, 640)
            self.assertEqual((status, error), ("ready", ""))
            self.assertEqual(max(range(3), key=bands.__getitem__), 2)
        finally:
            worker.close()

    def test_analysis_is_paced_and_requests_coalesce_to_the_latest_block(self):
        import numpy as np
        times = []
        real = PCMSpectrum()

        class Analyzer:
            def analyze(_self, samples, rate):
                times.append(time.perf_counter())
                return real.analyze(samples, rate)

        worker = _PlaybackSpectrum(np.tile(self.tone(200), 5), 16000, 640, analyzer=Analyzer())
        try:
            worker.request(640, 640)
            self.wait_ready(worker, 640)
            for offset in (1280, 1920, 2560):
                worker.request(offset, 640)
            self.wait_ready(worker, 2560)
            self.assertGreaterEqual(len(times), 3)  # First block plus worker calls.
            self.assertGreaterEqual(times[2]-times[1], .035)
            self.assertLessEqual(len(times), 4)
            self.assertIsNone(worker._requested)
        finally:
            worker.close()

    def test_cancellation_discards_an_inflight_block_before_the_next_generation(self):
        import numpy as np
        entered, release, closed = threading.Event(), threading.Event(), threading.Event()
        calls = 0
        real = PCMSpectrum()

        class Analyzer:
            def analyze(_self, samples, rate):
                nonlocal calls
                calls += 1
                if calls == 2:
                    entered.set()
                    release.wait(2)
                return real.analyze(samples, rate)

        old = _PlaybackSpectrum(np.tile(self.tone(200), 2), 16000, 640, analyzer=Analyzer())
        old.request(640, 640)
        self.assertTrue(entered.wait(2))
        closer = threading.Thread(target=lambda: (old.close(), closed.set()))
        closer.start()
        try:
            self.assertTrue(old._closed.wait(2))
            self.assertEqual(old.block(0, 640), (ZERO_BANDS, "waiting", ""))
            release.set()
            self.assertTrue(closed.wait(2))
            fresh = _PlaybackSpectrum(self.tone(3000), 16000, 640)
            try:
                self.assertEqual(max(range(3), key=fresh.block(0, 640)[0].__getitem__), 2)
                self.assertEqual(old.block(640, 640), (ZERO_BANDS, "waiting", ""))
            finally:
                fresh.close()
        finally:
            release.set()
            closer.join(2)
            old.close()
        self.assertFalse(closer.is_alive())
        self.assertFalse(old._thread.is_alive())

    def exercise_player(self, *, enabled=True, toggle=False, faulty=False):
        import numpy as np
        samples = np.concatenate([self.tone(f) for f in (200, 3000, 1000)])
        played, output_blocks, analyses, workers, driver_errors = [], [], [], [], []
        policy = SimpleNamespace(value=enabled)
        real_analyze, real_worker = PCMSpectrum.analyze, _PlaybackSpectrum

        def analyze(instance, values, rate):
            analyses.append(threading.current_thread().name)
            if faulty:
                raise ValueError("optional visual FFT failed")
            return real_analyze(instance, values, rate)

        def make_worker(*args, **kwargs):
            instance = real_worker(*args, **kwargs)
            workers.append(instance)
            return instance

        class CallbackStop(Exception):
            pass

        owner = self
        class Stream:
            active = True
            def __init__(self, **options):
                self.options = options
            def __enter__(self):
                self.thread = threading.Thread(target=self.drive, name="test-portaudio-callback")
                self.thread.start()
                return self
            def drive(self):
                try:
                    for index in range(3):
                        if index == 1 and toggle:
                            policy.value = True
                        if index == 2 and toggle:
                            policy.value = False
                        if policy.value:
                            deadline = time.monotonic()+2
                            while not workers and time.monotonic() < deadline:
                                time.sleep(.001)
                            owner.assertTrue(workers)
                            owner.wait_ready(workers[-1], index*640)
                        out = np.empty((640, 1), dtype="float32")
                        try:
                            self.options["callback"](out, 640,
                                SimpleNamespace(outputBufferDacTime=100+index*.04+.03,
                                                currentTime=100+index*.04), None)
                        except CallbackStop:
                            output_blocks.append(out[:, 0].copy())
                            self.options["finished_callback"]()
                            return
                        output_blocks.append(out[:, 0].copy())
                    raise AssertionError("Playback did not finish")
                except BaseException as error:
                    driver_errors.append(error)
                    self.options["finished_callback"]()
            def __exit__(self, *args):
                self.thread.join(3)
                owner.assertFalse(self.thread.is_alive())

        sd = SimpleNamespace(query_devices=Mock(return_value={"default_samplerate": 16000}),
                             OutputStream=Mock(side_effect=Stream), CallbackStop=CallbackStop)
        player = AudioPlayer("selected device")
        player.spectrum_control = policy
        with patch.dict("sys.modules", {"sounddevice": sd, "soxr": SimpleNamespace()}), \
                patch("jarvis.tts.resolve_device", return_value=3), \
                patch("jarvis.tts._PlaybackSpectrum", side_effect=make_worker), \
                patch.object(PCMSpectrum, "analyze", analyze):
            player.play(PCM(samples, 16000), "Parole française", played.append, 13)
        if driver_errors:
            raise driver_errors[0]
        self.assertTrue(all(not worker._thread.is_alive() for worker in workers))
        self.assertNotIn("test-portaudio-callback", analyses)
        self.assertEqual(sd.OutputStream.call_count, 1)
        self.assertTrue(all(np.array_equal(block, samples[index*640:(index+1)*640])
                            for index, block in enumerate(output_blocks)))
        return played, analyses

    def test_played_bands_match_exact_device_blocks_and_positive_dac_delay(self):
        played, analyses = self.exercise_player()
        self.assertTrue(analyses)
        self.assertEqual([event.generation for event in played], [13, 13, 13])
        self.assertEqual([max(range(3), key=event.payload["bands"].__getitem__) for event in played], [0, 2, 1])
        self.assertEqual([event.payload["spectrum_sample_start"] for event in played], [0, 640, 1280])
        self.assertTrue(all(event.payload["spectrum_sample_count"] == 640 for event in played))
        self.assertTrue(all(abs(event.payload["delay"]-.03) < 1e-6 for event in played))
        self.assertTrue(all(event.payload["started_at"] == played[0].payload["started_at"] for event in played))
        self.assertEqual(played[-1].payload["fraction"], 1)

    def test_canvas_default_needs_no_fft_or_analysis_thread(self):
        played, analyses = self.exercise_player(enabled=False)
        self.assertFalse(analyses)
        self.assertTrue(all("bands" not in event.payload for event in played))

    def test_shared_policy_can_enable_and_disable_during_the_same_audio_stream(self):
        played, _analyses = self.exercise_player(enabled=False, toggle=True)
        self.assertNotIn("bands", played[0].payload)
        self.assertEqual(played[1].payload["spectrum_status"], "ready")
        self.assertGreater(played[1].payload["bands"][2], .1)
        self.assertNotIn("bands", played[2].payload)

    def test_optional_fft_failure_preserves_playback_and_reports_diagnostic(self):
        played, _analyses = self.exercise_player(faulty=True)
        self.assertEqual(len(played), 3)
        self.assertTrue(all(event.payload["bands"] == ZERO_BANDS for event in played))
        self.assertTrue(all(event.payload["spectrum_status"] == "error" for event in played))
        self.assertTrue(all("optional visual FFT failed" in event.payload["spectrum_error"] for event in played))
