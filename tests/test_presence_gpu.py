"""Offline scene and CLI contracts: no OpenGL context, window or audio device."""
import builtins
from contextlib import redirect_stderr
import io
import json
import math
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import wave
import zlib

from jarvis import presence_gpu
from jarvis.gpu_config import GpuSettings
from jarvis.morphing import ENTER_SECONDS, FAMILIES, HOLD_SECONDS, MorphController, RETURN_SECONDS
from jarvis.presence import PresenceModel, SIGNAL_LIFETIME
from jarvis.presence_gpu import GpuUnavailable, ReactorScene, WavInput, context_info, parse_args, save_png


def pcm_signal():
    return {"rms": .25, "wave": [.6, -.4, .2, -.7] * 12}


def write_wav(path, samples, *, channels=1, rate=8000, sample_width=2):
    with wave.open(str(path), "wb") as output:
        output.setnchannels(channels)
        output.setsampwidth(sample_width)
        output.setframerate(rate)
        output.writeframes(struct.pack("<" + "h" * len(samples), *samples)
                           if sample_width == 2 else bytes(samples))


class ReactorSceneTests(unittest.TestCase):
    def test_every_state_timing_control_changes_the_actual_scene_without_changing_pcm(self):
        state_for = {"speaking_speed": "jarvis_speaking", "listening_speed": "listening",
                     "idle_speed": "silent"}
        fields = {"ring_speed": "orbit_phase", "thinking_speed": "orbit_phase",
                  "speaking_speed": "orbit_phase", "listening_speed": "orbit_phase",
                  "idle_speed": "orbit_phase", "thinking_contraction": "core_scale",
                  "transition_ms": "core_scale", "ring_acceleration_ms": "orbit_phase",
                  "audio_attack_ms": "audio_bands", "audio_release_ms": "audio_bands"}
        source = {**pcm_signal(), "bands": (.5, .3, .2)}
        for key, field in fields.items():
            spec = presence_gpu.GpuSettings.__dataclass_fields__[key]
            low, high = spec.metadata["low"], spec.metadata["high"]
            snapshots = []
            for value in (low, high):
                scene = ReactorScene()
                scene.set_settings({key: value})
                scene.update_state(state_for.get(key, "thinking"), now=0.)
                scene.update_audio(source, now=0.)
                for now in (.05, .10, .15):
                    scene.snapshot(960, 640, now)
                snapshots.append(scene.snapshot(960, 640, .25 if key == "audio_release_ms" else .16))
                self.assertEqual(scene.model.signal["rms"], source["rms"])
            with self.subTest(control=key):
                self.assertNotEqual(snapshots[0][field], snapshots[1][field])

    def test_gpu_expression_duration_and_alignment_controls_change_transition_hold_and_return(self):
        settings = (("expression_transition_ms", 120, 1000, .18, "surface_amount"),
                    ("expression_hold_ms", 250, 2500, .9, "surface_amount"),
                    ("expression_ring_speed", 40, 200, .18, "orbit_blend"))
        for key, low, high, age, field in settings:
            snapshots = []
            for value in (low, high):
                scene = ReactorScene()
                scene.set_settings({key: value})
                scene.update_state("jarvis_speaking", now=0.)
                self.assertTrue(scene.preview_expression("Heureux de te revoir 😊", 960, 640, now=0.))
                snapshots.append(scene.snapshot(960, 640, age))
                final = scene.snapshot(960, 640, 5.)
                self.assertIsNone(final["surface_family"])
                self.assertEqual(final["surface_amount"], 0.)
            with self.subTest(control=key):
                self.assertNotEqual(snapshots[0][field], snapshots[1][field])

    def test_gpu_fps_cap_respects_both_user_limit_and_profile(self):
        for profile, cap in (("eco", 15), ("balanced", 60), ("cinematic", 60)):
            for limit in (15, 24, 60):
                settings = GpuSettings.from_dict({"profile": profile, "fps_limit": limit})
                self.assertEqual(settings.frames_per_second, min(limit, cap))

    def test_one_existing_model_and_controller_supply_all_eight_distinct_symbols(self):
        symbols = dict(zip(FAMILIES, ("😊", "😂", "❤️", "😢", "😠", "😮", "🤔", "😉")))
        with patch.object(presence_gpu, "PresenceModel", wraps=PresenceModel) as model_factory, \
                patch.object(presence_gpu, "MorphController", wraps=MorphController) as morph_factory:
            scene = ReactorScene()
            model, controller = scene.model, scene.semantic
            frames = set()
            for index, (family, symbol) in enumerate(symbols.items()):
                with self.subTest(family=family):
                    now = index * 3.
                    scene.update_state("silent", now=now)
                    self.assertTrue(scene.preview_expression(symbol, 960, 640, now=now))
                    self.assertEqual(scene.semantic.family, family)
                    frame = scene.snapshot(960, 640, now + ENTER_SECONDS + HOLD_SECONDS / 2)
                    self.assertEqual(len(frame["points"]), 97)
                    self.assertEqual(frame["surface_family"], family)
                    self.assertEqual(frame["surface_amount"], 1.)
                    self.assertEqual(frame["reactor"], 1.)
                    self.assertTrue(all(-1 <= coordinate <= 1 for point in frame["points"] for coordinate in point))
                    frames.add((frame["points"], frame["details"]))
                    self.assertIs(scene.model, model)
                    self.assertIs(scene.semantic, controller)
            self.assertEqual(len(frames), 8)
            model_factory.assert_called_once()
            morph_factory.assert_called_once()

    def test_silence_never_invents_a_wave_in_idle_listening_or_speaking(self):
        for state in ("silent", "listening", "jarvis_speaking"):
            with self.subTest(state=state):
                scene = ReactorScene()
                scene.update_state(state, now=1)
                scene.update_audio({"rms": 0., "wave": [1., -1.] * 24}, now=1)
                first, later = scene.snapshot(960, 640, 1), scene.snapshot(960, 640, 30)
                self.assertEqual(first["points"], later["points"])
                self.assertTrue(all(y == 0 for x, y in first["points"]))
                self.assertEqual(first["rms"], 0)
                self.assertEqual(first["reactor"], 1)
                self.assertEqual(first["audio_bands"], (0., 0., 0.))
                self.assertEqual(later["audio_bands"], (0., 0., 0.))
                self.assertEqual(scene.moving(30), state != "silent")

    def test_thinking_to_speaking_keeps_the_sphere_and_slow_orbits_not_a_mesh_transition(self):
        scene = ReactorScene()
        scene.update_state("thinking", now=0)
        scene.snapshot(960, 640, .1)
        scene.snapshot(960, 640, .2)
        self.assertTrue(scene.model.morphing)
        scene.update_state("jarvis_speaking", now=1)
        for index in range(1, 21):
            frame = scene.snapshot(960, 640, 1 + index * .1)
        self.assertEqual(frame["reactor"], 1)
        self.assertTrue(all(y == 0 for x, y in frame["points"]))
        self.assertGreater(frame["core_scale"], .99)
        self.assertTrue(scene.moving(3))  # Explicit slow SPEAKING orbits, no fake PCM.
        scene.update_state("silent", now=3)
        for index in range(1, 101):
            idle = scene.snapshot(960, 640, 3 + index * .1)
        self.assertEqual(idle["rms"], 0)
        self.assertEqual(idle["reactor"], 1)
        self.assertFalse(scene.moving(13))

    def test_real_pcm_drives_listening_and_speaking_then_expires_to_a_quiet_sphere(self):
        for state in ("listening", "jarvis_speaking"):
            with self.subTest(state=state):
                scene = ReactorScene()
                scene.update_state(state, now=2)
                scene.update_audio(pcm_signal(), now=2)
                active = scene.snapshot(960, 640, 2.01)
                self.assertGreater(max(y for x, y in active["points"]), .01)
                self.assertLess(min(y for x, y in active["points"]), -.01)
                self.assertAlmostEqual(active["rms"], .25)
                self.assertTrue(scene.moving(2.01))
                # The event loop must paint one final frame when PCM expires;
                # otherwise its last non-flat buffer would remain on screen.
                self.assertTrue(scene.moving(2 + SIGNAL_LIFETIME + .01))
                expired = scene.snapshot(960, 640, 2 + SIGNAL_LIFETIME + .01)
                self.assertEqual(expired["rms"], 0)
                self.assertTrue(all(y == 0 for x, y in expired["points"]))
                self.assertEqual(expired["reactor"], 1)
                self.assertEqual(expired["audio_bands"], (0., 0., 0.))
                self.assertTrue(scene.moving(2 + SIGNAL_LIFETIME + .01))

    def test_thinking_sphere_persists_while_surface_lines_fade_in_hold_and_dissipate(self):
        scene = ReactorScene()
        scene.update_state("thinking", now=0)
        concentrating = scene.snapshot(960, 640, .1)
        self.assertEqual(concentrating["reactor"], 1)
        self.assertGreater(concentrating["core_scale"], .92)
        self.assertLess(concentrating["core_scale"], 1)
        self.assertTrue(scene.preview_expression("😊", 960, 640, now=.1))
        entering = scene.snapshot(960, 640, .1 + ENTER_SECONDS / 2)
        self.assertEqual(entering["reactor"], 1.)
        self.assertAlmostEqual(entering["surface_amount"], .5)
        self.assertEqual(entering["orbit_blend"], entering["surface_amount"])
        held = scene.snapshot(960, 640, .1 + ENTER_SECONDS + HOLD_SECONDS / 2)
        self.assertEqual(held["reactor"], 1.)
        self.assertEqual(held["surface_family"], "smile")
        self.assertEqual(held["surface_amount"], 1.)
        self.assertTrue(held["details"])
        returned = scene.snapshot(960, 640, .1 + ENTER_SECONDS + HOLD_SECONDS + RETURN_SECONDS * .9)
        self.assertEqual(returned["reactor"], 1.)
        self.assertGreater(returned["surface_amount"], 0.)
        self.assertLess(returned["surface_amount"], .1)
        done = scene.snapshot(960, 640, 2)
        self.assertFalse(scene.semantic.active)
        self.assertIsNone(done["surface_family"])
        self.assertEqual(done["surface_amount"], 0.)
        self.assertEqual(done["orbit_blend"], 0.)
        scene.update_state("silent", now=2)
        for index in range(1, 101):
            idle = scene.snapshot(960, 640, 2 + index * .1)
        self.assertEqual(idle["reactor"], 1)
        self.assertTrue(all(y == 0 for x, y in idle["points"]))
        self.assertFalse(scene.moving(12))

    def test_interrupt_and_user_pcm_cancel_the_current_expression(self):
        scene = ReactorScene()
        scene.update_state("thinking", now=1)
        scene.snapshot(960, 640, 1.1)
        self.assertTrue(scene.preview_expression("❤️", 960, 640, now=1.1))
        scene.update_state("listening", now=1.2, interrupt=True)
        self.assertEqual(scene.model.state, "listening")
        self.assertEqual(scene.reactor, 1)
        self.assertFalse(scene.semantic.active)
        self.assertFalse(scene.preview_expression("😊", 960, 640, now=1.2))
        scene.update_state("silent", now=2)
        self.assertTrue(scene.preview_expression("😊", 960, 640, now=2))
        scene.update_audio(pcm_signal(), now=2.1)
        self.assertFalse(scene.semantic.active)
        scene.update_state("dormant", now=3)
        self.assertEqual(scene.reactor, 0)

    def test_reduced_motion_cancels_morph_then_holds_static_thinking_and_symbol(self):
        scene = ReactorScene()
        scene.update_state("thinking", now=1)
        self.assertTrue(scene.preview_expression("😊", 960, 640, now=1))
        scene.set_reduced_motion(True)
        self.assertFalse(scene.semantic.active)
        first, later = scene.snapshot(960, 640, 2), scene.snapshot(960, 640, 20)
        self.assertEqual(first["points"], later["points"])
        self.assertEqual(first["reactor"], 1)
        self.assertTrue(first["reduced_motion"])
        self.assertFalse(scene.moving(20))
        self.assertTrue(scene.preview_expression("😂", 960, 640, now=21))
        symbol = scene.snapshot(960, 640, 21)
        self.assertTrue(symbol["details"])
        self.assertEqual(symbol["reactor"], 1.)
        self.assertEqual(symbol["surface_amount"], 1.)
        self.assertEqual(symbol["points"], scene.snapshot(960, 640, 21 + HOLD_SECONDS / 2)["points"])
        self.assertFalse(scene.moving(21 + HOLD_SECONDS / 2))
        scene.snapshot(960, 640, 21 + HOLD_SECONDS + .01)
        self.assertFalse(scene.semantic.active)

    def test_orbital_inertia_keeps_phases_continuous_and_thinking_contracts_the_same_core(self):
        scene = ReactorScene()
        scene.update_state("thinking", now=0.)
        for index in range(61):
            frame = scene.snapshot(960, 640, index / 30)
        fast = tuple(abs(value) for value in scene.orbit_velocity)
        self.assertGreater(min(fast), .6)
        self.assertGreater(len(set(round(value, 2) for value in fast)), 1)
        self.assertAlmostEqual(frame["core_scale"], .92, places=3)
        phases = frame["orbit_phase"]
        scene.update_state("jarvis_speaking", now=2.)
        self.assertEqual(tuple(scene.orbit_phase), phases)
        start = scene.snapshot(960, 640, 2.)
        self.assertEqual(start["orbit_phase"], phases)
        self.assertEqual(start["core_scale"], frame["core_scale"])
        for index in range(1, 61):
            frame = scene.snapshot(960, 640, 2 + index / 30)
        self.assertEqual(frame["reactor"], 1.)
        self.assertAlmostEqual(frame["core_scale"], 1., places=3)
        self.assertTrue(all(abs(value) < old / 2 for value, old in zip(scene.orbit_velocity, fast)))
        for before, after, sign in zip(phases, frame["orbit_phase"], (1, -1, 1)):
            self.assertGreater((after-before) * sign, 0.)

    def test_hidden_gap_and_reduced_motion_never_reset_or_teleport_orbital_angles(self):
        scene = ReactorScene()
        scene.update_state("thinking", now=0.)
        for index in range(31):
            scene.snapshot(960, 640, index / 30)
        before = tuple(scene.orbit_phase)
        resumed = scene.snapshot(960, 640, 100.)
        self.assertTrue(all(abs(last-first) < .12 for first, last in zip(before, resumed["orbit_phase"])))
        scene.set_reduced_motion(True, now=100.)
        held = scene.snapshot(960, 640, 101.)
        self.assertEqual(held["orbit_phase"], scene.snapshot(960, 640, 200.)["orbit_phase"])
        self.assertFalse(scene.moving(200.))
        scene.set_reduced_motion(False, now=200.)
        self.assertEqual(tuple(scene.orbit_phase), held["orbit_phase"])
        self.assertNotEqual(scene.snapshot(960, 640, 200.1)["orbit_phase"], held["orbit_phase"])

    def test_audio_bands_have_attack_release_silence_gate_and_generation_cancellation(self):
        scene = ReactorScene()
        scene.update_state("jarvis_speaking", now=0.)
        signal = dict(pcm_signal(), bands=(.8, .4, .2))
        self.assertTrue(scene.update_audio(signal, now=0., generation=scene.epoch))
        active = scene.snapshot(960, 640, .05)
        self.assertTrue(all(0. < actual < target for actual, target in zip(active["audio_bands"], signal["bands"])))
        self.assertGreater(active["audio_bands"][0], active["audio_bands"][1])
        scene.update_audio(dict(signal, rms=0.), now=.05)
        released = scene.snapshot(960, 640, .1)
        self.assertTrue(all(0. < actual < old for actual, old in zip(released["audio_bands"], active["audio_bands"])))
        for index in range(1, 41):
            silent = scene.snapshot(960, 640, .1 + index * .1)
        self.assertEqual(silent["audio_bands"], (0., 0., 0.))
        old_generation = scene.epoch
        scene.update_state("listening", now=5., interrupt=True)
        self.assertFalse(scene.update_audio(signal, now=5., generation=old_generation))
        self.assertEqual(scene.snapshot(960, 640, 5.1)["audio_bands"], (0., 0., 0.))
        self.assertEqual(scene.snapshot(960, 640, 5.1)["rms"], 0.)

    def test_classic_idle_line_and_dormancy_remain_static_without_obsolete_motion(self):
        scene = ReactorScene(idle_line=True)
        line = scene.snapshot(960, 640, 0.)
        self.assertEqual(line["reactor"], 0.)
        self.assertFalse(scene.moving(1.))
        scene.set_idle_line(False)
        self.assertEqual(scene.snapshot(960, 640, 1.)["reactor"], 1.)
        scene.update_state("thinking", now=2.)
        scene.snapshot(960, 640, 2.1)
        scene.update_state("dormant", now=3.)
        self.assertFalse(scene.moving(3.))
        self.assertEqual(scene.snapshot(960, 640, 4.)["reactor"], 0.)

    def test_speaking_pcm_animates_the_surface_without_cancelling_its_expression(self):
        scene = ReactorScene()
        scene.update_state("jarvis_speaking", now=0.)
        generation = scene.epoch
        self.assertTrue(scene.preview_expression("Heureux de te revoir 😊", 960, 640,
                                                 now=0., generation=generation))
        scene.update_audio(dict(pcm_signal(), bands=(.2, .4, .1)), now=.05, generation=generation)
        frame = scene.snapshot(960, 640, .1)
        self.assertEqual(frame["surface_family"], "smile")
        self.assertGreater(frame["surface_amount"], 0.)
        self.assertGreater(frame["audio_bands"][1], 0.)
        self.assertEqual(frame["reactor"], 1.)
        scene.update_state("listening", now=.2, interrupt=True)
        self.assertFalse(scene.semantic.active)
        self.assertFalse(scene.preview_expression("❤️", 960, 640, now=.2, generation=generation))
        self.assertFalse(scene.update_audio(pcm_signal(), now=.2, generation=generation))
        cancelled = scene.snapshot(960, 640, .21)
        self.assertIsNone(cancelled["surface_family"])
        self.assertEqual(cancelled["surface_amount"], 0.)
        self.assertEqual(cancelled["audio_bands"], (0., 0., 0.))
        self.assertEqual(cancelled["reactor"], 1.)

    def test_surface_temporarily_keeps_a_sphere_even_with_classic_idle_line(self):
        scene = ReactorScene(idle_line=True)
        self.assertEqual(scene.snapshot(960, 640, 0.)["reactor"], 0.)
        self.assertTrue(scene.preview_expression("Je t'aime ❤️", 960, 640, now=.1))
        held = scene.snapshot(960, 640, .1 + ENTER_SECONDS + HOLD_SECONDS / 2)
        self.assertEqual(held["surface_family"], "affection")
        self.assertEqual(held["reactor"], 1.)
        self.assertEqual(held["surface_amount"], 1.)
        done = scene.snapshot(960, 640, 2.)
        self.assertIsNone(done["surface_family"])
        self.assertEqual(done["reactor"], 0.)

    def test_surface_crowns_slow_orbits_without_reset_then_return_to_state_speed(self):
        scene = ReactorScene()
        scene.update_state("thinking", now=0.)
        for index in range(61):
            scene.snapshot(960, 640, index / 30)
        fast = tuple(abs(value) for value in scene.orbit_velocity)
        phase = tuple(scene.orbit_phase)
        self.assertTrue(scene.preview_expression("C'est drôle 😂", 960, 640, now=2.))
        self.assertEqual(scene.snapshot(960, 640, 2.)["orbit_phase"], phase)
        for index in range(1, 26):
            held = scene.snapshot(960, 640, 2 + index / 30)
        self.assertEqual(held["orbit_blend"], 1.)
        self.assertTrue(all(abs(value) < before / 4 for value, before in zip(scene.orbit_velocity, fast)))
        for index in range(26, 121):
            done = scene.snapshot(960, 640, 2 + index / 30)
        self.assertFalse(scene.semantic.active)
        self.assertEqual(done["orbit_blend"], 0.)
        self.assertGreater(min(abs(value) for value in scene.orbit_velocity), .6)
        self.assertEqual(done["reactor"], 1.)

    def test_three_preview_phrases_respect_code_link_quote_and_unknown_exclusions(self):
        scene = ReactorScene()
        for phrase, family in zip(presence_gpu.PREVIEWS, ("smile", "affection", "laughter")):
            with self.subTest(phrase=phrase):
                self.assertTrue(scene.preview_expression(phrase, 960, 640, now=1))
                self.assertEqual(scene.semantic.family, family)
                scene.semantic.cancel()
        for text in ("`😊`", "```python\nprint('❤️')\n```", "[😊](https://example.test)",
                     '"😊"', "regex 😊", "🧪", "sans expression"):
            with self.subTest(text=text):
                self.assertFalse(scene.preview_expression(text, 960, 640, now=2))
                self.assertFalse(scene.semantic.active)


class WavAndCaptureTests(unittest.TestCase):
    def test_pcm16_stereo_averages_channels_uses_file_rate_and_returns_silence_at_eof(self):
        with tempfile.TemporaryDirectory() as temporary:
            for rate in (8000, 16000, 44100):
                with self.subTest(rate=rate):
                    path = Path(temporary) / f"stereo-{rate}.wav"
                    offset, count = int(rate * .125), int(rate * .032)
                    samples = [16384, -16384] * offset + [16384, 0] * count
                    write_wav(path, samples, channels=2, rate=rate)
                    reader = WavInput(path)
                    try:
                        self.assertEqual(reader.signal(0)["rms"], 0)
                        active = reader.signal(.125)
                        self.assertAlmostEqual(active["rms"], .25)
                        self.assertTrue(active["wave"])
                        self.assertTrue(all(value == .25 for value in active["wave"]))
                        ended = reader.signal(1)
                        self.assertEqual(ended["rms"], 0)
                        self.assertTrue(all(value == 0 for value in ended["wave"]))
                    finally:
                        reader.close()

    def test_recorded_pcm_reaches_background_spectrum_then_scene_and_worker_stops(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "recorded-test-tone.wav"
            samples = [int(12000 * math.sin(math.tau * 900 * index / 16000)) for index in range(16000)]
            write_wav(path, samples, rate=16000)
            reader = WavInput(path)
            try:
                reader.signal(0.)
                deadline = time.monotonic() + 2.
                while reader.spectrum.analysis_count < 1 and time.monotonic() < deadline:
                    time.sleep(.005)
                signal = reader.signal(.01)
                self.assertGreater(signal["bands"][1], .15)
                self.assertLess(signal["bands"][0], signal["bands"][1] / 10)
                self.assertEqual(signal["spectrum_error"], "")
                scene = ReactorScene()
                scene.update_state("jarvis_speaking", now=0.)
                scene.update_audio(signal, now=.01)
                self.assertGreater(scene.snapshot(960, 640, .05)["audio_bands"][1], 0.)
                ended = reader.signal(2.)
                generation = reader.generation
                self.assertEqual(ended["bands"], (0., 0., 0.))
                reader.signal(3.)
                self.assertEqual(reader.generation, generation)
            finally:
                reader.close()
            self.assertFalse(reader.spectrum.alive)
            self.assertEqual(reader.spectrum.pending_count, 0)

    def test_interruption_suspends_recorded_pcm_until_explicit_resume(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "recorded.wav"
            write_wav(path, [8192] * 16000, rate=16000)
            reader = WavInput(path)
            try:
                self.assertGreater(reader.signal(0.)["rms"], 0.)
                position = reader.reader.tell()
                reader.suspend()
                generation = reader.generation
                for now in (.1, .2, .3):
                    paused = reader.signal(now)
                    self.assertEqual(paused["rms"], 0.)
                    self.assertEqual(paused["bands"], (0., 0., 0.))
                    self.assertEqual(reader.reader.tell(), position)
                    self.assertEqual(reader.spectrum.pending_count, 0)
                reader.resume()
                self.assertFalse(reader.paused)
                self.assertGreater(reader.generation, generation)
                self.assertGreater(reader.signal(.4)["rms"], 0.)
                self.assertGreater(reader.reader.tell(), position)
            finally:
                reader.close()

    def test_invalid_wav_formats_and_rates_close_the_reader_and_malformed_wav_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "invalid.wav"
            for channels, sample_width, rate in ((1, 1, 8000), (3, 2, 8000), (1, 2, 192001)):
                with self.subTest(channels=channels, sample_width=sample_width, rate=rate):
                    write_wav(path, [0] * (channels * 8), channels=channels,
                              rate=rate, sample_width=sample_width)
                    opened = wave.open(str(path), "rb")
                    with patch.object(presence_gpu.wave, "open", return_value=opened), \
                            patch.object(opened, "close", wraps=opened.close) as close:
                        with self.assertRaises(ValueError):
                            WavInput(path)
                        close.assert_called_once()
                    self.assertIsNone(opened._file)
            path.write_bytes(b"not a WAV file")
            with self.assertRaises((wave.Error, EOFError)):
                WavInput(path)

    def test_png_contains_valid_chunks_and_flips_bottom_up_framebuffer_rows(self):
        bottom = bytes((255, 0, 0, 0, 255, 0))
        top = bytes((0, 0, 255, 255, 255, 255))
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "capture.png"
            save_png(path, (2, 2), bottom + top)
            data = path.read_bytes()
        self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")
        chunks, cursor = [], 8
        while cursor < len(data):
            length = struct.unpack("!I", data[cursor:cursor + 4])[0]
            kind = data[cursor + 4:cursor + 8]
            payload = data[cursor + 8:cursor + 8 + length]
            crc = struct.unpack("!I", data[cursor + 8 + length:cursor + 12 + length])[0]
            self.assertEqual(crc, zlib.crc32(kind + payload) & 0xffffffff)
            chunks.append((kind, payload))
            cursor += length + 12
        self.assertEqual(cursor, len(data))
        self.assertEqual([kind for kind, payload in chunks], [b"IHDR", b"tEXt", b"IDAT", b"IEND"])
        self.assertEqual(struct.unpack("!2I5B", chunks[0][1]), (2, 2, 8, 2, 0, 0, 0))
        self.assertEqual(zlib.decompress(chunks[2][1]), b"\0" + top + b"\0" + bottom)
        self.assertIn(b"Offline prototype", chunks[1][1])

    def test_png_rejects_mismatched_rgb_without_creating_output_and_preserves_existing_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "capture.png"
            with self.assertRaises(ValueError):
                save_png(path, (2, 2), b"short")
            self.assertFalse(path.exists())
            path.write_bytes(b"existing capture")
            with self.assertRaises(FileExistsError):
                save_png(path, (1, 1), b"\0\0\0")
            self.assertEqual(path.read_bytes(), b"existing capture")


class PrototypeCliTests(unittest.TestCase):
    def test_cli_accepts_documented_edges_and_headless_probe_without_a_duration(self):
        args = parse_args(["--headless", "--probe", "--width", "240", "--height", "180"])
        self.assertEqual((args.width, args.height, args.seconds), (240, 180, 0))
        self.assertEqual(args.state, "idle")
        self.assertEqual(args.quality, "balanced")
        eco = parse_args(["--quality", "eco", "--idle-line"])
        self.assertEqual(eco.quality, "eco")
        self.assertTrue(eco.idle_line)
        maximum = parse_args(["--seconds", "3600", "--width", "7680", "--height", "4320"])
        self.assertEqual((maximum.width, maximum.height, maximum.seconds), (7680, 4320, 3600))

    def test_cli_rejects_nonfinite_out_of_bounds_and_unbounded_headless_runs(self):
        cases = (["--seconds", value] for value in ("-1", "nan", "inf", "3600.01"))
        cases = list(cases) + [["--width", value] for value in ("239", "7681")]
        cases += [["--height", value] for value in ("179", "4321")]
        cases += [["--headless"], ["--headless", "--seconds", "0"], ["--quality", "ultra"]]
        for argv in cases:
            with self.subTest(argv=argv), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                parse_args(argv)
            self.assertEqual(error.exception.code, 2)

    def test_cli_output_validation_preserves_existing_files_and_rejects_collisions(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            existing = root / "existing"
            existing.write_bytes(b"keep this output")
            collision = root / "new"
            cases = ([flag, str(existing)] for flag in ("--report", "--capture"))
            cases = list(cases) + [["--report", str(collision), "--capture", str(collision)],
                                   ["--capture", str(root / "missing" / "capture.png")]]
            for argv in cases:
                with self.subTest(argv=argv), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                    parse_args(argv)
            self.assertEqual(existing.read_bytes(), b"keep this output")
            self.assertFalse(collision.exists())

    def test_import_and_offline_scene_need_no_gpu_packages_window_or_application_data(self):
        repository = Path(__file__).resolve().parents[1]
        code = "\n".join((
            "import os, sys, tkinter",
            f"sys.path.insert(0, {str(repository)!r})",
            "def forbidden(*args, **kwargs): raise AssertionError('a GUI was opened')",
            "tkinter.Tk = forbidden",
            "from jarvis.presence_gpu import ReactorScene, parse_args",
            "parse_args(['--headless', '--probe'])",
            "assert ReactorScene().snapshot(240, 180, now=1)['rms'] == 0",
            "assert not any(name in sys.modules for name in ('moderngl', 'glcontext', 'glfw', 'jarvis.ui', 'jarvis.storage'))",
            "assert os.listdir('.') == []",
        ))
        with tempfile.TemporaryDirectory() as temporary:
            subprocess.run([sys.executable, "-B", "-c", code], cwd=temporary, check=True,
                           capture_output=True, text=True)

    def test_gpu_failures_distinguish_dependencies_unavailable_context_and_unexpected_errors(self):
        real_import = builtins.__import__

        def without_gpu(name, *args, **kwargs):
            if name == "moderngl":
                raise ModuleNotFoundError("No module named 'moderngl'")
            return real_import(name, *args, **kwargs)

        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "unsupported.json"
            args = parse_args(["--headless", "--probe", "--report", str(path)])
            with patch("builtins.__import__", side_effect=without_gpu):
                report, code = presence_gpu.run(args)
            self.assertEqual(code, 2)
            self.assertEqual(report["status"], "error")
            self.assertEqual(report["unavailable_reason"], "dependencies")
            self.assertIn("requirements-gpu.txt", report["error"])
            self.assertIn("Canvas", report["error"])
            self.assertFalse(report["application_integrated"])
            self.assertTrue(report["offline_preview"])
            self.assertEqual(report["shutdown"], "complete")
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), report)
            self.assertNotIn("frames", report)
            self.assertNotIn("unmeasured_workloads", report)
            self.assertEqual(sorted(item.name for item in Path(temporary).iterdir()), ["unsupported.json"])
        for error, expected in ((GpuUnavailable("OpenGL/EGL indisponible", "context"), "unsupported"),
                                (RuntimeError("unexpected initialization failure"), "error")):
            with self.subTest(error=error), patch.object(presence_gpu, "_open_context", side_effect=error):
                report, code = presence_gpu.run(parse_args(["--headless", "--probe"]))
                self.assertEqual(code, 2)
                self.assertEqual(report["status"], expected)
                self.assertIn(str(error), report["error"])
                self.assertEqual(report["shutdown"], "complete")

    def test_renderer_metadata_distinguishes_software_hardware_reported_and_unknown(self):
        cases = (("Mesa", "llvmpipe (LLVM 15)", "software"),
                 ("Intel", "Software Rasterizer", "software"),
                 ("Google", "ANGLE SwiftShader", "software"),
                 ("Microsoft", "Microsoft Basic Render Driver", "software"),
                 ("NVIDIA Corporation", "NVIDIA GeForce RTX 4090", "hardware_reported"),
                 ("Intel", "Intel UHD Graphics", "hardware_reported"),
                 ("AMD", "Radeon", "hardware_reported"),
                 ("Mesa", "unrecognized device", "unknown"))
        for vendor, name, acceleration in cases:
            with self.subTest(renderer=name):
                metadata = context_info(SimpleNamespace(info={"GL_VENDOR": vendor,
                    "GL_RENDERER": name, "GL_VERSION": "3.3 fixture"}))
                self.assertEqual(metadata["acceleration"], acceleration)
                self.assertEqual(metadata["renderer"], name)
                self.assertEqual(metadata["hardware_validation"], "pending")
                self.assertEqual(metadata["required_version"], "OpenGL 3.3")

    def test_hardware_policy_rejects_software_and_unknown_unless_explicit_developer_mode(self):
        for vendor, name in (("Mesa", "llvmpipe"), ("Fixture", "Unknown renderer")):
            for argv in ([], ["--headless", "--probe", "--require-hardware"],
                         ["--require-hardware", "--allow-software"]):
                with self.subTest(renderer=name, argv=argv):
                    context = SimpleNamespace(info={"GL_VENDOR": vendor, "GL_RENDERER": name}, release=Mock())
                    with patch.object(presence_gpu, "_open_context", return_value=(context, None, None)), \
                            patch("jarvis.gpu_renderer.GpuRenderer") as renderer:
                        report, code = presence_gpu.run(parse_args(argv))
                    self.assertEqual(code, 2)
                    self.assertEqual(report["status"], "unsupported")
                    self.assertEqual(report["unavailable_reason"], "hardware")
                    self.assertIn(name, report["error"])
                    self.assertEqual(report["shutdown"], "complete")
                    self.assertEqual(report["renderer"]["hardware_validation"], "pending")
                    renderer.assert_not_called()
                    context.release.assert_called_once()
        for argv in (["--headless", "--probe"], ["--probe"], ["--allow-software"]):
            with self.subTest(developer_argv=argv):
                context = SimpleNamespace(info={"GL_VENDOR": "Mesa", "GL_RENDERER": "llvmpipe"}, release=Mock())
                with patch.object(presence_gpu, "_open_context", return_value=(context, None, None)), \
                        patch("jarvis.gpu_renderer.GpuRenderer", side_effect=RuntimeError("stop after acceptance")) as renderer:
                    report, code = presence_gpu.run(parse_args(argv))
                renderer.assert_called_once()
                self.assertEqual(code, 2)
                self.assertEqual(report["status"], "error")
                self.assertIn("stop after acceptance", report["error"])
                context.release.assert_called_once()

    def test_cleanup_failures_return_nonzero_persist_report_and_release_following_resources(self):
        with tempfile.TemporaryDirectory() as temporary:
            for probe in (True, False):
                with self.subTest(probe=probe):
                    path = Path(temporary) / f"cleanup-{probe}.json"
                    argv = ["--report", str(path)] + (["--probe"] if probe else [])
                    context = SimpleNamespace(info={"GL_VENDOR": "NVIDIA", "GL_RENDERER": "fixture"}, error="GL_NO_ERROR",
                                              finish=Mock(), release=Mock())
                    window, glfw = object(), Mock()
                    glfw.get_framebuffer_size.return_value = (240, 180)
                    glfw.window_should_close.return_value = True
                    glfw.destroy_window.side_effect = RuntimeError("window shutdown failure")
                    renderer = SimpleNamespace(allocation_bytes=1024, size=(240, 180), quality="balanced",
                        render=Mock(), shutdown=Mock(side_effect=RuntimeError("renderer shutdown failure")))
                    constructor = Mock(return_value=renderer)
                    process = SimpleNamespace(start=Mock(), stop=Mock(side_effect=[None,
                        RuntimeError("process sampler shutdown failure")]))
                    gpu = SimpleNamespace(start=Mock(), stop=Mock(side_effect=[None,
                        RuntimeError("GPU sampler shutdown failure")]))
                    with patch.object(presence_gpu, "_open_context", return_value=(context, glfw, window)), \
                            patch.dict(sys.modules, {"jarvis.gpu_renderer": SimpleNamespace(GpuRenderer=constructor)}), \
                            patch("jarvis.gpu_benchmark.ProcessSampler", return_value=process), \
                            patch("jarvis.gpu_benchmark.NvidiaSampler", return_value=gpu), \
                            patch("jarvis.gpu_benchmark.build_report", return_value={}):
                        report, code = presence_gpu.run(parse_args(argv))
                    self.assertEqual(code, 2)
                    self.assertEqual(report["status"], "error")
                    self.assertEqual(report["shutdown"], "error")
                    self.assertTrue(report["error"])
                    errors = "\n".join(report["cleanup_errors"])
                    self.assertIn("renderer shutdown failure", errors)
                    self.assertIn("window shutdown failure", errors)
                    renderer.shutdown.assert_called_once()
                    context.release.assert_called_once()
                    glfw.destroy_window.assert_called_once_with(window)
                    glfw.terminate.assert_called_once()
                    self.assertEqual(json.loads(path.read_text(encoding="utf-8")), json.loads(json.dumps(report)))
                    if probe:
                        self.assertTrue(report["shader_compile_and_frame"])
                        renderer.render.assert_called_once()
                        context.finish.assert_called_once()
                        process.start.assert_not_called()
                    else:
                        self.assertIn("process sampler shutdown failure", errors)
                        self.assertIn("GPU sampler shutdown failure", errors)
                        self.assertEqual(process.stop.call_count, 2)
                        self.assertEqual(gpu.stop.call_count, 2)


if __name__ == "__main__":
    unittest.main()
