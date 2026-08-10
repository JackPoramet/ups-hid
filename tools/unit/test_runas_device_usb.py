#!/usr/bin/env python3
"""
tools/unit/test_runas_device_usb.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
ทดสอบสั่งรัน santak.lib.DeviceUsb ผ่าน Admin Elevation (Verb RunAs)
เพื่อยืนยันว่าเมื่อมีสิทธิ์ Administrator แล้ว hid_force_openEx บน PPC 2000D จะได้ Error 0 (Success)
และส่งคำสั่ง Battery Test ให้เกิดเสียง Relay Click + Beep เสียงดังได้ทันที
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

out_log = Path(__file__).resolve().parent / "admin_test.log"
if out_log.exists():
    out_log.unlink()

# สร้าง Java Command ที่จะรันผ่าน PowerShell RunAs
cmd_str = (
    f'& "C:\\Program Files\\WinpowerG2\\jre\\bin\\java.exe" '
    f'"-Djava.library.path=C:\\Program Files\\WinpowerG2" '
    f'-cp "C:\\Program Files\\WinpowerG2\\lib\\usbcomm-1.0.0.jar;C:\\Program Files\\WinpowerG2\\lib\\*" '
    f'santak.lib.DeviceUsb > "{out_log}" 2>&1'
)

print(f"🚀 กำลังเรียกรัน DeviceUsb ในสิทธิ์ Administrator (RunAs)...")

ps_cmd = [
    "powershell",
    "-Command",
    f"Start-Process powershell -ArgumentList '-NoProfile -ExecutionPolicy Bypass -Command \"{cmd_str}\"' -Verb RunAs -Wait"
]

try:
    proc = subprocess.run(ps_cmd, check=False, timeout=15)
    print(f"✅ Executed Admin command return code: {proc.returncode}")
except Exception as exc:
    print(f"⚠️ RunAs Command Execution Note: {exc}")

time.sleep(2.0)

if out_log.exists():
    log_txt = out_log.read_text(encoding="utf-8", errors="ignore")
    print(f"\n📋 ผลลัพธ์จากการรันในสิทธิ์ Administrator (Admin Log):\n{log_txt}")
else:
    print("⚠️ ไม่พบไฟล์ admin_test.log (โปรดดูหน้าต่าง Admin PowerShell)")
