"""Real Tk/SQLite command routing with designated audio-process doubles.

No microphone, Piper inference or acoustic echo cancellation is validated here.
"""
import unittest
from dataclasses import replace
from unittest.mock import Mock, patch

from jarvis.audio import AudioEvent
from jarvis.tts import SpeechText
from tests import test_voice_flow as flows
from tests.test_jarvis import display_available


class PresenceCommandRecorder(flows.SemanticPresenceRecorder):
    def __init__(self):
        super().__init__()
        self.begins = 0

    def begin_response(self):
        self.begins += 1


@unittest.skipUnless(display_available(), "Écran graphique indisponible")
class VoiceCommandsUITests(unittest.TestCase):
    # Reuse setup only: inheriting VoiceFlowTests would rerun its entire suite.
    setUp = flows.VoiceFlowTests.setUp
    close_app = flows.VoiceFlowTests.close_app
    activate = flows.VoiceFlowTests.activate

    def archive(self, content):
        mid = self.store.begin_turn(self.app.session_id, "Question", "local", source="voice")
        self.store.update_response(mid, content, "complete")
        return mid

    def transcript(self, text, generation=1, *, speech_start=True, now=10.):
        if speech_start:
            self.voice.capture.events.append(AudioEvent("speech_start", generation=generation))
        self.voice.capture.events.append(AudioEvent("transcript", text, generation))
        with patch("jarvis.voice_ui.time.monotonic", return_value=now):
            self.voice.poll()

    def played(self, text, *, start=0, end=None, now=10., delay=0.):
        self.voice.speech.events.append(AudioEvent("played", {
            "text": text, "spoken_text": text, "original_start": start,
            "original_end": len(text) if end is None else end,
            "fraction": .5, "rms": .1, "wave": [.1, -.1],
            "emitted_at": now, "started_at": now + delay, "delay": delay,
            "response_id": self.voice.epoch, "segment_id": 1,
        }, self.voice.epoch))
        with patch("jarvis.voice_ui.time.monotonic", return_value=now):
            self.voice.poll()

    def test_confirmed_microphone_stop_routes_locally_and_preserves_listening(self):
        self.activate("headphones")
        self.app.send = Mock()
        epoch = self.voice.epoch
        self.transcript("Stop !")
        self.app.send.assert_not_called()
        self.assertGreater(self.voice.epoch, epoch)
        self.assertTrue(self.voice.listening)
        self.assertTrue(self.voice.capture.alive())
        self.assertFalse(self.voice.tts_active)
        self.assertTrue(any("voice_command · stop" in event for event in self.voice.diagnostic_events))

    def test_quotes_dictation_and_embedded_commands_remain_original_conversation(self):
        self.activate("headphones")
        self.app.send = Mock()
        for generation, text in enumerate(('« Stop »', "Écris le mot répète.",
                                            "Je dis continue dans mon récit.", "Ne parle pas moins vite."), 1):
            with self.subTest(text=text):
                self.app.send.reset_mock()
                with patch.object(self.voice, "handle_command") as command:
                    self.transcript(text, generation)
                command.assert_not_called()
                self.app.send.assert_called_once_with(source="voice", text=text)

    def test_transcript_without_accepted_speech_start_cannot_be_a_command(self):
        self.activate("headphones")
        self.app.send = Mock()
        with patch.object(self.voice, "handle_command") as command:
            self.transcript("Stop", generation=0, speech_start=False)
        command.assert_not_called()
        self.assertIsNone(self.voice.confirmed_turn)

    def test_late_transcript_is_ignored_while_speaker_microphone_is_suspended(self):
        self.activate("speakers")
        self.voice.heard = self.voice.confirmed_turn = 2
        self.voice.set_mic_state("suspended", "Lecture haut-parleurs")
        self.app.send = Mock()
        with patch.object(self.voice, "handle_command") as command:
            self.transcript("Stop", generation=2, speech_start=False)
        command.assert_not_called()
        self.app.send.assert_not_called()
        self.assertEqual(self.voice.microphone_state, "suspended")
        self.assertTrue(any("Microphone suspendu" in event for event in self.voice.diagnostic_events))

    def test_recent_actual_playback_blocks_own_command_words_during_overlap(self):
        self.activate("headphones")
        text = "Pour interrompre, dites stop."
        mid = self.archive(text)
        self.voice.begin_turn(mid, "voice")
        self.voice.chunk(text)
        self.played(text, now=10.)
        self.assertIn(text, self.voice.recent_output)
        self.app.send = Mock()
        with patch.object(self.voice, "handle_command") as command:
            self.transcript("Stop", now=10.1)
        command.assert_not_called()
        self.app.send.assert_not_called()
        self.assertFalse(self.voice.tts_active)
        self.assertTrue(any("écho possible" in event for event in self.voice.diagnostic_events))
        # The same deliberate command is eligible on a fresh turn after playback.
        with patch.object(self.voice, "handle_command", wraps=self.voice.handle_command) as command:
            self.transcript("Stop", generation=2, now=12.)
        command.assert_called_once_with("stop")

    def test_pending_playback_conservatively_shields_commands_without_claiming_pcm_played(self):
        self.activate("headphones")
        text = "Pour interrompre, dites stop."
        mid = self.archive(text)
        self.voice.begin_turn(mid, "voice")
        self.voice.chunk(text)
        self.assertFalse(self.voice.recent_output)
        self.assertEqual(self.voice.replay_offset, 0)
        self.assertTrue(self.voice.tts_active)
        with patch.object(self.voice, "handle_command", wraps=self.voice.handle_command) as command:
            self.transcript("Stop")
        # Worker PCM callbacks can be queued behind capture events. The shield
        # intentionally covers submitted output, but never advances playback.
        command.assert_not_called()
        self.assertFalse(self.voice.recent_output)
        self.assertEqual(self.voice.replay_offset, 0)
        self.assertTrue(any("écho possible" in event for event in self.voice.diagnostic_events))

    def test_actual_playback_stays_echo_guarded_when_eight_later_phrases_are_submitted(self):
        self.activate("headphones")
        text = "Pour interrompre, dites stop."
        mid = self.archive(text)
        self.voice.begin_turn(mid, "voice")
        self.voice.chunk(text)
        self.played(text, now=10.)
        for index in range(8):
            self.voice.chunk(f"Une autre phrase à venir numéro {index}. ")
        self.assertEqual(len(self.voice.submitted_output), 8)
        self.assertNotIn(text, self.voice.submitted_output)
        self.assertIn(text, self.voice.recent_output)
        self.app.send = Mock()
        with patch.object(self.voice, "handle_command") as command:
            self.transcript("Stop", now=10.1)
        command.assert_not_called()
        self.app.send.assert_not_called()
        self.assertTrue(any("écho possible" in event for event in self.voice.diagnostic_events))

    def test_duplicate_transcript_for_same_generation_executes_once(self):
        self.activate("headphones")
        self.app.send = Mock()
        with patch.object(self.voice, "handle_command", wraps=self.voice.handle_command) as command:
            self.transcript("Stop")
            self.transcript("Stop", speech_start=False)
        command.assert_called_once_with("stop")
        self.app.send.assert_not_called()
        self.assertIsNone(self.voice.confirmed_turn)
        self.assertTrue(any("Tour déjà traité" in event for event in self.voice.diagnostic_events))

    def test_repeat_reads_sqlite_without_new_llm_and_resets_presence_generation(self):
        recorder = self.app.presence = PresenceCommandRecorder()
        self.activate("headphones")
        text = "**Bonjour** à nouveau 😊. Voici la suite."
        mid = self.archive(text)
        self.app.send = Mock()
        previous_epoch = self.voice.epoch
        self.assertTrue(self.voice.handle_command("repeat"))
        self.app.send.assert_not_called()
        self.assertGreater(self.voice.epoch, previous_epoch)
        self.assertEqual(recorder.begins, 1)
        self.assertEqual(self.voice.replay_mid, mid)
        self.assertEqual(self.voice.replay_session, self.app.session_id)
        self.assertEqual(self.voice.source_offset, 0)
        phrases = [command for command in self.voice.speech.commands if command is not None]
        self.assertTrue(phrases)
        self.assertNotIn("**", str(phrases[0]))
        self.assertIn("😊", phrases[0].original)
        self.assertEqual(phrases[0].response_id, self.voice.epoch)
        self.assertEqual(self.store.message(mid)["content"], text)

    def test_resume_starts_at_dac_observed_segment_not_last_queued_segment(self):
        recorder = self.app.presence = PresenceCommandRecorder()
        self.activate("headphones")
        first, second, third = "Première phrase. ", "Deuxième phrase. ", "Troisième phrase."
        text = first + second + third
        mid = self.archive(text)
        self.voice.begin_turn(mid, "voice")
        self.voice.chunk(text)
        self.voice.finish_turn("complete")
        self.assertEqual(self.voice.replay_offset, 0)  # Queueing is not playback.
        self.played(second, start=len(first), end=len(first + second), now=10.)
        self.assertEqual(self.voice.replay_offset, len(first))
        # A queued PCM callback for the next phrase must not advance the cursor.
        self.played(third, start=len(first + second), now=10.1, delay=2.)
        self.assertEqual(self.voice.replay_offset, len(first))
        old_epoch = self.voice.epoch
        self.app.send = Mock()
        self.voice.cancel_speech()
        self.assertTrue(self.voice.handle_command("resume"))
        self.app.send.assert_not_called()
        self.assertGreater(self.voice.epoch, old_epoch)
        self.assertEqual(self.voice.source_offset, len(first))
        self.assertFalse(self.voice.pending_visuals)
        self.assertEqual(recorder.begins, 2)
        phrases = [command for command in self.voice.speech.commands if command is not None]
        self.assertEqual(phrases[-2].start, len(first))
        self.assertTrue(phrases[-2].original.startswith(second.strip()))
        self.assertEqual(self.store.message(mid)["content"], text)

    def test_long_archive_resume_applies_backpressure_and_preserves_every_source_offset(self):
        self.activate("headphones")
        prefix = "Premier passage déjà lu. "
        remaining = "".join(f"Phrase suivante numéro {index}. " for index in range(200))
        original = prefix + remaining
        mid = self.archive(original)
        self.voice.replay_mid = mid
        self.voice.replay_session = self.app.session_id
        self.voice.replay_offset = len(prefix)
        self.app.send = Mock()
        # The process can start, while its bounded command channel temporarily
        # refuses new phrases. The archive must not be eagerly queued/dropped.
        self.voice.speech.accept_commands = False
        self.assertTrue(self.voice.replay_response(resume=True))
        with patch("jarvis.voice_ui.time.monotonic", return_value=10.):
            for _ in range(4):
                self.voice.poll()
            paused_cursor = self.voice.replay_cursor
            paused_pending = len(self.voice.pending_phrases)
            for _ in range(8):
                self.voice.poll()
        self.assertTrue(self.voice.reading)
        self.assertEqual(self.voice.replay_cursor, paused_cursor)
        self.assertLess(paused_cursor, len(remaining))
        self.assertGreater(paused_pending, 0)
        self.assertLess(paused_pending, self.voice.pending_phrases.maxlen)
        self.assertNotIn(None, self.voice.speech.commands)
        self.voice.speech.accept_commands = True
        largest_pending = paused_pending
        with patch("jarvis.voice_ui.time.monotonic", return_value=10.):
            for _ in range(2000):
                self.voice.poll()
                largest_pending = max(largest_pending, len(self.voice.pending_phrases))
                if None in self.voice.speech.commands:
                    break
            else:
                self.fail("La fin de relecture n’a pas été transmise après libération de la file.")
        phrases = [command for command in self.voice.speech.commands if isinstance(command, SpeechText)]
        self.assertEqual(len(phrases), 200)
        self.assertEqual("".join(phrase.original for phrase in phrases), remaining)
        cursor = len(prefix)
        for phrase in phrases:
            with self.subTest(segment=phrase.segment_id):
                self.assertEqual(phrase.start, cursor)
                self.assertEqual(phrase.end, cursor + len(phrase.original))
                self.assertEqual(phrase.response_id, self.voice.epoch)
            cursor = phrase.end
        self.assertEqual(cursor, len(original))
        self.assertLess(largest_pending, self.voice.pending_phrases.maxlen)
        self.assertEqual(self.voice.speech.commands.count(None), 1)
        self.assertIsNone(self.voice.speech.commands[-1])
        self.assertFalse(self.voice.pending_phrases)
        self.assertTrue(self.voice.tts_active)
        self.app.send.assert_not_called()
        self.assertEqual(self.store.message(mid)["content"], original)

    def test_stopping_long_archive_replay_clears_source_and_prevents_later_submissions(self):
        self.activate("headphones")
        original = "".join(f"Une phrase à lire numéro {index}. " for index in range(200))
        mid = self.archive(original)
        self.voice.speech.accept_commands = False
        self.assertTrue(self.voice.replay_response())
        self.assertTrue(self.voice.replay_source)
        self.assertTrue(self.voice.pending_phrases)
        epoch = self.voice.epoch
        self.assertTrue(self.voice.handle_command("stop"))
        self.assertGreater(self.voice.epoch, epoch)
        self.assertFalse(self.voice.replay_source)
        self.assertFalse(self.voice.pending_phrases)
        self.assertFalse(self.voice.reading)
        self.assertFalse(self.voice.tts_active)
        sent_before = self.voice.speech.commands[:]
        self.voice.speech.accept_commands = True
        with patch("jarvis.voice_ui.time.monotonic", return_value=10.):
            for _ in range(10):
                self.voice.poll()
        self.assertEqual(self.voice.speech.commands, sent_before)
        self.assertTrue(self.voice.listening)
        self.assertEqual(self.store.message(mid)["content"], original)

    def test_continue_uses_existing_continuation_route(self):
        self.activate("headphones")
        self.app.continuation_id = self.archive("Le récit s'interrompt ici.")
        self.app.send = Mock()
        with patch.object(self.app, "continue_response") as continuation:
            self.transcript("Continue")
        continuation.assert_called_once_with()
        self.app.send.assert_not_called()

    def test_expand_sends_explicit_bounded_archive_excerpt_through_normal_context(self):
        text = "Introduction. " + "Phrase archivée à développer. " * 80
        mid = self.archive(text)
        self.voice.replay_mid = mid
        self.app.send = Mock()
        self.assertTrue(self.voice.handle_command("expand"))
        self.app.send.assert_called_once_with(text=(
            "Développe ce passage de ta réponse (extrait original, sans inventer de faits) :\n\n"
            + text[-1500:]))
        self.assertNotIn("continuation", self.app.send.call_args.kwargs)
        self.assertEqual(self.store.message(mid)["content"], text)

    def test_actions_reopen_cleanly_and_delayed_resume_is_cancelled_on_stop(self):
        first = self.voice.open_actions()
        first.destroy()
        second = self.voice.open_actions()
        self.root.update()
        self.assertIsNot(second, first)
        self.assertEqual(len(second.controls), 6)
        self.activate("speakers")
        self.voice.schedule_resume()
        callback = self.voice.resume_id
        self.assertIn(callback, self.root.tk.call("after", "info"))
        self.voice.stop_listening()
        self.assertIsNone(self.voice.resume_id)
        self.assertNotIn(callback, self.root.tk.call("after", "info"))
        second.destroy()

    def test_slower_persists_bounded_speed_without_changing_other_preferences(self):
        self.voice.settings = replace(self.voice.settings, speed=.6, voice="fr_FR-siwis-medium",
                                      input_device="Microphone choisi", silence_ms=1100)
        before = self.voice.settings.to_dict()
        self.assertTrue(self.voice.handle_command("slower"))
        self.assertTrue(self.voice.handle_command("slower"))
        saved = self.store.get_preference("voice")
        self.assertEqual(saved, {**before, "speed": .5})
        self.assertEqual(self.voice.settings.speed, .5)
        self.assertFalse(self.voice.capture.starts)
        self.assertFalse(self.voice.speech.starts)

    def test_explicit_actions_are_reused_focusable_buttons_without_microphone(self):
        dialog = self.voice.open_actions()
        dialog.geometry("360x480")
        self.root.update()
        self.assertIs(self.voice.open_actions(), dialog)
        self.assertEqual(set(dialog.controls), {"stop", "repeat", "resume", "continue", "slower", "expand"})
        with patch.object(self.voice, "handle_command") as action:
            for name, button in dialog.controls.items():
                with self.subTest(name=name):
                    self.assertTrue(button.winfo_viewable())
                    self.assertLessEqual(button.winfo_rooty() + button.winfo_height(),
                                         dialog.winfo_rooty() + dialog.winfo_height())
                    button.focus_force()
                    self.root.update()
                    self.assertIs(dialog.focus_get(), button)
                    button.invoke()
                    action.assert_called_with(name)
        self.assertFalse(self.voice.listening)
        self.assertFalse(self.voice.capture.starts)
        dialog.destroy()

    def test_actions_scroll_into_view_on_keyboard_focus_in_small_high_dpi_window(self):
        scaling = self.root.tk.call("tk", "scaling")
        self.addCleanup(lambda: self.root.tk.call("tk", "scaling", scaling))
        self.root.tk.call("tk", "scaling", 1.75)
        dialog = self.voice.open_actions()
        dialog.geometry("300x320")
        self.root.update()
        canvas = next(child for frame in dialog.winfo_children() for child in frame.winfo_children()
                      if child.winfo_class() == "Canvas")
        for button in dialog.controls.values():
            button.focus_force()
            self.root.update()
            with self.subTest(button=str(button)):
                self.assertIs(dialog.focus_get(), button)
                self.assertGreaterEqual(button.winfo_rooty(), canvas.winfo_rooty())
                self.assertLessEqual(button.winfo_rooty() + button.winfo_height(),
                                     canvas.winfo_rooty() + canvas.winfo_height())
        self.assertFalse(self.voice.capture.starts)
        dialog.destroy()


if __name__ == "__main__":
    unittest.main()
