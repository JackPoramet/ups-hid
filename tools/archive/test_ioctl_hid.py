import sys
import time
import ctypes
from ctypes import wintypes

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

print("=== TESTING DEVICEIOCONTROL IOCTL_HID FOR MEC MEC0003 ===")

GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
OPEN_EXISTING = 3
INVALID_HANDLE_VALUE = -1

# IOCTL Codes
IOCTL_HID_SET_FEATURE          = 0x000B0191
IOCTL_HID_GET_FEATURE          = 0x000B0192
IOCTL_HID_GET_INPUT_REPORT     = 0x000B01A6
IOCTL_HID_SET_OUTPUT_REPORT    = 0x000B0195

kernel32 = ctypes.windll.kernel32

CreateFileA = kernel32.CreateFileA
CreateFileA.argtypes = [wintypes.LPCSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
CreateFileA.restype = wintypes.HANDLE

CloseHandle = kernel32.CloseHandle
CloseHandle.argtypes = [wintypes.HANDLE]
CloseHandle.restype = wintypes.BOOL

DeviceIoControl = kernel32.DeviceIoControl
DeviceIoControl.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD, wintypes.LPDWORD, wintypes.LPVOID]
DeviceIoControl.restype = wintypes.BOOL

import pywinusb.hid as pyhid
devices = pyhid.HidDeviceFilter(vendor_id=0x0001, product_id=0x0000).get_devices()
dev_path = devices[0].device_path

h = CreateFileA(dev_path.encode('ascii'), GENERIC_READ | GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_WRITE, None, OPEN_EXISTING, 0, None)
print(f"Handle opened: {h}")

bytes_returned = wintypes.DWORD(0)

# Test IOCTL_HID_SET_FEATURE with Q1\r
commands = [b"Q1\r", b"Q1", b"I\r", b"F\r"]

print("\n--- 1. Testing IOCTL_HID_SET_FEATURE ---")
for rep_id in [0, 1, 2, 3]:
    for cmd in commands:
        for payload_len in [8, 9, 16, 64]:
            buf = bytearray([rep_id]) + cmd
            buf = buf.ljust(payload_len, b'\x00')
            c_in = (ctypes.c_ubyte * len(buf)).from_buffer(buf)
            res = DeviceIoControl(h, IOCTL_HID_SET_FEATURE, c_in, len(buf), None, 0, ctypes.byref(bytes_returned), None)
            err = kernel32.GetLastError()
            if res:
                print(f"✅ IOCTL_HID_SET_FEATURE SUCCESS! RepID={rep_id}, cmd={cmd}, len={payload_len}")
                # Read GetFeature
                g_buf = (ctypes.c_ubyte * 16)()
                g_buf[0] = rep_id
                res_g = DeviceIoControl(h, IOCTL_HID_GET_FEATURE, g_buf, 16, g_buf, 16, ctypes.byref(bytes_returned), None)
                if res_g:
                    b = bytes(g_buf)
                    print(f"   🎉 GET_FEATURE RESPONSE: hex={b.hex()} str='{b}'")

print("\n--- 2. Testing IOCTL_HID_GET_FEATURE directly ---")
for rep_id in [0, 1, 2, 3]:
    g_buf = (ctypes.c_ubyte * 16)()
    g_buf[0] = rep_id
    res_g = DeviceIoControl(h, IOCTL_HID_GET_FEATURE, g_buf, 16, g_buf, 16, ctypes.byref(bytes_returned), None)
    err = kernel32.GetLastError()
    if res_g:
        b = bytes(g_buf)
        print(f"✅ IOCTL_HID_GET_FEATURE RepID={rep_id} SUCCESS! hex={b.hex()} str='{b}'")

CloseHandle(h)
print("\nDone!")

