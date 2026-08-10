import sys
import time
import ctypes
from ctypes import wintypes

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

print("=== TESTING ACCESS MODES WITH MEC MEC0003 ===")

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

HidD_SetFeature = hid.HidD_SetFeature
HidD_SetFeature.argtypes = [wintypes.HANDLE, wintypes.LPCVOID, wintypes.ULONG]
HidD_SetFeature.restype = wintypes.BOOL

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

for access_mode, mode_name in [(0, "0 (None/Query)"), (GENERIC_READ, "GENERIC_READ"), (GENERIC_READ | GENERIC_WRITE, "GENERIC_READ | GENERIC_WRITE")]:
    for share_mode, share_name in [(FILE_SHARE_READ | FILE_SHARE_WRITE, "SHARE_READ_WRITE"), (0, "EXCLUSIVE (0)")]:
        h = CreateFileA(dev_path.encode('ascii'), access_mode, share_mode, None, OPEN_EXISTING, 0, None)
        if h == INVALID_HANDLE_VALUE or h == 0 or h == -1:
            print(f"Access: {mode_name}, Share: {share_name} -> Handle FAILED (Error {kernel32.GetLastError()})")
            continue
        
        # Test GetFeature on Report ID 1
        g_buf = (ctypes.c_ubyte * 16)()
        g_buf[0] = 1
        g_res = HidD_GetFeature(h, g_buf, 16)
        g_err = kernel32.GetLastError()
        b = bytes(g_buf)
        print(f"Access: {mode_name:<25}, Share: {share_name:<20} -> GetFeature(1): success={g_res}, LastError={g_err}, hex={b.hex()}")
        CloseHandle(h)

