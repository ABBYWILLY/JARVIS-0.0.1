"""Natural voice integration: real Tk/SQLite, explicit audio process doubles.

These checks cover routing and lifetime contracts, not microphone capture,
Piper sound quality, acoustic echo cancellation or physical Windows latency.
"""
import sqlite3
import unittest
from dataclasses import replace
from unittest.mock import patch

from jarvis.audio import AudioEvent
from jarvis.voice_config import SPEECH_PROFILES, VoiceSettings
from tests import test_voice_flow as flows
from tests.test_jarvis import display_available


class NaturalVoiceSettingsTests(unittest.TestCase):
    def test_legacy_preferences_keep_devices_voice_speed_and_default_to_normal(self):
        original = {"voice": "fr_FR-siwis-medium", "speed": 1.25,
                    "input_device": "USB · MME", "output_device": "Bluetooth · MME",
                    "silence_ms": 1100, "vad_threshold": .72}
        settings = VoiceSettings(**original).validate()
        for key, value in original.items():
            self.assertEqual(getattr(settings, key), value)
        self.assertEqual(settings.speech_profile, "normal")
        self.assertEqual(settings.resume_delay_ms, 350)
        self.assertEqual(set(SPEECH_PROFILES), {"normal", "technical", "story", "brief"})

    def test_invalid_profile_or_resume_delay_is_rejected(self):
        for value in (True, 99, 1501, 350.5):
            with self.subTest(delay=value), self.assertRaises(ValueError):
                VoiceSettings(resume_delay_ms=value).validate()
        with self.assertRaises(ValueError):
            VoiceSettings(speech_profile="invented").validate()


@unittest.skipUnless(display_available(), "Écran graphique indisponible")
class NaturalVoiceIntegrationTests(unittest.TestCase):
    setUp = flows.VoiceFlowTests.setUp
    close_app = flows.VoiceFlowTests.close_app
    activate = flows.VoiceFlowTests.activate

    def archive(self, content="Première phrase. Deuxième phrase."):
        mid = self.store.begin_turn(self.app.session_id, "Question", "local", source="voice")
        self.store.update_response(mid, content, "complete")
        return mid

    def phrases(self):
        return [command for command in self.voice.speech.commands
                if command is not None and hasattr(command, "rate")]

    def test_replay_after_interruption_and_slower_applies_speed_only_once(self):
        self.activate("headphones")
        mid = self.archive()
        self.voice.replay_mid = mid
        self.voice.prepare_speech()
        self.voice.tts_active = True
        self.voice.cancel_speech()
        self.assertFalse(self.voice.speech.alive())
        self.assertTrue(self.voice.handle_command("slower"))
        self.assertTrue(self.voice.handle_command("repeat"))
        self.assertEqual(self.voice.tts_profile.speed, .9)
        self.assertEqual(len(self.voice.speech.starts), 2)
        phrases = self.phrases()
        self.assertEqual(len(phrases), 2)
        for phrase in phrases:
            self.assertEqual(phrase.rate, 1.)
            self.assertAlmostEqual(self.voice.tts_profile.speed * phrase.rate, .9)

    def test_speed_change_reuses_idle_piper_and_adjusts_per_segment_rate(self):
        self.activate("headphones")
        self.voice.replay_mid = self.archive()
        self.voice.prepare_speech()
        original_process = self.voice.speech.process
        self.assertTrue(self.voice.handle_command("slower"))
        self.assertTrue(self.voice.handle_command("repeat"))
        self.assertIs(self.voice.speech.process, original_process)
        self.assertEqual(len(self.voice.speech.starts), 1)
        self.assertEqual(self.voice.tts_profile.speed, 1.)
        for phrase in self.phrases():
            self.assertAlmostEqual(phrase.rate, .9)
            self.assertAlmostEqual(self.voice.tts_profile.speed * phrase.rate, .9)
        self.assertEqual(self.store.get_preference("voice")["speed"], .9)

    def test_enabling_speakers_microphone_during_preview_mutes_before_capture_ready(self):
        recorder = self.app.presence = flows.SemanticPresenceRecorder()
        self.voice.preview()
        self.voice.notify_presence("jarvis_speaking")
        recorder.events.clear()
        with patch("jarvis.voice_ui.messagebox.askyesno", return_value=True):
            self.voice.toggle()
        self.assertTrue(self.voice.listening)
        self.assertTrue(self.voice.tts_active)
        self.assertEqual(self.voice.capture.commands, [{"kind": "mute", "value": True}])
        self.assertEqual(self.voice.microphone_state, "suspended")
        self.voice.capture.events.append(AudioEvent("listening", {"capture_status": "open"}))
        self.voice.poll()
        self.assertEqual(self.voice.microphone_state, "suspended")
        self.assertEqual(recorder.state, "jarvis_speaking")
        self.assertNotIn("listening", [state for state, _ in recorder.events])
        self.assertTrue(self.voice.speech.alive())

    def test_enabling_microphone_fails_closed_if_speaker_mute_cannot_be_sent(self):
        self.voice.preview()
        self.voice.capture.accept_commands = False
        with patch("jarvis.voice_ui.messagebox.askyesno", return_value=True):
            self.voice.toggle()
        self.assertFalse(self.voice.listening)
        self.assertFalse(self.voice.capture.alive())
        self.assertFalse(self.voice.speech.alive())
        self.assertFalse(self.voice.tts_active)
        self.assertEqual(self.voice.microphone_state, "error")
        self.assertIn("suspension", self.voice.status.get().casefold())

    def test_all_speech_profiles_persist_in_existing_voice_preference_and_keep_devices(self):
        original = replace(self.voice.settings, voice="fr_FR-siwis-medium", speed=1.2,
                           input_device="USB · MME", output_device="Bluetooth · MME",
                           silence_ms=1100, vad_threshold=.72)
        self.voice.settings = original
        for key, (label, _rate, _pause) in SPEECH_PROFILES.items():
            with self.subTest(profile=key), patch("jarvis.audio.device_inventory", return_value={
                "input": [{"key": original.input_device}],
                "output": [{"key": original.output_device}]}):
                dialog = self.voice.open_settings()
                self.root.setvar(dialog.controls["speech_profile"].cget("textvariable"), label)
                self.root.setvar(dialog.controls["resume_delay_ms"].cget("textvariable"), "500")
                dialog.save_button.invoke()
                saved = self.store.get_preference("voice")
                self.assertEqual(saved, {**original.to_dict(), "speech_profile": key, "resume_delay_ms": 500})
                self.assertEqual(self.voice.settings.to_dict(), saved)
        self.assertFalse(self.voice.capture.starts)
        self.assertFalse(self.voice.speech.starts)

    def test_database_failure_in_command_stops_audio_without_touching_original_archive(self):
        self.activate("headphones")
        text = "**Réponse archivée** 😊 à préserver."
        mid = self.archive(text)
        self.voice.begin_turn(mid, "voice")
        self.voice.chunk(text)
        before = dict(self.store.message(mid))
        previous_settings = self.voice.settings
        with patch.object(self.store, "set_preference", side_effect=sqlite3.OperationalError("database is locked")):
            self.assertFalse(self.voice.handle_command("slower"))
        self.assertFalse(self.voice.capture.alive())
        self.assertFalse(self.voice.speech.alive())
        self.assertFalse(self.voice.listening)
        self.assertFalse(self.voice.tts_active)
        self.assertEqual(self.voice.settings, previous_settings)
        self.assertEqual(dict(self.store.message(mid)), before)
        self.assertIn("archive préservée", self.voice.status.get())
        self.assertIn("database is locked", self.voice.status.get())
        self.assertTrue(any("voice_command_error" in item for item in self.voice.diagnostic_events))

    def test_new_generation_cancels_delayed_resume_and_stale_callback_cannot_unmute(self):
        self.activate("speakers")
        mid = self.archive()
        self.voice.begin_turn(mid, "voice")
        self.voice.chunk("Une réponse parlée.")
        self.voice.cancel_speech()
        old_epoch = self.voice.epoch
        callback = self.voice.resume_id
        self.assertIsNotNone(callback)
        self.assertIn(callback, self.root.tk.call("after", "info"))
        self.voice.begin_turn(mid, "voice")
        self.assertNotIn(callback, self.root.tk.call("after", "info"))
        before = list(self.voice.capture.commands)
        self.voice._resume_microphone(old_epoch)
        self.assertEqual(self.voice.capture.commands, before)
        self.assertGreater(self.voice.epoch, old_epoch)

