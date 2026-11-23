import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from src.lords_mobile.manager import ShieldTimerManager
from src.lords_mobile.storage import ShieldStore, ShieldStoreError
from src.lords_mobile.timer import TimerParseError, parse_duration_text


class ShieldTimerTests(unittest.TestCase):
    def test_parse_compound_duration(self):
        self.assertEqual(parse_duration_text("2d 4h 15m 9s"), 187_209)

    def test_parse_clock_duration(self):
        self.assertEqual(parse_duration_text("04:15:09"), 15_309)

    def test_reject_ambiguous_or_invalid_text(self):
        for value in ("", "12:30", "2h xx", "1h 2h", "00:70:00", "0s"):
            with self.subTest(value=value), self.assertRaises(TimerParseError):
                parse_duration_text(value)

    def test_record_and_active_status(self):
        with tempfile.TemporaryDirectory() as folder:
            manager = ShieldTimerManager(ShieldStore(Path(folder) / "shield.json"))
            now = datetime(2026, 11, 24, 10, 0, tzinfo=timezone.utc)
            expiry = manager.record_observation("2h", observed_at=now)
            self.assertEqual(expiry.hour, 12)
            status = manager.status(now=now)
            self.assertEqual(status.state, "active")
            self.assertFalse(status.reminder_due)

    def test_warning_and_expired_states(self):
        with tempfile.TemporaryDirectory() as folder:
            manager = ShieldTimerManager(ShieldStore(Path(folder) / "shield.json"), warning_minutes=30)
            now = datetime(2026, 11, 24, 10, 0, tzinfo=timezone.utc)
            manager.record_observation("20m", observed_at=now)
            self.assertEqual(manager.status(now=now).state, "expiring")
            later = datetime(2026, 11, 24, 10, 21, tzinfo=timezone.utc)
            self.assertEqual(manager.status(now=later).state, "expired")

    def test_corrupt_state_fails_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "shield.json"
            path.write_text("{not-json", encoding="utf-8")
            with self.assertRaises(ShieldStoreError):
                ShieldStore(path).load()


if __name__ == "__main__":
    unittest.main()
