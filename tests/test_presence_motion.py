"""Pure timing/geometry policy tests, without models, microphones or Tk."""
import math
import unittest

from jarvis.presence_motion import (MICRO_COOLDOWN, MICRO_DURATION, MICRO_LABELS,
                                    MicroExpression)


class MicroExpressionTests(unittest.TestCase):
    def test_idle_unknown_and_invalid_labels_never_animate(self):
        pulse = MicroExpression()
        for mood in (None, [], {}, "", "neutralité", "phrase contenant joie"):
            self.assertFalse(pulse.trigger(mood, 0.))
        for now in (None, True, "0", math.nan, math.inf, -math.inf, 10 ** 1000):
            self.assertFalse(pulse.trigger("surprise", now))
            self.assertFalse(pulse.active(now))
            self.assertEqual(pulse.factors(now), (1., 1., 1.))
        self.assertIsNone(pulse.family)
        self.assertEqual(pulse.factors(0.), (1., 1., 1.))

    def test_each_preview_is_distinct_bounded_and_returns_exactly_to_identity(self):
        snapshots = []
        for family in MICRO_LABELS:
            with self.subTest(family=family):
                pulse = MicroExpression()
                self.assertTrue(pulse.trigger(family, 10.))
                self.assertEqual(pulse.factors(10.), (1., 1., 1.))
                self.assertFalse(pulse.active(9.))
                values = [pulse.factors(10. + MICRO_DURATION * index / 1000)
                          for index in range(1001)]
                self.assertTrue(all(math.isfinite(value) and .92 <= value <= 1.08
                                    for triple in values for value in triple))
                snapshots.append(values[250])
                self.assertTrue(pulse.active(10. + MICRO_DURATION / 2))
                self.assertFalse(pulse.active(10. + MICRO_DURATION + .001))
                self.assertEqual(pulse.factors(10. + MICRO_DURATION + .001), (1., 1., 1.))
                self.assertEqual(pulse.factors(1000.), (1., 1., 1.))
        self.assertEqual(len(set(snapshots)), 4)

    def test_surprise_contracts_then_expands_and_transitions_have_no_step(self):
        pulse = MicroExpression()
        pulse.trigger("surprise", 0.)
        self.assertLess(pulse.factors(MICRO_DURATION * .25)[0], 1.)
        self.assertGreater(pulse.factors(MICRO_DURATION * .75)[0], 1.)
        for family in MICRO_LABELS:
            pulse = MicroExpression()
            pulse.trigger(family, 0.)
            epsilon = 1e-5
            for endpoint in (0., MICRO_DURATION):
                before = pulse.factors(endpoint - epsilon)
                after = pulse.factors(endpoint + epsilon)
                self.assertLess(max(abs(a-b) for a, b in zip(before, after)), 1e-8)

    def test_mood_mapping_uses_existing_field_labels_without_per_word_retrigger(self):
        pulse = MicroExpression()
        self.assertTrue(pulse.trigger("joie", 0.))
        self.assertEqual(pulse.family, "enthusiasm")
        for now, mood in ((.1, "joie"), (1., "espoir"), (100., "volonté")):
            self.assertFalse(pulse.trigger(mood, now))
        self.assertTrue(pulse.trigger("compassion", 101.))
        self.assertEqual(pulse.family, "comfort")
        self.assertFalse(pulse.trigger("apaisement", 105.))
        self.assertTrue(pulse.trigger("deuil", 105.))
        self.assertEqual(pulse.family, "gravity")
        self.assertFalse(pulse.trigger("peur", 110.))
        self.assertFalse(pulse.trigger("colère", 111.))

    def test_cooldown_blocks_different_labels_and_backward_time(self):
        pulse = MicroExpression()
        pulse.trigger("surprise", 10.)
        self.assertFalse(pulse.trigger("gravité", 9.))
        self.assertFalse(pulse.trigger("gravité", 10. + MICRO_COOLDOWN - .001))
        self.assertEqual(pulse.family, "surprise")
        self.assertTrue(pulse.trigger("gravité", 10. + MICRO_COOLDOWN))
        self.assertEqual(pulse.family, "gravity")

    def test_interrupt_cancels_immediately_but_does_not_reset_cooldown(self):
        pulse = MicroExpression()
        pulse.trigger("enthousiasme", 0.)
        self.assertNotEqual(pulse.factors(.5), (1., 1., 1.))
        pulse.cancel()
        self.assertFalse(pulse.active(.5))
        self.assertEqual(pulse.factors(.5), (1., 1., 1.))
        self.assertIsNone(pulse.family)
        self.assertFalse(pulse.trigger("enthousiasme", .6))
        self.assertTrue(pulse.trigger("enthousiasme", MICRO_COOLDOWN))


if __name__ == "__main__":
    unittest.main()
