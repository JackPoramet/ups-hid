import json
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from ups_module.client import UPSClient
from ups_module.device_registry import DeviceRegistry


class TestDeviceIdentity(unittest.TestCase):
    def test_opened_product_refines_generic_profile_and_stop_opcode(self):
        handle = Mock()
        handle.send_feature_report.side_effect = lambda data: len(data)
        client = self._detect("")
        with patch("ups_module.client.open_ups_device", return_value=(handle, {"product_string": "Offline UPS"})):
            client.connect()
        self.assertEqual(client.profile.id, "enerex_offline_2000d")
        self.assertTrue(client.test_battery_stop()[0])
        handle.send_feature_report.assert_called_once_with([0x24, 0x03])
        client.disconnect()

    def test_implicit_library_connection_refines_but_explicit_overrides_remain(self):
        for explicit in (False, True):
            handle = Mock()
            handle.get_indexed_string.return_value = "Unity 1000 T"
            client = UPSClient(model="phoenixtec_innova_unity_rt3k" if explicit else None, report_ids=[1])
            with patch("ups_module.client.open_ups_device", return_value=(handle, {"product_string": "Innova Unity"})):
                client.connect()
            self.assertEqual(client.profile.id, "phoenixtec_innova_unity_rt3k" if explicit else "phoenixtec_innova_unity_tower_1k")
            self.assertEqual(client._report_ids, [1])
            client.disconnect()

    def _detect(self, product):
        with patch("hid.enumerate", return_value=[dict(vendor_id=0x06da, product_id=0xffff, product_string=product)]), patch("hid.device", side_effect=AssertionError("Real HID blocked")):
            return UPSClient.auto_detect()

    def test_generic_and_empty_product_do_not_claim_rt3k(self):
        for product in ("Innova Unity", "", None):
            with self.subTest(product=product):
                client = self._detect(product)
                self.assertTrue(client.profile.features.get("variant_unknown"))

    def test_specific_variants_are_matched_without_serial_rules(self):
        for product, model in (("Unity 1000 T", "phoenixtec_innova_unity_tower_1k"),
                               ("Tower 1K", "phoenixtec_innova_unity_tower_1k"),
                               ("Unity 3000 RT", "phoenixtec_innova_unity_rt3k"),
                               ("Unity 10K T", "phoenixtec_innova_unity_tower_3_1_10k"),
                               ("InnovaBasicG2", "enerex_innova_basic_g2"),
                               ("Offline UPS", "enerex_offline_2000d")):
            with self.subTest(product=product):
                self.assertEqual(self._detect(product).profile.id, model)

    def test_generic_identity_refines_using_known_phoenixtec_descriptor(self):
        fixture = Path(__file__).resolve().parents[3] / "tools/Tower_1K/ups_descriptor_06da_ffff.json"
        captured = json.loads(fixture.read_text(encoding="utf-8"))["device"]
        handle = Mock()
        handle.get_indexed_string.side_effect = lambda idx: captured["string_descriptors"].get(str(idx), "")
        client = self._detect("Innova Unity")
        with patch("ups_module.client.open_ups_device", return_value=(handle, {"product_string": "Innova Unity"})):
            client.connect()
        self.assertEqual(client.profile.id, "phoenixtec_innova_unity_tower_1k")
        self.assertIn("1K", client.device_info["model"])
        self.assertNotIn(4, [c.args[0] for c in handle.get_indexed_string.call_args_list])
        client.disconnect()

    def test_mec_connection_never_reads_control_descriptor_for_identity(self):
        handle = Mock()
        client = UPSClient(model="enerex_mec0003")
        with patch("ups_module.client.open_ups_device", return_value=(handle, {"product_string": "MEC0003"})):
            client.connect()
        handle.get_indexed_string.assert_not_called()
        client.disconnect()


if __name__ == "__main__":
    unittest.main()
