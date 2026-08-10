"""Tests for Linux hidapi path compatibility."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from ups_module.core import _hid_path_arg
from ups_module.diagnose_linux import _hid_path_arg as diagnostic_hid_path_arg
from ups_module.linux_setup import _hid_path_arg as setup_hid_path_arg


class TestHidPathArg(unittest.TestCase):
    def test_string_path_is_encoded(self):
        for converter in (_hid_path_arg, diagnostic_hid_path_arg, setup_hid_path_arg):
            self.assertEqual(converter("6-1:1.0"), b"6-1:1.0")

    def test_bytes_path_is_preserved(self):
        for converter in (_hid_path_arg, diagnostic_hid_path_arg, setup_hid_path_arg):
            value = b"/dev/hidraw0"
            self.assertIs(converter(value), value)

    def test_bytearray_path_is_converted(self):
        for converter in (_hid_path_arg, diagnostic_hid_path_arg, setup_hid_path_arg):
            self.assertEqual(converter(bytearray(b"/dev/hidraw0")), b"/dev/hidraw0")

    def test_missing_path_is_rejected(self):
        for converter in (_hid_path_arg, diagnostic_hid_path_arg, setup_hid_path_arg):
            with self.assertRaises(TypeError):
                converter(None)


if __name__ == "__main__":
    unittest.main()