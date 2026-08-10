#!/usr/bin/env python3
"""
tools/unit/test_2000d_writefile_output.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
ทดสอบส่ง Output Report (WriteFile / SetOutputReport) โดยตรงไปยัง PPC 2000D ผ่าน Win32 CreateFileA
(เพื่อตรวจสอบว่า 2000D รับคำสั่งผ่าน Output Report ID 0x00 / WriteFile สั่งงาน Relay จริงหรือไม่)
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
WINDOWS_DIR = ROOT_DIR / "windows"
for _p in (ROOT_DIR, WINDOWS_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from core_hid_ups import list_ups_devices

GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
OPEN_EXISTING = 3
INVALID_HANDLE_VALUE = -1

kernel32 = ctypes.windll.kernel32
hid_dll = ctypes.windll.hid

CreateFileA = kernel32.CreateFileA
CreateFileA.argtypes = [wintypes.LPCSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
CreateFileA.restype = wintypes.HANDLE

WriteFile = kernel32.WriteFile
WriteFile.argtypes = [wintypes.HANDLE, wintypes.LPCVOID, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), wintypes.LPVOID]
WriteFile.restype = wintypes.BOOL

CloseHandle = kernel32.CloseHandle
CloseHandle.argtypes = [wintypes.HANDLE]
CloseHandle.restype = wintypes.BOOL

HidD_SetOutputReport = hid_dll.HidD_SetOutputReport
HidD_SetOutputReport.argtypes = [wintypes.HANDLE, wintypes.LPVOID, wintypes.ULONG]
HidD_SetOutputReport.restype = wintypes.BOOL

devices = list_ups_devices(target_vid=None)
target = None
for d in devices:
    sn = str(d.get("serial_number") or "")
    path = str(d.get("path_str") or "")
    rel = d.get("release_number")
    if "000000000" in sn or "19f55223" in path or rel == 3:
        target = d
        break

if not target:
    print("❌ ไม่พบอุปกรณ์ PPC Offline UPS 2000D")
    sys.exit(1)

dev_path = target.get("path_str")
print(f"✅ เลือกอุปกรณ์: {target.get('manufacturer_string')} {target.get('product_string')}")
print(f"   Device Path: {dev_path}")

path_bytes = dev_path.encode("ascii") if isinstance(dev_path, str) else dev_path
h_dev = CreateFileA(path_bytes, GENERIC_READ | GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_WRITE, None, OPEN_EXISTING, 0, None)

if h_dev == INVALID_HANDLE_VALUE or h_dev == 0:
    print("❌ ไม่สามารถเปิด CreateFileA handle ได้ (อาจถูกโปรแกรมอื่นล็อกไว้)")
    sys.exit(1)

print("✅ เปิด handle สำเร็จ! เริ่มทดสอบส่ง Output Report และ SetOutputReport...")

test_buffers = [
    ("Q1 Command 'T\\r' (Output Report ID 0x00)", bytes([0x00] + list(b"T\r") + [0]*61)),
    ("Q1 Command 'T' (Output Report ID 0x00)", bytes([0x00] + list(b"T") + [0]*62)),
    ("Byte Code [0x00, 0x01] (Report 0x00)", bytes([0x00, 0x01] + [0]*62)),
    ("Byte Code [0x02, 0x01] (Report 0x02)", bytes([0x02, 0x01] + [0]*62)),
    ("Q1 Command 'T\\r' (HidD_SetOutputReport 0x00)", bytes([0x00] + list(b"T\r") + [0]*61)),
]

written = wintypes.DWORD(0)

try:
    for idx, (label, buf_bytes) in enumerate(test_buffers, start=1):
        print(f"\n [{idx}] กำลังส่ง {label}...")
        
        # 1. ลองผ่าน WriteFile
        res_wf = WriteFile(h_dev, buf_bytes, len(buf_bytes), ctypes.byref(written), None)
        print(f"     ➔ WriteFile: res={bool(res_wf)}, bytes_written={written.value}")

        # 2. ลองผ่าน HidD_SetOutputReport
        res_or = HidD_SetOutputReport(h_dev, buf_bytes, len(buf_bytes))
        print(f"     ➔ HidD_SetOutputReport: res={bool(res_or)}")

        time.sleep(2.0)

finally:
    CloseHandle(h_dev)

print("\n✅ ทดสอบเสร็จสิ้นทั้งหมด!")
