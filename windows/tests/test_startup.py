"""
Unit tests for Windows Startup Manager (startup_manager.py)
"""

import sys
import unittest
from pathlib import Path

# Add paths
_WINDOWS_DIR = Path(__file__).resolve().parent.parent
_ROOT = _WINDOWS_DIR.parent
for _p in (_WINDOWS_DIR, _ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from tray_service.startup_manager import is_startup_enabled, set_startup


class TestStartupManager(unittest.TestCase):

    TEST_APP_NAME = "UPS Monitor Test"

    def tearDown(self):
        # Cleanup test registry key
        set_startup(False, app_name=self.TEST_APP_NAME)

    def test_enable_and_disable_startup(self):
        # 1. Enable startup
        success_enable = set_startup(True, app_name=self.TEST_APP_NAME, exe_path="C:\\TestPath\\app.exe")
        self.assertTrue(success_enable)
        self.assertTrue(is_startup_enabled(app_name=self.TEST_APP_NAME))

        # 2. Disable startup
        success_disable = set_startup(False, app_name=self.TEST_APP_NAME)
        self.assertTrue(success_disable)
        self.assertFalse(is_startup_enabled(app_name=self.TEST_APP_NAME))


if __name__ == "__main__":
    unittest.main()
