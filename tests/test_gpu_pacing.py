"""Real-time visual clocks do not synthesize audio or conversation progress."""
import copy
import math
import unittest

from jarvis.gpu_pacing import MAX_ANIMATION_AGE, RenderGovernor, advance_frame, next_deadline, native_window_size


class PresentationClockTests(unittest.TestCase):
    def test_observed_dpi_ratios_cover_windows_mac_and_native_without_double_scaling(self):
        # Same 420×300 logical Mini, different GLFW coordinate conventions.
        self.assertEqual(native_window_size((420, 300), (1440, 960), (1440, 960), (1.5, 1.5)), (630, 450))
        self.assertEqual(native_window_size((420, 300), (960, 640), (1920, 1280), (2., 2.)), (420, 300))
        self.assertEqual(native_window_size((420, 300), (960, 640), (960, 640), (1., 1.)), (420, 300))

    def packet(self):
        return {"frame_at": 10., "animation": {"active": True,
            "orbit_velocity": (0., .2, -.2), "orbit_target": (1., -.5, .3), "orbit_tau": .45,
            "core_target": .92, "core_tau": .3},
            "frame": {"time_s": 4., "orbit_phase": (1., 2., 3.), "core_scale": 1.,
                      "rms": .1, "audio_bands": (.2, .3, .4), "reduced_motion": False}}

    def test_each_render_evaluates_distinct_time_and_exact_orbital_inertia_without_touching_pcm(self):
        packet = self.packet()
        original = copy.deepcopy(packet)
        before, running = advance_frame(packet, packet["frame"], 10.01)
        after, active = advance_frame(packet, packet["frame"], 10.02)
        self.assertTrue(running and active)
        self.assertGreater(after["time_s"], before["time_s"])
        for index, (speed, goal) in enumerate(zip(packet["animation"]["orbit_velocity"], packet["animation"]["orbit_target"])):
            expected = packet["frame"]["orbit_phase"][index]+goal*.02+(speed-goal)*.45*(1-math.exp(-.02/.45))
            self.assertAlmostEqual(after["orbit_phase"][index], expected)
        self.assertLess(after["core_scale"], before["core_scale"])
        self.assertEqual(after["rms"], packet["frame"]["rms"])
        self.assertEqual(after["audio_bands"], packet["frame"]["audio_bands"])
        self.assertEqual(packet, original)

    def test_snapshot_clock_is_independent_of_number_of_render_frames(self):
        packet = self.packet()
        # Asking for all intermediate 60Hz frames cannot change the final pose.
        expected, _ = advance_frame(packet, packet["frame"], 10.3)
        for index in range(19):
            advance_frame(packet, packet["frame"], 10+index/60)
        actual, _ = advance_frame(packet, packet["frame"], 10.3)
        self.assertEqual(actual, expected)

    def test_stale_parent_freezes_within_bound_and_reduced_or_idle_clocks_do_not_animate(self):
        packet = self.packet()
        stalled, running = advance_frame(packet, packet["frame"], 10+MAX_ANIMATION_AGE+1)
        self.assertFalse(running)
        self.assertAlmostEqual(stalled["time_s"], 4+MAX_ANIMATION_AGE)
        for change in ({"animation": {"active": False}}, {"animation": {}},
                       {"frame": {**packet["frame"], "reduced_motion": True}}):
            source = {**packet, **change}
            actual, active = advance_frame(source, source["frame"], 10.1)
            self.assertFalse(active)
            self.assertEqual(actual, source["frame"])

    def test_semantic_envelope_uses_authoritative_family_and_deadline(self):
        packet = self.packet()
        packet["expression_until"] = 10.+.36*2+.65
        packet["frame"]["surface_family"] = "smile"
        amounts = []
        for elapsed in (.0, .18, .36, 1.01, 1.19, 1.37):
            packet["frame_at"] = 10.+elapsed
            frame, _ = advance_frame(packet, packet["frame"], 10.+elapsed)
            amounts.append(frame["surface_amount"])
            self.assertEqual(frame["surface_family"], "smile")
        for actual, expected in zip(amounts, (0., .5, 1., 1., .5, 0.)):
            self.assertAlmostEqual(actual, expected)

    def test_absolute_deadlines_include_render_and_vsync_duration_once(self):
        period = 1/60
        self.assertAlmostEqual(next_deadline(0., 0., period), period)
        # The next deadline is computed at draw start. A swap returning at
        # 16.8ms must not impose an extra full interval after that return.
        deadline = next_deadline(0., 0., period)
        self.assertLess(deadline, .0168)
        self.assertAlmostEqual(next_deadline(deadline, .017, period), 2*period)
        self.assertGreater(next_deadline(deadline, .2, period), .2)


class RenderGovernorTests(unittest.TestCase):
    def test_sustained_overload_degrades_gradually_then_restores_after_long_stable_recovery(self):
        policy = RenderGovernor()
        self.assertEqual(policy.observe(.03, 0., 60), 0)
        self.assertEqual(policy.observe(.03, 1.99, 60), 0)
        self.assertEqual(policy.observe(.03, 2.01, 60), 1)
        self.assertEqual(policy.observe(.03, 2.1, 60), 1)
        self.assertEqual(policy.observe(.03, 4.2, 60), 2)
        self.assertEqual(policy.observe(.003, 5., 60), 2)
        self.assertEqual(policy.observe(.003, 12.9, 60), 2)
        self.assertEqual(policy.observe(.003, 13.1, 60), 1)
        self.assertEqual(policy.observe(.003, 13.2, 60), 1)
        self.assertEqual(policy.observe(.003, 21.3, 60), 0)

    def test_isolated_long_frame_never_degrades_and_hidden_time_is_not_recovery(self):
        policy = RenderGovernor(level=2)
        policy.observe(.03, 0., 60)
        policy.observe(.003, .1, 60)
        policy.suspend()
        self.assertEqual(policy.observe(.003, 100., 60), 2)
        self.assertEqual(policy.observe(.003, 108.1, 60), 1)
        for bad in ((math.nan, 0., 60), (.01, math.inf, 60), (.01, 1., 0)):
            with self.assertRaises(ValueError):
                policy.observe(*bad)


if __name__ == "__main__":
    unittest.main()
