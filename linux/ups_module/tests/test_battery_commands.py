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
    def test_quick_alias_triggers_test_descriptor_and_canonical_payload(self):
        device = FakeHidHandle()
        seen = []
        device.get_indexed_string = lambda idx: seen.append(idx) or "ACK"
        with patch("ups_module.drivers.megatec.time.sleep"):
            self.assertTrue(MegatecQ1Driver(device).send_command("QUICK")[0])
        self.assertEqual(seen[0], 4)
        device = FakeHidHandle()
        self.assertTrue(MegatecQ1Driver(device).send_command("QUICK")[0])
        self.assertIn(b"T\r", device.feature_reports[0])
        self.assertNotIn(b"QUICK", device.feature_reports[0])

    def test_truncated_pyusb_descriptor_does_not_start_lifecycle(self):
        device = FakeHidHandle()
        device.send_feature_report = lambda _: 0
        device.write = lambda _: 0
        usb = MagicMock()
        for response in (b"\x03", b"\x04\x03A", b"\x03\x03A", b"\x04\x02A\x00", 8):
            with self.subTest(response=response):
                usb.ctrl_transfer.side_effect = lambda **kw: response if kw["bmRequestType"] == 0x80 else 0
                with patch("usb.core.find", return_value=usb):
                    self.assertFalse(MegatecQ1Driver(device).test_battery_quick()[0])

    def test_malformed_fault_voltage_rejects_entire_frame(self):
        with self.assertRaises(RuntimeError):
            self._telemetry_driver("(230 BAD 230 10 50 13.8 --.- 00000000").get_vars()

    def test_elapsed_command_timer_never_fabricates_a_pass(self):
        device = FakeHidHandle()
        device.get_indexed_string = lambda idx: "#220 4 12 50" if idx == 13 else "(230 230 230 10 50 13.8 25 00000000"
        driver = MegatecQ1Driver(device)
        driver.test_battery_quick()
        driver._test_start_time = 0
        result = driver.get_vars()
        self.assertEqual(result["battery.test.status"], "unknown")
        self.assertNotIn("passed", result["ups.test.result"].lower())
        self.assertNotIn("CAL", result["ups.status"].split())

    def test_empty_pyusb_read_is_not_success(self):
        device = FakeHidHandle()
        device.send_feature_report = lambda _: 0
        device.write = lambda _: 0
        usb = MagicMock()
        usb.ctrl_transfer.side_effect = lambda **kw: [] if kw["bmRequestType"] == 0x80 else 0
        with patch("usb.core.find", return_value=usb):
            ok, _ = MegatecQ1Driver(device).test_battery_quick()
        self.assertFalse(ok)

    def setUp(self):
        # The driver tries PyUSB before HID writes, even with a fake HID handle.
        for guard in (
            patch("hid.enumerate", return_value=[]),
            patch("hid.device", side_effect=AssertionError("Real HID access blocked in tests")),
            patch("usb.core.find", return_value=None),
        ):
            guard.start()
            self.addCleanup(guard.stop)

    def _failed_driver(self):
        dev = MagicMock()
        dev.get_indexed_string.side_effect = OSError("mock USB failure")
        dev.send_feature_report.side_effect = OSError("mock USB failure")
        dev.write.side_effect = OSError("mock USB failure")
        return MegatecQ1Driver(dev)

    def test_failed_quick_does_not_start_lifecycle(self):
        driver = self._failed_driver()
        before = dict(vars(driver))
        self.assertFalse(driver.test_battery_quick()[0])
        self.assertEqual(vars(driver), before)

    def test_failed_deep_does_not_start_lifecycle(self):
        driver = self._failed_driver()
        before = dict(vars(driver))
        self.assertFalse(driver.test_battery_deep()[0])
        self.assertEqual(vars(driver), before)

    def test_failed_stop_preserves_active_test(self):
        driver = self._failed_driver()
        driver._test_active = True
        driver._test_status = "in progress"
        driver._test_start_time = 123.0
        before = dict(vars(driver))
        self.assertFalse(driver.test_battery_stop()[0])
        self.assertEqual(vars(driver), before)

    def test_short_write_is_not_success(self):
        dev = FakeHidHandle()
        dev.send_feature_report = lambda payload: 1
        dev.write = lambda payload: 1
        driver = MegatecQ1Driver(dev)
        self.assertFalse(driver.test_battery_quick()[0])
        self.assertFalse(driver._test_active)

    def test_explicit_nak_does_not_retry_other_transports(self):
        dev = MagicMock()
        dev.get_indexed_string.side_effect = ["", "NAK"]
        with patch("ups_module.drivers.megatec.time.sleep"):
            self.assertFalse(MegatecQ1Driver(dev).test_battery_quick()[0])
        dev.send_feature_report.assert_not_called()
        dev.write.assert_not_called()

    def _telemetry_driver(self, telemetry):
        dev = MagicMock()
        dev.get_indexed_string.side_effect = lambda idx: "#220.0 4.0 12.0 50.0" if idx == 13 else telemetry
        dev.get_manufacturer_string.return_value = "MEC"
        dev.get_product_string.return_value = "MEC0003"
        return MegatecQ1Driver(dev)

    def test_invalid_q1_telemetry_is_communication_failure(self):
        for telemetry in (None, "", "NAK", "230 230 230", "(230 230",
                          "(bad 230 230 000 50 13.8 --.- 00001000",
                          "(nan 230 230 000 50 13.8 --.- 00001000",
                          "(230 230 inf 000 50 13.8 --.- 00001000",
                          "(230 230 230 000 50 13.8 --.- 001",
                          "(230 230 230 000 50 13.8 --.- 00001X00"):
            with self.subTest(telemetry=telemetry), self.assertRaises(RuntimeError):
                self._telemetry_driver(telemetry).get_vars()

    def test_valid_q1_without_temperature_sensor(self):
        data = self._telemetry_driver("(232.1 232.2 232.0 000 50.1 13.8 --.- 00001000").get_vars()
        self.assertEqual(data["ups.status"], "OL")
        self.assertEqual(data["input.voltage"], 232.1)
        self.assertNotIn("ups.temperature", data)

    def test_valid_q1_on_battery_preserves_zero_input(self):
        data = self._telemetry_driver("(0.0 0.0 230.0 010 50.0 11.0 --.- 11001000").get_vars()
        self.assertIn("OB", data["ups.status"])
        self.assertIn("LB", data["ups.status"])
        self.assertEqual(data["input.voltage"], 0.0)

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

    def test_megatec_convenience_methods(self):
        fake_dev = FakeHidHandle()
        driver = MegatecQ1Driver(fake_dev)

        s1, m1 = driver.test_battery_quick()
        self.assertTrue(s1)
        self.assertEqual(driver._test_duration, 10.0)

        s2, m2 = driver.test_battery_deep()
        self.assertTrue(s2)
        self.assertEqual(driver._test_duration, 30.0)

        s3, m3 = driver.test_battery_stop()
        self.assertTrue(s3)
        self.assertEqual(driver._test_status, "aborted")

    def test_megatec_pyusb_fallback(self):
        # When HID handle fails, PyUSB fallback is attempted
        fail_dev = MagicMock()
        fail_dev.get_indexed_string.side_effect = RuntimeError("HID write failed")
        fail_dev.send_feature_report.side_effect = RuntimeError("HID write failed")
        fail_dev.write.side_effect = RuntimeError("HID write failed")

        mock_usb_dev = MagicMock()
        mock_usb_dev.ctrl_transfer.return_value = bytes([4, 3, 65, 0])

        with patch("usb.core.find", return_value=mock_usb_dev):
            driver = MegatecQ1Driver(fail_dev)
            success, msg = driver.send_command("T")
            self.assertTrue(success)
            self.assertIn("PyUSB", msg)
            mock_usb_dev.ctrl_transfer.assert_called()

    def test_client_get_vars_preserves_driver_custom_fields(self):
        client = UPSClient()
        fake_dev = FakeHidHandle()
        driver = MegatecQ1Driver(fake_dev)
        driver.get_vars = MagicMock(return_value={
            "input.voltage": 220.0,
            "output.voltage": 220.0,
            "battery.voltage": 13.8,
            "battery.test.status": "in progress",
            "ups.test.date": "2026/09/07 03:00:00",
            "device.mfr": "MEC",
            "device.model": "MEC0003",
        })
        client._driver = driver
        client._handle = fake_dev

        vars_dict = client.get_vars()
        self.assertEqual(vars_dict.get("ups.test.date"), "2026/09/07 03:00:00")
        self.assertEqual(vars_dict.get("device.mfr"), "MEC")
        self.assertEqual(vars_dict.get("device.model"), "MEC0003")

    def test_enrich_nut_variables_includes_instant_commands(self):
        data = {"ups.status": "OL"}
        info = {"product_string": "MEC0003"}
        from ups_module.device_registry import DeviceRegistry
        enriched = enrich_nut_variables(data, info, DeviceRegistry().get_by_id("enerex_mec0003"))
        self.assertEqual(enriched.get("cmd.test.battery.start"), 1)
        self.assertEqual(enriched.get("cmd.test.battery.start.quick"), 1)
        self.assertEqual(enriched.get("cmd.test.battery.start.deep"), 1)
        self.assertEqual(enriched.get("cmd.test.battery.stop"), 1)


class TestHardwareIsolation(unittest.TestCase):
    def test_command_tests_never_discover_real_usb(self):
        for method in ("test_megatec_send_command_quick_test",
                       "test_megatec_send_command_deep_test",
                       "test_megatec_send_command_cancel_test"):
            with self.subTest(method=method), patch("usb.core.find", return_value=None) as outside_find:
                result = unittest.TestResult()
                TestBatteryCommands(method).run(result)
                self.assertTrue(result.wasSuccessful(), result.errors + result.failures)
                outside_find.assert_not_called()


if __name__ == "__main__":
    unittest.main()

