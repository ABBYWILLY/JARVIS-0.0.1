"""Real PCM frequency separation and bounded background-worker lifetimes."""
import math
import subprocess
import sys
import threading
import unittest

from jarvis.audio_spectrum import MAX_SAMPLES, PCMSpectrum, SpectrumWorker, ZERO_BANDS


def tone(frequency, rate=16000, duration=.04, amplitude=.5):
    return [amplitude * math.sin(math.tau * frequency * index / rate)
            for index in range(round(rate * duration))]


class PCMSpectrumTests(unittest.TestCase):
    def setUp(self):
        self.spectrum = PCMSpectrum()

    def test_real_frequency_bands_distinguish_equal_volume_sines_at_native_rates(self):
        for rate in (8000, 16000, 22050, 44100, 48000, 192000):
            for band, frequency in enumerate((200, 1000, 3000)):
                with self.subTest(rate=rate, frequency=frequency):
                    bands = self.spectrum.analyze(tone(frequency, rate), rate)
                    self.assertEqual(max(range(3), key=bands.__getitem__), band)
                    self.assertGreater(bands[band], .30)
                    self.assertLess(bands[band], .40)
                    self.assertGreater(bands[band], 10 * max(bands[:band] + bands[band + 1:]))

    def test_mixture_preserves_relative_band_energy_instead_of_copying_global_rms(self):
        samples = [bass + mid + high for bass, mid, high in zip(
            tone(200, amplitude=.2), tone(1000, amplitude=.4), tone(4000, amplitude=.1))]
        low, middle, high = self.spectrum.analyze(samples, 16000)
        self.assertGreater(middle, low)
        self.assertGreater(low, high)
        self.assertAlmostEqual(middle / low, 2., delta=.08)
        self.assertAlmostEqual(low / high, 2., delta=.08)

    def test_silence_dc_empty_and_out_of_range_frequencies_do_not_invent_audio(self):
        for values in ([], [0.], [0.] * 1024, [.7] * 1024):
            with self.subTest(count=len(values)):
                self.assertEqual(self.spectrum.analyze(values, 16000), ZERO_BANDS)
        outside = self.spectrum.analyze(tone(12000, 48000), 48000)
        self.assertLess(max(outside), .0001)

    def test_only_latest_bounded_window_is_retained_and_pcm_input_is_unchanged(self):
        values = tone(1000, 48000, duration=.2)
        original = values[:]
        expected = self.spectrum.analyze(values[-MAX_SAMPLES:], 48000)
        self.assertEqual(self.spectrum.analyze(values, 48000), expected)
        self.assertEqual(values, original)
        self.assertTrue(all(0 <= value <= 1 for value in self.spectrum.analyze(
            tone(1000, amplitude=10), 16000)))

    def test_nonfinite_pcm_and_invalid_sample_rates_fail_explicitly(self):
        for rate in (0, 192001, True, 16000.5, "16000"):
            with self.subTest(rate=rate), self.assertRaises(ValueError):
                self.spectrum.analyze([0.] * 16, rate)
        for value in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.spectrum.analyze([value] * 16, 16000)

    def test_module_import_starts_no_worker_and_needs_no_audio_or_gpu_dependency(self):
        code = ("import sys,threading; import jarvis.audio_spectrum; "
                "assert len(threading.enumerate()) == 1; "
                "assert not any(n in sys.modules for n in "
                "('numpy','sounddevice','moderngl','piper','tkinter'))")
        subprocess.run([sys.executable, "-c", code], check=True, capture_output=True)


class SpectrumWorkerTests(unittest.TestCase):
    def wait_count(self, worker, count):
        # Condition waiting makes completion deterministic, without timing sleeps
        # or replacing the actual background thread with an immediate callback.
        with worker._condition:
            self.assertTrue(worker._condition.wait_for(
                lambda: worker.analysis_count >= count, timeout=2.), "FFT worker did not finish")

    def test_real_transform_runs_in_background_and_results_expire_without_new_pcm(self):
        worker = SpectrumWorker()
        try:
            self.assertTrue(worker.alive)
            self.assertTrue(worker.submit(tone(1000), 16000, 4.))
            self.wait_count(worker, 1)
            bands = worker.snapshot(4.)
            self.assertGreater(bands[1], .3)
            self.assertEqual(worker.snapshot(3.9), ZERO_BANDS)
            self.assertEqual(worker.snapshot(4.21), ZERO_BANDS)
            self.assertEqual(worker.snapshot(4., generation=1), ZERO_BANDS)
        finally:
            worker.close()
        self.assertFalse(worker.alive)
        self.assertEqual(worker.snapshot(4.), ZERO_BANDS)

    def test_queue_keeps_only_latest_pcm_and_analysis_cadence_is_bounded(self):
        entered, release = threading.Event(), threading.Event()
        clock, calls = [0.], []

        class Analyzer:
            def analyze(self, samples, _rate):
                calls.append(samples[0])
                if len(calls) == 1:
                    entered.set()
                    if not release.wait(2):
                        raise RuntimeError("test did not release analyzer")
                return (samples[0], 0., 0.)

        worker = SpectrumWorker(analyzer=Analyzer(), clock=lambda: clock[0])
        try:
            worker.submit([.1] * 16, 16000, 1.)
            self.assertTrue(entered.wait(2))
            for index in range(200):
                worker.submit([.9] * 16, 16000, 1. + index / 1000)
                self.assertEqual(worker.pending_count, 1)
            release.set()
            self.wait_count(worker, 1)
            self.assertEqual(worker.analysis_count, 1)  # Fake clock has not advanced 40 ms.
            self.assertEqual(worker.snapshot(1.), (.1, 0., 0.))
            clock[0] = .04
            with worker._condition:
                worker._condition.notify_all()
            self.wait_count(worker, 2)
            self.assertEqual(calls, [.1, .9])
            self.assertEqual(worker.snapshot(1.199), (.9, 0., 0.))
            self.assertEqual(worker.pending_count, 0)
        finally:
            release.set()
            worker.close()
        self.assertFalse(worker.alive)

    def test_reset_rejects_both_inflight_and_queued_obsolete_generations(self):
        entered, release = threading.Event(), threading.Event()
        clock = [0.]

        class Analyzer:
            def analyze(self, samples, _rate):
                if samples[0] == .1:
                    entered.set()
                    if not release.wait(2):
                        raise RuntimeError("test did not release analyzer")
                return (samples[0], 0., 0.)

        worker = SpectrumWorker(analyzer=Analyzer(), clock=lambda: clock[0])
        try:
            worker.submit([.1] * 16, 16000, 2.)
            self.assertTrue(entered.wait(2))
            worker.submit([.2] * 16, 16000, 2.01)
            self.assertTrue(worker.reset(1))
            self.assertEqual(worker.pending_count, 0)
            self.assertFalse(worker.submit([.3] * 16, 16000, 2.02, generation=0))
            self.assertFalse(worker.reset(0))
            release.set()
            self.wait_count(worker, 1)
            self.assertEqual(worker.snapshot(2.03, generation=1), ZERO_BANDS)
            clock[0] = .04
            self.assertTrue(worker.submit([.8] * 16, 16000, 2.1, generation=1))
            self.wait_count(worker, 2)
            self.assertEqual(worker.snapshot(2.1, generation=1), (.8, 0., 0.))
            self.assertFalse(worker.submit([.4] * 16, 16000, 2.09, generation=1))
            worker.reset(1)  # Same generation still invalidates cached data.
            self.assertEqual(worker.snapshot(2.1, generation=1), ZERO_BANDS)
        finally:
            release.set()
            worker.close()

    def test_failure_is_visible_worker_recovers_and_invalid_band_results_are_rejected(self):
        clock, calls = [0.], []

        class Analyzer:
            def analyze(self, samples, _rate):
                calls.append(samples[0])
                if len(calls) == 1:
                    raise ValueError("PCM défectueux")
                return (.2, .4, .6) if len(calls) == 2 else (float("nan"), 0., 0.)

        worker = SpectrumWorker(analyzer=Analyzer(), clock=lambda: clock[0])
        try:
            worker.submit([.1] * 16, 16000, 1.)
            self.wait_count(worker, 1)
            self.assertIn("ValueError: PCM défectueux", worker.diagnostic)
            self.assertEqual(worker.snapshot(1.), ZERO_BANDS)
            self.assertTrue(worker.alive)
            clock[0] = .04
            worker.submit([.2] * 16, 16000, 1.04)
            self.wait_count(worker, 2)
            self.assertEqual(worker.snapshot(1.04), (.2, .4, .6))
            self.assertEqual(worker.diagnostic, "")
            clock[0] = .08
            worker.submit([.3] * 16, 16000, 1.08)
            self.wait_count(worker, 3)
            self.assertIn("trois bandes finies", worker.diagnostic)
            self.assertEqual(worker.snapshot(1.08), ZERO_BANDS)
        finally:
            worker.close()

    def test_close_discards_pending_data_is_idempotent_and_leaves_no_thread(self):
        worker = SpectrumWorker()
        worker.submit(tone(1000), 16000, 0.)
        worker.close()
        worker.close()
        self.assertFalse(worker.alive)
        self.assertEqual(worker.pending_count, 0)
        self.assertEqual(worker.snapshot(0.), ZERO_BANDS)
        with self.assertRaisesRegex(RuntimeError, "fermé"):
            worker.submit([], 16000, 1.)

    def test_invalid_policy_and_timestamps_do_not_enqueue_data(self):
        for kwargs in ({"frequency": 26}, {"frequency": 0}, {"frequency": float("nan")},
                       {"lifetime": 0}, {"lifetime": 2}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                SpectrumWorker(**kwargs)
        worker = SpectrumWorker()
        try:
            for timestamp in (float("inf"), float("nan")):
                with self.subTest(timestamp=timestamp), self.assertRaises(ValueError):
                    worker.submit([], 16000, timestamp)
            for generation in (-1, True, 1.5):
                with self.subTest(generation=generation), self.assertRaises(ValueError):
                    worker.reset(generation)
            self.assertEqual(worker.pending_count, 0)
        finally:
            worker.close()


if __name__ == "__main__":
    unittest.main()
