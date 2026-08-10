import sys
import time
import ctypes
from ctypes import wintypes

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

print("=== NON-BLOCKING WIN32 HID READ TEST FOR MEC MEC0003 ===")

GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
OPEN_EXISTING = 3
INVALID_HANDLE_VALUE = -1

hid = ctypes.windll.hid
kernel32 = ctypes.windll.kernel32

CreateFileA = kernel32.CreateFileA
CreateFileA.argtypes = [wintypes.LPCSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
CreateFileA.restype = wintypes.HANDLE

CloseHandle = kernel32.CloseHandle
CloseHandle.argtypes = [wintypes.HANDLE]
CloseHandle.restype = wintypes.BOOL

HidD_GetFeature = hid.HidD_GetFeature
HidD_GetFeature.argtypes = [wintypes.HANDLE, wintypes.LPVOID, wintypes.ULONG]
HidD_GetFeature.restype = wintypes.BOOL

HidD_GetInputReport = getattr(hid, 'HidD_GetInputReport', None)
if HidD_GetInputReport:
    HidD_GetInputReport.argtypes = [wintypes.HANDLE, wintypes.LPVOID, wintypes.ULONG]
    HidD_GetInputReport.restype = wintypes.BOOL

import pywinusb.hid as pyhid
devices = pyhid.HidDeviceFilter(vendor_id=0x0001, product_id=0x0000).get_devices()
dev_path = devices[0].device_path

h_dev = CreateFileA(
    dev_path.encode('ascii'),
    GENERIC_READ | GENERIC_WRITE,
    FILE_SHARE_READ | FILE_SHARE_WRITE,
    None,
    OPEN_EXISTING,
    0,
    None
)

print(f"Opened handle: {h_dev}")

# 1. Test GetFeature for all report IDs (0..10) with feature length = 16
print("\n--- Testing HidD_GetFeature for Report IDs 0..10 ---")
for rep_id in range(0, 10):
    buf = (ctypes.c_ubyte * 16)()
    buf[0] = rep_id
    res = HidD_GetFeature(h_dev, buf, 16)
    err = kernel32.GetLastError()
    b = bytes(buf)
    if res:
        print(f"✅ HidD_GetFeature Report ID={rep_id}: SUCCESS! hex={b.hex()} str='{b}'")
    else:
        print(f"❌ HidD_GetFeature Report ID={rep_id}: failed (LastError={err})")

# 2. Test HidD_GetInputReport for all report IDs (0..10) with input length = 9
if HidD_GetInputReport:
    print("\n--- Testing HidD_GetInputReport for Report IDs 0..10 ---")
    for rep_id in range(0, 10):
        buf = (ctypes.c_ubyte * 9)()
        buf[0] = rep_id
        res = HidD_GetInputReport(h_dev, buf, 9)
        err = kernel32.GetLastError()
        b = bytes(buf)
        if res:
            print(f"✅ HidD_GetInputReport Report ID={rep_id}: SUCCESS! hex={b.hex()} str='{b}'")
        else:
            print(f"❌ HidD_GetInputReport Report ID={rep_id}: failed (LastError={err})")

CloseHandle(h_dev)
print("\nDone!")

