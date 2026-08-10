import sys
import time
import ctypes
from ctypes import wintypes

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

print("=== WIN32 HIDD_SETFEATURE & HIDD_GETFEATURE TEST ===")

# Win32 Constants
GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
OPEN_EXISTING = 3
INVALID_HANDLE_VALUE = -1

hid = ctypes.windll.hid
kernel32 = ctypes.windll.kernel32

# Load APIs
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

# Get device path via PyWinUSB or hidapi
import pywinusb.hid as pyhid
devices = pyhid.HidDeviceFilter(vendor_id=0x0001, product_id=0x0000).get_devices()
if not devices:
    print("No device found!")
    sys.exit(1)

dev_path = devices[0].device_path
print(f"Device Path: {dev_path}")

# Open handle using CreateFileA
h_dev = CreateFileA(
    dev_path.encode('ascii'),
    GENERIC_READ | GENERIC_WRITE,
    FILE_SHARE_READ | FILE_SHARE_WRITE,
    None,
    OPEN_EXISTING,
    0,
    None
)

if h_dev == INVALID_HANDLE_VALUE or h_dev == 0 or h_dev == -1:
    print(f"Failed to open device handle! LastError={kernel32.GetLastError()}")
    sys.exit(1)

print(f"Opened handle: {h_dev}")

# Test SetFeature & GetFeature with Report IDs 0, 1, 2, 3
commands = [b"Q1\r", b"Q1", b"I\r", b"F\r", b"M\r"]
feature_len = 16  # From HID caps!

for rep_id in [0, 1, 2, 3]:
    print(f"\n--- Testing Report ID={rep_id} ---")
    for cmd in commands:
        # Buffer: Report ID + cmd + padding zeros to feature_len (16 bytes)
        buf = bytearray([rep_id]) + cmd
        buf = buf.ljust(feature_len, b'\x00')
        
        c_buf = (ctypes.c_ubyte * len(buf)).from_buffer(buf)
        res = HidD_SetFeature(h_dev, c_buf, len(buf))
        err = kernel32.GetLastError()
        print(f"  HidD_SetFeature (ReportID={rep_id}, cmd={cmd}): success={res}, LastError={err}")
        
        if res:
            time.sleep(0.1)
            # Try GetFeature to read response
            resp_buf = (ctypes.c_ubyte * feature_len)()
            resp_buf[0] = rep_id
            g_res = HidD_GetFeature(h_dev, resp_buf, feature_len)
            g_err = kernel32.GetLastError()
            resp_bytes = bytes(resp_buf)
            print(f"    HidD_GetFeature: success={g_res}, LastError={g_err}, hex={resp_bytes.hex()} str='{resp_bytes}'")

CloseHandle(h_dev)
print("\nClosed handle. Done!")

