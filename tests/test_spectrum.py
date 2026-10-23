from dataclasses import FrozenInstanceError
import unittest

from jarvis.spectrum import (
    CYAN, OPERATIONAL, TONES, FieldEvent, MoodTracker, Tone, ToneAnalyzer, ToneEvent,
    analyze_passages, caption_group, emotional_spans, keyword_spans,
)


class SpectrumTests(unittest.TestCase):
    def test_surprise_uses_existing_local_scopes_and_never_changes_operational_colors(self):
        operational = dict(OPERATIONAL)
        self.assertEqual(ToneAnalyzer().update("Je suis vraiment surpris !").name, "surprise")
        self.assertEqual(ToneAnalyzer().update("Je suis étonnée.").name, "surprise")
        for text in ("Je ne suis pas surpris.", "Le mot surprise est cité.",
                     'Il écrit « Je suis surpris ».', "Je suis surpris ?"):
            self.assertEqual(ToneAnalyzer().update(text), Tone())
        self.assertEqual(OPERATIONAL, operational)

    def test_expression_is_default_and_a_single_explicit_cue_suffices(self):
        analyzer = ToneAnalyzer()
        self.assertEqual(analyzer.mode, "expression")
        self.assertEqual(analyzer.hold_seconds, 0)
        tone = analyzer.update("Je suis furieux !", now=0)
        self.assertEqual(tone.name, "colère")
        self.assertEqual(tone.words, ("furieux",))
        self.assertEqual(tone.color, TONES["colère"][0])

    def test_topic_and_expression_have_different_meanings(self):
        text = "La colère est une émotion."
        self.assertEqual(ToneAnalyzer().update(text), Tone())
        self.assertEqual(ToneAnalyzer(mode="thematic").update(text).name, "colère")
        self.assertEqual(ToneAnalyzer(mode="thematic").update("Je suis furieux !").name, "colère")

    def test_bare_words_and_mentions_do_not_assert_a_feeling(self):
        for text in ("furieux", "Le mot colère figure ici", "Un essai sur la colère et la rage.",
                     "Je suis spécialiste de la colère.", "Je comprends votre peur."):
            with self.subTest(text=text):
                self.assertEqual(ToneAnalyzer().update(text), Tone())

    def test_each_palette_family_has_a_local_expression(self):
        examples = {
            "joie": "Je suis heureux !", "colère": "Cela m'énerve !", "désir": "J'ai envie de réussir.",
            "peur": "Je suis inquiète.", "volonté": "Je suis déterminée.",
            "espoir": "J'espère réussir.", "compassion": "Je compatis avec vous.",
            "attachement": "Je t'aime.", "renouveau": "Je renais enfin.",
            "deuil": "Je suis en deuil.",
        }
        for name, text in examples.items():
            with self.subTest(name=name):
                self.assertEqual(ToneAnalyzer().update(text).name, name)

    def test_clear_joy_expressions_have_their_own_tone(self):
        for text in ("Je suis heureux !", "Je suis ravie !", "Je suis content !", "Je suis si heureux !", "Avec plaisir !", "Quelle joie !"):
            with self.subTest(text=text):
                self.assertEqual(ToneAnalyzer().update(text).name, "joie")
        for text in ("La joie est une émotion.", "Je ne suis pas heureux.", "Je suis heureux ?", "Je suis heureux et furieux."):
            with self.subTest(text=text):
                self.assertEqual(ToneAnalyzer().update(text), Tone())
        self.assertEqual(ToneAnalyzer(mode="thematic").update("La joie est une émotion.").name, "joie")

    def test_neutral_mode_always_returns_cyan(self):
        analyzer = ToneAnalyzer(mode="neutral")
        self.assertEqual(analyzer.update("Je suis furieux !"), Tone())
        self.assertTrue(all(event.tone.color == CYAN for event in
                            analyze_passages("Je suis furieux. J'ai confiance.", mode="neutral")))

    def test_invalid_modes_fail_clearly(self):
        with self.assertRaises(ValueError):
            ToneAnalyzer(mode="unknown")
        with self.assertRaises(ValueError):
            analyze_passages("texte", mode="unknown")

    def test_conflicting_affirmed_emotions_stay_cyan(self):
        for text in ("Je suis furieux et inquiet.", "Je ressens colère, espoir et peur.",
                     "Je ressens colère et rage, mais aussi espoir et confiance.",
                     "Je ne suis pas seulement heureux, je suis aussi triste."):
            with self.subTest(text=text):
                self.assertEqual(ToneAnalyzer().update(text), Tone())
        self.assertEqual(ToneAnalyzer(mode="thematic").update("colère espoir peur"), Tone())

    def test_questions_do_not_assert_a_feeling(self):
        for text in ("Je suis furieux ?", "Ressens-tu de la colère et de la rage ?", "Ai-je peur ?"):
            with self.subTest(text=text):
                self.assertEqual(ToneAnalyzer().update(text), Tone())
        self.assertEqual(ToneAnalyzer(mode="thematic").update("Pourquoi la colère ?").name, "colère")

    def test_hypothetical_and_uncertain_feelings_stay_cyan(self):
        for text in ("Si je suis furieux, je sors.", "Je serais furieux.",
                     "Je suis peut-être furieux.", "Je suis furieux, peut-être.", "Je pourrais ressentir de la colère."):
            with self.subTest(text=text):
                self.assertEqual(ToneAnalyzer().update(text), Tone())
                self.assertEqual(ToneAnalyzer(mode="thematic").update(text), Tone())

    def test_explicit_and_coordinated_negations_stay_neutral(self):
        for text in ("aucune colère et pas de rage", "Je ne suis pas furieux.",
                     "Je ne ressens ni colère ni rage.", "Je suis sans colère.",
                     "Je ne suis pas sans colère ni rage.", "Cela ne m'angoisse pas.",
                     "Ma colère n’existe pas.", "Ma joie ne revient jamais."):
            with self.subTest(text=text):
                self.assertEqual(ToneAnalyzer().update(text), Tone())
                self.assertEqual(ToneAnalyzer(mode="thematic").update(text), Tone())

    def test_negation_does_not_spill_into_a_new_assertion(self):
        for text in ("Je n'ai pas peur mais je suis furieux !",
                     "Je ne suis pas furieux et j'ai confiance."):
            with self.subTest(text=text):
                expected = "colère" if "mais" in text else "espoir"
                self.assertEqual(ToneAnalyzer().update(text).name, expected)

    def test_negated_cause_does_not_negate_the_expressed_feeling(self):
        self.assertEqual(ToneAnalyzer().update("J'ai peur de ne pas réussir.").name, "peur")
        self.assertEqual(ToneAnalyzer().update("Je suis furieux sans être inquiet.").name, "colère")

    def test_quoted_and_reported_speech_stay_neutral(self):
        for text in ('Il dit : « Je suis furieux ! »', 'Exemple : "Je suis furieux !"',
                     "Il cite 'Je suis furieux'.", "“Je suis furieux !”", "> Je suis furieux !"):
            with self.subTest(text=text):
                self.assertEqual(ToneAnalyzer().update(text), Tone())

    def test_apostrophes_are_not_quote_delimiters(self):
        for text in ("J'ai confiance.", "J’ai confiance.", "J’éprouve de l’affection."):
            with self.subTest(text=text):
                expected = "attachement" if "affection" in text else "espoir"
                self.assertEqual(ToneAnalyzer().update(text).name, expected)

    def test_changes_and_return_to_cyan_are_immediate(self):
        analyzer = ToneAnalyzer(hold_seconds=3)
        self.assertEqual(analyzer.update("Je suis furieux !", now=0).name, "colère")
        self.assertEqual(analyzer.changed_at, 0)
        self.assertEqual(analyzer.update("J'ai confiance.", now=0.1).name, "espoir")
        self.assertEqual(analyzer.changed_at, 0.1)
        self.assertEqual(analyzer.update("Voici le résultat.", now=0.2), Tone())
        self.assertEqual(analyzer.changed_at, 0.2)
        self.assertEqual(analyzer.current, Tone())

    def test_update_uses_the_last_passage(self):
        analyzer = ToneAnalyzer()
        self.assertEqual(analyzer.update("Je suis furieux. Voici le résultat."), Tone())
        self.assertEqual(analyzer.update("Voici le résultat. Je suis furieux !").name, "colère")

    def test_passages_include_factual_and_negated_returns_to_cyan(self):
        source = "Je suis furieux ! Voici le résultat. Je n'ai pas peur. J'ai confiance."
        events = analyze_passages(source)
        self.assertEqual([event.tone.name for event in events],
                         ["colère", "neutralité", "neutralité", "espoir"])
        self.assertEqual(''.join(event.text for event in events), source)

    def test_paragraphs_and_newlines_segment_without_punctuation(self):
        source = "Je suis furieux\n\nVoici le résultat\nJ'ai confiance"
        events = analyze_passages(source)
        self.assertEqual([event.tone.name for event in events], ["colère", "neutralité", "espoir"])
        self.assertEqual(''.join(event.text for event in events), source)

    def test_absolute_python_offsets_preserve_markdown_and_composed_emoji(self):
        source = "👩🏽‍💻 **Je suis furieuse !**\n\nJ’ai confiance."
        events = analyze_passages(source, start=73)
        self.assertEqual([event.tone.name for event in events], ["colère", "espoir"])
        self.assertEqual(events[0].start, 73)
        self.assertEqual(events[-1].end, 73 + len(source))
        for event in events:
            self.assertEqual(event.text, source[event.start - 73:event.end - 73])
        self.assertEqual(''.join(event.text for event in events), source)

    def test_opaque_code_math_urls_and_html_are_not_emotion_evidence(self):
        for text in ("```text\nJe suis furieux !\n```", "`Je suis furieux !`",
                     "https://example.com/colère/rage", "<p>Je suis furieux !</p>", "<p>Je suis furieux !",
                     '<img alt="Je suis furieux !">', "$Je suis furieux$"):
            with self.subTest(text=text):
                events = analyze_passages(text, mode="thematic")
                self.assertTrue(events)
                self.assertTrue(all(event.tone == Tone() for event in events))
                self.assertEqual(''.join(event.text for event in events), text)

    def test_code_passages_are_neutral_between_affirmed_feelings(self):
        source = "Je suis furieux.\n```txt\nJ'ai peur !\n```\nJ'ai confiance."
        events = analyze_passages(source)
        self.assertEqual([event.tone.name for event in events], ["colère", "neutralité", "espoir"])
        self.assertEqual(''.join(event.text for event in events), source)

    def test_link_labels_can_express_a_feeling_but_destinations_cannot(self):
        self.assertEqual(ToneAnalyzer().update("Je suis [furieux](https://example.com/espoir).").name, "colère")
        self.assertEqual(ToneAnalyzer(mode="thematic").update("[Un lien](https://example.com/colere)."), Tone())
        # The source link label belongs to the same natural language passage.
        events = analyze_passages("Je suis [furieux](https://example.com/espoir) !")
        self.assertEqual(events[0].tone.name, "colère")
        self.assertEqual(events[0].tone.words, ("furieux",))

    def test_events_are_frozen_and_empty_input_has_no_events(self):
        self.assertEqual(analyze_passages(""), ())
        event = analyze_passages("Texte.")[0]
        self.assertIsInstance(event, ToneEvent)
        with self.assertRaises(FrozenInstanceError):
            event.start = 1

    def test_only_selected_words_not_whole_paragraph(self):
        text = "Je ressens de la COLÈRE et de la rage, mais le reste est ordinaire."
        tone = ToneAnalyzer().update(text)
        spans = keyword_spans(text, tone.words)
        self.assertEqual([text[a:b] for a, b in spans], ["COLÈRE", "rage"])

    def test_emotion_never_mutates_operational_spectrum(self):
        original = {key: dict(value) for key, value in OPERATIONAL.items()}
        for mode in ("expression", "thematic", "neutral"):
            ToneAnalyzer(mode=mode).update("Je suis en deuil.")
        self.assertEqual(OPERATIONAL, original)
        self.assertNotIn("permission", ToneAnalyzer().current.__dict__)

    def test_caption_is_empty_before_audio_and_bounded_after(self):
        text = ' '.join('mot' + str(i) for i in range(60))
        self.assertEqual(caption_group(text, 0), "")
        first = caption_group(text, 0.01)
        self.assertEqual(first, "mot0 mot1 mot2")
        final = caption_group(text, 1)
        self.assertEqual(len(final.split()), 12)
        self.assertTrue(final.endswith("mot59"))
        self.assertEqual(caption_group(text, float('nan')), "")

    def test_apaisement_and_contextual_reassurance(self):
        for text in ("Je suis calme.", "Je me sens sereine.", "Je suis apaisé.",
                     "Tout va bien.", "Ça va aller."):
            with self.subTest(text=text):
                tone = ToneAnalyzer().update(text)
                self.assertEqual(tone.name, "apaisement")
                self.assertTrue(emotional_spans(text, tone, mode="expression"))
        self.assertEqual(ToneAnalyzer().update("Je suis avec vous de tout cœur.").name, "compassion")
        self.assertEqual(ToneAnalyzer().update("Je t'aime de tout cœur.").name, "attachement")
        for text in ("De tout cœur.", "La phrase tout va bien est citée.", "Ça va aller ?",
                     "Ça ne va pas aller.", "Peut-être que tout va bien.",
                     "Je ne suis pas calme.", "Je suis heureux et calme."):
            with self.subTest(text=text):
                self.assertEqual(ToneAnalyzer().update(text), Tone())

    def test_intensifier_strengthens_only_affirmed_evidence(self):
        plain = ToneAnalyzer().update("Je suis serein.")
        strong = ToneAnalyzer().update("Je suis vraiment très serein.")
        self.assertGreater(strong.confidence, plain.confidence)
        self.assertEqual(strong.name, plain.name)
        self.assertLessEqual(strong.confidence, 1)
        self.assertEqual(ToneAnalyzer().update("Je ne suis vraiment pas serein."), Tone())
        self.assertEqual(ToneAnalyzer(mode="thematic").update("Une très belle étude sur le calme.").confidence,
                         plain.confidence)

    def test_contextual_spans_exclude_same_word_in_negations_quotes_and_code(self):
        source = 'Je suis furieux, mais pas furieux ni en rage. « furieux » `furieux`'
        tone = analyze_passages(source)[0].tone
        spans = emotional_spans(source, tone, mode="expression")
        self.assertEqual([source[a:b] for a, b in spans], ["furieux"])
        self.assertEqual(emotional_spans(source, Tone()), ())
        self.assertEqual(emotional_spans(source, tone, mode="neutral"), ())
        self.assertEqual(emotional_spans("Je suis furieux et inquiet.", tone), ())
        with self.assertRaises(ValueError):
            emotional_spans(source, tone, mode="unknown")

    def test_compound_spans_and_decomposed_accents_keep_python_offsets(self):
        source = "👩🏽‍💻 **Ça va aller**, tout va bien."
        tone = ToneAnalyzer().update(source)
        self.assertEqual([source[a:b] for a, b in emotional_spans(source, tone)],
                         ["Ça va aller", "tout va bien"])
        source = "👩🏽‍💻 Je suis en cole\u0300re, mais sans colère."
        tone = ToneAnalyzer().update(source)
        self.assertEqual(tone.name, "colère")
        self.assertEqual([source[a:b] for a, b in emotional_spans(source, tone)], ["cole\u0300re"])
        self.assertEqual([source[a:b] for a, b in keyword_spans(source, tone.words)],
                         ["cole\u0300re", "colère"])
        source = "Je suis avec vous de tout cœur."
        tone = ToneAnalyzer().update(source)
        self.assertEqual([source[a:b] for a, b in emotional_spans(source, tone)], ["de tout cœur"])


class MoodTrackerTests(unittest.TestCase):
    def test_first_reliable_mood_survives_isolated_nuance_and_factual_passages(self):
        source = "J'ai confiance. Je suis furieux. Voici le résultat. J'ai confiance."
        raw = analyze_passages(source, mode="thematic", start=17)
        events = MoodTracker().feed(raw)
        self.assertEqual([event.dominant.name for event in events], ["espoir"] * 4)
        self.assertEqual([event.tone for event in events], [event.tone for event in raw])
        self.assertEqual(''.join(event.text for event in events), source)
        self.assertEqual(events[0].start, 17)
        self.assertEqual(events[-1].end, 17 + len(source))
        self.assertIsInstance(events[0], FieldEvent)
        with self.assertRaises(FrozenInstanceError):
            events[0].dominant = Tone()

    def test_two_consecutive_new_passages_allow_a_coherent_pivot(self):
        raw = analyze_passages("J'ai confiance. Je suis furieux. Je suis vraiment en colère.", mode="thematic")
        tracker = MoodTracker()
        events = tuple(event for passage in raw for event in tracker.feed((passage,)))
        self.assertEqual([event.dominant.name for event in events], ["espoir", "espoir", "colère"])
        self.assertEqual(MoodTracker().feed(raw), events)
        self.assertEqual(tracker.dominant.name, "colère")

    def test_explicit_affirmed_narrative_pivot_does_not_wait_for_second_passage(self):
        for passage in ("Désormais, je suis apaisé.", "Maintenant, tout va bien.",
                        "Enfin, je suis calme.", "Je suis enfin serein."):
            with self.subTest(passage=passage):
                raw = analyze_passages("Je suis furieux. " + passage, mode="thematic")
                events = MoodTracker().feed(raw)
                self.assertEqual(events[-1].dominant.name, "apaisement")
                self.assertEqual(events[-1].tone.name, "apaisement")

    def test_quoted_pivot_markers_and_unreliable_evidence_do_not_force_pivot(self):
        tracker = MoodTracker()
        tracker.feed(analyze_passages("J'ai confiance.", mode="thematic"))
        event = tracker.feed(analyze_passages("Je suis calme « désormais ».", mode="thematic"))[-1]
        self.assertEqual(event.dominant.name, "espoir")
        weak = Tone("apaisement", TONES["apaisement"][0], ("calme",), 0.3)
        events = tracker.feed((ToneEvent(0, 5, "calme", weak),) * 3)
        self.assertTrue(all(event.dominant.name == "espoir" for event in events))
        tracker.feed(analyze_passages("Voici le résultat.", mode="thematic"))
        event = tracker.feed(analyze_passages("Je suis calme.", mode="thematic"))[-1]
        self.assertEqual(event.dominant.name, "espoir")

    def test_ambiguous_initial_passages_stay_cyan_and_reset_clears_response(self):
        tracker = MoodTracker()
        events = tracker.feed(analyze_passages('« Je suis furieux ». Je ne suis pas calme. Peur et espoir.', mode="thematic"))
        self.assertTrue(all(event.dominant == Tone() for event in events))
        tracker.feed(analyze_passages("J'ai confiance.", mode="thematic"))
        tracker.reset()
        self.assertEqual(tracker.dominant, Tone())
        self.assertEqual(tracker.feed(()), ())
        event = tracker.feed(analyze_passages("Je suis furieux.", mode="thematic"))[0]
        self.assertEqual(event.dominant.name, "colère")

    def test_neutral_mode_and_mode_validation(self):
        raw = analyze_passages("Je suis furieux. Maintenant je suis calme.", mode="thematic")
        events = MoodTracker(mode="neutral").feed(raw)
        self.assertTrue(all(event.tone == Tone() and event.dominant == Tone() for event in events))
        with self.assertRaises(ValueError):
            MoodTracker(mode="unknown")

    def test_long_response_keeps_no_event_or_source_history(self):
        import gc
        import weakref

        tracker = MoodTracker()
        event = analyze_passages("J'ai confiance.", mode="thematic")[0]
        reference = weakref.ref(event)
        tracker.feed((event,))
        del event
        gc.collect()
        self.assertIsNone(reference())
        for _ in range(1000):
            tracker.feed(analyze_passages("Je suis furieux. J'ai confiance.", mode="thematic"))
        self.assertEqual(tracker.dominant.name, "espoir")
        self.assertLessEqual(tracker._candidate_count, 1)
