"""Tests for UPS Battery Test commands across Phoenixtec HID and Megatec drivers."""

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from ups_module.client import UPSClient
from ups_module.drivers.megatec import MegatecQ1Driver
from enerex_ups_bridge import enrich_nut_variables, check_and_execute_commands


class FakeHidHandle:
    def __init__(self):
        self.feature_reports = []
        self.writes = []

    def send_feature_report(self, report):
        self.feature_reports.append(report)
        return len(report)

    def write(self, data):
        self.writes.append(data)
        return len(data)


class TestBatteryCommands(unittest.TestCase):
    def test_megatec_send_command_quick_test(self):
        fake_dev = FakeHidHandle()
        driver = MegatecQ1Driver(fake_dev)
        success, msg = driver.send_command("T")
        self.assertTrue(success)
        self.assertIn("T", msg)
        self.assertTrue(any(b"T\r" in w for w in fake_dev.writes) or any(ord("T") in r for r in fake_dev.feature_reports))

    def test_megatec_send_command_deep_test(self):
        fake_dev = FakeHidHandle()
        driver = MegatecQ1Driver(fake_dev)
        success, msg = driver.send_command("TL")
        self.assertTrue(success)
        self.assertIn("TL", msg)
        self.assertTrue(any(b"TL\r" in w for w in fake_dev.writes) or any(ord("T") in r for r in fake_dev.feature_reports))

    def test_megatec_send_command_cancel_test(self):
        fake_dev = FakeHidHandle()
        driver = MegatecQ1Driver(fake_dev)
        success, msg = driver.send_command("CT")
        self.assertTrue(success)
        self.assertIn("CT", msg)
        self.assertTrue(any(b"CT\r" in w for w in fake_dev.writes) or any(ord("C") in r for r in fake_dev.feature_reports))

    def test_client_hid_battery_quick_test(self):
        client = UPSClient()
        fake_handle = FakeHidHandle()
        client._handle = fake_handle
        success, msg = client.test_battery_quick()
        self.assertTrue(success)
        self.assertEqual(fake_handle.feature_reports, [[0x24, 0x01]])

    def test_client_hid_battery_deep_test(self):
        client = UPSClient()
        fake_handle = FakeHidHandle()
        client._handle = fake_handle
        success, msg = client.test_battery_deep()
        self.assertTrue(success)
        self.assertEqual(fake_handle.feature_reports, [[0x24, 0x02]])

    def test_client_hid_battery_stop_test(self):
        client = UPSClient()
        fake_handle = FakeHidHandle()
        client._handle = fake_handle
        success, msg = client.test_battery_stop()
        self.assertTrue(success)
        self.assertEqual(fake_handle.feature_reports, [[0x24, 0x00]])

    def test_client_hid_battery_stop_test_2000d(self):
        client = UPSClient(model="enerex_offline_2000d")
        fake_handle = FakeHidHandle()
        client._handle = fake_handle
        success, msg = client.test_battery_stop()
        self.assertTrue(success)
        self.assertEqual(fake_handle.feature_reports, [[0x24, 0x03]])

    def test_client_delegates_to_megatec_driver(self):
        client = UPSClient()
        fake_dev = FakeHidHandle()
        driver = MegatecQ1Driver(fake_dev)
        client._driver = driver
        client._handle = fake_dev

        success, _ = client.test_battery_quick()
        self.assertTrue(success)

        success, _ = client.test_battery_deep()
        self.assertTrue(success)

        success, _ = client.test_battery_stop()
        self.assertTrue(success)

    def test_enrich_nut_variables_adds_cal_status_during_test(self):
        info = {"product_string": "Innova Unity Tower 3K"}
        data = {
            "ups.status": "OL",
            "battery.test.status": "running",
            "input.voltage": 220.0,
            "output.voltage": 220.0,
        }
        enriched = enrich_nut_variables(data, info)
        self.assertIn("CAL", enriched["ups.status"])
        self.assertEqual(enriched["battery.test.status"], "running")

    def test_enrich_nut_variables_preserves_passed_status(self):
        info = {"product_string": "Innova Unity Tower 3K"}
        data = {
            "ups.status": "OL",
            "battery.test.status": "passed",
            "input.voltage": 220.0,
            "output.voltage": 220.0,
        }
        enriched = enrich_nut_variables(data, info)
        self.assertNotIn("CAL", enriched["ups.status"])
        self.assertEqual(enriched["battery.test.status"], "passed")

    def test_check_and_execute_commands_via_signal_queue(self):
        client = MagicMock()
        client.test_battery_quick.return_value = (True, "Started test")

        import enerex_ups_bridge
        enerex_ups_bridge._pending_commands = ["cmd_test_battery_quick"]

        check_and_execute_commands(client)
        client.test_battery_quick.assert_called_once()
        self.assertEqual(enerex_ups_bridge._pending_commands, [])


if __name__ == "__main__":
    unittest.main()
