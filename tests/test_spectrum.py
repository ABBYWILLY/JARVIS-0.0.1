import unittest
from jarvis.spectrum import OPERATIONAL, ToneAnalyzer, caption_group, keyword_spans


class SpectrumTests(unittest.TestCase):
    def test_ambiguous_and_single_word_stay_cyan(self):
        analyzer = ToneAnalyzer()
        self.assertEqual(analyzer.update("Le mot colère figure ici", now=0).name, "neutralité")
        self.assertEqual(analyzer.update("colère espoir peur", now=5).name, "neutralité")

    def test_conservative_majority_and_inertia(self):
        analyzer = ToneAnalyzer()
        angry = analyzer.update("Une colère et une rage explicites", now=0)
        self.assertEqual(angry.name, "colère")
        self.assertEqual(analyzer.update("espoir confiance", now=1), angry)
        self.assertEqual(analyzer.update("espoir confiance", now=4).name, "espoir")
        self.assertEqual(analyzer.update("texte ambigu", now=8).name, "neutralité")

    def test_explicit_negation_stays_neutral(self):
        self.assertEqual(ToneAnalyzer().update("aucune colère et pas de rage").name, "neutralité")

    def test_only_selected_words_not_whole_paragraph(self):
        text = "La COLÈRE et la rage, mais le reste est ordinaire."
        tone = ToneAnalyzer().update(text)
        spans = keyword_spans(text, tone.words)
        self.assertEqual([text[a:b] for a, b in spans], ["COLÈRE", "rage"])

    def test_emotion_never_mutates_operational_spectrum(self):
        original = {key: dict(value) for key, value in OPERATIONAL.items()}
        ToneAnalyzer().update("mort et deuil")
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
