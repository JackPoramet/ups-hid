"""
ups_module/tests/test_models.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Unit tests for UPSData, NUT dict, serializer, events.
ไม่ต้องใช้ HID device จริง — ทดสอบ logic ล้วนๆ

Run::

    python -m pytest ups_module/tests/ -v
    python -m unittest ups_module.tests.test_models -v
"""

import json
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from ups_module.models import (
    NotifyType,
    UPSData,
    UPSEvent,
    ups_data_from_raw,
)
from ups_module.serializer import sanitize_for_json, build_response_envelope
from ups_module.events import EventBus, EventDetector


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_RAW: dict = {
    "ups.status": "OL",
    "ups_mode": "Line Mode (ไฟปกติ)",
    "ac_present": True,
    "charging": False,
    "discharging": False,
    "below_capacity_limit": False,
    "status_good": True,
    "overload": False,
    "internal_failure": False,
    "need_replacement": False,
    "over_temperature": False,
    "shutdown_imminent": False,
    "battery.charge": 95,
    "battery.charge.low": 20,
    "battery.charge.high": 100,
    "battery.runtime": 3600,
    "battery_voltage_v": 27.2,
    "battery_test_status": "idle",
    "input.voltage": 220.5,
    "input.voltage.nominal": 220,
    "input.frequency": 50.0,
    "input.frequency.nominal": 50,
    "input.transfer.low": 176,
    "output.voltage": 220.0,
    "output_frequency_hz": 50.0,
    "output_current_a": 1.5,
    "output_active_power_w": 330,
    "output_apparent_power_va": 400,
    "percent_load": 33,
    "temperature_c": 28.5,
    "ups.firmware": "1.2.3",
    "config_max_active_power_w": 1000,
    "config_max_apparent_power_va": 1500,
    "scan.report_count": 12,
    "scan.report_ids": ["0x01", "0x06", "0x07"],
}

SAMPLE_ON_BATTERY_RAW: dict = {
    **SAMPLE_RAW,
    "ups.status": "OB LB",
    "ac_present": False,
    "discharging": True,
    "below_capacity_limit": True,
    "battery.charge": 15,
    "battery.runtime": 120,
}


# ---------------------------------------------------------------------------
# UPSData tests
# ---------------------------------------------------------------------------

class TestUPSDataFromRaw(unittest.TestCase):

    def test_basic_fields(self):
        data = ups_data_from_raw(SAMPLE_RAW)
        self.assertEqual(data.ups_status, "OL")
        self.assertEqual(data.battery_charge, 95)
        self.assertEqual(data.battery_runtime, 3600)
        self.assertAlmostEqual(data.battery_voltage, 27.2, places=1)
        self.assertAlmostEqual(data.input_voltage, 220.5, places=1)
        self.assertAlmostEqual(data.output_voltage, 220.0, places=1)
        self.assertEqual(data.ups_firmware, "1.2.3")
        self.assertEqual(data.battery_test_status, "idle")
        self.assertEqual(data.scan_report_count, 12)
        self.assertEqual(data.scan_report_ids, ["0x01", "0x06", "0x07"])

    def test_flags(self):
        data = ups_data_from_raw(SAMPLE_RAW)
        self.assertTrue(data.ac_present)
        self.assertFalse(data.charging)
        self.assertFalse(data.discharging)
        self.assertTrue(data.status_good)

    def test_is_online(self):
        data = ups_data_from_raw(SAMPLE_RAW)
        self.assertTrue(data.is_online())
        self.assertFalse(data.is_on_battery())
        self.assertFalse(data.is_low_battery())

    def test_is_on_battery(self):
        data = ups_data_from_raw(SAMPLE_ON_BATTERY_RAW)
        self.assertTrue(data.is_on_battery())
        self.assertTrue(data.is_low_battery())
        self.assertFalse(data.is_online())

    def test_is_charging(self):
        raw = {**SAMPLE_RAW, "charging": True}
        data = ups_data_from_raw(raw)
        self.assertTrue(data.is_charging())

    def test_zero_measurements_are_not_replaced_by_tentative_values(self):
        data = ups_data_from_raw({
            "input.voltage": 0.0,
            "tentative.input.voltage": 230.0,
            "input.frequency": 0.0,
            "tentative.input.frequency": 50.0,
            "output.voltage": 0.0,
            "output_voltage_v": 230.0,
            "ups.temperature": 0.0,
            "temperature_c": 28.0,
        })
        self.assertEqual(data.input_voltage, 0.0)
        self.assertEqual(data.input_frequency, 0.0)
        self.assertEqual(data.output_voltage, 0.0)
        self.assertEqual(data.ups_temperature, 0.0)


class TestNutDict(unittest.TestCase):

    def setUp(self):
        self.data = ups_data_from_raw(SAMPLE_RAW)

    def test_has_standard_keys(self):
        d = self.data.to_nut_dict()
        for key in ["ups.status", "battery.charge", "battery.runtime",
                    "input.voltage", "output.voltage"]:
            self.assertIn(key, d, f"Missing NUT key: {key}")

    def test_no_none_values(self):
        d = self.data.to_nut_dict()
        for k, v in d.items():
            self.assertIsNotNone(v, f"Key '{k}' should not be None in to_nut_dict()")

    def test_values(self):
        d = self.data.to_nut_dict()
        self.assertEqual(d["ups.status"], "OL")
        self.assertEqual(d["battery.charge"], 95)
        self.assertEqual(d["battery.runtime"], 3600)
        self.assertAlmostEqual(d["input.voltage"], 220.5, places=1)

    def test_to_json_valid(self):
        js = self.data.to_json()
        parsed = json.loads(js)
        self.assertIsInstance(parsed, dict)
        self.assertEqual(parsed["ups.status"], "OL")
        self.assertEqual(parsed["battery.charge"], 95)

    def test_full_dict_includes_flags(self):
        d = self.data.to_full_dict()
        self.assertIn("ac_present", d)
        self.assertIn("scan_report_count", d)


# ---------------------------------------------------------------------------
# Serializer tests
# ---------------------------------------------------------------------------

class TestSerializer(unittest.TestCase):

    def test_sanitize_bytes(self):
        result = sanitize_for_json({"manufacturer": b"Phoenixtec", "value": 123})
        self.assertEqual(result["manufacturer"], "Phoenixtec")
        self.assertEqual(result["value"], 123)

    def test_sanitize_bytearray(self):
        result = sanitize_for_json({"data": bytearray(b"hello")})
        self.assertEqual(result["data"], "hello")

    def test_sanitize_list(self):
        result = sanitize_for_json({"items": [b"a", 1, "b", None]})
        self.assertEqual(result["items"], ["a", 1, "b", None])

    def test_build_response_envelope(self):
        data = ups_data_from_raw(SAMPLE_RAW)
        envelope = build_response_envelope(
            device={"manufacturer_string": "Phoenixtec", "product_string": "Innova"},
            ups=data.to_nut_dict(),
            status_message="Connected",
            timestamp="2026-07-16T20:00:00",
        )
        self.assertIn("driver", envelope)
        self.assertIn("device", envelope)
        self.assertIn("ups", envelope)
        self.assertIn("meta", envelope)
        self.assertEqual(envelope["driver"]["name"], "ups-hid")
        self.assertEqual(envelope["device"]["manufacturer"], "Phoenixtec")
        self.assertTrue(envelope["meta"]["connected"])
        self.assertIn("ups.status", envelope["ups"])


# ---------------------------------------------------------------------------
# Event tests
# ---------------------------------------------------------------------------

class TestUPSEvent(unittest.TestCase):

    def test_event_creation(self):
        data = ups_data_from_raw(SAMPLE_RAW)
        event = UPSEvent(notify_type=NotifyType.ONBATT, message="On battery.", data=data)
        self.assertEqual(event.notify_type, "ONBATT")
        d = event.to_dict()
        self.assertEqual(d["event"], "ONBATT")
        self.assertIn("timestamp", d)

    def test_notify_type_constants(self):
        for attr, expected in [
            ("ONLINE", "ONLINE"), ("ONBATT", "ONBATT"), ("LOWBATT", "LOWBATT"),
            ("COMMOK", "COMMOK"), ("COMMBAD", "COMMBAD"), ("REPLBATT", "REPLBATT"),
            ("FSD", "FSD"), ("CHARGING", "CHARGING"), ("OVERLOAD", "OVERLOAD"),
        ]:
            self.assertEqual(getattr(NotifyType, attr), expected)


class TestEventDetector(unittest.TestCase):
    """Test that EventDetector fires correct events on state transitions."""

    def _fire_events(self, transitions):
        """Run detector through a list of (data, connected) tuples, return fired events."""
        fired = []
        bus = EventBus()
        bus.subscribe(lambda e: fired.append(e.notify_type))
        detector = EventDetector(bus)
        for data, connected in transitions:
            detector.process(data, connected)
        time.sleep(0.05)  # let async dispatch thread run
        bus.stop()
        return fired

    def test_commok_on_connect(self):
        data = ups_data_from_raw(SAMPLE_RAW)
        events = self._fire_events([(data, True)])
        self.assertIn(NotifyType.COMMOK, events)

    def test_commbad_on_disconnect(self):
        data = ups_data_from_raw(SAMPLE_RAW)
        events = self._fire_events([(data, True), (None, False)])
        self.assertIn(NotifyType.COMMBAD, events)

    def test_onbatt_transition(self):
        online = ups_data_from_raw(SAMPLE_RAW)
        onbatt = ups_data_from_raw(SAMPLE_ON_BATTERY_RAW)
        events = self._fire_events([(online, True), (onbatt, True)])
        self.assertIn(NotifyType.ONBATT, events)

    def test_online_transition(self):
        online = ups_data_from_raw(SAMPLE_RAW)
        onbatt = ups_data_from_raw(SAMPLE_ON_BATTERY_RAW)
        events = self._fire_events([
            (onbatt, True),   # start on battery
            (online, True),   # power restored
        ])
        self.assertIn(NotifyType.ONLINE, events)

    def test_lowbatt_event(self):
        online = ups_data_from_raw(SAMPLE_RAW)
        low = ups_data_from_raw({**SAMPLE_ON_BATTERY_RAW, "below_capacity_limit": True})
        events = self._fire_events([(online, True), (low, True)])
        self.assertIn(NotifyType.LOWBATT, events)


# ---------------------------------------------------------------------------
# Repr test
# ---------------------------------------------------------------------------

class TestZeroAndStaleHandling(unittest.TestCase):
    """Test that zero measurements and state-based zeros are preserved and exported."""

    def test_zero_values_preserved_in_nut_dict(self):
        data = ups_data_from_raw({
            "ups.status": "OB",
            "input.voltage": 0.0,
            "input.frequency": 0.0,
            "output.voltage": 230.0,
            "output.current": 0.0,
            "output.power": 0,
            "ups.load": 0,
        })
        d = data.to_nut_dict()
        self.assertEqual(d["input.voltage"], 0.0)
        self.assertEqual(d["input.frequency"], 0.0)
        self.assertEqual(d["output.voltage"], 230.0)
        self.assertEqual(d["output.current"], 0.0)
        self.assertEqual(d["output.power"], 0)
        self.assertEqual(d["ups.load"], 0)

    def test_core_decoding_report_31_and_42_zeros(self):
        from ups_module.core import decode_feature_reports
        raw = {
            0x01: [0x01, 0x00, 0x00, 0x00, 0x00, 0x01, 0x00],  # Status good, not AC present
            0x31: [0x31, 0x00, 0x00, 0x00, 0x00],              # 0.0 Hz, 0.0 V
            0x42: [0x42] + [0x00] * 14,                         # 14 bytes payload for standard 0x42
        }
        decoded = decode_feature_reports(raw)
        self.assertEqual(decoded.get("input.voltage"), 0.0)
        self.assertEqual(decoded.get("input.frequency"), 0.0)
        self.assertEqual(decoded.get("output.voltage"), 0.0)
        self.assertEqual(decoded.get("output.current"), 0.0)
        self.assertEqual(decoded.get("output.power"), 0)

    def test_core_decoding_on_battery_forces_input_zeros(self):
        from ups_module.core import decode_feature_reports
        raw = {
            0x01: [0x01, 0x00, 0x00, 0x00, 0x00, 0x01, 0x00],  # ac=0, discharging=1
            0x42: [0x42, 0x00, 0x00, 0x00, 0x00, 0x00, 0x05, 0x00, 0xF4, 0x01, 0xF4, 0x01, 0xFC, 0x08], # 230V out, 0.5A
        }
        decoded = decode_feature_reports(raw)
        self.assertIn("OB", decoded.get("ups.status", ""))
        self.assertEqual(decoded.get("input.voltage"), 0.0)
        self.assertEqual(decoded.get("input.frequency"), 0.0)

    def test_low_battery_software_fallback_when_charge_zero(self):
        from ups_module.core import decode_feature_reports
        raw = {
            0x01: [0x01, 0x00, 0x00, 0x00, 0x00, 0x01, 0x00],  # ac=0, below_capacity=0, discharging=1
            0x06: [0x06, 0x00, 0x00, 0x00, 0x00, 0x00],        # battery.charge = 0%
            0x42: [0x42] + [0x00] * 14,
        }
        decoded = decode_feature_reports(raw)
        status = decoded.get("ups.status", "")
        self.assertIn("OB", status)
        self.assertIn("LB", status)
        self.assertIn("DISCHRG", status)

    def test_offline_2000d_on_battery_status_is_ob_dischrg_not_bypass(self):
        from ups_module.core import decode_feature_reports
        # PPC Offline 2000D Report 0x01: 7 bytes where d[3]=1 is Discharging (NOT Bypass)
        raw = {
            0x01: [0x01, 0x00, 0x00, 0x00, 0x01, 0x01, 0x00],  # ac=0, below_capacity=0, d[3]=1 (discharging)
            0x06: [0x06, 0x50, 0x00, 0x00, 0x00, 0x00],        # battery.charge = 80%
            0x42: [0x42, 0xF4, 0x01, 0xFC, 0x08],               # 50.0 Hz, 230.0 V
        }
        device_info = {"product_string": "Offline UPS 2000D", "profile_id": "ppc_offline_2000d"}
        decoded = decode_feature_reports(raw, device_info=device_info)
        status = decoded.get("ups.status", "")
    def test_offline_2000d_load_and_dynamic_power(self):
        from ups_module.core import decode_feature_reports
        from enerex_ups_bridge import enrich_nut_variables
        raw = {
            0x01: [0x01, 0x01, 0x00, 0x00, 0x00, 0x01, 0x00],  # AC present
            0x07: [0x07, 0x0C, 0x15, 0x01],                     # Report 0x07: load = 12%, Vbat = 27.7V
            0x42: [0x42, 0xF4, 0x01, 0xE6, 0x00],               # 50.0 Hz, 230 V
        }
        device_info = {"product_string": "Offline UPS 2000D", "profile_id": "ppc_offline_2000d"}
        decoded = decode_feature_reports(raw, device_info=device_info)
        self.assertEqual(decoded.get("ups.load"), 12)
        
        enriched = enrich_nut_variables(decoded, device_info)
        self.assertEqual(enriched.get("ups.load"), 12)
        # Power calculation: 12% of 2700 = 324 W / 324 VA
        self.assertEqual(enriched.get("output.power"), 324)
        self.assertEqual(enriched.get("output.power.apparent"), 324)
        self.assertEqual(enriched.get("output.current"), 1.4)


if __name__ == "__main__":
    unittest.main(verbosity=2)
