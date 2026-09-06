import ctypes
from ctypes import wintypes
import sys
import pywinusb.hid as pyhid

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

hid = ctypes.windll.hid
kernel32 = ctypes.windll.kernel32

GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
OPEN_EXISTING = 3
INVALID_HANDLE_VALUE = -1

CreateFileA = kernel32.CreateFileA
CreateFileA.argtypes = [wintypes.LPCSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
CreateFileA.restype = wintypes.HANDLE
CloseHandle = kernel32.CloseHandle
CloseHandle.argtypes = [wintypes.HANDLE]
CloseHandle.restype = wintypes.BOOL

HidD_GetFeature = hid.HidD_GetFeature
HidD_GetFeature.argtypes = [wintypes.HANDLE, wintypes.LPVOID, wintypes.ULONG]
HidD_GetFeature.restype = wintypes.BOOL

HidD_SetFeature = hid.HidD_SetFeature
HidD_SetFeature.argtypes = [wintypes.HANDLE, wintypes.LPCVOID, wintypes.ULONG]
HidD_SetFeature.restype = wintypes.BOOL

HidD_GetInputReport = hid.HidD_GetInputReport
HidD_GetInputReport.argtypes = [wintypes.HANDLE, wintypes.LPVOID, wintypes.ULONG]
HidD_GetInputReport.restype = wintypes.BOOL

devices = pyhid.HidDeviceFilter(vendor_id=0x0001, product_id=0x0000).get_devices()
dev_path = devices[0].device_path
h = CreateFileA(dev_path.encode('ascii'), GENERIC_READ | GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_WRITE, None, OPEN_EXISTING, 0, None)

buf16 = (ctypes.c_ubyte * 16)()
buf16[0] = 0x00
res = HidD_GetFeature(h, ctypes.cast(buf16, wintypes.LPVOID), 16)
err = kernel32.GetLastError()
print(f"GetFeature 16: res={res}, err={err}")
if res:
    print(f"Data: {bytes(buf16).hex()}")

buf9 = (ctypes.c_ubyte * 9)()
buf9[0] = 0x00
res = HidD_GetInputReport(h, ctypes.cast(buf9, wintypes.LPVOID), 9)
err = kernel32.GetLastError()
print(f"GetInputReport 9: res={res}, err={err}")
if res:
    print(f"Data: {bytes(buf9).hex()}")

# Try SetFeature
buf_set = (ctypes.c_ubyte * 16)()
buf_set[0] = 0x00
buf_set[1] = ord('T')
buf_set[2] = 0x0D
res = HidD_SetFeature(h, ctypes.cast(buf_set, wintypes.LPCVOID), 16)
err = kernel32.GetLastError()
print(f"SetFeature 'T\\r': res={res}, err={err}")

CloseHandle(h)
