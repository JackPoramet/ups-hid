import ctypes
from ctypes import wintypes
import sys
import time
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
    buf = ctypes.create_unicode_buffer(256)
    res = hid.HidD_GetIndexedString(h_dev, index, buf, 512)
    if res:
        return buf.value.strip()
    return None

def check_status(h_dev):
    s = get_indexed_string(h_dev, 3)
    if s and s.startswith("("):
        parts = s[1:].split()
        if len(parts) >= 8:
            bits = parts[7]
            bit5 = bits[5] if len(bits) >= 6 else "?"
            return f"Vin={parts[0]} Vout={parts[2]} Vbat={parts[5]} Bits={bits} TestBit5={bit5}"
    return f"Raw={s}"

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

    print("Initial Status:")
    print(" ", check_status(h_dev))
    time.sleep(0.5)

    print("\nScanning String Indices 1 to 100 with 150ms delay...")
    found = {}
    for idx in range(1, 101):
        s = get_indexed_string(h_dev, idx)
        if s:
            # Filter non-printable / garbage
            printable = "".join(c for c in s if 32 <= ord(c) <= 126)
            found[idx] = (s, printable)
            print(f"Index [{idx:>3}]: len={len(s)} text='{printable}' (repr={repr(s[:30])})")
        time.sleep(0.15)

    print("\nChecking Status after scan:")
    print(" ", check_status(h_dev))

    CloseHandle(h_dev)

if __name__ == "__main__":
    main()
