import sys
from pathlib import Path
sys.path.insert(0, r"d:\Work\CoE\Project\UPS\windows")

import ctypes
from ctypes import wintypes
import hid
import pywinusb.hid as pyhid

h_hidapi = hid.device()
devs = pyhid.HidDeviceFilter(vendor_id=0x0001, product_id=0x0000).get_devices()
path = devs[0].device_path

print("Opening with hid.device()...")
path_bytes = path.encode('utf-8')
try:
    h_hidapi.open_path(path_bytes)
    print("hid.device() opened successfully.")
except Exception as e:
    print(f"hid.device() failed: {e}")

from win32_hid_wrapper import WinHidApi, normalize_path
api = WinHidApi()
try:
    h_win = api.create_file(normalize_path(path))
    print(f"WinHidApi handle: {h_win}")
    str3 = api.get_indexed_string(h_win, 3)
    print(f"Indexed string 3: {str3}")
    api.close_handle(h_win)
except Exception as e:
    print(f"WinHidApi failed: {e}")

h_hidapi.close()
