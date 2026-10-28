"""PCM-derived display envelopes and actual GL state signatures, without devices."""
import math
import os
import unittest

from jarvis.gpu_config import GpuSettings
from jarvis.gpu_renderer import GpuRenderer
from jarvis.morphing import CATALOGUE
from jarvis.presence_gpu import ReactorScene


def signal(level=.056, bands=(.056, .03, .015)):
    return {"rms": level, "wave": [level, -level]*24, "bands": bands}


def feed(scene, state, *, level=.056, bands=(.056, .03, .015), seconds=.4):
    scene.update_state(state, now=0.)
    for index in range(round(seconds/.04)+1):
        now = index*.04
        scene.update_audio(signal(level, bands), now=now)
        frame = scene.snapshot(480, 360, now)
    return frame


class VoiceEnvelopeTests(unittest.TestCase):
    def test_silence_and_gate_never_invent_voice_energy_even_with_active_speaking_state(self):
        for state in ("silent", "listening", "user_speaking", "jarvis_speaking", "thinking"):
            for level in (0., .002, .0025):
                with self.subTest(state=state, level=level):
                    frame = feed(ReactorScene(), state, level=level, bands=(0., 0., 0.))
                    self.assertEqual(frame["voice_envelopes"], (0., 0., 0.))
                    self.assertEqual(frame["input_energy"], 0.)

    def test_compression_is_bounded_perceptible_and_three_envelopes_have_distinct_speeds(self):
        scene = ReactorScene()
        scene.update_state("jarvis_speaking", now=0.)
        scene.update_audio(signal(.056, (.056, .056, .056)), now=0.)
        attack = scene.snapshot(480, 360, .04)["voice_envelopes"]
        self.assertGreater(attack[0], attack[1])
        self.assertGreater(attack[1], attack[2])
        for index in range(2, 11):
            now = index*.04
            scene.update_audio(signal(.056, (.056, .056, .056)), now=now)
            held = scene.snapshot(480, 360, now)["voice_envelopes"]
        self.assertTrue(all(.5 < value <= 1. for value in held))
        scene.update_audio(signal(0., (0., 0., 0.)), now=.44)
        released = scene.snapshot(480, 360, .44)["voice_envelopes"]
        self.assertTrue(all(0 < after < before for before, after in zip(held, released)))
        self.assertLess(released[0]/held[0], released[1]/held[1])
        self.assertLess(released[1]/held[1], released[2]/held[2])
        for index in range(12, 160):
            final = scene.snapshot(480, 360, index*.04)
        self.assertEqual(final["voice_envelopes"], (0., 0., 0.))

    def test_existing_audio_controls_change_only_display_and_frequency_weights_are_observed(self):
        original = signal(.06, (.06, .04, .02))
        for key in ("bass_contribution", "mid_contribution", "treble_contribution", "audio_reactivity"):
            baseline, muted = ReactorScene(), ReactorScene()
            muted.set_settings({key: 0})
            before = feed(baseline, "jarvis_speaking", level=original["rms"], bands=original["bands"])
            after = feed(muted, "jarvis_speaking", level=original["rms"], bands=original["bands"])
            with self.subTest(control=key):
                self.assertNotEqual(before["voice_envelopes"], after["voice_envelopes"])
                self.assertEqual(baseline.model.signal, muted.model.signal)
                self.assertEqual(before["audio_bands"], after["audio_bands"])
        self.assertEqual(after["voice_envelopes"], (0., 0., 0.))

    def test_vad_reception_is_not_triggered_by_unconfirmed_microphone_noise(self):
        quiet = ReactorScene()
        quiet_frame = feed(quiet, "listening", level=.09)
        self.assertEqual(quiet_frame["input_energy"], 0.)
        self.assertEqual(quiet_frame["receipt"], 0.)
        quiet.model.update_event("user_speaking", signal(.06), now=.44)
        quiet.snapshot(480, 360, .44)
        heard = quiet.snapshot(480, 360, .48)
        self.assertGreater(heard["input_energy"], .5)
        self.assertGreater(heard["receipt"], 0.)
        quiet.model.update_event("thinking", now=.5)
        quiet.snapshot(480, 360, .5)
        received = quiet.snapshot(480, 360, .54)
        self.assertGreater(received["receipt"], 0.)
        self.assertEqual(received["visual_state"], 3)
        self.assertEqual(received["input_energy"], 0.)

    def test_interruption_dormant_and_stale_generation_discard_old_voice_energy(self):
        scene = ReactorScene()
        spoken = feed(scene, "jarvis_speaking")
        self.assertGreater(max(spoken["voice_envelopes"]), .5)
        generation = scene.epoch
        scene.update_state("user_speaking", now=.44, interrupt=True)
        self.assertFalse(scene.update_audio(signal(), now=.45, generation=generation))
        interrupted = scene.snapshot(480, 360, .45)
        self.assertEqual(interrupted["voice_envelopes"], (0., 0., 0.))
        self.assertEqual(interrupted["audio_bands"], (0., 0., 0.))
        scene.update_state("dormant", now=.5)
        asleep = scene.snapshot(480, 360, .6)
        self.assertEqual(asleep["receipt"], 0.)
        self.assertEqual(asleep["visual_mix"], (0., 0., 0.))
        self.assertFalse(scene.moving(.6))

    def test_reduced_motion_removes_acknowledgement_and_keeps_actual_signal(self):
        scene = ReactorScene(reduced_motion=True)
        frame = feed(scene, "user_speaking")
        self.assertEqual(frame["receipt"], 0.)
        self.assertEqual(frame["rms"], .056)
        self.assertGreater(frame["input_energy"], 0.)
        self.assertEqual(frame["orbit_phase"], (0., .85, -.62))


class VisualStateEglTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import moderngl
            cls.context = moderngl.create_standalone_context(require=330, backend="egl")
        except Exception as error:
            if os.environ.get("JARVIS_REQUIRE_GPU") == "1":
                raise RuntimeError("Required actual EGL visual-state context unavailable") from error
            raise unittest.SkipTest(f"Optional EGL unavailable: {error}") from error

    @classmethod
    def tearDownClass(cls):
        cls.context.release()

    def setUp(self):
        self.renderer = GpuRenderer(self.context, 480, 360)
        self.target = self.context.simple_framebuffer((480, 360), components=3)
        self.addCleanup(self.target.release)
        self.addCleanup(self.renderer.shutdown)

    def render(self, frame):
        self.renderer.render(**frame, target=self.target)
        self.context.finish()
        return self.target.read(components=3, alignment=1)

    def test_listening_thinking_and_speaking_are_distinct_pixels_with_one_preserved_core(self):
        images = []
        for state in ("listening", "user_speaking", "thinking", "jarvis_speaking"):
            frame = feed(ReactorScene(), state)
            image = self.render(frame)
            images.append(image)
            center = ((360//2)*480+480//2)*3
            self.assertGreater(max(image[center:center+3]), 0)
            for x, y in ((0, 0), (479, 0), (0, 359), (479, 359)):
                pixel = (y*480+x)*3
                self.assertEqual(image[pixel:pixel+3], b"\0\0\0")
        self.assertEqual(len(set(images)), 4)

    def test_pcm_aura_is_brighter_outside_core_and_silence_is_unchanged(self):
        frame = feed(ReactorScene(), "jarvis_speaking", level=.06)
        quiet = {**frame, "voice_envelopes": (0., 0., 0.), "audio_bands": (0., 0., 0.), "rms": 0.}
        plain, speaking = self.render(quiet), self.render(frame)
        def annulus_energy(image):
            return sum(sum(image[(y*480+x)*3:(y*480+x)*3+3])
                       for y in range(360) for x in range(480)
                       if 68**2 < (x-240)**2+(y-180)**2 < 90**2)
        self.assertGreater(annulus_energy(speaking), annulus_energy(plain)*1.15)
        self.assertEqual(self.render(quiet), plain)

    def test_reference_30_disables_new_layers_and_reduced_motion_freezes_motion(self):
        frame = feed(ReactorScene(), "jarvis_speaking")
        frame["art"] = GpuSettings.reference_30().to_dict()
        original = self.render({**frame, "visual_mix": (0., 0., 0.), "voice_envelopes": (0., 0., 0.),
                                "receipt": 0., "input_energy": 0.})
        self.assertEqual(self.render(frame), original)
        frame["art"] = GpuSettings().to_dict()
        frame["reduced_motion"] = True
        first = self.render({**frame, "time_s": 1.})
        self.assertEqual(first, self.render({**frame, "time_s": 19.}))

    def test_all_eight_engravings_remain_visible_during_pcm_aura(self):
        frame = feed(ReactorScene(), "jarvis_speaking", level=.09)
        plain = self.render(frame)
        for family, symbol in CATALOGUE.items():
            with self.subTest(family=family):
                image = self.render({**frame, "surface_family": family, "surface_amount": 1.,
                    "points": symbol.contour, "details": symbol.details, "orbit_blend": 1.})
                self.assertNotEqual(image, plain)
                self.assertGreater(sum(abs(a-b) for a, b in zip(image, plain)), 1000)


if __name__ == "__main__":
    unittest.main()
