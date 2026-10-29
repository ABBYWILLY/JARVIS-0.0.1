"""Opt-in offline proof tool: imports stay local and existing files stay intact."""
import unittest
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch


class CognitiveProofToolTests(unittest.TestCase):
    def test_import_and_help_require_no_audio_gpu_or_graphical_backend(self):
        code = ("import sys; import scripts.capture_cognitive_hud; import scripts.benchmark_cognitive_idle; "
                "assert not any(name in sys.modules for name in "
                "('moderngl','glfw','tkinter','sounddevice','piper','PIL'))")
        subprocess.run([sys.executable, "-c", code], capture_output=True, check=True)
        result = subprocess.run([sys.executable, "scripts/capture_cognitive_hud.py", "--help"],
                                capture_output=True, text=True, check=True)
        self.assertIn("--benchmark", result.stdout)
        self.assertIn("--output", result.stdout)

    def test_existing_proof_directory_is_never_overwritten(self):
        from scripts.capture_cognitive_hud import main
        with tempfile.TemporaryDirectory() as directory:
            preserved = Path(directory)/"preserved.txt"
            preserved.write_text("Existing proof")
            with patch("scripts.capture_cognitive_hud.shutil.which", return_value="ffmpeg"):
                with self.assertRaises(FileExistsError):
                    main(["--output", directory])
            self.assertEqual(preserved.read_text(), "Existing proof")

    def test_demo_covers_every_requested_state_and_keeps_signals_explicit(self):
        from scripts.capture_cognitive_hud import STAGES
        self.assertEqual({activity for activity, _visual in STAGES},
                         {"idle", "listening", "user_speaking", "transcribing", "context", "waiting",
                          "generating", "synthesis", "speaking", "interrupted", "error", "cancelled"})
        self.assertEqual(STAGES[0], STAGES[-1])


