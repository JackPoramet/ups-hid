import ctypes
from ctypes import wintypes
import sys
import pywinusb.hid as pyhid

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

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

def get_indexed_string(h_dev, index: int):
    buf = ctypes.create_unicode_buffer(512)
    res = hid.HidD_GetIndexedString(h_dev, index, buf, 1024)
    if res:
        val = buf.value
        # also raw bytes
        raw = ctypes.string_at(ctypes.byref(buf), 1024)
        return val, raw[:len(val)*2]
    return None, None

def main():
    devices = pyhid.HidDeviceFilter(vendor_id=0x0001, product_id=0x0000).get_devices()
    if not devices:
        print("❌ MEC not found!")
        return
    dev_path = devices[0].device_path
    h_dev = CreateFileA(dev_path.encode('ascii'), GENERIC_READ | GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_WRITE, None, OPEN_EXISTING, 0, None)
    if h_dev == INVALID_HANDLE_VALUE:
        print("❌ Cannot open handle!")
        return

    print("=== Complete String Descriptor Scan (0..64) ===")
    for i in range(0, 65):
        s, raw = get_indexed_string(h_dev, i)
        if s is not None and len(s) > 0:
            print(f"Index [{i:>2}]: len={len(s)} repr={repr(s)} hex={raw.hex()[:40]}")

    CloseHandle(h_dev)

if __name__ == "__main__":
    main()
