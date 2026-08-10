#!/usr/bin/env python3
"""
tools/unit/test_2000d_win32_query_access.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
ทดสอบเปิด Win32 Handle ด้วย Query Access Mode (dwDesiredAccess = 0)
ซึ่งเป็นเทคนิคมาตรฐานบน Windows HID สำหรับ bypass สิทธิการส่ง HidD_SetFeature / HidD_SetOutputReport
ไปยัง PPC 2000D (path: 19f55223)
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
from win32_hid_wrapper import normalize_path

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

HidD_SetFeature = hid_dll.HidD_SetFeature
HidD_SetFeature.argtypes = [wintypes.HANDLE, wintypes.LPVOID, wintypes.ULONG]
HidD_SetFeature.restype = wintypes.BOOL

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
    print("❌ ไม่พบอุปกรณ์ PPC 2000D")
    sys.exit(1)

dev_path = normalize_path(target.get("path_str"))
print(f"✅ เลือกอุปกรณ์ PPC 2000D: {dev_path}")

# เปิดด้วย dwDesiredAccess = 0 (Query Access Mode)
path_bytes = dev_path.encode("ascii") if isinstance(dev_path, str) else dev_path
h_dev = CreateFileA(path_bytes, 0, FILE_SHARE_READ | FILE_SHARE_WRITE, None, OPEN_EXISTING, 0, None)

if h_dev == INVALID_HANDLE_VALUE or h_dev == 0:
    print("❌ ไม่สามารถเปิด CreateFileA handle (dwDesiredAccess=0) ได้")
    sys.exit(1)

print("✅ เปิด Handle ด้วย dwDesiredAccess = 0 สำเร็จ!")

test_reports = [
    ("Report 0x03 Code 1 [0x03, 0x01]", [0x03, 0x01]),
    ("Report 0x24 Code 1 [0x24, 0x01]", [0x24, 0x01]),
    ("Report 0x07 Code 1 [0x07, 0x01]", [0x07, 0x01]),
    ("Report 0x02 Q1 'T\\r'", [0x02] + list(b"T\r")),
    ("Report 0x03 Q1 'T\\r'", [0x03] + list(b"T\r")),
    ("Report 0x00 Q1 'T\\r'", [0x00] + list(b"T\r")),
]

written = wintypes.DWORD(0)

print("\n🚀 เริ่มทดสอบส่ง Feature / Output Reports (เว้นระยะ 2.5 วินาทีโปรดฟังเสียง Relay / Beep)...\n")

try:
    for label, p_bytes in test_reports:
        buf = ctypes.create_string_buffer(bytes(p_bytes + [0]*(64 - len(p_bytes))))
        
        # 1. ทดสอบ HidD_SetFeature
        res_sf = HidD_SetFeature(h_dev, buf, len(buf))
        
        # 2. ทดสอบ HidD_SetOutputReport
        res_so = HidD_SetOutputReport(h_dev, buf, len(buf))
        
        # 3. ทดสอบ WriteFile
        res_wf = WriteFile(h_dev, buf, len(buf), ctypes.byref(written), None)

        print(f"  • {label:<40} ➔ SetFeature={bool(res_sf)}, SetOutput={bool(res_so)}, WriteFile={bool(res_wf)}")
        time.sleep(2.5)

finally:
    CloseHandle(h_dev)

print("\n✅ การทดสอบเสร็จสิ้นทั้งหมด")
