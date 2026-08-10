#!/usr/bin/env python3
"""
tools/unit/test_winusb_guid.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
สแกนหา WinUSB Interface Path (GUID_DEVINTERFACE_USB_DEVICE) สำหรับ VID 0x06DA PID 0xFFFF
แทนที่จะใช้ HID GUID Path
"""

import ctypes
from ctypes import wintypes
import os
import sys
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# GUID structure
class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_ulong),
        ("Data2", ctypes.c_ushort),
        ("Data3", ctypes.c_ushort),
        ("Data4", ctypes.c_ubyte * 8),
    ]

# SP_DEVINFO_DATA structure
class SP_DEVINFO_DATA(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("ClassGuid", GUID),
        ("DevInst", wintypes.DWORD),
        ("Reserved", ctypes.c_void_p),
    ]

# SP_DEVICE_INTERFACE_DATA structure
class SP_DEVICE_INTERFACE_DATA(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("InterfaceClassGuid", GUID),
        ("Flags", wintypes.DWORD),
        ("Reserved", ctypes.c_void_p),
    ]

class WINUSB_SETUP_PACKET(ctypes.Structure):
    _fields_ = [
        ("RequestType", ctypes.c_uint8),
        ("Request", ctypes.c_uint8),
        ("Value", ctypes.c_uint16),
        ("Index", ctypes.c_uint16),
        ("Length", ctypes.c_uint16),
    ]

# GUID_DEVINTERFACE_USB_DEVICE = {A5DC0760-6524-11D1-8E38-00C04FB68820}
GUID_DEVINTERFACE_USB_DEVICE = GUID(
    0xA5DC0760, 0x6524, 0x11D1, (ctypes.c_ubyte * 8)(0x8E, 0x38, 0x00, 0xC0, 0x4F, 0xB6, 0x88, 0x20)
)

DIGCF_PRESENT = 0x0002
DIGCF_DEVICEINTERFACE = 0x0010
GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
OPEN_EXISTING = 3
FILE_FLAG_OVERLAPPED = 0x40000000
INVALID_HANDLE_VALUE = -1

setupapi = ctypes.windll.setupapi
kernel32 = ctypes.windll.kernel32
winusb = ctypes.windll.winusb

def scan_winusb_paths():
    print("==============================================================================")
    print(" 🔍 Direct USB Device Interface Path Scanner (GUID_DEVINTERFACE_USB_DEVICE)")
    print("==============================================================================")

    h_dev_info = setupapi.SetupDiGetClassDevsW(
        ctypes.byref(GUID_DEVINTERFACE_USB_DEVICE), None, None, DIGCF_PRESENT | DIGCF_DEVICEINTERFACE
    )

    if h_dev_info == INVALID_HANDLE_VALUE or h_dev_info == 0:
        print("❌ ไม่สามารถดึง List ของ USB Class Devs ได้")
        return []

    found_paths = []
    dev_interface_data = SP_DEVICE_INTERFACE_DATA()
    dev_interface_data.cbSize = ctypes.sizeof(SP_DEVICE_INTERFACE_DATA)

    index = 0
    while setupapi.SetupDiEnumDeviceInterfaces(h_dev_info, None, ctypes.byref(GUID_DEVINTERFACE_USB_DEVICE), index, ctypes.byref(dev_interface_data)):
        index += 1
        
        # ดึงขนาดของ Detail Data
        needed = wintypes.DWORD(0)
        setupapi.SetupDiGetDeviceInterfaceDetailW(h_dev_info, ctypes.byref(dev_interface_data), None, 0, ctypes.byref(needed), None)

        if needed.value > 0:
            buf = ctypes.create_string_buffer(needed.value)
            # cbSize = 8 บิตสำหรับ 64-bit OS
            cb_size = 8 if ctypes.sizeof(ctypes.c_void_p) == 8 else 6
            ctypes.struct.pack_into("I", buf, 0, cb_size)

            if setupapi.SetupDiGetDeviceInterfaceDetailW(h_dev_info, ctypes.byref(dev_interface_data), buf, needed.value, None, None):
                # Path string อยู่ที่ offset cb_size
                path_bytes = buf.raw[cb_size:]
                path_str = path_bytes.decode("utf-16le", errors="ignore").split("\x00")[0]
                
                if "06da" in path_str.lower() or "06DA" in path_str:
                    print(f"  🎯 Found Matching WinUSB Device Path: {path_str}")
                    found_paths.append(path_str)
                else:
                    print(f"  - USB Path [{index}]: {path_str}")

    setupapi.SetupDiDestroyDeviceInfoList(h_dev_info)
    return found_paths

def test_direct_winusb(path_str):
    print(f"\n⚡ Testing WinUsb_Initialize on {path_str}...")

    h_file = kernel32.CreateFileW(
        path_str,
        GENERIC_READ | GENERIC_WRITE,
        FILE_SHARE_READ | FILE_SHARE_WRITE,
        None,
        OPEN_EXISTING,
        FILE_FLAG_OVERLAPPED,
        None
    )

    if h_file == INVALID_HANDLE_VALUE or h_file == 0:
        err = kernel32.GetLastError()
        print(f"  ❌ CreateFile failed (WinError: {err})")
        return

    winusb_handle = wintypes.HANDLE()
    ok = winusb.WinUsb_Initialize(h_file, ctypes.byref(winusb_handle))
    if not ok:
        err = kernel32.GetLastError()
        print(f"  ❌ WinUsb_Initialize failed (WinError: {err})")
        kernel32.CloseHandle(h_file)
        return

    print(f"  🎉 SUCCESS! WinUSB Handle: {hex(winusb_handle.value)}")

    try:
        # Send Control Transfer
        setup = WINUSB_SETUP_PACKET()
        setup.RequestType = 0x21
        setup.Request = 0x09
        setup.Value = 0x0301
        setup.Index = 0
        setup.Length = 8

        transferred = wintypes.DWORD(0)
        payload = b"T\r\x00\x00\x00\x00\x00\x00"
        buf = ctypes.create_string_buffer(payload)

        ret = winusb.WinUsb_ControlTransfer(winusb_handle, setup, buf, 8, ctypes.byref(transferred), None)
        if ret:
            print(f"  🎯 CONTROL TRANSFER SUCCESS! Transferred: {transferred.value} bytes")
            print("  🔊 LISTEN FOR RELAY CLICK SOUND!")
        else:
            err = kernel32.GetLastError()
            print(f"  ControlTransfer failed -> WinError: {err}")

    finally:
        winusb.WinUsb_Free(winusb_handle)
        kernel32.CloseHandle(h_file)

def main():
    paths = scan_winusb_paths()
    if paths:
        for p in paths:
            test_direct_winusb(p)
    else:
        print("\n⚠️ ไม่พบ Direct USB Path ที่เป็น VID 0x06DA ในสเกล USB Class Device")

if __name__ == "__main__":
    main()
