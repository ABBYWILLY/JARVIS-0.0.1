"""Frozen/source renderer checks distinguish packaging bugs from missing drivers."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from jarvis.gpu_smoke import expected_driver_absence, run_smoke


class GpuSmokePolicyTests(unittest.TestCase):
    def fake_session(self, closure, driver_error=None):
        class Session:
            def __init__(self, **_options): pass
            def start(self): pass
            def submit(self, _packet): pass
            def poll(self):
                if driver_error is not None:
                    return [driver_error]
                return [{"kind": "ready", "renderer": {"renderer": "explicit test double"}},
                        {"kind": "heartbeat", "frames": 1}]
            def stop(self, **_options): return closure
        return Session

    def test_first_frame_does_not_hide_cleanup_errors_forced_exit_or_missing_acknowledgment(self):
        for state in ("cleanup_failed", "forced", "unconfirmed"):
            with self.subTest(state=state), tempfile.TemporaryDirectory() as folder:
                closure = {"status": state, "acknowledged": state == "cleanup_failed",
                           "forced": state == "forced", "cleanup_errors":
                           ["renderer: release failed"] if state == "cleanup_failed" else [], "errors": []}
                with patch("jarvis.gpu_session.GpuSession", self.fake_session(closure)), \
                        patch("importlib.import_module"):
                    self.assertEqual(run_smoke(folder), 1)
                report = json.loads((Path(folder) / "gpu-smoke.json").read_text(encoding="utf-8"))
                self.assertTrue(report["shader_compile_and_frame"])
                self.assertEqual(report["status"], "failed")
                self.assertEqual(report["shutdown"], "failed")
                self.assertEqual(report["closure"], closure)

    def test_late_runtime_error_fails_even_when_cleanup_was_acknowledged(self):
        closure = {"status": "complete", "acknowledged": True, "forced": False,
                   "cleanup_errors": [], "errors": [{"kind": "error", "stage": "runtime",
                   "message": "driver failed after first frame", "renderer": {}}]}
        with tempfile.TemporaryDirectory() as folder:
            with patch("jarvis.gpu_session.GpuSession", self.fake_session(closure)), \
                    patch("importlib.import_module"):
                self.assertEqual(run_smoke(folder), 1)
            report = json.loads((Path(folder) / "gpu-smoke.json").read_text(encoding="utf-8"))
            self.assertEqual(report["shutdown"], "failed")
            self.assertTrue(report["shader_compile_and_frame"])

    def test_confirmed_driver_absence_still_requires_and_accepts_clean_shutdown(self):
        event = {"kind": "error", "stage": "context", "message":
                 "Accélération GPU non confirmée (llvmpipe)", "renderer": {"acceleration": "software"}}
        closure = {"status": "complete", "acknowledged": True, "forced": False,
                   "cleanup_errors": [], "errors": [event]}
        with tempfile.TemporaryDirectory() as folder:
            with patch("jarvis.gpu_session.GpuSession", self.fake_session(closure, event)), \
                    patch("importlib.import_module"):
                self.assertEqual(run_smoke(folder), 0)
            report = json.loads((Path(folder) / "gpu-smoke.json").read_text(encoding="utf-8"))
            self.assertFalse(report["shader_compile_and_frame"])
            self.assertEqual(report["status"], "driver_unavailable")
            self.assertEqual(report["shutdown"], "complete")

    def test_only_explicit_context_driver_absence_is_accepted(self):
        event = {"kind": "error", "stage": "context", "message":
                 "OpenGL 3.3 indisponible : WGL: The driver does not appear to support OpenGL"}
        self.assertTrue(expected_driver_absence(event))
        for change in ({"stage": "renderer"}, {"stage": "imports"}, {"stage": "runtime"},
                       {"message": "Shader compilation failed"}, {"message": "DLL load failed"},
                       {"message": "GLFW initialization failed"}, {"kind": "closed"}):
            with self.subTest(change=change):
                self.assertFalse(expected_driver_absence({**event, **change}))

    def test_software_fallback_is_reportable_only_with_confirmed_renderer_metadata(self):
        event = {"kind": "error", "stage": "context", "message":
                 "Accélération GPU non confirmée (llvmpipe)",
                 "renderer": {"acceleration": "software"}}
        self.assertTrue(expected_driver_absence(event))
        self.assertFalse(expected_driver_absence({**event, "renderer": {}}))
        self.assertFalse(expected_driver_absence({**event, "stage": "renderer"}))

    def test_native_import_failure_is_fatal_and_writes_a_fresh_report(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch("importlib.import_module", side_effect=ImportError("native test failure")):
                result = run_smoke(folder)
            report = json.loads((Path(folder) / "gpu-smoke.json").read_text(encoding="utf-8"))
            self.assertEqual(result, 1)
            self.assertEqual(report["stage"], "native_imports")
            self.assertFalse(report["shader_compile_and_frame"])
            self.assertEqual(report["shutdown"], "complete")
            self.assertIn("ImportError", report["error"])
            self.assertTrue((Path(folder) / "jarvis.sqlite3").is_file())


class GpuSmokeEglTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import moderngl
            context = moderngl.create_standalone_context(require=330, backend="egl")
            context.release()
        except Exception as error:
            if os.environ.get("JARVIS_REQUIRE_GPU") == "1":
                raise RuntimeError("Required real EGL smoke context unavailable") from error
            raise unittest.SkipTest(f"Optional EGL unavailable: {error}") from error

    def test_actual_spawned_renderer_draws_a_frame_and_finishes_cleanly(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(run_smoke(folder, headless=True, allow_software=True), 0)
            report = json.loads((Path(folder) / "gpu-smoke.json").read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "supported")
            self.assertTrue(report["shader_compile_and_frame"])
            self.assertEqual(report["shutdown"], "complete")
            self.assertTrue(report["closure"]["acknowledged"])
            self.assertFalse(report["closure"]["forced"])
            self.assertEqual(report["closure"]["cleanup_errors"], [])
            self.assertEqual(report["hardware_validation"], "pending")
            self.assertEqual(report["microphone_and_models"], "not_opened")
            self.assertTrue(report["renderer"]["renderer"])


if __name__ == "__main__":
    unittest.main()
