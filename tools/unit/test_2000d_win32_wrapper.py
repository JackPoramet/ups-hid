#!/usr/bin/env python3
"""
tools/unit/test_2000d_win32_wrapper.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
ทดสอบส่ง Feature Report ผ่าน win32_hid_wrapper.py (WinHidApi / HidD_SetFeature Direct Win32 Handle)
ไปยัง PPC 2000D เพื่อตรวจสอบว่า Win32 Handle สามารถส่ง Feature Report สั่งงาน Relay ได้หรือไม่
"""

from __future__ import annotations

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

from win32_hid_wrapper import WinHidApi, normalize_path
from core_hid_ups import list_ups_devices

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

api = WinHidApi()
h_dev = api.create_file(dev_path)

if not h_dev or h_dev == -1:
    print("❌ เปิด Win32 Handle ล้มเหลว")
    sys.exit(1)

print("✅ เปิด Win32 Direct Handle สำเร็จ! เริ่มทดสอบส่ง Feature Report 0x01..0x3F ผ่าน HidD_SetFeature...")

successful_rids = []

for rid in range(1, 0x40):
    # Payload Form 1: Byte code [rid, 0x01]
    p1 = bytes([rid, 0x01] + [0]*62)
    s1 = api.set_feature_report(h_dev, p1)

    # Payload Form 2: Q1 string [rid] + b"T\r"
    q1_bytes = list(b"T\r")
    p2 = bytes([rid] + q1_bytes + [0]*(63 - len(q1_bytes)))
    s2 = api.set_feature_report(h_dev, p2)

    if s1 or s2:
        successful_rids.append((rid, s1, s2))
        print(f"  ✨ RID 0x{rid:02X}: Form1=[rid, 0x01] ➔ {s1} | Form2=Q1 'T\\r' ➔ {s2}")

api.close_handle(h_dev)

print(f"\n✅ สรุป Report IDs ที่ส่งผ่าน Win32 HidD_SetFeature สำเร็จ ({len(successful_rids)} รายการ):")
for rid, s1, s2 in successful_rids:
    print(f"  • Report ID 0x{rid:02X} (Form1={s1}, Form2={s2})")

if not successful_rids:
    print("  ❌ ไม่มี Report ID ใดที่ส่งผ่าน Win32 HidD_SetFeature สำเร็จ")
