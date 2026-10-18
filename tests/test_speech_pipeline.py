"""Source-preserving text -> real worker protocol (no model or device required)."""
import pickle
import queue
import unittest
from dataclasses import replace
from unittest.mock import patch

from jarvis.audio import AudioEvent
from jarvis.richtext import SpeechBuffer, parse_text
from jarvis.tts import PCM, SpeechText
from jarvis.voice_config import VoiceSettings
from jarvis.voice_runtime import speech_worker


class SpeechPipelineTests(unittest.TestCase):
    def test_windows_spawn_serialization_preserves_source_and_visual_events(self):
        source = "**Bonjour** 👩🏽‍🚀, voici [le guide](https://example.org)."
        segment = SpeechBuffer().feed(source, final=True)[0]
        command = SpeechText(segment.text, original=segment.original,
            display_text=parse_text(segment.original).text, start=segment.start,
            end=segment.end, events=segment.events, segment_id=7)
        restored = pickle.loads(pickle.dumps(command))
        self.assertEqual(str(restored), segment.text)
        self.assertEqual(restored.__dict__, command.__dict__)
        self.assertIn("👩🏽‍🚀", restored.display_text)
        self.assertNotIn("👩", str(restored))

    def test_pcm_callback_captions_retain_emoji_while_piper_receives_only_speech(self):
        source = "**Bonjour** ❤️, le prix est $12."
        document = parse_text(source)
        command = SpeechText(document.speech, original=source, display_text=document.text,
            start=12, end=12 + len(source), events=document.events, segment_id=3)
        outbox, inbox = queue.Queue(), queue.Queue()
        inbox.put(pickle.loads(pickle.dumps(command)))
        inbox.put(None)
        pcm = PCM([0.1], 16000)

        def played(pcm, text, emit, generation):
            self.assertEqual(text, document.speech)
            emit(AudioEvent("played", {"text": text, "fraction": 0.5,
                "rms": 0.1, "delay": 0.02, "started_at": 2.0}, generation))

        with patch("jarvis.tts.PiperSpeech") as piper, patch("jarvis.tts.AudioPlayer") as player:
            piper.return_value.synthesize.return_value = [pcm]
            player.return_value.play.side_effect = played
            speech_worker(outbox, inbox, VoiceSettings().to_dict(), 9)
        piper.return_value.synthesize.assert_called_once_with(document.speech)
        events = list(outbox.queue)
        self.assertEqual([event.kind for event in events],
            ["tts_ready", "tts_pcm_ready", "played", "speech_done"])
        event = events[2]
        self.assertEqual(event.generation, 9)
        self.assertEqual(event.payload["text"], document.text)
        self.assertIn("❤️", event.payload["text"])
        self.assertNotIn("❤️", event.payload["spoken_text"])
        self.assertEqual(event.payload["original_start"], 12)
        self.assertEqual(event.payload["segment_id"], 3)
        self.assertIn("approximatif", event.payload["alignment"])
        self.assertTrue(any(item["kind"] == "emoji" for item in event.payload["text_events"]))
        self.assertEqual(event.payload["delay"], 0.02)

    def test_code_reading_is_explicit_and_preferences_round_trip(self):
        self.assertFalse(VoiceSettings().speak_code)
        enabled = replace(VoiceSettings(), speak_code=True).validate()
        self.assertEqual(VoiceSettings(**enabled.to_dict()), enabled)
        with self.assertRaisesRegex(ValueError, "lecture du code"):
            replace(enabled, speak_code="false").validate()
        source = "```python\nprint(42)\n```"
        self.assertIn("non lu", parse_text(source).speech)
        self.assertIn("42", parse_text(source, speak_code=True).speech)


if __name__ == "__main__":
    unittest.main()
