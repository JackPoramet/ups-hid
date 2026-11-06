"""Regression tests for safety-critical HID client and decoder behavior."""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch, Mock

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from ups_module.client import UPSClient
from ups_module.core import decode_feature_reports, read_all_feature_reports
from ups_module.events import EventBus
from ups_module.linux_setup import generate_udev_rule
from ups_module.poller import UPSPoller
from ups_module.store import DataStore


class FakeHandle:
    def __init__(self, write_result=None):
        self.write_result = write_result
        self.sent = []

    def send_feature_report(self, report):
        self.sent.append(report)
        return len(report) if self.write_result is None else self.write_result


class FailingFeatureHandle:
    def get_feature_report(self, rid, size):
        raise OSError("HID unavailable")


class TestAuthoritativeStatus(unittest.TestCase):
    def test_client_rejects_status_id_without_payload(self):
        client = UPSClient()
        client._handle = object()
        with patch("ups_module.client.read_all_feature_reports", return_value=({1: [1]}, {})):
            with self.assertRaisesRegex(RuntimeError, "authoritative UPS status"):
                client.get_vars()

    def test_missing_meter_does_not_mean_output_off(self):
        decoded = decode_feature_reports({1: [1, 1, 0, 0, 0, 0, 1]})
        self.assertEqual(decoded["ups.status"], "OL")
        self.assertNotIn("output.voltage", decoded)
        self.assertNotIn("output.power", decoded)
        self.assertNotIn("Standby", decoded["ups_mode"])

    def test_empty_reports_do_not_claim_on_battery(self):
        decoded = decode_feature_reports({})
        self.assertNotIn("ups.status", decoded)
        self.assertEqual(decoded["ups_mode"], "Unknown (status report unavailable)")

    def test_read_metadata_preserves_hid_errors(self):
        raw, meta = read_all_feature_reports(FailingFeatureHandle(), [0x01])
        self.assertEqual(raw, {})
        self.assertEqual(meta[0x01]["errors"], 1)

    def test_client_rejects_missing_status_report(self):
        client = UPSClient()
        client._handle = object()
        with patch("ups_module.client.read_all_feature_reports", return_value=({}, {0x01: {"errors": 1}})):
            with self.assertRaisesRegex(RuntimeError, "authoritative UPS status"):
                client._read_raw()


class TestPollerStatus(unittest.TestCase):
    def _poll(self, response=None, error=None):
        store = DataStore()
        poller = UPSPoller(store)
        poller._report_ids = [1]
        handle = Mock()
        handle.get_feature_report.return_value = response
        handle.get_feature_report.side_effect = error
        poller._device_handle = handle
        with patch("ups_module.poller.platform.system", return_value="Linux"):
            poller._poll_once()
        return store, handle

    def test_zero_status_payload_is_a_successful_read(self):
        store, handle = self._poll([1, 0, 0, 0, 0, 0, 0])
        self.assertTrue(store.is_connected, store.status_message)
        handle.close.assert_not_called()

    def test_empty_and_header_only_are_not_valid_status(self):
        for response in (None, [], [1]):
            with self.subTest(response=response):
                store, handle = self._poll(response)
                self.assertFalse(store.is_connected)
                handle.close.assert_called_once()

    def test_status_read_error_disconnects(self):
        store, handle = self._poll(error=OSError("disconnected"))
        self.assertFalse(store.is_connected)
        handle.close.assert_called_once()


class TestControlSafety(unittest.TestCase):
    def setUp(self):
        self.client = UPSClient()
        self.handle = FakeHandle()
        self.client._handle = self.handle

    def test_rejects_negative_shutdown_delay(self):
        ok, message = self.client.schedule_shutdown(-1)
        self.assertFalse(ok)
        self.assertIn("unsigned 32-bit", message)
        self.assertEqual(self.handle.sent, [])

    def test_reserves_cancel_sentinel(self):
        ok, message = self.client.schedule_shutdown(0xFFFFFFFF)
        self.assertFalse(ok)
        self.assertIn("cancel_shutdown", message)
        self.assertEqual(self.handle.sent, [])

    def test_requires_complete_feature_write(self):
        self.handle.write_result = 1
        ok, message = self.client.run_self_test()
        self.assertFalse(ok)
        self.assertIn("incomplete write", message)

    def test_rejects_unsupported_frequency(self):
        ok, message = self.client.set_frequency(55)
        self.assertFalse(ok)
        self.assertIn("50 or 60", message)


class TestLifecycleSafety(unittest.TestCase):
    def test_monitor_interval_must_be_positive(self):
        client = UPSClient()
        with self.assertRaises(ValueError):
            client.start_monitor(0)

    def test_poller_interval_must_be_positive(self):
        with self.assertRaises(ValueError):
            UPSPoller(store=object(), poll_interval=-1)

    def test_event_bus_stop_is_idempotent(self):
        bus = EventBus(maxsize=1)
        bus.stop()
        bus.stop()

    def test_udev_rule_does_not_grant_world_raw_usb_access(self):
        rule = generate_udev_rule()
        self.assertIn('MODE="0660"', rule)
        self.assertIn('GROUP="ups-hid"', rule)
        self.assertNotIn('MODE="0666"', rule)
        self.assertNotIn('SUBSYSTEM=="usb"', rule)


if __name__ == "__main__":
    unittest.main()
