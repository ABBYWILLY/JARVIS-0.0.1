"""Caption preparation and PCM-fraction windows without a display or model."""
from dataclasses import FrozenInstanceError, asdict
import json
import math
import pickle
import unittest
from unittest.mock import patch

from jarvis.captions import CaptionMark, CaptionPlan, CaptionWindow, prepare_caption
from jarvis.richtext import parse_text
from jarvis.spectrum import analyze_passages


def marked(window):
    return [(window.text[mark.start:mark.end], mark.tone) for mark in window.marks]


class CaptionPreparationTests(unittest.TestCase):
    def test_french_contexts_preserve_marks_and_neutral_words(self):
        source = "Je n’ai pas peur, mais j’ai confiance. Je suis pleine d’espoir !"
        plan = prepare_caption(source)
        self.assertEqual(plan.text, source)
        self.assertNotIn("peur", [source[mark.start:mark.end] for mark in plan.marks])
        self.assertTrue(any("confiance" in source[mark.start:mark.end] for mark in plan.marks))
        self.assertTrue(any("espoir" in source[mark.start:mark.end] for mark in plan.marks))
        for mark in plan.marks:
            self.assertEqual(mark.tone, "espoir")
            self.assertNotIn("!", source[mark.start:mark.end])

    def test_quoted_code_negated_and_emoji_only_text_remain_neutral(self):
        sources = ('« Je suis furieuse ! »', '"Je suis furieuse !"',
                   '`Je suis furieuse !`', '```txt\nJe suis furieuse !\n```',
                   "Je ne ressens ni colère ni rage.", "👩🏽‍💻 ❤️ ✨", "... ; !")
        for source in sources:
            with self.subTest(source=source):
                self.assertEqual(prepare_caption(source).marks, ())

    def test_raw_markdown_and_clean_display_keep_their_own_offsets(self):
        source = "👩🏽‍💻 **Je suis furieuse !** `peur`\nJ’ai confiance."
        for text in (source, parse_text(source).text):
            with self.subTest(text=text):
                plan = prepare_caption(text)
                selected = [(text[mark.start:mark.end], mark.tone) for mark in plan.marks]
                self.assertIn(("furieuse", "colère"), selected)
                self.assertIn(("confiance", "espoir"), selected)
                self.assertTrue(all("👩" not in word and "!" not in word for word, _ in selected))
        self.assertNotIn("peur", [source[mark.start:mark.end] for mark in prepare_caption(source).marks])

    def test_contextual_compounds_and_decomposed_accents_keep_exact_spans(self):
        source = "Ça va aller. Je suis avec vous de tout cœur. 👩🏽‍💻 Je suis en colère."
        plan = prepare_caption(source)
        self.assertEqual([(source[mark.start:mark.end], mark.tone) for mark in plan.marks],
                         [("Ça va aller", "apaisement"), ("de tout cœur", "compassion"),
                          ("colère", "colère")])
        for source in ("Ça ne va pas aller.", "Il cite « ça va aller ».", "Le mot confiance n’est pas une émotion exprimée."):
            with self.subTest(source=source):
                self.assertEqual(prepare_caption(source, mode="expression").marks, ())

    def test_classification_happens_once_and_windows_do_no_analysis(self):
        with patch("jarvis.captions.analyze_passages", wraps=analyze_passages) as classify:
            plan = prepare_caption("Je suis furieuse. Puis j’ai confiance.")
        classify.assert_called_once()
        with patch("jarvis.captions.analyze_passages", side_effect=AssertionError("render classified")), \
                patch("jarvis.captions.emotional_spans", side_effect=AssertionError("render searched")), \
                patch("jarvis.captions._WORDS") as words:
            for fraction in (0, 0.01, 0.12, 0.51, 1.0, 0.2, 0.99) * 5:
                plan.window(fraction, measure=len, width=22)
            words.finditer.assert_not_called()

    def test_mode_is_respected_and_invalid_mode_fails(self):
        source = "La colère est une émotion."
        self.assertTrue(prepare_caption(source, mode="thematic").marks)
        self.assertEqual(prepare_caption(source, mode="expression").marks, ())
        self.assertEqual(prepare_caption("Je suis furieuse.", mode="neutral").marks, ())
        with self.assertRaises(ValueError):
            prepare_caption(source, mode="incorrect")

    def test_bounds_stop_at_complete_token_not_inside_emoji(self):
        source = "mot " * 999 + "x👩🏽‍💻 famille"
        plan = prepare_caption(source)
        self.assertLessEqual(len(plan.text), 4000)
        self.assertEqual(plan.text, "mot " * 998 + "mot")
        self.assertEqual(prepare_caption("👩🏽‍💻" * 1001).text, "…")

    def test_frozen_values_pickle_and_ready_worker_metadata(self):
        plan = prepare_caption("Je suis furieuse. J’ai confiance.")
        restored = pickle.loads(pickle.dumps(plan))
        self.assertEqual(restored, plan)
        metadata = json.loads(json.dumps(asdict(plan)))
        with patch("jarvis.captions.analyze_passages", side_effect=AssertionError("metadata classified")):
            self.assertEqual(CaptionPlan.from_dict(metadata), plan)
            self.assertEqual(CaptionPlan.from_dict(plan), plan)
        for value, field, replacement in ((plan, "text", "autre"),
                                          (plan.marks[0], "start", 12),
                                          (plan.window(1), "text", "autre")):
            with self.subTest(field=field):
                with self.assertRaises(FrozenInstanceError):
                    setattr(value, field, replacement)

    def test_bad_metadata_is_rejected_without_analysis(self):
        bad = (None, {}, {"text": "x", "words": [[0, 2]]},
               {"text": "xy", "words": [[1, 2], [0, 1]]},
               {"text": "x", "marks": [{"start": 0, "end": 2, "tone": "peur"}]},
               {"text": "x", "words": [[False, 1]]}, {"text": "x" * 4001})
        for metadata in bad:
            with self.subTest(metadata=str(metadata)[:60]):
                with self.assertRaises(ValueError):
                    CaptionPlan.from_dict(metadata)


class CaptionWindowTests(unittest.TestCase):
    def test_groups_supply_context_but_do_not_highlight_future_words(self):
        text = "confiance peur amour quatrième"
        plan = CaptionPlan(text, ((0, 9), (10, 14), (15, 20), (21, 30)),
                           (CaptionMark(0, 9, "espoir"), CaptionMark(10, 14, "peur"),
                            CaptionMark(15, 20, "attachement")))
        first = plan.window(0.01)
        self.assertEqual(first.text, "confiance peur amour")
        self.assertEqual(marked(first), [("confiance", "espoir")])
        self.assertEqual(marked(plan.window(0.5)), [("confiance", "espoir"), ("peur", "peur")])
        self.assertEqual(plan.window(0), CaptionWindow())

    def test_compound_mark_stops_at_spoken_word_even_across_newline(self):
        text = "pleine d’espoir pour demain"
        plan = CaptionPlan(text, ((0, 6), (7, 15), (16, 20), (21, 27)),
                           (CaptionMark(0, 15, "espoir"),))
        first = plan.window(0.01, measure=len, width=10)
        self.assertEqual(first.text, "pleine\nd’espoir")
        self.assertEqual(marked(first), [("pleine", "espoir")])
        second = plan.window(0.5, measure=len, width=10)
        self.assertEqual(marked(second), [("pleine\nd’espoir", "espoir")])

    def test_recent_words_only_and_marks_relative_to_rebased_window(self):
        text = "un deux trois quatre cinq six sept huit neuf dix onze colère"
        plan = prepare_caption(text)
        full = plan.window(1)
        self.assertEqual(full.text, text)
        compact = plan.window(1, max_words=3)
        self.assertEqual(compact.text, "dix onze colère")
        self.assertEqual(marked(compact), [("colère", "colère")])
        self.assertEqual(compact.marks[0].start, compact.text.index("colère"))
        self.assertEqual(len(plan.window(1, max_words=500).text.split()), 12)
        self.assertEqual(plan.window(1, max_words=0), CaptionWindow())

    def test_width_fits_two_lines_preserving_current_word(self):
        plan = prepare_caption("un deux trois quatre cinq six sept huit neuf dix onze douze treize quatorze")
        for fraction in (0.01, 0.2, 0.5, 0.8, 1):
            with self.subTest(fraction=fraction):
                window = plan.window(fraction, measure=len, width=12)
                self.assertLessEqual(len(window.text.splitlines()), 2)
                self.assertTrue(all(len(line) <= 12 for line in window.text.splitlines()))
                spoken = min(len(plan.words), max(1, math.ceil(fraction * len(plan.words))))
                left, right = plan.words[spoken - 1]
                self.assertIn(plan.text[left:right], window.text)
        self.assertEqual(plan.window(0.01, max_words=1).text, "un")

    def test_whitespace_normalization_and_unicode_keep_correct_marks(self):
        text = "écho\t👩🏽‍💻\n\ncolère !"
        left = text.index("colère")
        plan = CaptionPlan(text, ((0, 4), (5, 9), (11, 18), (19, 20)),
                           (CaptionMark(left, left + len("colère"), "colère"),))
        window = plan.window(1)
        self.assertEqual(window.text, "écho 👩🏽‍💻 colère !")
        self.assertEqual(marked(window), [("colère", "colère")])

    def test_oversized_tokens_are_replaced_whole_without_slicing_emoji(self):
        text = "👩🏽‍💻👨🏾‍🚀 normal"
        plan = prepare_caption(text)
        window = plan.window(0.01, measure=len, width=3)
        self.assertEqual(window.text, "… …")
        self.assertEqual(window.marks, ())
        self.assertEqual(plan.window(1, measure=lambda text: len(text) * 10, width=1), CaptionWindow())

    def test_fraction_validation_and_empty_text(self):
        plan = prepare_caption("un deux trois")
        for fraction in (None, "bad", float("nan"), float("inf"), -float("inf"), -1, 0):
            with self.subTest(fraction=fraction):
                self.assertEqual(plan.window(fraction), CaptionWindow())
        self.assertEqual(plan.window(42), plan.window(1))
        self.assertEqual(prepare_caption("").window(1), CaptionWindow())
        self.assertEqual(prepare_caption(" \n\t").window(1), CaptionWindow())

    def test_rapid_segments_and_out_of_order_fractions_never_retain_marks(self):
        angry = prepare_caption("Je suis furieuse !")
        ordinary = prepare_caption("Voici le résultat.")
        hopeful = prepare_caption("J’ai confiance.")
        for _ in range(10):
            self.assertTrue(angry.window(1).marks)
            self.assertEqual(ordinary.window(1).marks, ())
            self.assertTrue(hopeful.window(1).marks)
            self.assertEqual(angry.window(0), CaptionWindow())
            self.assertTrue(angry.window(1).marks)


if __name__ == "__main__":
    unittest.main()
