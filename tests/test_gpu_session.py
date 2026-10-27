"""Visual transport bounds and lifecycle; no microphone or model is opened."""
import copy
import subprocess
import sys
import unittest

from jarvis.gpu_session import validate_packet


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


if __name__ == "__main__":
    unittest.main()
