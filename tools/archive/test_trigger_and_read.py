import sys
import time
import ctypes
from ctypes import wintypes

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

print("=== TRIGGER AND READ TEST FOR MEC MEC0003 ===")

GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
OPEN_EXISTING = 3
FILE_FLAG_OVERLAPPED = 0x40000000
INVALID_HANDLE_VALUE = -1
ERROR_IO_PENDING = 997

class OVERLAPPED(ctypes.Structure):
    _fields_ = [
        ("Internal", ctypes.c_ulong),
        ("InternalHigh", ctypes.c_ulong),
        ("Offset", wintypes.DWORD),
        ("OffsetHigh", wintypes.DWORD),
        ("hEvent", wintypes.HANDLE),
    ]

hid = ctypes.windll.hid
kernel32 = ctypes.windll.kernel32

CreateFileA = kernel32.CreateFileA
CreateFileA.argtypes = [wintypes.LPCSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
CreateFileA.restype = wintypes.HANDLE

CloseHandle = kernel32.CloseHandle
CloseHandle.argtypes = [wintypes.HANDLE]
CloseHandle.restype = wintypes.BOOL

CreateEventA = kernel32.CreateEventA
CreateEventA.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.BOOL, wintypes.LPCSTR]
CreateEventA.restype = wintypes.HANDLE

ReadFile = kernel32.ReadFile
ReadFile.argtypes = [wintypes.HANDLE, wintypes.LPVOID, wintypes.DWORD, wintypes.LPDWORD, ctypes.POINTER(OVERLAPPED)]
ReadFile.restype = wintypes.BOOL

WriteFile = kernel32.WriteFile
WriteFile.argtypes = [wintypes.HANDLE, wintypes.LPCVOID, wintypes.DWORD, wintypes.LPDWORD, ctypes.POINTER(OVERLAPPED)]
WriteFile.restype = wintypes.BOOL

GetOverlappedResult = kernel32.GetOverlappedResult
GetOverlappedResult.argtypes = [wintypes.HANDLE, ctypes.POINTER(OVERLAPPED), wintypes.LPDWORD, wintypes.BOOL]
GetOverlappedResult.restype = wintypes.BOOL

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
    FILE_FLAG_OVERLAPPED,
    None
)

ov_read = OVERLAPPED()
ov_read.hEvent = CreateEventA(None, True, False, None)

ov_write = OVERLAPPED()
ov_write.hEvent = CreateEventA(None, True, False, None)

def try_read(timeout_ms=500):
    buf = (ctypes.c_ubyte * 64)()
    bytes_read = wintypes.DWORD(0)
    res = ReadFile(h, buf, 64, ctypes.byref(bytes_read), ctypes.byref(ov_read))
    err = kernel32.GetLastError()
    if not res and err == ERROR_IO_PENDING:
        wait_res = kernel32.WaitForSingleObject(ov_read.hEvent, timeout_ms)
        if wait_res == 0:
            res = GetOverlappedResult(h, ctypes.byref(ov_read), ctypes.byref(bytes_read), False)
            if res and bytes_read.value > 0:
                b = bytes(buf[:bytes_read.value])
                print(f"  🎉 SUCCESS READ! len={bytes_read.value}, hex={b.hex()}, str='{b}'")
                kernel32.ResetEvent(ov_read.hEvent)
                return True
        kernel32.CancelIo(h)
        kernel32.ResetEvent(ov_read.hEvent)
    elif res and bytes_read.value > 0:
        b = bytes(buf[:bytes_read.value])
        print(f"  🎉 SUCCESS IMMEDIATE READ! len={bytes_read.value}, hex={b.hex()}, str='{b}'")
        kernel32.ResetEvent(ov_read.hEvent)
        return True
    return False

# Test WriteFile / SetFeature / SetOutputReport triggers
commands = [b"Q1\r", b"Q1", b"I\r", b"F\r"]

print("\n--- 1. Testing Overlapped WriteFile triggers ---")
for rep_id in range(0, 4):
    for cmd in commands:
        for payload_len in [8, 9, 16, 64]:
            buf = bytearray([rep_id]) + cmd
            buf = buf.ljust(payload_len, b'\x00')
            written = wintypes.DWORD(0)
            res = WriteFile(h, (ctypes.c_ubyte * len(buf)).from_buffer(buf), len(buf), ctypes.byref(written), ctypes.byref(ov_write))
            err = kernel32.GetLastError()
            if not res and err == ERROR_IO_PENDING:
                GetOverlappedResult(h, ctypes.byref(ov_write), ctypes.byref(written), True)
                kernel32.ResetEvent(ov_write.hEvent)
                res = True
            if res:
                print(f"WriteFile sent: RepID={rep_id}, cmd={cmd}, len={payload_len}")
                if try_read(100):
                    break

print("\n--- 2. Testing SetFeature triggers ---")
for rep_id in range(0, 4):
    for cmd in commands:
        for payload_len in [8, 9, 16, 64]:
            buf = bytearray([rep_id]) + cmd
            buf = buf.ljust(payload_len, b'\x00')
            c_buf = (ctypes.c_ubyte * len(buf)).from_buffer(buf)
            res = HidD_SetFeature(h, c_buf, len(buf))
            if res:
                print(f"SetFeature sent: RepID={rep_id}, cmd={cmd}, len={payload_len}")
                if try_read(100):
                    break

if HidD_SetOutputReport:
    print("\n--- 3. Testing SetOutputReport triggers ---")
    for rep_id in range(0, 4):
        for cmd in commands:
            for payload_len in [8, 9, 16, 64]:
                buf = bytearray([rep_id]) + cmd
                buf = buf.ljust(payload_len, b'\x00')
                c_buf = (ctypes.c_ubyte * len(buf)).from_buffer(buf)
                res = HidD_SetOutputReport(h, c_buf, len(buf))
                if res:
                    print(f"SetOutputReport sent: RepID={rep_id}, cmd={cmd}, len={payload_len}")
                    if try_read(100):
                        break

CloseHandle(ov_read.hEvent)
CloseHandle(ov_write.hEvent)
CloseHandle(h)
print("\nDone!")

