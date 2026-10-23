import unittest

from jarvis.richtext import SpeechBuffer, parse_text, safe_url, verbalize_math


class RichTextTests(unittest.TestCase):
    def test_nested_emphasis_and_blocks(self):
        doc = parse_text("# Bonjour **cher *ami***\n- un\n> deux")
        self.assertEqual(doc.text, "Bonjour cher ami\n• un\ndeux")
        self.assertEqual(doc.speech, "Bonjour cher ami. un. deux")
        ami = next(span for span in doc.spans if "ami" in span.text)
        self.assertEqual(set(ami.tags), {"heading1", "bold", "italic"})
        self.assertTrue(any("list" in span.tags for span in doc.spans))
        self.assertTrue(any("quote" in span.tags for span in doc.spans))

    def test_french_and_emoji_clusters(self):
        emojis = ["😀", "👩🏽‍💻", "👨‍👩‍👧‍👦", "🇫🇷", "1️⃣", "*️⃣", "✈️", "🏴\U000e0067\U000e0062\U000e007f"]
        raw = "Élève, cœur, français, reçu. " + " ".join(emojis) + " Ça va !"
        doc = parse_text(raw)
        self.assertEqual(doc.text, raw)
        self.assertEqual(doc.original, raw)
        self.assertEqual(doc.speech, "Élève, cœur, français, reçu. Ça va !")
        events = [event for event in doc.events if event.kind == "emoji"]
        self.assertEqual([raw[event.start:event.end] for event in events], emojis)
        self.assertEqual([event.value for event in events], emojis)

    def test_inline_and_fenced_code_have_explicit_speech_policy(self):
        raw = "Utilisez `print(1)`.\n```python\nprint('bonjour')\n```\nFin."
        doc = parse_text(raw)
        self.assertIn("Utilisez print(1).", doc.speech)
        self.assertIn("Bloc de code non lu.", doc.speech)
        self.assertNotIn("print('bonjour')", doc.speech)
        self.assertIn("print('bonjour')", parse_text(raw, speak_code=True).speech)
        self.assertTrue(any("codeblock" in span.tags for span in doc.spans))
        self.assertNotIn("```", doc.text)

    def test_links_keep_label_and_validate_destination(self):
        raw = "[**Guide**](https://example.com/a_(b)) [danger](javascript:alert(1))"
        doc = parse_text(raw)
        self.assertEqual(doc.text, "Guide danger")
        self.assertEqual(doc.speech, "Guide danger")
        links = [span for span in doc.spans if "link" in span.tags]
        self.assertEqual(links[0].url, "https://example.com/a_(b)")
        self.assertIn("bold", links[0].tags)
        self.assertIsNone(links[-1].url)
        self.assertEqual(parse_text("[a](https://a.com)[b](https://b.com)").spans[-1].url, "https://b.com")

    def test_unsafe_urls_and_inert_html(self):
        for value in ["http://example.com", "file:///etc/passwd", "data:text/html,x", "javascript:alert(1)",
                      "https://user:secret@example.com", "https://localhost", "https://x.local", "https://127.0.0.1",
                      "https://[::1]", "https://10.1.2.3", "https://169.254.1.2", "https://2130706433", "https://x.com:99999"]:
            with self.subTest(value=value):
                self.assertIsNone(safe_url(value))
                self.assertIsNone(parse_text("[lien](" + value + ")").spans[0].url)
        self.assertEqual(safe_url("https://example.com/a"), "https://example.com/a")
        self.assertEqual(safe_url("https://8.8.8.8/"), "https://8.8.8.8/")
        raw = '<script>alert("x")</script><b>texte</b>'
        self.assertEqual(parse_text(raw).text, raw)

    def test_math_and_currency(self):
        raw = r"Prix $5 et $10. Calcul $12/12$ ; \(\frac{1}{2} + \sqrt{4}\) ; $$α^2 ≤ 3\,\mathrm{m/s}$$."
        doc = parse_text(raw)
        self.assertIn("5 dollars et 10 dollars", doc.speech)
        self.assertIn("12 divisé par 12", doc.speech)
        self.assertIn("fraction de 1 sur 2", doc.speech)
        self.assertIn("racine carrée de 4", doc.speech)
        self.assertIn("alpha au carré inférieur ou égal à 3", doc.speech)
        self.assertIn("mètres par seconde", doc.speech)
        self.assertEqual(len([event for event in doc.events if event.kind == "math"]), 3)

    def test_math_keeps_unknown_units_and_nested_groups(self):
        spoken = verbalize_math(r"\frac{\sqrt{x^2}}{10^{-3}} \approx 2.14\mathrm{widgets}")
        self.assertIn("racine carrée de x au carré", spoken)
        self.assertIn("10 puissance moins 3", spoken)
        self.assertIn("2.14 widgets", spoken)

    def test_currency_suffix_before_punctuation_and_adjacent_prices_are_not_latex(self):
        doc = parse_text("Le total est 20 $. Deux prix : $5+$10.")
        self.assertIn("20 dollars.", doc.speech)
        self.assertIn("5 dollars", doc.speech)
        self.assertIn("10 dollars", doc.speech)
        self.assertEqual(doc.speech.count("dollars"), 3)
        self.assertFalse(any(event.kind == "math" for event in doc.events))

    def test_paragraphs_and_lists_keep_audible_pauses(self):
        raw = "**Premier paragraphe\n\nDeuxième paragraphe.**\n- Un élément\n- Deuxième élément !\nFin"
        expected = "Premier paragraphe. Deuxième paragraphe. Un élément. Deuxième élément ! Fin"
        self.assertEqual(parse_text(raw).speech, expected)
        buffer = SpeechBuffer()
        segments = []
        for char in raw:
            segments.extend(buffer.feed(char))
        segments.extend(buffer.feed("", final=True))
        self.assertEqual(" ".join(segment.text for segment in segments), expected)

    def test_unclosed_markdown_final_keeps_words(self):
        for raw, expected in [("**bonjour", "bonjour"), ("`commande", "commande"),
                              ("[guide](https://example", "guide"), (r"\(x^2", "x au carré")]:
            with self.subTest(raw=raw):
                self.assertEqual(parse_text(raw).speech, expected)

    def test_controlled_styles_compose_without_html_or_technical_false_positives(self):
        raw = "++souligné **gras**++ et ==très *clair*==. C++ et a==b ; $2+2=4$."
        doc = parse_text(raw)
        self.assertEqual(doc.original, raw)
        self.assertEqual(doc.text, "souligné gras et très clair. C++ et a==b ; 2+2=4.")
        self.assertIn("C++ et a==b", doc.speech)
        self.assertIn("2 plus 2 égal à 4", doc.speech)
        self.assertFalse(any(marker in doc.speech for marker in ("++souligné", "==très")))
        self.assertTrue(any(span.text == "gras" and {"underline", "bold"} <= set(span.tags) for span in doc.spans))
        self.assertTrue(any(span.text == "clair" and {"highlight", "italic"} <= set(span.tags) for span in doc.spans))
        opaque = parse_text("`++a++ ==b==` et \\++sans++ https://example.com/a==b")
        self.assertFalse(any({"underline", "highlight"} & set(span.tags) for span in opaque.spans))
        self.assertIn("++a++ ==b==", opaque.text)

    def test_strikethrough_composes_with_emphasis_and_preserves_french_and_currency(self):
        raw = "Avant ~~Été **gras et *italique***~~, 20 $. Après."
        doc = parse_text(raw)
        self.assertEqual(doc.original, raw)
        self.assertEqual(doc.text, "Avant Été gras et italique, 20 $. Après.")
        self.assertEqual(doc.speech, "Avant Été gras et italique, 20 dollars. Après.")
        self.assertTrue(any(span.text == "italique" and {"strike", "bold", "italic"} <= set(span.tags)
                            for span in doc.spans))
        self.assertFalse(any("strike" in span.tags for span in doc.spans if "Après" in span.text))

    def test_strikethrough_does_not_close_inside_code_or_interpret_technical_tildes(self):
        raw = "~~Ancien `a~~b` résultat~~. [~~le guide~~](https://example.org)."
        doc = parse_text(raw)
        self.assertEqual(doc.text, "Ancien a~~b résultat. le guide.")
        self.assertTrue(any(span.text == "a~~b" and {"strike", "code"} <= set(span.tags)
                            for span in doc.spans))
        self.assertTrue(any(span.text == "le guide" and {"strike", "link"} <= set(span.tags)
                            and span.url == "https://example.org" for span in doc.spans))
        literal = parse_text(r"~10 et a~~b~~c ; `~~code~~` ; \~\~littéral\~\~")
        self.assertEqual(literal.text, "~10 et a~~b~~c ; ~~code~~ ; ~~littéral~~")
        self.assertFalse(any("strike" in span.tags for span in literal.spans))
        fenced = parse_text("~~~python\n~~code~~\n~~~\n")
        self.assertTrue(all("strike" not in span.tags for span in fenced.spans))
        self.assertIn("~~code~~", fenced.text)

    def test_partial_strikethrough_retains_words_and_holds_speech_until_closed(self):
        self.assertEqual(parse_text("~~Été inachevé").speech, "Été inachevé")
        self.assertEqual(parse_text("~~Été inachevé", final=False).text, "Été inachevé")
        buffer = SpeechBuffer()
        self.assertEqual(buffer.feed("~~Une phrase. "), [])
        segments = buffer.feed("Encore une~~. ")
        self.assertEqual([segment.text for segment in segments], ["Une phrase. Encore une."])
        self.assertEqual(segments[0].original, "~~Une phrase. Encore une~~. ")

    def test_controlled_partial_styles_are_provisional_until_closed(self):
        for marker, tag in (("++", "underline"), ("==", "highlight")):
            with self.subTest(marker=marker):
                partial = parse_text(marker + "Été", final=False)
                self.assertEqual(partial.text, "Été")
                self.assertFalse(any(tag in span.tags for span in partial.spans))
                complete = parse_text(marker + "Été" + marker, final=False)
                self.assertEqual(complete.text, "Été")
                self.assertTrue(all(tag in span.tags for span in complete.spans))
                buffer = SpeechBuffer()
                self.assertEqual(buffer.feed(marker + "Été. "), [])
                self.assertEqual([segment.text for segment in buffer.feed("Fini" + marker + ". ")], ["Été. Fini."])

    def test_lists_show_markers_and_indentation_without_pronouncing_prefixes(self):
        doc = parse_text("- Un\n  2. Deux\n    + Trois")
        self.assertEqual(doc.text, "• Un\n2. Deux\n• Trois")
        self.assertEqual(doc.speech, "Un. Deux. Trois")
        self.assertTrue(any("list_depth_2" in span.tags for span in doc.spans))
        self.assertEqual(parse_text("Avant\n---\nAprès").speech, "Avant. Après")
        self.assertIn("separator", parse_text("***\n").spans[0].tags)
        self.assertEqual(parse_text("`---`\n```\n---\n```").text, "---\n---\n")

    def test_tables_preserve_styles_unicode_values_and_source_offsets(self):
        raw = "| Nom | Valeur |\n| :--- | ---: |\n| **Été** | 20 $ |\n| 👩🏽‍💻 | `a|b` |\n\nFin."
        doc = parse_text(raw)
        self.assertEqual(doc.original, raw)
        self.assertIn("Nom", doc.text)
        self.assertIn("Été", doc.text)
        self.assertIn("👩🏽‍💻", doc.text)
        self.assertIn("a|b", doc.text)
        self.assertNotIn("---", doc.text)
        self.assertNotIn("**", doc.text)
        self.assertTrue(any({"table", "tableheader"} <= set(span.tags) for span in doc.spans))
        self.assertTrue(any(span.text == "Été" and "bold" in span.tags for span in doc.spans))
        self.assertEqual(doc.speech, "Nom ; Valeur. Été ; 20 dollars. ; a|b. Fin.")
        emoji = next(event for event in doc.events if event.kind == "emoji")
        self.assertEqual(raw[emoji.start:emoji.end], "👩🏽‍💻")
        buffer, segments = SpeechBuffer(), []
        for char in raw:
            segments.extend(buffer.feed(char))
        segments.extend(buffer.feed("", final=True))
        self.assertEqual(" ".join(segment.text for segment in segments), doc.speech)
        for segment in segments:
            self.assertEqual(segment.original, raw[segment.start:segment.end])

    def test_non_tables_and_escaped_pipes_remain_literal_or_cell_content(self):
        self.assertEqual(parse_text("a | b\nordinary prose").text, "a | b\nordinary prose")
        doc = parse_text("A | B\n--- | ---\nx\\|y | z\n")
        self.assertIn("x|y", doc.text)
        self.assertIn("x|y ; z", doc.speech)


class SpeechBufferTests(unittest.TestCase):
    def test_character_stream_matches_complete_speech(self):
        samples = [
            "Bonjour **cher *ami*** ! Voici [le guide](https://example.com/a?b=1). À bientôt.",
            r"Prix $5 et $10. Calcul $12/12$ puis \(\frac{1}{2} + \sqrt{4}\) et $2.14 + α^2$.",
            "Élève œuf 👩🏽‍💻 🇫🇷 1️⃣ ! Famille 👨‍👩‍👧‍👦. Fin.",
            "```python\nx = '**inert**'\n```\nUtilisez `x`. Fin.",
            "Un lien nu https://example.com/path. Puis la suite.",
            "Texte **inachevé et `code",
            "Titre\n\n- Premier élément\n- Deuxième.\nFin",
            "~~Ancien **choix**~~. [~~le guide~~](https://example.org) ; ~10 euros. Fin.",
        ]
        for raw in samples:
            for speak_code in (False, True):
                with self.subTest(raw=raw, speak_code=speak_code):
                    buffer = SpeechBuffer(speak_code=speak_code)
                    segments = []
                    for char in raw:
                        segments.extend(buffer.feed(char))
                    segments.extend(buffer.feed("", final=True))
                    self.assertEqual(" ".join(segment.text for segment in segments), parse_text(raw, speak_code=speak_code).speech)
                    self.assertEqual(buffer.original, raw)
                    self.assertEqual(buffer.pending, "")
                    for segment in segments:
                        self.assertEqual(segment.original, raw[segment.start:segment.end])
                        for event in segment.events:
                            self.assertTrue(segment.start <= event.start <= event.end <= segment.end)

    def test_balanced_constructs_wait_and_then_emit(self):
        for opening, closing in [("**Un texte. ", "Ferme**. "), ("[Un texte.](https://exam", "ple.com). "),
                                 (r"\(2. ", r"+ 14\). "), ("```python\nprint(1).\n", "```\n")]:
            with self.subTest(opening=opening):
                buffer = SpeechBuffer()
                self.assertEqual(buffer.feed(opening), [])
                self.assertTrue(buffer.feed(closing))

    def test_decimal_waits_for_next_digit(self):
        buffer = SpeechBuffer()
        self.assertEqual(buffer.feed("La valeur est 2."), [])
        self.assertEqual(buffer.feed("14"), [])
        segments = buffer.feed(". ")
        self.assertEqual([segment.text for segment in segments], ["La valeur est 2.14."])

    def test_offsets_are_global_and_events_keep_original_ranges(self):
        raw = "Bonjour. **Ça va** 👩🏽‍💻 ! Dernier mot."
        buffer = SpeechBuffer()
        segments = buffer.feed(raw, final=True)
        self.assertGreater(len(segments), 1)
        events = [event for segment in segments for event in segment.events if event.kind == "emoji"]
        self.assertEqual([raw[event.start:event.end] for event in events], ["👩🏽‍💻"])
        self.assertEqual(segments[0].start, 0)
        self.assertEqual(segments[-1].end, len(raw))

    def test_long_plain_text_uses_whitespace_without_losing_words(self):
        raw = "mot " * 300
        buffer = SpeechBuffer()
        segments = buffer.feed(raw, final=True)
        self.assertTrue(all(len(segment.text) <= 240 for segment in segments))
        self.assertLessEqual(len(segments[0].text), 96)
        self.assertEqual(" ".join(segment.text for segment in segments).split(), raw.split())

    def test_partial_bare_url_never_emits(self):
        buffer = SpeechBuffer()
        self.assertEqual(buffer.feed("Voir https://exam"), [])
        self.assertEqual(buffer.feed("ple.com/path"), [])
        self.assertEqual([segment.text for segment in buffer.feed(". ")], ["Voir lien ."])


if __name__ == "__main__":
    unittest.main()
