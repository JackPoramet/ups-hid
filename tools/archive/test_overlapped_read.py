import sys
import time
import ctypes
from ctypes import wintypes

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

print("=== TESTING OVERLAPPED READFILE FOR MEC MEC0003 ===")

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

GetOverlappedResult = kernel32.GetOverlappedResult
GetOverlappedResult.argtypes = [wintypes.HANDLE, ctypes.POINTER(OVERLAPPED), wintypes.LPDWORD, wintypes.BOOL]
GetOverlappedResult.restype = wintypes.BOOL

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

if h == INVALID_HANDLE_VALUE:
    print(f"Failed to open handle: Error {kernel32.GetLastError()}")
    sys.exit(1)

print(f"Handle opened: {h}")

# Input Report length is 9 bytes
input_len = 9

h_event = CreateEventA(None, True, False, None)
ov = OVERLAPPED()
ov.hEvent = h_event

buf = (ctypes.c_ubyte * input_len)()
bytes_read = wintypes.DWORD(0)

print("\nReading input reports for 5 seconds...")
start_time = time.time()
count = 0

while time.time() - start_time < 5:
    res = ReadFile(h, buf, input_len, ctypes.byref(bytes_read), ctypes.byref(ov))
    err = kernel32.GetLastError()
    
    if not res and err == ERROR_IO_PENDING:
        # Wait up to 500ms
        wait_res = kernel32.WaitForSingleObject(h_event, 500)
        if wait_res == 0: # WAIT_OBJECT_0
            res = GetOverlappedResult(h, ctypes.byref(ov), ctypes.byref(bytes_read), False)
            if res:
                b = bytes(buf)
                count += 1
                print(f"  [{count}] Received Input Report: len={bytes_read.value}, hex={b.hex()}, str='{b}'")
            kernel32.ResetEvent(h_event)
    elif res:
        b = bytes(buf)
        count += 1
        print(f"  [{count}] Received Immediate Input Report: len={bytes_read.value}, hex={b.hex()}, str='{b}'")
        kernel32.ResetEvent(h_event)

CloseHandle(h_event)
CloseHandle(h)
print(f"\nDone! Total packets received: {count}")

