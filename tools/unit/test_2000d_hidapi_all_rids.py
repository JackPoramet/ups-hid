#!/usr/bin/env python3
"""
tools/unit/test_2000d_hidapi_all_rids.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
ทดสอบส่ง Feature Report ผ่าน hidapi ครอบคลุมทุก Report ID (0x01..0x3F) และทุกรูปแบบ Payload
ไปยัง PPC 2000D (Serial: 000000000___ / path: 19f55223) เพื่อค้นหา Report ID ที่สามารถสวิตช์ Relay จริง
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
import hid

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

devices = hid.enumerate(0x06DA, 0xFFFF)
target_path = None
target_info = None

for d in devices:
    sn = d.get("serial_number", "")
    p_str = d.get("path", b"").decode("utf-8", errors="ignore")
    rel = d.get("release_number")
    if "000000000" in sn or "19f55223" in p_str or rel == 3:
        target_path = d.get("path")
        target_info = d
        break

if not target_path:
    print("❌ ไม่พบอุปกรณ์ PPC 2000D ใน hid.enumerate()")
    sys.exit(1)

print(f"✅ เปิดอุปกรณ์ PPC 2000D: path={target_info.get('path')}")

h = hid.device()
try:
    h.open_path(target_path)
    print("✅ เปิด hidapi device handle สำเร็จ!")
except Exception as exc:
    print(f"❌ เปิด hidapi device ล้มเหลว: {exc}")
    sys.exit(1)

print("\n🚀 เริ่มทดสอบส่ง Feature Report 0x01..0x3F สองรูปแบบ Payload...\n")

successful_rids = []

for rid in range(1, 0x40):
    # Form 1: Byte code [rid, 0x01]
    p1 = [rid, 0x01] + [0]*62
    s1 = False
    err1 = ""
    try:
        res1 = h.send_feature_report(p1)
        if res1 > 0:
            s1 = True
    except Exception as e:
        err1 = str(e)

    # Form 2: Q1 string [rid] + b"T\r"
    q1_bytes = list(b"T\r")
    p2 = [rid] + q1_bytes + [0]*(63 - len(q1_bytes))
    s2 = False
    err2 = ""
    try:
        res2 = h.send_feature_report(p2)
        if res2 > 0:
            s2 = True
    except Exception as e:
        err2 = str(e)

    if s1 or s2:
        successful_rids.append((rid, s1, s2))
        print(f"  ✨ RID 0x{rid:02X}: Payload [rid, 0x01] -> {s1} | Payload Q1 'T\\r' -> {s2}")

h.close()

print(f"\n✅ สรุป Report IDs ที่ส่ง Feature Report สำเร็จ ({len(successful_rids)} รายการ):")
for rid, s1, s2 in successful_rids:
    print(f"  • Report ID 0x{rid:02X} (Form1={s1}, Form2={s2})")

if not successful_rids:
    print("  ❌ ไม่มี Report ID ใดที่สามารถส่ง Feature Report ผ่าน hidapi สำเร็จ")
