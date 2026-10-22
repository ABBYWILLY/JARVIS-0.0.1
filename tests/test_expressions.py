"""Deterministic expressions, raw Unicode offsets and a speech-only boundary.

No voice model, device, cloud inference or display is involved here.
"""
import unittest

from jarvis.expressions import FAMILY_SYMBOLS, expression_family
from jarvis.richtext import SpeechBuffer, parse_text


def expression_events(document):
    return tuple(event for event in document.events if event.kind == "expression")


class ExpressionTests(unittest.TestCase):
    def test_eight_families_and_every_declared_alias_are_real_recognitions(self):
        self.assertEqual(set(FAMILY_SYMBOLS), {"smile", "laughter", "affection", "sadness",
                                               "anger", "surprise", "thinking", "wink"})
        for family, symbols in FAMILY_SYMBOLS.items():
            for symbol in symbols:
                with self.subTest(family=family, symbol=symbol):
                    self.assertEqual(expression_family(symbol), family)
                    self.assertEqual([event.value for event in expression_events(parse_text("Bonjour " + symbol))], [symbol])

    def test_unicode_selectors_skin_and_known_zwj_never_match_an_unknown_prefix(self):
        for symbol, family in (("❤️", "affection"), ("♥︎", "affection"),
                               ("🫶🏽", "affection"), ("❤️‍🔥", "affection"), ("❤️‍🩹", "affection")):
            with self.subTest(symbol=symbol):
                self.assertEqual(expression_family(symbol), family)
                doc = parse_text("Été " + symbol + " !")
                self.assertEqual(len(expression_events(doc)), 1)
                event = expression_events(doc)[0]
                self.assertEqual(doc.original[event.start:event.end], symbol)
                self.assertEqual(doc.text, doc.original)
                self.assertEqual(doc.speech, "Été !")
        for symbol in ("🙂‍↕️", "👨‍👩‍👧‍👦", "👩🏽‍💻", "🇫🇷", "1️⃣", "🚀", "❤‍🛸", "not an emoji", None):
            with self.subTest(symbol=symbol):
                self.assertIsNone(expression_family(symbol))
                if isinstance(symbol, str):
                    self.assertFalse(expression_events(parse_text(symbol)))

    def test_ascii_and_emoji_keep_display_original_words_and_punctuation(self):
        original = "Heureux de te revoir Abraham :) Un cœur ❤️ et une fusée 🚀, oui ! ;)"
        doc = parse_text(original)
        self.assertEqual(doc.original, original)
        self.assertEqual(doc.text, original)
        self.assertEqual(doc.speech, "Heureux de te revoir Abraham Un cœur et une fusée , oui !")
        events = expression_events(doc)
        self.assertEqual([event.value for event in events], [":)", "❤️", ";)"])
        self.assertTrue(all(original[event.start:event.end] == event.value for event in events))
        self.assertFalse(any(word in doc.speech for word in ("visage", "souriant", "rouge")))

    def test_opaque_contexts_and_literal_explanations_do_not_morph(self):
        samples = [
            "`:) 😊`", "```python\nprint('❤️ :)')\n```", "$x := :) ❤️$",
            "https://example.com/😊/:)", "[😊 :)](https://example.com)",
            '"😊 :)"', "«❤️ ;)»", "‘🤔 :(’", "'😮 :D'", "“😉 :-)”",
            r"C:\images\😊\:)", "/tmp/❤️/figure.png", "./😊.png",
            "Le symbole ASCII :) sert d'exemple.", "Une regex contient 😊.",
            "pattern = :) 😊", "if (x):) 😊", "return ':)'",
        ]
        for sample in samples:
            with self.subTest(sample=sample):
                self.assertFalse(expression_events(parse_text(sample)))
        self.assertEqual(parse_text("J'aime beaucoup 😊.").speech, "J'aime beaucoup .")
        self.assertEqual([event.value for event in expression_events(parse_text("J'aime beaucoup 😊."))], ["😊"])

    def test_ascii_boundaries_protect_technical_text_without_losing_consecutive_symbols(self):
        for sample in ("http:)/x", "nom:)identifiant", "C:)\\foo", "x;)y", "D:D"):
            with self.subTest(sample=sample):
                self.assertFalse(expression_events(parse_text(sample)))
                self.assertEqual(parse_text(sample).speech, sample)
        doc = parse_text("Bonjour :):D❤️;)!")
        self.assertEqual([event.value for event in expression_events(doc)], [":)", ":D", "❤️", ";)"])
        self.assertEqual(doc.speech, "Bonjour !")

    def test_heart_suit_is_spoken_when_it_has_a_real_card_meaning(self):
        for sample, expected in (("L'as de ♥", "L'as de cœur"), ("10 ♥", "10 cœur"),
                                 ("Roi ♥️", "Roi cœur")):
            with self.subTest(sample=sample):
                doc = parse_text(sample)
                self.assertEqual(doc.text, sample)
                self.assertEqual(doc.speech, expected)
                self.assertFalse(expression_events(doc))
        self.assertEqual(expression_events(parse_text("Je t'aime ♥"))[0].value, "♥")


class ExpressionStreamingTests(unittest.TestCase):
    def test_ascii_fragments_wait_for_complete_symbol_and_do_not_speak_it(self):
        for opening, closing in ((":", ")"), (":-", ")"), (";", ")"), (":", "D")):
            with self.subTest(opening=opening):
                buffer = SpeechBuffer()
                self.assertEqual(buffer.feed("Bonjour " + opening), [])
                self.assertEqual(buffer.feed(closing), [])
                segments = buffer.feed("", final=True)
                self.assertEqual([segment.text for segment in segments], ["Bonjour"])
                self.assertEqual([event.value for segment in segments for event in segment.events
                                  if event.kind == "expression"], [opening + closing])

    def test_final_expressive_tail_is_visual_only_never_fake_speech(self):
        for tail in ("😊", "❤️", ":)", "😊.", ";)!"):
            with self.subTest(tail=tail):
                raw = "Bonjour. " + tail
                buffer = SpeechBuffer()
                segments = buffer.feed(raw, final=True)
                self.assertEqual(segments[0].text, "Bonjour.")
                self.assertFalse(segments[0].visual_only)
                self.assertEqual(segments[-1].text, "")
                self.assertTrue(segments[-1].visual_only)
                self.assertEqual(segments[-1].original, raw[segments[-1].start:segments[-1].end])
                self.assertTrue(any(event.kind == "expression" for event in segments[-1].events))
        for raw in ("😊", ":)", "❤️ !!!"):
            segments = SpeechBuffer().feed(raw, final=True)
            self.assertEqual(len(segments), 1)
            self.assertTrue(segments[0].visual_only)
            self.assertEqual(segments[0].text, "")

    def test_unknown_emoji_tail_preserves_caption_offsets_without_morphing_or_audio(self):
        raw = "Bonjour. 👩🏽‍🚀"
        segments = SpeechBuffer().feed(raw, final=True)
        self.assertEqual([segment.text for segment in segments if not segment.visual_only], ["Bonjour."])
        tail = segments[-1]
        self.assertTrue(tail.visual_only)
        self.assertEqual(tail.text, "")
        self.assertEqual(tail.original, raw[tail.start:tail.end])
        self.assertEqual(tail.original, "👩🏽‍🚀")
        self.assertFalse(any(event.kind == "expression" for event in tail.events))
        emoji = next(event for event in tail.events if event.kind == "emoji")
        self.assertEqual(raw[emoji.start:emoji.end], "👩🏽‍🚀")
        self.assertEqual(parse_text(raw).speech, "Bonjour.")

    def test_character_stream_keeps_global_offsets_unicode_and_all_words(self):
        samples = ("Bonjour :) Ensuite une fusée 🚀. Merci ❤️ !",
                   "Été 😊 au milieu puis calme. Fin 😉", "Bonjour. 😊",
                   "**Bonjour :)** et ==merci ❤️==. Fin.")
        for raw in samples:
            with self.subTest(raw=raw):
                buffer, segments = SpeechBuffer(), []
                for char in raw:
                    segments.extend(buffer.feed(char))
                segments.extend(buffer.feed("", final=True))
                spoken = " ".join(segment.text for segment in segments if not segment.visual_only)
                self.assertEqual(spoken, parse_text(raw).speech)
                for segment in segments:
                    self.assertEqual(segment.original, raw[segment.start:segment.end])
                    for event in segment.events:
                        self.assertTrue(segment.start <= event.start < event.end <= segment.end)
                        if event.kind == "expression":
                            self.assertEqual(raw[event.start:event.end], event.value)


if __name__ == "__main__":
    unittest.main()
