"""
Unit tests for DatabaseManager (SQLite)
"""

import sys
import tempfile
import unittest
from pathlib import Path

# Add paths
_WINDOWS_DIR = Path(__file__).resolve().parent.parent
_ROOT = _WINDOWS_DIR.parent
for _p in (_WINDOWS_DIR, _ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from tray_service.database import DatabaseManager


class TestDatabaseManager(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_ups.db"
        self.db = DatabaseManager(db_path=self.db_path)

    def tearDown(self):
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_init_db(self):
        self.assertTrue(self.db_path.exists())

    def test_log_and_fetch_events(self):
        self.db.log_event("AC_FAIL", "Power outage detected", battery_level=85, ac_present=False)
        self.db.log_event("AC_RESTORE", "Power restored", battery_level=90, ac_present=True)

        events = self.db.get_events_history(limit=10)
        self.assertEqual(len(events), 2)
        # Ordered DESC
        self.assertEqual(events[0]["event_type"], "AC_RESTORE")
        self.assertEqual(events[1]["event_type"], "AC_FAIL")
        self.assertFalse(events[1]["ac_present"])

    def test_log_and_fetch_telemetry(self):
        state = {
            "ac_present": True,
            "battery.charge": 98,
            "battery.runtime": 4200,
            "input.voltage": 220.5,
            "output.voltage": 220.0,
            "output.load": 15,
        }
        self.db.log_telemetry(state)

        history = self.db.get_telemetry_history(hours=1.0)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["battery_charge"], 98)
        self.assertEqual(history[0]["input_voltage"], 220.5)

    def test_prune_and_clear(self):
        self.db.log_event("TEST_EVENT", "Test Message")
        self.db.clear_all()
        events = self.db.get_events_history(limit=10)
        self.assertEqual(len(events), 0)


if __name__ == "__main__":
    unittest.main()
