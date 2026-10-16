"""Installer integrity/control tests; never download weights during CI."""
import hashlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from scripts.install_voice_models import install, verified_download


class InstallerTests(unittest.TestCase):
    def test_installer_is_standalone_outside_checkout(self):
        with tempfile.TemporaryDirectory() as folder:
            script = Path(folder) / "install_voice_models.py"
            shutil.copyfile(Path(__file__).parents[1] / "scripts/install_voice_models.py", script)
            result = subprocess.run([sys.executable, str(script), "--help"], cwd=folder,
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("--accept-model-licenses", result.stdout)

    def test_bad_lfs_checksum_refuses_install_then_valid_checksum_copies(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "cached"
            source.write_bytes(b"test artifact content")
            target = Path(folder) / "installed/model.bin"
            metadata = SimpleNamespace(rfilename="model.bin", lfs=SimpleNamespace(sha256="0" * 64))
            info = SimpleNamespace(sha="fixed-revision", siblings=[metadata])
            hub = SimpleNamespace(HfApi=Mock(return_value=SimpleNamespace(model_info=Mock(return_value=info))),
                                  hf_hub_download=Mock(return_value=str(source)))
            with patch.dict(sys.modules, {"huggingface_hub": hub}):
                with self.assertRaisesRegex(RuntimeError, "Intégrité"):
                    verified_download("test/repo", "main", "model.bin", target)
                self.assertFalse(target.exists())
                metadata.lfs.sha256 = hashlib.sha256(source.read_bytes()).hexdigest()
                record = verified_download("test/repo", "main", "model.bin", target)
                self.assertEqual(target.read_bytes(), source.read_bytes())
                self.assertEqual(record["revision"], "fixed-revision")
                hub.hf_hub_download.assert_called_with("test/repo", "model.bin", revision="fixed-revision")

    def test_licenses_only_does_not_download_model_weights(self):
        with tempfile.TemporaryDirectory() as folder:
            hub = SimpleNamespace(HfApi=Mock())
            with patch.dict(sys.modules, {"huggingface_hub": hub}), patch(
                    "scripts.install_voice_models.verified_download", return_value={}) as download:
                install(Path(folder), accept=False, stt_size="small")
            self.assertEqual(download.call_count, 3)
            self.assertTrue(all(call.args[2].endswith(("MODEL_CARD", "README.md")) for call in download.call_args_list))
            self.assertFalse((Path(folder) / "piper").exists())
