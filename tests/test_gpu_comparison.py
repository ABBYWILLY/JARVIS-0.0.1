"""Comparison provenance and output preservation, without requiring OpenGL."""
from contextlib import redirect_stderr
import hashlib
import io
from pathlib import Path
import sys
import tempfile
import unittest

from scripts.compare_presence_gpu import (REPO, compatible_frame, parse_args,
                                         renderer_source, scene_source, validate_revision)


class GpuComparisonTests(unittest.TestCase):
    def test_revision_cannot_be_a_git_option_or_expression(self):
        for value in ("HEAD", "--help", "main", "231de9e:path", "abc123;id", "", "0" * 41):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_revision(value)
        self.assertEqual(validate_revision("231de9e"), "231de9e")
        self.assertEqual(validate_revision("current"), "current")

    def test_existing_outputs_are_refused_and_untouched(self):
        with tempfile.TemporaryDirectory() as folder:
            existing = Path(folder) / "existing"
            existing.mkdir()
            sentinel = existing / "report.json"
            sentinel.write_text("preserve me")
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                parse_args(["--output", str(existing)])
            self.assertEqual(sentinel.read_text(), "preserve me")

    def test_unbounded_or_nonfinite_measurements_are_rejected(self):
        for options in (("--seconds", "nan"), ("--seconds", "inf"), ("--seconds", "61"),
                        ("--width", "99999"), ("--height", "0")):
            with self.subTest(options=options), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                parse_args(["--output", "/tmp/nonexistent-comparison-output", *options])

    def test_snapshot_matches_exact_sources_and_cleans_imports(self):
        before = {name: (REPO / "jarvis" / name).read_bytes()
                  for name in ("gpu_renderer.py", "reactor_shaders.py", "gpu_config.py")
                  if (REPO / "jarvis" / name).exists()}
        with renderer_source("current") as (renderer, hashes):
            self.assertEqual(renderer.__name__, "GpuRenderer")
            self.assertEqual(hashes, {name: hashlib.sha256(raw).hexdigest() for name, raw in before.items()})
            self.assertTrue(any(name.startswith("_jarvis_gpu_comparison_source_")
                                and name.endswith(".gpu_renderer") for name in sys.modules))
        self.assertFalse(any(name.startswith("_jarvis_gpu_comparison_source") for name in sys.modules))
        self.assertEqual(before, {name: (REPO / "jarvis" / name).read_bytes() for name in before})

    def test_two_snapshots_can_be_loaded_together_without_reusing_module_objects(self):
        with renderer_source("current") as (before, before_hashes):
            with renderer_source("current") as (after, after_hashes):
                self.assertIsNot(before, after)
                self.assertNotEqual(before.__module__, after.__module__)
                self.assertEqual(before_hashes, after_hashes)
            self.assertIn(before.__module__, sys.modules)
        self.assertFalse(any(name.startswith("_jarvis_gpu_comparison_source_") for name in sys.modules))

    def test_scene_snapshot_is_frozen_independent_and_cleans_module_after_error(self):
        expected = hashlib.sha256((REPO / "jarvis/presence_gpu.py").read_bytes()).hexdigest()
        with self.assertRaisesRegex(RuntimeError, "capture failed"):
            with scene_source("current") as (before, digest):
                self.assertEqual(digest, expected)
                with scene_source("current") as (after, other):
                    self.assertIsNot(before, after)
                    self.assertEqual(digest, other)
                self.assertIn(before.__module__, sys.modules)
                raise RuntimeError("capture failed")
        self.assertFalse(any(name.startswith("jarvis._gpu_comparison_scene_") for name in sys.modules))

    def test_shared_scene_compatibility_reports_every_omitted_renderer_field(self):
        original = {"reactor": 1., "orbit_phase": (1., 2., 3.), "rms": 0.}
        frame, omitted = compatible_frame(original, {"reactor", "rms"})
        self.assertEqual(frame, {"reactor": 1., "rms": 0.})
        self.assertEqual(omitted, ["orbit_phase"])
        self.assertIn("orbit_phase", original)
        self.assertEqual(compatible_frame(original, set(original)), (original, []))


if __name__ == "__main__":
    unittest.main()
