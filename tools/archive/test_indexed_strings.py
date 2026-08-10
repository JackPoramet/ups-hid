import sys
import ctypes
from ctypes import wintypes

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

print("=== TESTING HIDD_GETINDEXEDSTRING FOR MEC MEC0003 ===")

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

HidD_GetIndexedString = hid.HidD_GetIndexedString
HidD_GetIndexedString.argtypes = [wintypes.HANDLE, wintypes.ULONG, wintypes.LPVOID, wintypes.ULONG]
HidD_GetIndexedString.restype = wintypes.BOOL

import pywinusb.hid as pyhid
devices = pyhid.HidDeviceFilter(vendor_id=0x0001, product_id=0x0000).get_devices()
dev_path = devices[0].device_path

h = CreateFileA(dev_path.encode('ascii'), GENERIC_READ | GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_WRITE, None, OPEN_EXISTING, 0, None)
print(f"Handle opened: {h}")

for idx in range(0, 30):
    buf = ctypes.create_unicode_buffer(256)
    res = HidD_GetIndexedString(h, idx, buf, 512)
    err = kernel32.GetLastError()
    if res and buf.value:
        print(f"  ✅ Index {idx}: '{buf.value}'")
    else:
        if err != 121: # ERROR_SEM_TIMEOUT
            pass

CloseHandle(h)
print("\nDone!")

