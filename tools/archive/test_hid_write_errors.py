import sys
import ctypes
from ctypes import wintypes

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

print("=== DIAGNOSING HID WRITE ERRORS FOR MEC MEC0003 ===")

GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
OPEN_EXISTING = 3
FILE_FLAG_OVERLAPPED = 0x40000000
INVALID_HANDLE_VALUE = -1

hid = ctypes.windll.hid
kernel32 = ctypes.windll.kernel32

CreateFileA = kernel32.CreateFileA
CreateFileA.argtypes = [wintypes.LPCSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
CreateFileA.restype = wintypes.HANDLE

CloseHandle = kernel32.CloseHandle
CloseHandle.argtypes = [wintypes.HANDLE]
CloseHandle.restype = wintypes.BOOL

WriteFile = kernel32.WriteFile
WriteFile.argtypes = [wintypes.HANDLE, wintypes.LPCVOID, wintypes.DWORD, wintypes.LPDWORD, wintypes.LPVOID]
WriteFile.restype = wintypes.BOOL

HidD_SetFeature = hid.HidD_SetFeature
HidD_SetFeature.argtypes = [wintypes.HANDLE, wintypes.LPCVOID, wintypes.ULONG]
HidD_SetFeature.restype = wintypes.BOOL

HidD_SetOutputReport = getattr(hid, 'HidD_SetOutputReport', None)
if HidD_SetOutputReport:
    HidD_SetOutputReport.argtypes = [wintypes.HANDLE, wintypes.LPCVOID, wintypes.ULONG]
    HidD_SetOutputReport.restype = wintypes.BOOL

import pywinusb.hid as pyhid
devices = pyhid.HidDeviceFilter(vendor_id=0x0001, product_id=0x0000).get_devices()
dev_path = devices[0].device_path

h = CreateFileA(
    dev_path.encode('ascii'),
    GENERIC_READ | GENERIC_WRITE,
    FILE_SHARE_READ | FILE_SHARE_WRITE,
    None,
    OPEN_EXISTING,
    0,
    None
)

print(f"Handle opened: {h}")

# Test WriteFile, SetFeature, SetOutputReport with Report IDs 0..5 and lengths 1..64
for rep_id in range(0, 6):
    for buf_len in [8, 9, 16, 64]:
        buf = bytearray([rep_id]) + b"Q1\r"
        buf = buf.ljust(buf_len, b'\x00')
        
        # 1. WriteFile
        written = wintypes.DWORD(0)
        res1 = WriteFile(h, (ctypes.c_ubyte * len(buf)).from_buffer(buf), len(buf), ctypes.byref(written), None)
        err1 = kernel32.GetLastError()
        if res1:
            print(f"✅ WriteFile SUCCESS! RepID={rep_id}, len={buf_len}")
        else:
            if err1 != 1: # ERROR_INVALID_FUNCTION / ERROR_GEN_FAILURE
                print(f"  WriteFile RepID={rep_id}, len={buf_len}: Error {err1}")

        # 2. SetFeature
        c_buf = (ctypes.c_ubyte * len(buf)).from_buffer(buf)
        res2 = HidD_SetFeature(h, c_buf, len(buf))
        err2 = kernel32.GetLastError()
        if res2:
            print(f"✅ SetFeature SUCCESS! RepID={rep_id}, len={buf_len}")
        else:
            if err2 != 1:
                print(f"  SetFeature RepID={rep_id}, len={buf_len}: Error {err2}")

        # 3. SetOutputReport
        if HidD_SetOutputReport:
            res3 = HidD_SetOutputReport(h, c_buf, len(buf))
            err3 = kernel32.GetLastError()
            if res3:
                print(f"✅ SetOutputReport SUCCESS! RepID={rep_id}, len={buf_len}")
            else:
                if err3 != 1:
                    print(f"  SetOutputReport RepID={rep_id}, len={buf_len}: Error {err3}")

CloseHandle(h)
print("\nDone!")

