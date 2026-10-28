"""Renderer counters measure real draw calls, never animation intentions."""
import json
import subprocess
import sys
import unittest

from jarvis.gpu_telemetry import RenderTelemetry


MEMORY = {"rss_current_bytes": 1234, "rss_peak_bytes": 2000,
          "source": "explicit_test_fixture", "unavailable_reason": None}


class RenderTelemetryTests(unittest.TestCase):
    def telemetry(self, **options):
        return RenderTelemetry(clock=lambda: 10., cpu_clock=lambda: 2.,
                               memory_reader=lambda: MEMORY, **options)

    def test_import_needs_no_graphics_audio_or_optional_dependencies(self):
        subprocess.run([sys.executable, "-c", "import sys; import jarvis.gpu_telemetry; "
            "assert not any(k in sys.modules for k in ('moderngl','glfw','tkinter','numpy','PIL','sounddevice'))"],
            check=True, capture_output=True)

    def test_counts_draws_and_returned_swaps_separately_with_finite_timings(self):
        metric = self.telemetry()
        metric.record(.002, 10., presented=True, animated=True)
        metric.record(.003, 10.01, presented=True, animated=True)
        metric.record(.004, 10.03, presented=False, animated=True)
        data = metric.snapshot(10.05)
        self.assertEqual(data["frames_drawn"], 3)
        self.assertEqual(data["swap_calls"], 2)
        self.assertEqual(data["animated_frames_drawn"], 3)
        self.assertAlmostEqual(data["actual_draw_fps"], 60.)
        self.assertAlmostEqual(data["animated_fps"], 1000/15)
        self.assertAlmostEqual(data["frame_mean_ms"], 15.)
        self.assertAlmostEqual(data["frame_p50_ms"], 10.)
        self.assertAlmostEqual(data["frame_p95_ms"], 20.)
        self.assertAlmostEqual(data["frame_p99_ms"], 20.)
        self.assertEqual(data["render_mean_ms"], 3.)
        self.assertEqual(data["render_p50_ms"], 3.)
        self.assertEqual(data["render_p99_ms"], 4.)
        self.assertEqual(data["long_frames"], 0)
        self.assertEqual(data["presentation_observation"], "swap_buffers_returned_not_physical_scanout")
        json.dumps(data, allow_nan=False)

    def test_bounded_recent_samples_keep_exact_counters_and_long_frame_count(self):
        metric = self.telemetry(max_samples=2)
        for timestamp, duration in ((10., .001), (10.01, .002), (10.04, .003), (10.08, .004)):
            metric.record(duration, timestamp, animated=True)
        data = metric.snapshot(10.1)
        self.assertEqual(data["frames_drawn"], 4)
        self.assertEqual(data["sampled_render_frames"], 2)
        self.assertEqual(data["sampled_frame_intervals"], 2)
        self.assertEqual(data["long_frames"], 2)
        self.assertAlmostEqual(data["render_mean_ms"], 3.5)
        self.assertAlmostEqual(data["frame_mean_ms"], 35.)

    def test_idle_hidden_and_pause_never_become_false_long_animation_frames(self):
        metric = self.telemetry()
        metric.record(.001, 10., animated=True)
        metric.record(.001, 10.01, animated=True)
        metric.pause()
        metric.record(.001, 15., animated=True)
        metric.record(.001, 15.01, animated=True)
        metric.record(.001, 18., animated=False)
        metric.record(.001, 20., animated=True)
        data = metric.snapshot(21.)
        self.assertEqual(data["frames_drawn"], 6)
        self.assertEqual(data["sampled_frame_intervals"], 2)
        self.assertEqual(data["long_frames"], 0)
        self.assertAlmostEqual(data["animated_fps"], 100.)
        self.assertLess(data["actual_draw_fps"], 1.)

    def test_cpu_memory_and_unknown_vram_remain_honest_and_reset_is_transactional(self):
        cpu = iter((2., 3., 3.2))
        metric = RenderTelemetry(clock=lambda: 10., cpu_clock=lambda: next(cpu), memory_reader=lambda: MEMORY)
        metric.record(.002, 10.01, presented=True)
        before = metric.snapshot(10.5, reset=True)
        self.assertEqual(before["frames_drawn"], 1)
        self.assertEqual(before["cpu_percent"], 200.)
        self.assertEqual(before["rss_current_bytes"], 1234)
        self.assertEqual(before["rss_peak_bytes"], 2000)
        self.assertIsNone(before["physical_vram_bytes"])
        self.assertTrue(before["physical_vram_unavailable_reason"])
        after = metric.snapshot(11.)
        self.assertEqual(after["frames_drawn"], 0)
        self.assertEqual(after["actual_draw_fps"], 0.)
        self.assertAlmostEqual(after["cpu_percent"], 40.)
        self.assertIsNone(after["frame_mean_ms"])

    def test_unavailable_rss_is_not_replaced_with_a_guess(self):
        def unavailable():
            raise OSError("test unavailable")
        metric = RenderTelemetry(clock=lambda: 10., cpu_clock=lambda: 0., memory_reader=unavailable)
        data = metric.snapshot(11.)
        self.assertIsNone(data["rss_current_bytes"])
        self.assertIsNone(data["rss_peak_bytes"])
        self.assertIn("OSError", data["memory_unavailable_reason"])

    def test_invalid_or_backward_samples_do_not_increment_counters(self):
        metric = self.telemetry()
        invalid = ((-.1, 10.), (True, 10.), (float("nan"), 10.), (float("inf"), 10.),
                   (1e308, 10.), (.1, float("nan")), (.1, float("inf")), (.1, 9.))
        for duration, stamp in invalid:
            with self.subTest(duration=duration, timestamp=stamp), self.assertRaises(ValueError):
                metric.record(duration, stamp)
        self.assertEqual(metric.snapshot(10.)["frames_drawn"], 0)
        metric.record(.001, 11.)
        with self.assertRaises(ValueError):
            metric.record(.001, 10.5)
        with self.assertRaises(ValueError):
            metric.snapshot(10.9)
        self.assertEqual(metric.snapshot(12.)["frames_drawn"], 1)
        for maximum in (0, 601, True, 2.5):
            with self.subTest(maximum=maximum), self.assertRaises(ValueError):
                self.telemetry(max_samples=maximum)
        for fps in (0, 241, True, float("nan")):
            with self.subTest(fps=fps), self.assertRaises(ValueError):
                self.telemetry(target_fps=fps)

    def test_target_fps_defines_long_frames_and_zero_time_never_invents_fps(self):
        metric = self.telemetry(target_fps=15)
        metric.record(.001, 10., animated=True)
        self.assertIsNone(metric.snapshot(10.)["actual_draw_fps"])
        metric.record(.001, 10.07, animated=True)
        self.assertEqual(metric.snapshot(10.1)["long_frames"], 0)
        metric.target_fps = 60
        metric.record(.001, 10.14, animated=True)
        self.assertEqual(metric.snapshot(10.2)["long_frames"], 1)


if __name__ == "__main__":
    unittest.main()
