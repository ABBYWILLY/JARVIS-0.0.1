"""Deterministic geometry tests: no model, audio device, Tk or network needed."""
from dataclasses import FrozenInstanceError
import math
import unittest

from jarvis.morphing import (CATALOGUE, ENTER_SECONDS, FAMILIES, HOLD_SECONDS,
                             INTENSITIES, POINT_COUNT, RETURN_SECONDS,
                             MorphController)


def line(width=1000, height=700):
    return tuple((width * (.08 + .84 * i / (POINT_COUNT - 1)), height / 2)
                 for i in range(POINT_COUNT))


def extent(points):
    xs, ys = zip(*points)
    return max(xs) - min(xs), max(ys) - min(ys)


class MorphCatalogueTests(unittest.TestCase):
    def test_eight_real_distinct_symbols_have_closed_contours_and_bounded_details(self):
        self.assertEqual(set(CATALOGUE), set(FAMILIES))
        self.assertEqual(len(FAMILIES), 8)
        self.assertEqual(len({(symbol.contour, symbol.details) for symbol in CATALOGUE.values()}), 8)
        for family, symbol in CATALOGUE.items():
            with self.subTest(family=family):
                self.assertEqual(len(symbol.contour), POINT_COUNT)
                self.assertEqual(symbol.contour[0], symbol.contour[-1])
                width, height = extent(symbol.contour)
                self.assertGreater(width, 1)
                self.assertGreater(height, 1)
                self.assertLessEqual(len(symbol.details), 8)
                if family != "affection":
                    self.assertGreaterEqual(len(symbol.details), 3)
                for path in (symbol.contour, *symbol.details):
                    self.assertTrue(all(math.isfinite(value) and -1.2 <= value <= 1.2
                                        for point in path for value in point))
                self.assertTrue(all(3 <= len(path) <= 25 for path in symbol.details))

    def test_catalogue_is_immutable_and_initialized_once(self):
        original = CATALOGUE["smile"]
        with self.assertRaises(TypeError):
            CATALOGUE["smile"] = CATALOGUE["sadness"]
        with self.assertRaises(FrozenInstanceError):
            original.details = ()
        first, second = MorphController(), MorphController()
        first.trigger("smile", 0)
        second.trigger("smile", 0)
        first.frame(line(), 1000, 700, .5)
        second.frame(line(), 1000, 700, .5)
        self.assertIs(CATALOGUE["smile"], original)

    def test_affection_is_a_heart_outline_not_a_face_placeholder(self):
        heart = CATALOGUE["affection"]
        self.assertNotEqual(heart.contour, CATALOGUE["smile"].contour)
        xs, ys = zip(*heart.contour)
        # The first point is the notch; the bottom cusp is farther down than
        # that notch. This geometric distinction survives monochrome rendering.
        self.assertGreater(min(ys), -1.1)
        self.assertLess(heart.contour[0][1], .1)
        self.assertGreater(max(ys) - heart.contour[0][1], 1)
        self.assertAlmostEqual(min(xs), -max(xs))


class MorphControllerTests(unittest.TestCase):
    def setUp(self):
        self.controller = MorphController()
        self.normal = line()

    def test_inactive_and_unknown_expressions_do_not_change_geometry_or_schedule(self):
        self.assertFalse(self.controller.active)
        self.assertIsNone(self.controller.family)
        self.assertIsNone(self.controller.frame(self.normal, 1000, 700, 0))
        self.assertIsNone(self.controller.next_delay_ms(0, 33))
        for unknown in ("rocket", "😊", "", None, []):
            self.assertFalse(self.controller.trigger(unknown, 0))
        self.assertFalse(self.controller.active)

    def test_all_families_complete_entry_hold_return_without_a_second_main_contour(self):
        total = ENTER_SECONDS + HOLD_SECONDS + RETURN_SECONDS
        for family in FAMILIES:
            with self.subTest(family=family):
                self.assertTrue(self.controller.trigger(family, 10))
                self.assertTrue(self.controller.active)
                self.assertEqual(self.controller.family, family)
                start = self.controller.frame(self.normal, 1000, 700, 10)
                self.assertEqual(start.contour, self.normal)
                self.assertEqual(start.phase, "enter")
                self.assertEqual(start.details, ())
                hold = self.controller.frame(self.normal, 1000, 700, 10 + ENTER_SECONDS + .1)
                self.assertEqual(hold.phase, "hold")
                self.assertEqual(len(hold.contour), POINT_COUNT)
                self.assertNotEqual(hold.contour, self.normal)
                self.assertEqual(hold.opacity, 1)
                self.assertEqual(hold.detail_opacity, 1)
                returning = self.controller.frame(self.normal, 1000, 700, 10 + total - .03)
                self.assertEqual(returning.phase, "return")
                self.assertIsNone(self.controller.frame(self.normal, 1000, 700, 10 + total + .001))
                self.assertFalse(self.controller.active)
                self.assertIsNone(self.controller.next_delay_ms(10 + total, 33))

    def test_incompatible_line_and_heart_pass_through_the_same_center(self):
        self.controller.trigger("affection", 0)
        middle = ENTER_SECONDS / 2
        collapsed = self.controller.frame(self.normal, 1000, 700, middle)
        self.assertTrue(all(point == (500, 350) for point in collapsed.contour))
        self.assertEqual(collapsed.details, ())
        before = self.controller.frame(self.normal, 1000, 700, middle - .00001)
        after = self.controller.frame(self.normal, 1000, 700, middle + .00001)
        self.assertLess(max(math.dist(a, b) for a, b in zip(before.contour, after.contour)), .001)

    def test_details_fade_in_only_after_the_main_symbol_starts_expanding(self):
        self.controller.trigger("smile", 0)
        early = self.controller.frame(self.normal, 1000, 700, ENTER_SECONDS * .25)
        growing = self.controller.frame(self.normal, 1000, 700, ENTER_SECONDS * .75)
        stable = self.controller.frame(self.normal, 1000, 700, ENTER_SECONDS + .1)
        self.assertEqual(early.detail_opacity, 0)
        self.assertGreater(growing.detail_opacity, 0)
        self.assertLess(growing.detail_opacity, stable.detail_opacity)
        fading = self.controller.frame(self.normal, 1000, 700, ENTER_SECONDS + HOLD_SECONDS + .09)
        self.assertGreater(fading.detail_opacity, 0)
        self.assertLess(fading.detail_opacity, 1)

    def test_return_uses_current_real_geometry_and_reaches_it_continuously(self):
        self.controller.trigger("smile", 0, origin=self.normal, viewport=(1000, 700))
        current = tuple((x, y + 30 * math.sin(i / 8)) for i, (x, y) in enumerate(self.normal))
        end = ENTER_SECONDS + HOLD_SECONDS + RETURN_SECONDS
        final = self.controller.frame(current, 1000, 700, end - .00001)
        self.assertLess(max(math.dist(a, b) for a, b in zip(final.contour, current)), .001)
        self.assertEqual(final.details, ())
        self.assertIsNone(self.controller.frame(current, 1000, 700, end))

    def test_entry_preserves_the_exact_visible_origin_after_the_model_changes_state(self):
        origin = tuple((500 + 90 * math.cos(math.tau * i / (POINT_COUNT - 1)),
                        350 + 90 * math.sin(math.tau * i / (POINT_COUNT - 1)))
                       for i in range(POINT_COUNT))
        mutable = [list(point) for point in origin]
        self.controller.trigger("affection", 0, origin=mutable, viewport=(1000, 700))
        mutable[0][0] = 9999
        first = self.controller.frame(self.normal, 1000, 700, 0)
        self.assertEqual(first.contour, origin)
        moving_model = tuple((x, y + 90) for x, y in self.normal)
        before = self.controller.frame(self.normal, 1000, 700, .09)
        after = self.controller.frame(moving_model, 1000, 700, .09)
        self.assertEqual(before.contour, after.contour)
        self.assertNotEqual(before.contour, self.normal)

    def test_frozen_origin_resizes_about_the_new_center_without_distorting_proportions(self):
        origin = tuple((500 + 90 * math.cos(math.tau * i / (POINT_COUNT - 1)),
                        350 + 90 * math.sin(math.tau * i / (POINT_COUNT - 1)))
                       for i in range(POINT_COUNT))
        self.controller.trigger("smile", 0, origin=origin, viewport=(1000, 700))
        frame = self.controller.frame(line(800, 600), 800, 600, 0)
        xs, ys = zip(*frame.contour)
        self.assertAlmostEqual((min(xs) + max(xs)) / 2, 400)
        self.assertAlmostEqual((min(ys) + max(ys)) / 2, 300)
        self.assertAlmostEqual(max(xs) - min(xs), 180 * 600 / 700)
        self.assertAlmostEqual(max(ys) - min(ys), 180 * 600 / 700)
        self.assertIs(frame.contour, self.controller._origin_cache)
        same = self.controller.frame(line(800, 600), 800, 600, 0)
        self.assertIs(same.contour, frame.contour)

    def test_cancellation_and_next_trigger_release_the_frozen_origin(self):
        self.controller.trigger("smile", 0, origin=self.normal, viewport=(1000, 700))
        self.controller.frame(line(800, 600), 800, 600, .1)
        self.controller.cancel()
        self.assertIsNone(self.controller._origin)
        self.assertIsNone(self.controller._origin_normalized)
        self.assertIsNone(self.controller._origin_cache)
        self.controller.trigger("affection", 1)
        changed = tuple((x, y + 12) for x, y in self.normal)
        self.assertEqual(self.controller.frame(changed, 1000, 700, 1).contour, changed)

    def test_invalid_frozen_origin_is_rejected_before_starting_an_expression(self):
        for origin, viewport in ((self.normal, None), (self.normal[:-1], (1000, 700)),
                                 (self.normal, (1000, 0)), (self.normal, (float("nan"), 700)),
                                 (((0, 1, 2),) * POINT_COUNT, (1000, 700))):
            with self.subTest(viewport=viewport), self.assertRaises(ValueError):
                self.controller.trigger("smile", 0, origin=origin, viewport=viewport)
            self.assertFalse(self.controller.active)

    def test_reduced_motion_shows_a_static_recognizable_symbol_then_returns(self):
        self.controller.trigger("wink", 0, reduced_motion=True)
        first = self.controller.frame(self.normal, 1000, 700, 0)
        last = self.controller.frame(self.normal, 1000, 700, HOLD_SECONDS - .01)
        self.assertEqual(first, last)
        self.assertEqual(first.phase, "hold")
        self.assertIs(first.contour, last.contour)
        self.assertEqual(self.controller.next_delay_ms(.1, 16), 550)
        self.assertIsNone(self.controller.frame(self.normal, 1000, 700, HOLD_SECONDS))

    def test_holding_keeps_cached_geometry_and_only_schedules_the_phase_end(self):
        self.controller.trigger("laughter", 0)
        first = self.controller.frame(self.normal, 1000, 700, ENTER_SECONDS)
        later = self.controller.frame(self.normal, 1000, 700, ENTER_SECONDS + .2)
        self.assertIs(first.contour, later.contour)
        self.assertIs(first.details, later.details)
        self.assertEqual(self.controller.next_delay_ms(ENTER_SECONDS + .2, 16), 450)
        self.assertEqual(self.controller.next_delay_ms(.1, 33), 33)
        self.assertEqual(self.controller.next_delay_ms(ENTER_SECONDS + HOLD_SECONDS + .1, 33), 33)

    def test_geometry_cache_is_bounded_across_resize_and_uses_new_viewport_center(self):
        self.controller.trigger("affection", 0)
        for width, height in ((1000, 700), (620, 440), (1400, 900), (700, 900)):
            with self.subTest(width=width, height=height):
                frame = self.controller.frame(line(width, height), width, height, .5)
                xs, ys = zip(*frame.contour)
                self.assertAlmostEqual((min(xs) + max(xs)) / 2, width / 2)
                self.assertAlmostEqual((min(ys) + max(ys)) / 2, height / 2)
                self.assertLessEqual(max(xs) - min(xs), min(width, height) * .36)
                self.assertIs(frame.contour, self.controller._cache.contour)
                self.assertEqual(self.controller._cache_key[-2:], (width, height))

    def test_intensity_scales_the_same_family_without_changing_detail_count(self):
        widths, counts = [], []
        for intensity in INTENSITIES:
            self.controller.trigger("smile", 0, intensity=intensity)
            frame = self.controller.frame(self.normal, 1000, 700, .5)
            widths.append(extent(frame.contour)[0])
            counts.append(len(frame.details))
        self.assertLess(widths[0], widths[1])
        self.assertLess(widths[1], widths[2])
        self.assertEqual(len(set(counts)), 1)

    def test_profiles_reduce_optional_details_but_keep_main_outline(self):
        self.controller.trigger("laughter", 0)
        frames = {profile: self.controller.frame(self.normal, 1000, 700, .5, profile=profile)
                  for profile in ("eco", "balanced", "cinematic")}
        self.assertEqual(len(frames["eco"].details), 4)
        self.assertEqual(len(frames["balanced"].details), 6)
        self.assertEqual(frames["eco"].contour, frames["cinematic"].contour)
        self.assertEqual(frames["eco"].details, frames["cinematic"].details[:4])

    def test_cancellation_is_immediate_and_cannot_resurrect_on_late_frames(self):
        for elapsed in (0, .2, .6, 1.2):
            with self.subTest(elapsed=elapsed):
                self.controller.trigger("anger", 0)
                self.controller.frame(self.normal, 1000, 700, elapsed)
                self.controller.cancel()
                self.assertFalse(self.controller.active)
                self.assertIsNone(self.controller.family)
                self.assertIsNone(self.controller.frame(self.normal, 1000, 700, elapsed + .1))
                self.assertIsNone(self.controller.next_delay_ms(elapsed + .1, 33))
        self.assertTrue(self.controller.trigger("smile", 2))
        self.assertEqual(self.controller.frame(self.normal, 1000, 700, 2).phase, "enter")

    def test_new_trigger_replaces_an_expression_without_a_concurrent_queue(self):
        self.controller.trigger("sadness", 0)
        self.controller.frame(self.normal, 1000, 700, .5)
        self.controller.trigger("affection", .5)
        current = self.controller.frame(self.normal, 1000, 700, .5)
        self.assertEqual(self.controller.family, "affection")
        self.assertEqual(current.contour, self.normal)
        self.assertEqual(current.details, ())

    def test_invalid_configuration_and_nan_do_not_poison_active_geometry(self):
        with self.assertRaises(ValueError):
            self.controller.trigger("smile", 0, intensity="loud")
        with self.assertRaises(ValueError):
            self.controller.trigger("smile", float("nan"))
        self.assertFalse(self.controller.active)
        self.controller.trigger("smile", 0)
        for args in ((self.normal, 0, 700, .5), (self.normal, 1000, 700, float("inf")),
                     (self.normal[:-1], 1000, 700, .5)):
            with self.assertRaises(ValueError):
                self.controller.frame(*args)
        with self.assertRaises(ValueError):
            self.controller.frame(self.normal, 1000, 700, .5, profile="ultra")
        self.assertEqual(self.controller.frame(self.normal, 1000, 700, .5).phase, "hold")


if __name__ == "__main__":
    unittest.main()
