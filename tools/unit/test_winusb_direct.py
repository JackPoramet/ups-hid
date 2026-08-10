#!/usr/bin/env python3
"""
tools/unit/test_winusb_direct.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
การทดสอบส่งคำสั่งผ่าน Microsoft WinUSB API (winusb.dll -> WinUsb_ControlTransfer)
ซึ่งเป็นเลเยอร์ Low-Level HID/USB ที่ Winpower G2 (jusb.dll - WINUSB Project) ใช้จริง!
"""

import ctypes
from ctypes import wintypes
import os
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Microsoft WinUSB structures & constants
class WINUSB_SETUP_PACKET(ctypes.Structure):
    _fields_ = [
        ("RequestType", ctypes.c_uint8),
        ("Request", ctypes.c_uint8),
        ("Value", ctypes.c_uint16),
        ("Index", ctypes.c_uint16),
        ("Length", ctypes.c_uint16),
    ]

# Setup Windows DLLs
kernel32 = ctypes.windll.kernel32
setupapi = ctypes.windll.setupapi
winusb = ctypes.windll.winusb

# Constants
GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
OPEN_EXISTING = 3
FILE_FLAG_OVERLAPPED = 0x40000000
INVALID_HANDLE_VALUE = -1

def is_admin() -> bool:
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False

def test_winusb_control_transfer():
    print("==============================================================================")
    print(" 🚀 Low-Level Microsoft WinUSB API Direct Control Transfer Test for PPC 2000D")
    print("==============================================================================")

    if not is_admin():
        print("🔒 [UAC] ขอยกระดับสิทธิ์ Administrator เพื่อเข้าถึง WinUSB Low-Level Handle...")
        script = os.path.abspath(sys.argv[0])
        ret = ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, f'"{script}"', None, 1)
        if ret > 32:
            sys.exit(0)
        else:
            print("❌ ไม่ได้รับสิทธิ์ Admin")
            return

    # 1. ค้นหา Device Path ของ PPC 2000D ผ่าน SetupDiGetClassDevs / hid.dll
    import hid
    devices = hid.enumerate(0x06DA, 0xFFFF)
    if not devices:
        print("❌ ไม่พบอุปกรณ์ VID 0x06DA PID 0xFFFF ในระบบ")
        return

    dev_info = devices[0]
    dev_path = dev_info['path']
    if isinstance(dev_path, bytes):
        dev_path_str = dev_path.decode('utf-8', errors='ignore')
    else:
        dev_path_str = str(dev_path)

    print(f"✅ พบอุปกรณ์ PPC 2000D Path: {dev_path_str}")

    # 2. เปิด CreateFile Handle ด้วย FILE_FLAG_OVERLAPPED สำหรับ WinUSB
    CreateFileW = kernel32.CreateFileW
    CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    CreateFileW.restype = wintypes.HANDLE

    h_file = CreateFileW(
        dev_path_str,
        GENERIC_READ | GENERIC_WRITE,
        FILE_SHARE_READ | FILE_SHARE_WRITE,
        None,
        OPEN_EXISTING,
        FILE_FLAG_OVERLAPPED,
        None
    )

    if h_file == INVALID_HANDLE_VALUE or h_file == 0:
        err = kernel32.GetLastError()
        print(f"❌ ไม่สามารถเปิด CreateFile Handle ได้ (WinError: {err})")
        return

    print(f"✅ เปิด CreateFile Handle สำเร็จ! (Handle: {hex(h_file)})")

    # 3. เรียก WinUsb_Initialize
    winusb_handle = wintypes.HANDLE()
    WinUsb_Initialize = winusb.WinUsb_Initialize
    WinUsb_Initialize.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.HANDLE)]
    WinUsb_Initialize.restype = wintypes.BOOL

    init_ok = WinUsb_Initialize(h_file, ctypes.byref(winusb_handle))
    if not init_ok:
        err = kernel32.GetLastError()
        print(f"⚠️ WinUsb_Initialize ล้มเหลว (WinError: {err})")
        print("ℹ️  กำลังทดสอบสร้าง Direct WinUSB Interface...")
        kernel32.CloseHandle(h_file)
        return

    print(f"🎉 WinUsb_Initialize สำเร็จ! WinUSB Interface Handle: {hex(winusb_handle.value)}")

    # 4. เรียก WinUsb_ControlTransfer ยิงคำสั่ง "T\r"
    WinUsb_ControlTransfer = winusb.WinUsb_ControlTransfer
    WinUsb_ControlTransfer.argtypes = [
        wintypes.HANDLE,
        WINUSB_SETUP_PACKET,
        ctypes.c_char_p,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
        ctypes.c_void_p
    ]
    WinUsb_ControlTransfer.restype = wintypes.BOOL

    # ทดสอบค่า wValue ต่างๆ (0x0301, 0x0324, 0x0303, 0x0200)
    test_values = [0x0301, 0x0324, 0x0303, 0x0200]
    payload = b"T\r\x00\x00\x00\x00\x00\x00"

    try:
        for val in test_values:
            setup = WINUSB_SETUP_PACKET()
            setup.RequestType = 0x21 # Host to Device | Class | Interface
            setup.Request = 0x09     # SET_REPORT
            setup.Value = val
            setup.Index = 0
            setup.Length = 8

            transferred = wintypes.DWORD(0)
            buf = ctypes.create_string_buffer(payload)

            ok = WinUsb_ControlTransfer(winusb_handle, setup, buf, 8, ctypes.byref(transferred), None)
            if ok:
                print(f"🎯 SUCCESS! WinUsb_ControlTransfer (wValue=0x{val:04X}) -> Transferred: {transferred.value} bytes")
                print("🔊 สังเกตเสียง RELAY CLICK สลับโหมด และเสียง BEEP จาก UPS!")
            else:
                err = kernel32.GetLastError()
                print(f"  WinUsb_ControlTransfer (wValue=0x{val:04X}) failed -> WinError: {err}")

    finally:
        WinUsb_Free = winusb.WinUsb_Free
        WinUsb_Free.argtypes = [wintypes.HANDLE]
        WinUsb_Free(winusb_handle)
        kernel32.CloseHandle(h_file)
        print("🔒 ปิด WinUSB Handle เรียบร้อย")

if __name__ == "__main__":
    test_winusb_control_transfer()
