import sys
import time
import ctypes
from ctypes import wintypes

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

print("=== COMPREHENSIVE HID COMMUNICATION TEST FOR MEC MEC0003 ===")

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

WriteFile = kernel32.WriteFile
WriteFile.argtypes = [wintypes.HANDLE, wintypes.LPCVOID, wintypes.DWORD, wintypes.LPDWORD, wintypes.LPVOID]
WriteFile.restype = wintypes.BOOL

ReadFile = kernel32.ReadFile
ReadFile.argtypes = [wintypes.HANDLE, wintypes.LPVOID, wintypes.DWORD, wintypes.LPDWORD, wintypes.LPVOID]
ReadFile.restype = wintypes.BOOL

HidD_SetFeature = hid.HidD_SetFeature
HidD_SetFeature.argtypes = [wintypes.HANDLE, wintypes.LPCVOID, wintypes.ULONG]
HidD_SetFeature.restype = wintypes.BOOL

HidD_GetFeature = hid.HidD_GetFeature
HidD_GetFeature.argtypes = [wintypes.HANDLE, wintypes.LPVOID, wintypes.ULONG]
HidD_GetFeature.restype = wintypes.BOOL

HidD_SetOutputReport = getattr(hid, 'HidD_SetOutputReport', None)
if HidD_SetOutputReport:
    HidD_SetOutputReport.argtypes = [wintypes.HANDLE, wintypes.LPCVOID, wintypes.ULONG]
    HidD_SetOutputReport.restype = wintypes.BOOL

import pywinusb.hid as pyhid
devices = pyhid.HidDeviceFilter(vendor_id=0x0001, product_id=0x0000).get_devices()
if not devices:
    print("No device found!")
    sys.exit(1)

dev_path = devices[0].device_path
print(f"Opening device: {dev_path}")

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

print(f"Handle opened: {h_dev}")

# 1. Test HidD_SetOutputReport
if HidD_SetOutputReport:
    print("\n--- 1. Testing HidD_SetOutputReport ---")
    for rep_id in range(0, 4):
        for cmd in [b"Q1\r", b"Q1", b"I\r", b"F\r"]:
            for buf_len in [9, 16, 64]:
                buf = bytearray([rep_id]) + cmd
                buf = buf.ljust(buf_len, b'\x00')
                c_buf = (ctypes.c_ubyte * len(buf)).from_buffer(buf)
                res = HidD_SetOutputReport(h_dev, c_buf, len(buf))
                err = kernel32.GetLastError()
                if res:
                    print(f"  ✅ SetOutputReport SUCCESS! RepID={rep_id}, cmd={cmd}, len={buf_len}")
                    # Try GetFeature or GetInputReport or ReadFile to read answer!
                    time.sleep(0.1)
                    # Check GetFeature
                    f_buf = (ctypes.c_ubyte * 16)()
                    f_buf[0] = rep_id
                    g_res = HidD_GetFeature(h_dev, f_buf, 16)
                    if g_res:
                        b = bytes(f_buf)
                        print(f"     GetFeature readback: hex={b.hex()} str='{b}'")

# 2. Test WriteFile
print("\n--- 2. Testing WriteFile ---")
for rep_id in range(0, 4):
    for cmd in [b"Q1\r", b"Q1", b"I\r", b"F\r"]:
        for buf_len in [9, 16, 64]:
            buf = bytearray([rep_id]) + cmd
            buf = buf.ljust(buf_len, b'\x00')
            written = wintypes.DWORD(0)
            res = WriteFile(h_dev, (ctypes.c_ubyte * len(buf)).from_buffer(buf), len(buf), ctypes.byref(written), None)
            err = kernel32.GetLastError()
            if res:
                print(f"  ✅ WriteFile SUCCESS! RepID={rep_id}, cmd={cmd}, len={buf_len}, bytes_written={written.value}")
                time.sleep(0.1)
                # Try GetFeature
                f_buf = (ctypes.c_ubyte * 16)()
                f_buf[0] = rep_id
                g_res = HidD_GetFeature(h_dev, f_buf, 16)
                if g_res:
                    b = bytes(f_buf)
                    print(f"     GetFeature readback: hex={b.hex()} str='{b}'")

# 3. Test HidD_SetFeature with different buffer lengths
print("\n--- 3. Testing HidD_SetFeature with lengths 2..16 ---")
for rep_id in range(0, 4):
    for cmd in [b"Q1\r", b"Q1", b"I\r"]:
        for buf_len in range(2, 17):
            buf = bytearray([rep_id]) + cmd
            if len(buf) > buf_len:
                continue
            buf = buf.ljust(buf_len, b'\x00')
            c_buf = (ctypes.c_ubyte * len(buf)).from_buffer(buf)
            res = HidD_SetFeature(h_dev, c_buf, len(buf))
            err = kernel32.GetLastError()
            if res:
                print(f"  ✅ SetFeature SUCCESS! RepID={rep_id}, cmd={cmd}, len={buf_len}")
                time.sleep(0.1)
                f_buf = (ctypes.c_ubyte * 16)()
                f_buf[0] = rep_id
                g_res = HidD_GetFeature(h_dev, f_buf, 16)
                if g_res:
                    b = bytes(f_buf)
                    print(f"     GetFeature readback: hex={b.hex()} str='{b}'")

CloseHandle(h_dev)
print("\nDone!")

