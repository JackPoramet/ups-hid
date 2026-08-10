import sys
import ctypes
from ctypes import wintypes

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

print("=== TESTING ALL REPORT IDS AND LENGTHS FOR MEC MEC0003 ===")

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

h = CreateFileA(dev_path.encode('ascii'), GENERIC_READ | GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_WRITE, None, OPEN_EXISTING, 0, None)

print("\n--- 1. Testing HidD_GetFeature (Report ID vs Length) ---")
success_feature = []
for rep_id in range(0, 16):
    for buf_len in range(1, 65):
        g_buf = (ctypes.c_ubyte * buf_len)()
        g_buf[0] = rep_id
        res = HidD_GetFeature(h, g_buf, buf_len)
        if res:
            b = bytes(g_buf)
            print(f"✅ GetFeature SUCCESS! RepID={rep_id}, Length={buf_len}: hex={b.hex()} str='{b}'")
            success_feature.append((rep_id, buf_len, b))

print(f"Total GetFeature successes: {len(success_feature)}")

if HidD_GetInputReport:
    print("\n--- 2. Testing HidD_GetInputReport (Report ID vs Length) ---")
    success_input = []
    for rep_id in range(0, 16):
        for buf_len in range(1, 65):
            i_buf = (ctypes.c_ubyte * buf_len)()
            i_buf[0] = rep_id
            res = HidD_GetInputReport(h, i_buf, buf_len)
            if res:
                b = bytes(i_buf)
                print(f"✅ GetInputReport SUCCESS! RepID={rep_id}, Length={buf_len}: hex={b.hex()} str='{b}'")
                success_input.append((rep_id, buf_len, b))
    print(f"Total GetInputReport successes: {len(success_input)}")

CloseHandle(h)
print("\nDone!")

