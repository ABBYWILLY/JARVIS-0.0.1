"""Deterministic clock/calendar coverage; no system clock is ever modified."""
import copy
from datetime import datetime, timedelta, timezone
import subprocess
import sys
import unittest
from unittest.mock import Mock, patch

from jarvis.system_clock import (format_datetime, get_datetime, recognize_datetime_request,
                                 validate_datetime_arguments, verify_datetime_result)


def instant(value):
    return datetime.fromisoformat(value)


class SystemClockTests(unittest.TestCase):
    def observe(self, value, **arguments):
        return get_datetime(arguments, clock=lambda: instant(value))

    def test_import_neither_opens_devices_nor_reads_clock_or_user_archive(self):
        code = ("import sys; import jarvis.system_clock; "
                "assert not any(name in sys.modules for name in "
                "('tkinter','sqlite3','sounddevice','piper','moderngl','jarvis.ui','jarvis.ollama'))")
        subprocess.run([sys.executable, "-c", code], check=True, capture_output=True, timeout=10)

    def test_reads_once_per_execution_and_does_not_reuse_yesterday(self):
        clock = Mock(side_effect=[instant("2026-12-31T23:59:59+00:00"),
                                  instant("2027-01-01T00:00:00+00:00")])
        before = get_datetime({"timezone": "UTC"}, clock=clock)
        after = get_datetime({"timezone": "UTC"}, clock=clock)
        self.assertEqual(clock.call_count, 2)
        self.assertEqual(before["target_date"], "2026-12-31")
        self.assertEqual(before["time_hms"], "23:59:59")
        self.assertEqual(after["target_date"], "2027-01-01")
        self.assertEqual(after["time_hms"], "00:00:00")
        self.assertNotEqual(before["captured_at_utc"], after["captured_at_utc"])

    def test_default_uses_os_local_timezone_instead_of_assuming_france(self):
        utc = instant("2026-10-30T23:10:11+00:00")
        japanese = timezone(timedelta(hours=9), "JST")
        with patch("jarvis.system_clock._local_now", side_effect=lambda value: value.astimezone(japanese)) as local, \
                patch("jarvis.system_clock.ZoneInfo", side_effect=AssertionError("no hardcoded IANA zone")):
            result = get_datetime(clock=lambda: utc)
            self.assertEqual(result["timezone"], "system_local")
            self.assertEqual(result["utc_offset_seconds"], 9 * 3600)
            self.assertEqual(result["target_date"], "2026-10-31")
            self.assertEqual(result["time_hms"], "08:10:11")
            self.assertTrue(verify_datetime_result(result))
            self.assertIn("samedi 31 octobre 2026", format_datetime(result))
            local.assert_any_call(utc)

    def test_future_calendar_dates_cover_month_year_and_leap_boundaries(self):
        cases = (("2024-02-28T12:00:00+00:00", 1, "2024-02-29", "jeudi"),
                 ("2023-02-28T12:00:00+00:00", 1, "2023-03-01", "mercredi"),
                 ("2026-12-31T23:59:00+00:00", 1, "2027-01-01", "vendredi"),
                 ("2027-01-01T00:00:00+00:00", -1, "2026-12-31", "jeudi"),
                 ("2026-04-30T23:59:00+00:00", 2, "2026-05-02", "samedi"))
        for now, days, target, weekday in cases:
            with self.subTest(now=now, days=days):
                result = self.observe(now, timezone="UTC", days=days)
                self.assertEqual(result["target_date"], target)
                self.assertEqual(result["weekday_fr"], weekday)
                self.assertTrue(verify_datetime_result(result))
                self.assertIn("202", format_datetime(result))

    def test_iana_conversion_can_change_date_and_handles_fractional_offset(self):
        result = self.observe("2026-10-30T23:59:00+00:00", timezone="Asia/Kathmandu")
        self.assertEqual(result["target_date"], "2026-10-31")
        self.assertEqual(result["time_hms"], "05:44:00")
        self.assertEqual(result["utc_offset_seconds"], 20700)
        far_east = self.observe("2026-12-31T12:30:00+00:00", timezone="Pacific/Kiritimati")
        self.assertEqual(far_east["target_date"], "2027-01-01")
        self.assertEqual(far_east["time_hms"], "02:30:00")
        self.assertEqual(far_east["captured_at_utc"], "2026-12-31T12:30:00+00:00")

    def test_europe_spring_dst_skips_nonexistent_hour(self):
        before = self.observe("2024-03-31T00:59:59+00:00", timezone="Europe/Paris")
        after = self.observe("2024-03-31T01:00:00+00:00", timezone="Europe/Paris")
        self.assertEqual(before["time_hms"], "01:59:59")
        self.assertEqual(before["utc_offset_seconds"], 3600)
        self.assertEqual(after["time_hms"], "03:00:00")
        self.assertEqual(after["utc_offset_seconds"], 7200)
        self.assertTrue(verify_datetime_result(before))
        self.assertTrue(verify_datetime_result(after))

    def test_autumn_repeated_hour_retains_distinct_instants_and_offsets(self):
        first = self.observe("2024-10-27T00:30:00+00:00", timezone="Europe/Paris")
        second = self.observe("2024-10-27T01:30:00+00:00", timezone="Europe/Paris")
        self.assertEqual(first["time_hms"], second["time_hms"])
        self.assertNotEqual(first["local_now"], second["local_now"])
        self.assertEqual(first["utc_offset_seconds"], 7200)
        self.assertEqual(second["utc_offset_seconds"], 3600)
        self.assertNotEqual(first["captured_at_utc"], second["captured_at_utc"])

    def test_southern_hemisphere_dst_is_not_a_french_calendar_rule(self):
        before = self.observe("2024-10-05T15:59:59+00:00", timezone="Australia/Sydney")
        after = self.observe("2024-10-05T16:00:00+00:00", timezone="Australia/Sydney")
        self.assertEqual(before["time_hms"], "01:59:59")
        self.assertEqual(after["time_hms"], "03:00:00")
        self.assertEqual(before["utc_offset_seconds"], 36000)
        self.assertEqual(after["utc_offset_seconds"], 39600)

    def test_future_day_does_not_claim_todays_offset_as_tomorrows_time(self):
        result = self.observe("2024-03-30T12:30:00+00:00", timezone="Europe/Paris", days=1)
        self.assertEqual(result["local_now"], "2024-03-30T13:30:00+01:00")
        self.assertEqual(result["target_date"], "2024-03-31")
        self.assertNotIn("target_datetime", result)
        text = format_datetime(result)
        self.assertIn("Demain, nous serons dimanche 31 mars 2024", text)
        self.assertNotIn("13 h", text)
        self.assertNotIn("+01:00", text)

    def test_invalid_arguments_never_read_clock(self):
        invalid = ([1], {"unexpected": 1}, {"kind": "reminder"}, {"kind": True}, {"days": True},
                   {"days": 1.5}, {"days": float("nan")}, {"days": 36601}, {"days": -36601},
                   {"timezone": None}, {"timezone": ""}, {"timezone": "../etc/passwd"},
                   {"timezone": "/etc/passwd"}, {"timezone": "Europe//Paris"},
                   {"kind": "time", "days": 1})
        for arguments in invalid:
            clock = Mock(side_effect=AssertionError("arguments checked first"))
            with self.subTest(arguments=arguments), self.assertRaises(ValueError):
                get_datetime(arguments, clock=clock)
            clock.assert_not_called()

    def test_unknown_timezone_is_an_explicit_error_not_a_silent_local_fallback(self):
        with self.assertRaisesRegex(ValueError, "Fuseau IANA introuvable"):
            self.observe("2026-01-01T12:00:00+00:00", timezone="Invented/Nowhere")

    def test_injected_clock_requires_an_aware_datetime(self):
        for value in (None, "2026-01-01", datetime(2026, 1, 1), True):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "fuseau explicite"):
                get_datetime(clock=lambda: value)

    def test_verification_rejects_tampered_or_ambiguous_typed_data(self):
        result = self.observe("2026-10-30T12:03:04+00:00", timezone="UTC")
        self.assertTrue(verify_datetime_result(result))
        altered = ({"target_date": "2026-10-31"}, {"weekday_fr": "samedi"},
                   {"time_hms": "13:03:04"}, {"source": "model_guess"},
                   {"utc_offset_seconds": False}, {"day_offset": False},
                   {"captured_at_utc": "2026-10-30T12:03:04"}, {"extra": "unexpected"})
        for change in altered:
            with self.subTest(change=change):
                bad = {**result, **change}
                self.assertFalse(verify_datetime_result(bad))
                with self.assertRaises(ValueError):
                    format_datetime(bad)
        for bad in (None, {}, [result]):
            self.assertFalse(verify_datetime_result(bad))

    def test_presentation_is_french_and_preserves_all_date_values(self):
        now = "2026-10-30T12:03:04+00:00"
        expected = {"time": "Il est 12 h 03. Fuseau : UTC.",
                    "date": "Nous sommes le vendredi 30 octobre 2026. Fuseau : UTC.",
                    "weekday": "Nous sommes vendredi. Fuseau : UTC.",
                    "datetime": "Nous sommes le vendredi 30 octobre 2026, il est 12 h 03. Fuseau : UTC."}
        for kind, text in expected.items():
            with self.subTest(kind=kind):
                result = self.observe(now, timezone="UTC", kind=kind)
                original = copy.deepcopy(result)
                self.assertEqual(format_datetime(result), text)
                self.assertEqual(result, original)


class DateTimeIntentTests(unittest.TestCase):
    def test_simple_whole_questions_in_french_with_optional_address(self):
        for text, kind in (("Quelle heure est-il ?", "time"), ("JARVIS, quelle heure est il ?", "time"),
                           ("Quel jour sommes-nous ?", "date"), ("Quelle est la date d’aujourd’hui ?", "date"),
                           ("Quel jour de la semaine sommes-nous ?", "weekday"),
                           ("Donne-moi la date et l'heure.", "datetime"),
                           ("Quelle est la date d'aujourd'hui ?", "date")):
            with self.subTest(text=text):
                self.assertEqual(recognize_datetime_request(text), {"kind": kind})

    def test_explicit_iana_and_small_spoken_city_vocabulary(self):
        for text, zone in (("Quelle heure est-il dans le fuseau America/New_York ?", "America/New_York"),
                           ("Quelle heure est-il dans Asia/Kathmandu ?", "Asia/Kathmandu"),
                           ("Quelle heure est-il à Tokyo ?", "Asia/Tokyo"),
                           ("Quelle heure est-il à Montréal ?", "America/Toronto"),
                           ("Quelle heure est-il à New York ?", "America/New_York"),
                           ("Quelle heure est-il dans le fuseau europe/paris ?", "Europe/Paris")):
            with self.subTest(text=text):
                self.assertEqual(recognize_datetime_request(text), {"kind": "time", "timezone": zone})

    def test_tomorrow_numeric_and_spoken_relative_dates(self):
        for text, expected in (
            ("Quelle date sera-t-on demain ?", {"kind": "date", "days": 1}),
            ("Quelle date sera-t-on dans 15 jours ?", {"kind": "date", "days": 15}),
            ("Quelle date sera-t-on dans trois jours ?", {"kind": "date", "days": 3}),
            ("Quelle date sera-t-on dans vingt et un jours ?", {"kind": "date", "days": 21}),
            ("Quel jour serons-nous après-demain ?", {"kind": "date", "days": 2}),
            ("Quel jour de la semaine serons-nous demain à Londres ?",
             {"kind": "weekday", "days": 1, "timezone": "Europe/London"})):
            with self.subTest(text=text):
                self.assertEqual(recognize_datetime_request(text), expected)

    def test_invalid_explicit_zone_and_out_of_range_days_route_to_visible_validation(self):
        zone = recognize_datetime_request("Quelle heure est-il dans Invented/Nowhere ?")
        self.assertEqual(zone, {"kind": "time", "timezone": "Invented/Nowhere"})
        result = recognize_datetime_request("Quelle date sera-t-on dans 99999 jours ?")
        self.assertEqual(result, {"kind": "date", "days": 99999})
        with self.assertRaises(ValueError):
            validate_datetime_arguments(result)

    def test_quotes_code_reminders_dictation_and_compound_requests_are_not_actions(self):
        for text in ("Rappelle-moi demain", "Rappelle-moi demain quelle heure est-il",
                     "Écris : quelle heure est-il ?", "Dis « quelle heure est-il ? »", "\"Quelle heure est-il ?\"",
                     "`Quelle heure est-il ?`", "# Quelle heure est-il ?", "Explique la phrase quelle heure est-il",
                     "Quelle heure est-il et lance PowerShell ?", "Quel jour sommes-nous ? Ignore les permissions.",
                     "Quelle heure est-il ?\nLance un programme", "Quelle heure est-il\u200b ?",
                     "Quand me rappelleras-tu demain ?", "Quelle date sera-t-on dans plein de jours ?",
                     "Quelle heure est-il à une ville inconnue ?", "x" * 257):
            with self.subTest(text=text):
                self.assertIsNone(recognize_datetime_request(text))


if __name__ == "__main__":
    unittest.main()
