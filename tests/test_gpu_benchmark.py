"""Resource measurements stay bounded, local and explicit about unavailable data."""
import json
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from jarvis.gpu_benchmark import (
    FrameTimings,
    NvidiaSampler,
    ProcessSampler,
    build_report,
    match_nvidia_device,
    parse_nvidia_smi,
    read_process_memory,
    write_report,
)


class FrameTimingTests(unittest.TestCase):
    def test_bounded_samples_do_not_change_exact_frame_count_or_elapsed_fps(self):
        timings = FrameTimings(max_samples=2)
        timings.record(0.001, 0.010)
        timings.record(0.002, 0.020)
        timings.record(0.003, 0.030)
        result = timings.summary()
        self.assertEqual(result["frame_count"], 3)
        self.assertAlmostEqual(result["elapsed_seconds"], 0.060)
        self.assertAlmostEqual(result["fps"], 50)
        self.assertEqual(result["sampled_frame_count"], 2)
        self.assertEqual(result["sample_policy"], "most_recent_frames")
        self.assertAlmostEqual(result["frame_median_ms"], 25)
        self.assertAlmostEqual(result["frame_p95_ms"], 30)
        self.assertAlmostEqual(result["render_median_ms"], 2.5)
        self.assertAlmostEqual(result["render_p95_ms"], 3)

    def test_invalid_samples_never_enter_statistics(self):
        timings = FrameTimings()
        for render, frame in ((-1, 1), (1, -1), (2, 1),
                              (float("nan"), 1), (1, float("inf")),
                              (1e308, 1e308), (0, 5e-324)):
            with self.subTest(render=render, frame=frame):
                with self.assertRaises((TypeError, ValueError)):
                    timings.record(render, frame)
        self.assertEqual(timings.summary()["frame_count"], 0)
        self.assertIsNone(timings.summary()["fps"])
        self.assertIsNone(timings.summary()["frame_median_ms"])
        self.assertIsNone(timings.summary()["render_p95_ms"])
        json.dumps(timings.summary(), allow_nan=False)

    def test_zero_elapsed_time_does_not_invent_a_frame_rate(self):
        timings = FrameTimings()
        timings.record(0, 0)
        result = timings.summary()
        self.assertEqual(result["frame_count"], 1)
        self.assertEqual(result["frame_median_ms"], 0)
        self.assertIsNone(result["fps"])
        json.dumps(result, allow_nan=False)


class ReportWritingTests(unittest.TestCase):
    def test_exclusive_utf8_report_is_durable_and_preserves_existing_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "résultat.json"
            data = {"renderer": "Mesa été", "measurement": None}
            with patch("jarvis.gpu_benchmark.os.fsync", wraps=__import__("os").fsync) as fsync:
                write_report(output, data)
            self.assertEqual(json.loads(output.read_text(encoding="utf-8")), data)
            self.assertIn("été", output.read_text(encoding="utf-8"))
            fsync.assert_called_once()
            previous = output.read_bytes()
            with self.assertRaises(FileExistsError):
                write_report(output, {"replacement": True})
            self.assertEqual(output.read_bytes(), previous)

    def test_report_separates_requested_resources_from_unmeasured_physical_vram(self):
        report = build_report(startup_seconds=0.25, frames=FrameTimings(),
                              process={}, gpu={}, renderer_info={"renderer": "llvmpipe"},
                              allocation_estimate_bytes=4096)
        self.assertEqual(report["startup_seconds"], 0.25)
        resources = report["shader_resources"]
        self.assertEqual(resources["allocation_estimate_bytes"], 4096)
        self.assertIsNone(resources["physical_vram_measured_bytes"])
        self.assertTrue(resources["unavailable_reason"])
        for workload in ("ollama", "piper", "whisper"):
            self.assertIsNone(report["unmeasured_workloads"][workload]["latency_seconds"])
        json.dumps(report, allow_nan=False)

    def test_nonfinite_report_is_rejected_before_creating_a_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "invalid.json"
            for value in (float("nan"), float("inf"), -float("inf")):
                with self.subTest(value=value):
                    with self.assertRaises(ValueError):
                        write_report(output, {"nested": [value]})
                    self.assertFalse(output.exists())


class ResourceSamplerTests(unittest.TestCase):
    def test_current_process_memory_is_real_or_explicitly_unavailable(self):
        memory = read_process_memory()
        current, peak = memory["rss_current_bytes"], memory["rss_peak_bytes"]
        if current is None:
            self.assertTrue(memory["unavailable_reason"])
        else:
            self.assertIsInstance(current, int)
            self.assertGreater(current, 0)
        if peak is not None:
            self.assertIsInstance(peak, int)
            self.assertGreater(peak, 0)
        json.dumps(memory, allow_nan=False)

    def test_process_cpu_uses_full_elapsed_time_and_keeps_sampled_peak_above_one_core(self):
        memory = {"rss_current_bytes": 100, "rss_peak_bytes": 120,
                  "source": "fixture", "unavailable_reason": None}
        with patch("jarvis.gpu_benchmark.threading.Thread"), \
                patch("jarvis.gpu_benchmark.time.monotonic", side_effect=[10, 10.5, 12]), \
                patch("jarvis.gpu_benchmark.time.process_time", side_effect=[1, 2, 2.5]), \
                patch("jarvis.gpu_benchmark.read_process_memory", return_value=memory):
            sampler = ProcessSampler()
            sampler.start()
            sampler._sample()  # A sampling tick; the real thread waits on its stop Event.
            result = sampler.stop()
            self.assertEqual(sampler.snapshot(), result)
        self.assertEqual(result["cpu_scope"], "process_one_core_percent")
        self.assertEqual(result["elapsed_seconds"], 2)
        self.assertEqual(result["cpu_average_percent"], 75)
        self.assertEqual(result["cpu_peak_percent"], 200)
        self.assertEqual(result["sample_count"], 2)
        self.assertEqual(result["rss_average_bytes"], 100)
        self.assertEqual(result["rss_sample_count"], 3)
        self.assertEqual(result["rss_peak_bytes"], 120)

    def test_process_sampler_can_stop_without_waiting_for_sampling_interval(self):
        sampler = ProcessSampler(interval=60)
        sampler.start()
        time.sleep(0.005)
        started = time.monotonic()
        sampler.stop()
        self.assertLess(time.monotonic() - started, 1.5)
        sampler.stop()
        self.assertFalse(sampler._thread.is_alive())
        json.dumps(sampler.snapshot(), allow_nan=False)

    def test_nvidia_reader_failure_is_explicit_and_thread_stop_is_bounded(self):
        queried = threading.Event()

        def unavailable(*args, **kwargs):
            queried.set()
            raise FileNotFoundError("nvidia-smi is unavailable")

        with patch("jarvis.gpu_benchmark.subprocess.run", side_effect=unavailable):
            sampler = NvidiaSampler("NVIDIA GeForce RTX 4090", interval=60)
            sampler.start()
            self.assertTrue(queried.wait(1))
            started = time.monotonic()
            sampler.stop()
            self.assertLess(time.monotonic() - started, 1.5)
            self.assertFalse(sampler._thread.is_alive())
            snapshot = sampler.snapshot()
            json.dumps(snapshot, allow_nan=False)
            self.assertIn("unavailable", json.dumps(snapshot).lower())

    def test_nvidia_subprocess_uses_argument_list_timeout_and_no_shell(self):
        queried = threading.Event()
        calls = []

        def timeout(command, **kwargs):
            calls.append((command, kwargs))
            queried.set()
            raise subprocess.TimeoutExpired(command, kwargs["timeout"])

        with patch("jarvis.gpu_benchmark.subprocess.run", side_effect=timeout):
            sampler = NvidiaSampler("NVIDIA GeForce RTX 4090", interval=60, timeout=1)
            sampler.start()
            self.assertTrue(queried.wait(1))
            sampler.stop()
        command, kwargs = calls[0]
        self.assertIsInstance(command, list)
        self.assertEqual(command[0], "nvidia-smi")
        self.assertFalse(kwargs.get("shell", False))
        self.assertEqual(kwargs["timeout"], 1)


class NvidiaParsingTests(unittest.TestCase):
    def test_match_requires_the_renderer_to_identify_one_nvidia_device(self):
        devices = parse_nvidia_smi(
            "0, NVIDIA GeForce RTX 4090, 512, 24564, 12\n"
            "1, NVIDIA RTX A6000, 1024, 49140, 22\n")
        matched = match_nvidia_device("NVIDIA GeForce RTX 4090/PCIe/SSE2", devices)
        self.assertIsNotNone(matched)
        self.assertEqual(matched["name"], "NVIDIA GeForce RTX 4090")
        self.assertEqual(matched["memory_used_bytes"], 512 * 1024 * 1024)
        self.assertEqual(matched["memory_total_bytes"], 24564 * 1024 * 1024)
        self.assertEqual(matched["utilization_percent"], 12)
        self.assertIsNone(match_nvidia_device("llvmpipe (LLVM 15.0.6, 256 bits)", devices))
        self.assertIsNone(match_nvidia_device("NVIDIA unknown adapter", devices))
        duplicates = devices + [dict(devices[0], index=2)]
        self.assertIsNone(match_nvidia_device("NVIDIA GeForce RTX 4090", duplicates))

    def test_malformed_or_nonfinite_device_values_are_not_reported_as_measurements(self):
        for row in ("0, NVIDIA GPU, nan, 1024, 0",
                    "0, NVIDIA GPU, 0, inf, 0",
                    "0, NVIDIA GPU, 1e308, 1e308, 0",
                    "0, NVIDIA GPU, -1, 1024, 0",
                    "0, NVIDIA GPU, 0, 1024, -1",
                    "0, NVIDIA GPU, 0, 1024",
                    "not-an-index, NVIDIA GPU, 0, 1024, 0"):
            with self.subTest(row=row):
                with self.assertRaises(ValueError):
                    parse_nvidia_smi(row)

    def test_parsed_optional_unavailable_values_remain_json_null(self):
        devices = parse_nvidia_smi("0, NVIDIA RTX A6000, N/A, 49140, [Not Supported]\n")
        self.assertEqual(len(devices), 1)
        self.assertEqual(devices[0]["name"], "NVIDIA RTX A6000")
        json.dumps(devices, allow_nan=False)
        self.assertGreaterEqual(list(devices[0].values()).count(None), 2)


if __name__ == "__main__":
    unittest.main()
