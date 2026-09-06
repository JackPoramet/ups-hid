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

HidD_GetFeature = hid.HidD_GetFeature
HidD_GetFeature.argtypes = [wintypes.HANDLE, wintypes.LPVOID, wintypes.ULONG]
HidD_GetFeature.restype = wintypes.BOOL

HidD_SetFeature = hid.HidD_SetFeature
HidD_SetFeature.argtypes = [wintypes.HANDLE, wintypes.LPCVOID, wintypes.ULONG]
HidD_SetFeature.restype = wintypes.BOOL

HidD_GetInputReport = hid.HidD_GetInputReport
HidD_GetInputReport.argtypes = [wintypes.HANDLE, wintypes.LPVOID, wintypes.ULONG]
HidD_GetInputReport.restype = wintypes.BOOL

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

    print("=== Testing Exact HidD_GetInputReport (Length = 9) ===")
    in_buf = (ctypes.c_ubyte * 9)()
    in_buf[0] = 0x00
    res = HidD_GetInputReport(h_dev, in_buf, 9)
    err = kernel32.GetLastError()
    print(f"HidD_GetInputReport: res={res}, err={err}")
    if res:
        b = bytes(in_buf)
        print(f"  Data hex: {b.hex()} ASCII: {repr(b)}")

    print("\n=== Testing Exact HidD_GetFeature (Length = 16) ===")
    feat_buf = (ctypes.c_ubyte * 16)()
    feat_buf[0] = 0x00
    res = HidD_GetFeature(h_dev, feat_buf, 16)
    err = kernel32.GetLastError()
    print(f"HidD_GetFeature: res={res}, err={err}")
    if res:
        b = bytes(feat_buf)
        print(f"  Data hex: {b.hex()} ASCII: {repr(b)}")

    print("\n=== Testing HidD_SetFeature with various commands (Length = 16) ===")
    test_commands = [
        b"T\r",
        b"TL\r",
        b"Q1\r",
        b"T",
        b"C\r",
        b"CT\r",
        # Fuji / ATCL style: [0x80, 0x06, len+1, 0x03, 'T', '\r', 0, ...]
        bytes([0x80, 0x06, 0x02, 0x03, ord('T'), 0x0D]),
        bytes([0x80, 0x06, 0x03, 0x03, ord('T'), ord('L'), 0x0D]),
    ]

    for cmd in test_commands:
        payload = (ctypes.c_ubyte * 16)()
        payload[0] = 0x00  # Report ID 0
        for i, byte_val in enumerate(cmd):
            if i + 1 < 16:
                payload[i + 1] = byte_val
        res = HidD_SetFeature(h_dev, payload, 16)
        err = kernel32.GetLastError()
        cmd_repr = repr(cmd) if isinstance(cmd, bytes) else cmd
        print(f"  SetFeature cmd={cmd_repr:<25} -> res={res}, err={err}")
        if res:
            print(f"    SUCCESS for {cmd_repr}!")

    CloseHandle(h_dev)

if __name__ == "__main__":
    main()
