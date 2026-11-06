"""Rating evidence collection uses fake USB only."""
import sys
import unittest
import tempfile
import json
import struct
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from ups_module.capture_ratings import capture_device, main
import ups_module.capture_ratings as capture


class FakeDevice:
    idVendor = 0x06DA
    idProduct = 0xFFFF
    manufacturer = "PPC"
    product = "Offline UPS"
    serial_number = "fixture"
    bus = 6
    address = 5

    def __init__(self):
        self.requests = []

    def get_active_configuration(self):
        return [SimpleNamespace(bInterfaceClass=3, bInterfaceNumber=0)]

    def is_kernel_driver_active(self, interface):
        return False

    def ctrl_transfer(self, **kw):
        self.requests.append(kw)
        if kw["bmRequestType"] == 0x81:
            return bytes([0x85, 0x74, 0x75, 0x10])
        return bytes([0x74, 9, 0])


class TestRatingCapture(unittest.TestCase):
    def test_basic_uses_actual_advertised_descriptor_length_and_flags_short_capture(self):
        fixture = Path(__file__).resolve().parents[3] / "tools/Basic_G2/usb_configuration_06da_ffff.json"
        config = json.loads(fixture.read_text())
        dev = FakeDevice()
        dev.get_active_configuration = lambda: [SimpleNamespace(
            bInterfaceClass=3, bInterfaceNumber=0,
            extra_descriptors=bytes.fromhex(config["hid_descriptor_hex"]))]
        result = capture_device(dev)
        descriptor_request = next(r for r in dev.requests if r["bmRequestType"] == 0x81)
        self.assertEqual(descriptor_request["data_or_wLength"], 1041)
        self.assertFalse(result["complete"])  # Fake returns only4 of1041 declared bytes.

    def setUp(self):
        self.real_find_hidraw = capture._find_hidraw_node
        guard = patch.object(capture, "_find_hidraw_node", side_effect=RuntimeError("Real kernel HID access blocked"))
        guard.start()
        self.addCleanup(guard.stop)

    @unittest.skipUnless(os.name == "posix", "Requires sysfs-style symlinks")
    def test_hidraw_mapping_matches_bus_address_interface_and_rejects_ambiguity(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            sys_class = root / "class"
            sys_class.mkdir()
            def add(name, address):
                usb = root / name
                interface = usb / "interface"
                hid = interface / "hid"
                hid.mkdir(parents=True)
                (usb / "busnum").write_text("6")
                (usb / "devnum").write_text(str(address))
                (interface / "bInterfaceNumber").write_text("00")
                entry = sys_class / name
                entry.mkdir()
                (entry / "device").symlink_to(hid, target_is_directory=True)
            add("hidraw0", 99)
            add("hidraw1", 5)
            self.assertEqual(self.real_find_hidraw(FakeDevice(), 0, sys_class, root / "dev"), root / "dev/hidraw1")
            add("hidraw2", 5)
            with self.assertRaises(RuntimeError):
                self.real_find_hidraw(FakeDevice(), 0, sys_class, root / "dev")

    def test_kernel_owned_device_uses_get_only_hidraw_without_usb_claim(self):
        dev = FakeDevice()
        dev.is_kernel_driver_active = lambda _: True
        desc = bytes([0x85, 0x74, 0x75, 0x10])
        requests = []
        def ioctl(fd, request, buf, mutate=True):
            requests.append(request)
            if request == 0x80084803:
                buf[:] = struct.pack("IHH", 3, 0x06DA, 0xFFFF)
            elif request == 0x80044801:
                buf[:] = struct.pack("I", len(desc))
            elif request == 0x90044802:
                buf[4:4+len(desc)] = desc
            elif request == 0xC0404807:
                self.assertEqual(buf[0], 0x74)
                buf[:3] = bytes([0x74, 9, 0])
                return 3
            else:
                self.fail(f"Unexpected ioctl {request:x}")
            return 0
        with patch.object(capture, "_find_hidraw_node", return_value=Path("/dev/hidraw-fixture"), create=True), patch("os.open", return_value=42), patch("os.close") as close, patch("usb.util.dispose_resources"), patch.dict(sys.modules, {"fcntl": SimpleNamespace(ioctl=ioctl)}):
            result = capture_device(dev)
        self.assertTrue(result["complete"])
        self.assertEqual(result["report_74_raw"], [0x74, 9, 0])
        self.assertEqual(result["report_descriptor_hex"], desc.hex())
        self.assertEqual(result["transport"], "hidraw")
        self.assertEqual(requests, [0x80084803, 0x80044801, 0x90044802, 0xC0404807])
        self.assertEqual(dev.requests, [])
        close.assert_called_once_with(42)

    def test_hidraw_identity_mismatch_cannot_read_feature(self):
        dev = FakeDevice()
        dev.is_kernel_driver_active = lambda _: True
        requests = []
        def ioctl(fd, request, buf, mutate=True):
            requests.append(request)
            buf[:] = struct.pack("IHH", 3, 1, 0)
            return 0
        with patch.object(capture, "_find_hidraw_node", return_value=Path("/dev/hidraw-fixture"), create=True), patch("os.open", return_value=42), patch("os.close") as close, patch("usb.util.dispose_resources"), patch.dict(sys.modules, {"fcntl": SimpleNamespace(ioctl=ioctl)}):
            with self.assertRaisesRegex(RuntimeError, "identity"):
                capture_device(dev)
        self.assertEqual(requests, [0x80084803])
        close.assert_called_once_with(42)

    def test_partial_cli_capture_preserves_file_but_returns_failure(self):
        dev = FakeDevice()
        read = dev.ctrl_transfer
        def transfer(**kw):
            if kw["bmRequestType"] == 0x81:
                raise OSError("descriptor unavailable")
            return read(**kw)
        dev.ctrl_transfer = transfer
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "partial.json"
            with patch("usb.core.find", return_value=[dev]), patch("usb.util.dispose_resources"), patch.object(sys, "argv", ["capture", "--output", str(output)]):
                self.assertEqual(main(), 2)
            self.assertFalse(json.loads(output.read_text())["complete"])

    def test_header_only_or_wrong_report_is_incomplete_evidence(self):
        for raw in (bytes([0x74]), bytes([0x73, 9, 0])):
            dev = FakeDevice()
            read = dev.ctrl_transfer
            dev.ctrl_transfer = lambda **kw: raw if kw["bmRequestType"] == 0xA1 else read(**kw)
            result = capture_device(dev)
            self.assertFalse(result["complete"])
            self.assertEqual(result["report_74_raw"], list(raw))

    def test_retains_exact_raw_bytes_and_uses_only_two_read_requests(self):
        dev = FakeDevice()
        result = capture_device(dev)
        self.assertEqual(result["report_74_raw"], [0x74, 9, 0])
        self.assertEqual(result["report_descriptor_hex"], "85747510")
        self.assertEqual(result["device"]["product"], "Offline UPS")
        self.assertEqual(dev.requests, [
            dict(bmRequestType=0xA1, bRequest=0x01, wValue=0x0374,
                 wIndex=0, data_or_wLength=64, timeout=5000),
            dict(bmRequestType=0x81, bRequest=0x06, wValue=0x2200,
                 wIndex=0, data_or_wLength=4096, timeout=5000),
        ])

    def test_rejects_mec_before_accessing_usb(self):
        dev = FakeDevice()
        dev.idVendor, dev.idProduct = 1, 0
        with self.assertRaisesRegex(ValueError, "Phoenixtec"):
            capture_device(dev)
        self.assertEqual(dev.requests, [])

    def test_kernel_owned_interface_is_not_detached(self):
        dev = FakeDevice()
        dev.is_kernel_driver_active = lambda _: True
        with self.assertRaisesRegex(RuntimeError, "kernel"):
            capture_device(dev)
        self.assertEqual(dev.requests, [])

    def test_ambiguous_hid_interfaces_are_rejected(self):
        dev = FakeDevice()
        dev.get_active_configuration = lambda: [
            SimpleNamespace(bInterfaceClass=3, bInterfaceNumber=0),
            SimpleNamespace(bInterfaceClass=3, bInterfaceNumber=1),
        ]
        with self.assertRaisesRegex(RuntimeError, "one HID"):
            capture_device(dev)
        self.assertEqual(dev.requests, [])

    def test_missing_descriptor_is_recorded_without_inventing_layout(self):
        dev = FakeDevice()
        transfer = dev.ctrl_transfer
        def read(**kw):
            if kw["bmRequestType"] == 0x81:
                raise OSError("descriptor unavailable")
            return transfer(**kw)
        dev.ctrl_transfer = read
        result = capture_device(dev)
        self.assertEqual(result["report_74_raw"], [0x74, 9, 0])
        self.assertIsNone(result["report_descriptor_hex"])
        self.assertFalse(result["complete"])
        self.assertIn("descriptor unavailable", result["errors"]["report_descriptor"])


if __name__ == "__main__":
    unittest.main()
