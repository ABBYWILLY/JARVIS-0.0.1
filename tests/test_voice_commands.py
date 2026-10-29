"""Commands are opt-in, whole user utterances, never cleaned model text."""
import unicodedata
import unittest

from jarvis.voice_commands import COMMANDS, command_echo, recognize_command


class VoiceCommandTests(unittest.TestCase):
    def recognize(self, text, **kwargs):
        return recognize_command(text, confirmed_user_turn=True, **kwargs)

    def test_required_commands_and_explicit_resume(self):
        examples = {
            "Stop": "stop", "Arrête !": "stop", "Répète.": "repeat",
            "Répète la réponse": "repeat", "Reprends": "resume",
            "Reprends la lecture.": "resume", "Continue": "continue",
            "Continue la réponse": "continue", "Plus lentement": "slower",
            "Parle moins vite.": "slower", "Ralentis": "slower",
            "Développe ce passage": "expand",
        }
        self.assertEqual(COMMANDS, frozenset(examples.values()))
        for text, action in examples.items():
            with self.subTest(text=text):
                self.assertEqual(self.recognize(text), action)

    def test_case_whitespace_nfc_nfd_and_unaccented_stt(self):
        for text in ("  RÉPÈTE ! \n", "repete", "  Jarvis, répète !",
                     "JARVIS REPETE.", "parle\tmoins   vite",
                     "\u00a0Jarvis,\u00a0répète\u202f!\u00a0",
                     unicodedata.normalize("NFD", "répète")):
            with self.subTest(text=text):
                expected = "slower" if text.startswith("parle") else "repeat"
                self.assertEqual(self.recognize(text), expected)

    def test_confirmation_is_required_and_is_not_merely_truthy(self):
        self.assertIsNone(recognize_command("Stop"))
        for confirmation in (False, None, 0, 1, "True"):
            with self.subTest(confirmation=confirmation):
                self.assertIsNone(recognize_command("Stop", confirmed_user_turn=confirmation))

    def test_only_microphone_is_an_eligible_source(self):
        for source in ("text", "voice", "assistant", "piper", "history", "pcm", "", None):
            with self.subTest(source=source):
                self.assertIsNone(self.recognize("Stop", source=source))

    def test_quoted_commands_never_execute(self):
        for text in ('"Stop"', "'Stop'", "« Stop »", "“Stop”", "‘Stop’",
                     "Jarvis, « Continue »", "Il a dit : Stop.",
                     'La phrase est "Répète".', "Dis « Continue »."):
            with self.subTest(text=text):
                self.assertIsNone(self.recognize(text))

    def test_code_markdown_lists_and_examples_never_execute(self):
        for text in ("`Stop`", "```\nStop\n```", "**Stop**", "# Stop",
                     "- Continue", "1. Répète", "Exemple : Stop", "Stop :"):
            with self.subTest(text=text):
                self.assertIsNone(self.recognize(text))

    def test_dictation_negation_and_embedded_commands_remain_text(self):
        for text in ("Écris Stop", "Je dicte : continue", "Dicte stop",
                     "Le panneau Stop est rouge.", "Ne répète pas", "Ne dis pas Stop",
                     "Que signifie plus lentement", "Continue est un mot",
                     "Je veux que tu dises répète", "Arrête de dire stop",
                     "Stop et répète", "Répète le mot stop"):
            with self.subTest(text=text):
                self.assertIsNone(self.recognize(text))

    def test_ambiguous_questions_remain_conversation(self):
        for text in ("Stop ?", "Continue?", "Répète ?!", "Plus lentement ?"):
            with self.subTest(text=text):
                self.assertIsNone(self.recognize(text))

    def test_controls_invisible_characters_and_multiline_are_rejected(self):
        for text in ("sto\u200bp", "Stop\u200d", "\ufeffStop", "Stop\x00",
                     "Répète\nla réponse", "Stop\nContinue", "Stop\u202e",
                     "Stop\ufe0f", "Stop\u20e3"):
            with self.subTest(text=text):
                self.assertIsNone(self.recognize(text))

    def test_invalid_or_unbounded_input_is_not_a_command(self):
        for value in (None, b"Stop", 7, "", "  ", "Stop" + " " * 121):
            with self.subTest(value=value):
                self.assertIsNone(self.recognize(value))

    def test_matching_preserves_original_text(self):
        original = unicodedata.normalize("NFD", "  JARVIS, Répète ! ")
        saved = original[:]
        self.assertEqual(self.recognize(original), "repeat")
        self.assertEqual(original, saved)

    def test_echo_guard_matches_actual_command_words_in_recent_playback(self):
        cases = (
            ("Stop", "Si besoin, dites stop."),
            ("Jarvis, répète !", "Vous pouvez dire « répète »."),
            ("Répète la réponse", "Dites : **RÉPÈTE LA RÉPONSE**."),
            ("Parle moins vite", "Le réglage est : parle — moins vite."),
            ("Continue.", "Un exemple de commande est `continue`."),
            ("Développe ce passage", unicodedata.normalize("NFD", "Développe ce passage.")),
        )
        for text, spoken in cases:
            with self.subTest(text=text, spoken=spoken):
                self.assertTrue(command_echo(text, ["Une autre phrase.", spoken]))

    def test_echo_guard_requires_complete_contiguous_words(self):
        for text, spoken in (
            ("Stop", "Le moteur est stoppé."),
            ("Répète", "Je vais répéter."),
            ("Continue", "La continuation est enregistrée."),
            ("Répète la réponse", "Répète seulement la réponse."),
            ("Plus lentement", "Je parle moins vite."),
        ):
            with self.subTest(text=text, spoken=spoken):
                self.assertFalse(command_echo(text, [spoken]))

    def test_echo_guard_handles_empty_and_bounded_history(self):
        for text, history in ((None, ["Stop"]), ("", ["Stop"]),
                              ("Jarvis", ["Jarvis"]), ("Stop", None),
                              ("Stop", []), ("Stop", [None, 7])):
            with self.subTest(text=text, history=history):
                self.assertFalse(command_echo(text, history))
        self.assertTrue(command_echo("Stop", "Dites stop."))
        self.assertTrue(command_echo("Stop", ["Autre"] * 8 + ["Stop"]))
        self.assertFalse(command_echo("Stop", ["Autre"] * 16 + ["Stop"]))
        self.assertFalse(command_echo("Stop", ["x " * 4096 + " Stop"]))


if __name__ == "__main__":
    unittest.main()
