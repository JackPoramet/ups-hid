"""
UPS Power Mode & Status Diagnostic Tool
=========================================
สคริปต์สำหรับตรวจสอบสถานะและโหมดไฟฟ้าของ UPS (Online / Bypass / On Battery / Standby)
อิงตาม Hardware WorkMode Enum (Report ID 0x07) ของ Phoenixtec Innova Unity (Winpower G2 Compatible)

วิธีรัน:
    .venv\\Scripts\\python.exe windows\\check_ups_status.py
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core_hid_ups import (
    decode_feature_reports,
    infer_tentative_live_values,
    open_ups_device,
    read_all_feature_reports,
)

WORKMODE_MAP = {
    1: ("STANDBY", "⏸️  Standby Mode (เสียบปลั๊ก / ปิดการจ่ายไฟ Output)"),
    2: ("BYPASS",  "🔄 Bypass Mode (โหมดบายพาส — ไฟตรงจากปลั๊ก)"),
    3: ("ONLINE",  "🟢 Line Mode / Online (โหมดปกติผ่าน Inverter)"),
    4: ("BATTERY", "🔋 Battery Mode / On Battery (โหมดสำรองไฟ — ไฟดับ!)"),
    5: ("TEST",    "🧪 Battery Self-Test Mode (โหมดทดสอบแบตเตอรี่)"),
}

def monitor_ups_status(interval_sec: float = 1.0, duration_sec: float = 300.0) -> None:
    print("=" * 72)
    print(" 🔌 UPS POWER MODE MONITORING TOOL (Phoenixtec / Innova Unity)")
    print("=" * 72)
    
    h, info = open_ups_device(0x06DA, 0xFFFF)
    if not h:
        print("❌ ไม่พบอุปกรณ์ UPS (VID=0x06DA)")
        sys.exit(1)

    print(f"✅ เปิดอุปกรณ์สำเร็จ: {info.get('manufacturer', '')} {info.get('product', '')} (SN: {info.get('serial', '')})")
    print("กด Ctrl+C เพื่อหยุดการสแกน\n")
    print(f"{'TIMESTAMP':<10} | {'RAW WORKMODE':<12} | {'STATUS KEY':<10} | {'DESCRIPTION'}")
    print("-" * 72)

    start_time = time.time()
    last_mode_byte = None

    try:
        while time.time() - start_time < duration_sec:
            reports, _ = read_all_feature_reports(
                h, report_ids=list(range(0x01, 0x80)), sizes=(64,), retries=1
            )
            
            # RID 0x07 Byte 1 (d[0]) contains exact WorkMode enum
            r7 = reports.get(0x07, b"")
            mode_byte = r7[1] if len(r7) > 1 else None
            
            ups_data = decode_feature_reports(reports)
            ups_data.update(infer_tentative_live_values(reports, ups_data))

            t_str = time.strftime("%H:%M:%S")
            key, desc = WORKMODE_MAP.get(mode_byte, ("UNKNOWN", f"❓ Unknown Mode ({mode_byte})"))

            # Highlight when mode changes
            changed_mark = " *** CHANGED ***" if (last_mode_byte is not None and last_mode_byte != mode_byte) else ""
            print(f"{t_str:<10} | 0x07[0]={mode_byte:<5} | {key:<10} | {desc}{changed_mark}")
            
            last_mode_byte = mode_byte
            time.sleep(interval_sec)
    except KeyboardInterrupt:
        print("\n🛑 สิ้นสุดการทำงานโดยผู้ใช้")
    finally:
        h.close()
        print("🔌 ปิด Connection อุปกรณ์ UPS เรียบร้อย")

if __name__ == "__main__":
    monitor_ups_status()
