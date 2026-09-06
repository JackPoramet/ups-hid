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

class HIDP_CAPS(ctypes.Structure):
    _fields_ = [
        ("Usage", wintypes.USHORT),
        ("UsagePage", wintypes.USHORT),
        ("InputReportByteLength", wintypes.USHORT),
        ("OutputReportByteLength", wintypes.USHORT),
        ("FeatureReportByteLength", wintypes.USHORT),
        ("Reserved", wintypes.USHORT * 17),
        ("NumberLinkCollectionNodes", wintypes.USHORT),
        ("NumberInputButtonCaps", wintypes.USHORT),
        ("NumberInputValueCaps", wintypes.USHORT),
        ("NumberInputDataIndices", wintypes.USHORT),
        ("NumberOutputButtonCaps", wintypes.USHORT),
        ("NumberOutputValueCaps", wintypes.USHORT),
        ("NumberOutputDataIndices", wintypes.USHORT),
        ("NumberFeatureButtonCaps", wintypes.USHORT),
        ("NumberFeatureValueCaps", wintypes.USHORT),
        ("NumberFeatureDataIndices", wintypes.USHORT),
    ]

HidD_GetPreparsedData = hid.HidD_GetPreparsedData
HidD_GetPreparsedData.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.LPVOID)]
HidD_GetPreparsedData.restype = wintypes.BOOL

HidP_GetCaps = hid.HidP_GetCaps
HidP_GetCaps.argtypes = [wintypes.LPVOID, ctypes.POINTER(HIDP_CAPS)]
HidP_GetCaps.restype = wintypes.LONG

HidD_FreePreparsedData = hid.HidD_FreePreparsedData
HidD_FreePreparsedData.argtypes = [wintypes.LPVOID]
HidD_FreePreparsedData.restype = wintypes.BOOL

devices = pyhid.HidDeviceFilter(vendor_id=0x0001, product_id=0x0000).get_devices()
dev_path = devices[0].device_path
h = CreateFileA(dev_path.encode('ascii'), GENERIC_READ | GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_WRITE, None, OPEN_EXISTING, 0, None)

p_data = wintypes.LPVOID()
if HidD_GetPreparsedData(h, ctypes.byref(p_data)):
    caps = HIDP_CAPS()
    status = HidP_GetCaps(p_data, ctypes.byref(caps))
    print(f"Status: {status}")
    print(f"UsagePage: 0x{caps.UsagePage:04x}")
    print(f"Usage: 0x{caps.Usage:04x}")
    print(f"InputReportByteLength: {caps.InputReportByteLength}")
    print(f"OutputReportByteLength: {caps.OutputReportByteLength}")
    print(f"FeatureReportByteLength: {caps.FeatureReportByteLength}")
    HidD_FreePreparsedData(p_data)
else:
    print("Failed to get preparsed data!")

CloseHandle(h)
