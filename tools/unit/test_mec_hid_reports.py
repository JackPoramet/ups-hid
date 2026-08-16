import ctypes
from ctypes import wintypes
import sys
import pywinusb.hid as pyhid

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

HidD_GetInputReport = hid.HidD_GetInputReport
HidD_GetInputReport.argtypes = [wintypes.HANDLE, wintypes.LPVOID, wintypes.ULONG]
HidD_GetInputReport.restype = wintypes.BOOL

def get_feature_report(h_dev, rid, length=64):
    buf = (ctypes.c_ubyte * length)()
    buf[0] = rid
    res = HidD_GetFeature(h_dev, ctypes.byref(buf), length)
    if res:
        return list(buf)
    return None

def get_input_report(h_dev, rid, length=64):
    buf = (ctypes.c_ubyte * length)()
    buf[0] = rid
    res = HidD_GetInputReport(h_dev, ctypes.byref(buf), length)
    if res:
        return list(buf)
    return None

def main():
    devices = pyhid.HidDeviceFilter(vendor_id=0x0001, product_id=0x0000).get_devices()
    if not devices:
        print("❌ MEC 800E not found!")
        return
    
    dev = devices[0]
    dev.open()
    print("--- HID Reports Test via PyWinUSB ---")
    
def get_indexed_string(h_dev, index: int) -> str:
    buf = ctypes.create_unicode_buffer(256)
    res = hid.HidD_GetIndexedString(h_dev, index, buf, 512)
    if res:
        return buf.value.strip()
    return ""

def main():
    devices = pyhid.HidDeviceFilter(vendor_id=0x0001, product_id=0x0000).get_devices()
    if not devices:
        print("❌ MEC 800E not found!")
        return
    dev_path = devices[0].device_path
    h_dev = CreateFileA(dev_path.encode('ascii'), GENERIC_READ | GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_WRITE, None, OPEN_EXISTING, 0, None)
    
    if h_dev == INVALID_HANDLE_VALUE or h_dev == 0 or h_dev == -1:
        print("❌ Cannot open handle!")
        return

    print("--- String Descriptors Scan ---")
    for i in range(1, 21):
        s = get_indexed_string(h_dev, i)
        if s:
            print(f"String [{i:>2}]: {s}")
            
    CloseHandle(h_dev)

if __name__ == "__main__":
    main()
