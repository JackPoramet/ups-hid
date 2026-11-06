import sys
import json
import io
import unittest
from pathlib import Path
from unittest.mock import patch, Mock
from contextlib import redirect_stdout

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from ups_module.client import UPSClient
from ups_module.core import decode_feature_reports
from ups_module.models import ups_data_from_raw
from enerex_ups_bridge import enrich_nut_variables
from ups_module.poller import UPSPoller
from ups_module.store import DataStore
import ups_module.core as core


class TestPowerRatings(unittest.TestCase):
    def test_captured_basic_g2_ratings_survive_client_model_bridge_pipeline(self):
        fixture = Path(__file__).resolve().parents[3] / "tools/Basic_G2/ratings_06da_ffff.json"
        captured = json.loads(fixture.read_text())
        info = {"product_string": captured["device"]["product"], "profile_id": "enerex_innova_basic_g2"}
        for padding in (0, 59):
            with self.subTest(padding=padding):
                decoded = decode_feature_reports({0x74: captured["report_74_raw"] + [0]*padding}, device_info=info)
                client = UPSClient(model="enerex_innova_basic_g2")
                with patch.object(client, "_read_raw", return_value=decoded):
                    result = enrich_nut_variables(client.get_vars(), info)
                self.assertEqual(result["ups.power.nominal"], 1000)
                self.assertEqual(result["ups.apparent.power.nominal"], 1000)
                self.assertEqual(result["ups.realpower.nominal"], 900)

    def _padded_offline_capture(self):
        fixture = Path(__file__).resolve().parents[3] / "tools/Offline_2000D/ratings_06da_ffff.json"
        captured = json.loads(fixture.read_text())
        return {1: [1, 1, 0, 0, 0, 1, 0], 0x74: captured["report_74_raw"] + [0]*61}, {"product_string": "Offline UPS"}

    def test_poller_preserves_identity_when_decoding_captured_rating(self):
        raw, info = self._padded_offline_capture()
        store = DataStore()
        poller = UPSPoller(store)
        poller._device_handle = Mock()
        poller._device_info = info
        with patch("ups_module.poller.read_all_feature_reports", return_value=(raw, {})), patch.object(poller, "_fallback_read_input_voltage"):
            poller._poll_once()
        self.assertTrue(store.is_connected)
        self.assertNotIn("ups.realpower.nominal", store.get_ups_dict())

    def test_cli_scan_and_monitor_preserve_identity_for_rating_decode(self):
        raw, info = self._padded_offline_capture()
        decoded = []
        def decode(*args, **kwargs):
            data = decode_feature_reports(*args, **kwargs)
            decoded.append(data)
            return data
        argv = ["scanner", "--model", "enerex_offline_2000d", "--passes", "1",
                "--input-sec", "0", "--monitor-count", "1", "--monitor-interval", "0.001"]
        for opened_info in (info, {}):
            with self.subTest(info=opened_info):
                decoded.clear()
                with patch.object(sys, "argv", argv), patch.object(core, "open_ups_device", return_value=(Mock(), opened_info)), patch.object(core, "read_all_feature_reports", return_value=(raw, {})), patch.object(core, "collect_feature_snapshots", return_value=(raw, {}, {})), patch.object(core, "read_input_reports", return_value={}), patch.object(core, "decode_feature_reports", side_effect=decode), redirect_stdout(io.StringIO()):
                    self.assertEqual(core.main(), 0)
                self.assertEqual(len(decoded), 2)
                for data in decoded:
                    self.assertNotIn("ups.realpower.nominal", data)

    def test_captured_2000d_single_field_is_not_unity_watt_va_layout(self):
        fixture = Path(__file__).resolve().parents[3] / "tools/Offline_2000D/ratings_06da_ffff.json"
        captured = json.loads(fixture.read_text(encoding="utf-8"))
        info = {"product_string": captured["device"]["product"], "profile_id": "enerex_offline_2000d"}
        for padding in (0, 61):
            with self.subTest(padding=padding):
                decoded = decode_feature_reports({0x74: captured["report_74_raw"] + [0] * padding}, device_info=info)
                self.assertNotIn("ups.realpower.nominal", decoded)
                self.assertNotIn("config_max_active_power_w", decoded)
                self.assertNotIn("ups.power.nominal", decoded)
                result = enrich_nut_variables(ups_data_from_raw(decoded).to_nut_dict(), info)
                self.assertEqual(result["ups.power.nominal"], 2000)
                self.assertEqual(result["ups.realpower.nominal"], 1200)

    def test_report_74_two_u16_fields_survive_full_pipeline(self):
        # Tower_1K capture: ConfigActivePower bits 0..15, ConfigApparentPower 16..31.
        for watts, va in ((900, 1000), (2700, 3000), (1200, 2000)):
            payload = [0x74, watts & 255, watts >> 8, va & 255, va >> 8]
            for padding in (0, 59):
                with self.subTest(watts=watts, va=va, padding=padding):
                    decoded = decode_feature_reports({0x74: payload + [0]*padding})
                    client = UPSClient()
                    with patch.object(client, "_read_raw", return_value=decoded):
                        data = client.get_vars()
                    result = enrich_nut_variables(data, {"product_string": "Innova Unity"})
                    self.assertEqual(result["ups.power.nominal"], va)
                    self.assertEqual(result["ups.apparent.power.nominal"], va)
                    self.assertEqual(result["ups.realpower.nominal"], watts)

    def test_generic_unity_does_not_invent_3k_ratings(self):
        data = enrich_nut_variables({"ups.status": "OL", "output.voltage": 230.0},
                                    {"product_string": "Innova Unity"})
        self.assertNotIn("ups.power.nominal", data)
        self.assertNotIn("ups.realpower.nominal", data)

    def test_missing_active_rating_stays_unknown(self):
        raw = {"ups.power.nominal": 1000, "ups.status": "OL", "output.voltage": 230.0}
        result = enrich_nut_variables(ups_data_from_raw(raw).to_nut_dict(), {"product_string": "Innova Unity"})
        self.assertEqual(result["ups.power.nominal"], 1000)
        self.assertNotIn("ups.realpower.nominal", result)

    def test_truncated_report_is_not_a_rating(self):
        for payload in ([0x74, 9, 0], [0x74, 0x84, 3]):
            with self.subTest(payload=payload):
                decoded = decode_feature_reports({0x74: payload})
                self.assertNotIn("ups.power.nominal", decoded)
                self.assertNotIn("config_max_apparent_power_va", decoded)


if __name__ == "__main__":
    unittest.main()
