#!/usr/bin/env python3
"""
tools/unit/test_2000d_rid01_subcommands.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
ค้นพบจากการทดสอบ: Report ID 0x01 เป็น Report ID เดียวที่ผ่านการตรวจสอบของ Windows HID Stack (WinError 31 ไม่ใช่ WinError 87)
ทดสอบเปิด Handle ด้วยสิทธิ์ GENERIC_READ | GENERIC_WRITE และส่ง Payload บน RID 0x01 ทุกรูปแบบ
เพื่อกระตุ้นให้วงจร PPC 2000D สวิตช์ Relay และ Beep จริง
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

CloseHandle = kernel32.CloseHandle
CloseHandle.argtypes = [wintypes.HANDLE]
CloseHandle.restype = wintypes.BOOL

HidD_SetFeature = hid_dll.HidD_SetFeature
HidD_SetFeature.argtypes = [wintypes.HANDLE, wintypes.LPVOID, wintypes.ULONG]
HidD_SetFeature.restype = wintypes.BOOL

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

path_bytes = dev_path.encode("ascii") if isinstance(dev_path, str) else dev_path

# เปิดด้วย GENERIC_READ | GENERIC_WRITE ( write access )
h_dev = CreateFileA(path_bytes, GENERIC_READ | GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_WRITE, None, OPEN_EXISTING, 0, None)
if h_dev == INVALID_HANDLE_VALUE or h_dev == 0:
    print("⚠️ ไม่สามารถเปิดด้วย GENERIC_WRITE ได้ ลองใช้ 0 Access Mode...")
    h_dev = CreateFileA(path_bytes, 0, FILE_SHARE_READ | FILE_SHARE_WRITE, None, OPEN_EXISTING, 0, None)

if h_dev == INVALID_HANDLE_VALUE or h_dev == 0:
    print("❌ ไม่สามารถเปิด Handle ได้")
    sys.exit(1)

print("✅ เปิด Handle สำเร็จ! เริ่มส่ง Report ID 0x01 Subcommands (โปรดฟังเสียง Relay / Beep)...\n")

test_payloads = [
    ("RID 0x01 'T\\r' [0x01, 'T', '\\r', 0..]", bytes([0x01, ord('T'), ord('\r'), 0, 0, 0, 0, 0])),
    ("RID 0x01 'T' [0x01, 'T', 0, 0..]", bytes([0x01, ord('T'), 0, 0, 0, 0, 0, 0])),
    ("RID 0x01 Code [0x01, 0x01, 0, 0..]", bytes([0x01, 0x01, 0, 0, 0, 0, 0, 0])),
    ("RID 0x01 Code [0x01, 0x03, 0x01, 0..]", bytes([0x01, 0x03, 0x01, 0, 0, 0, 0, 0])),
    ("RID 0x01 'TL\\r' [0x01, 'T', 'L', '\\r', 0..]", bytes([0x01, ord('T'), ord('L'), ord('\r'), 0, 0, 0, 0])),
    ("RID 0x01 Q1 Hex [0x01, 0x54, 0x0D, 0..]", bytes([0x01, 0x54, 0x0D, 0, 0, 0, 0, 0])),
    ("RID 0x24 'T\\r' [0x24, 'T', '\\r', 0..]", bytes([0x24, ord('T'), ord('\r'), 0, 0, 0, 0, 0])),
    ("RID 0x24 Code [0x24, 0x01, 0, 0..]", bytes([0x24, 0x01, 0, 0, 0, 0, 0, 0])),
]

try:
    for label, p_bytes in test_payloads:
        buf = ctypes.create_string_buffer(p_bytes, 8)
        res = HidD_SetFeature(h_dev, buf, 8)
        err = kernel32.GetLastError() if not res else 0
        print(f"  • {label:<45} ➔ SetFeature={bool(res)} (WinError={err})")
        time.sleep(2.5)

finally:
    CloseHandle(h_dev)

print("\n✅ การทดสอบเสร็จสิ้นทั้งหมด")
