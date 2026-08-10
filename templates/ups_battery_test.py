#!/usr/bin/env python3
"""
tools/ups_battery_test.py
~~~~~~~~~~~~~~~~~~~~~~~~~
Universal PHOENIXTEC & HID UPS Battery Test Live Runner & Monitor CLI Tool.
รองรับอุปกรณ์ HID UPS ทุกยี่ห้อ (PHOENIXTEC, Innova Unity, Innova Basic G2, MEC, PPC, APC, CyberPower, Eaton, Tripp Lite, Powercom)

Usage:
    # 1. แสดงรายการอุปกรณ์ HID UPS ทั้งหมดที่พบในระบบ
    python tools/ups_battery_test.py --list

    # 2. รัน Quick Battery Test (10 วินาที) แบบ Hold Process อ่านค่าสดๆ ทุก 1 วินาที
    python tools/ups_battery_test.py --quick

    # 3. รัน Quick Battery Test เจาะจงอุปกรณ์ลำดับที่ 2
    python tools/ups_battery_test.py --device 2 --quick

    # 4. รัน Deep Battery Test (ทดสอบจนแบตเตอรี่ต่ำ) แบบ Hold Process
    python tools/ups_battery_test.py --deep

    # 5. ยกเลิกการทดสอบ Battery Test (Cancel Test)
    python tools/ups_battery_test.py --cancel

    # 6. แสดงประวัติ Discharge History ทั้งหมด (รูปแบบ Winpower G2 JSON API Response)
    python tools/ups_battery_test.py --history
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add unit tools path to sys.path
UNIT_DIR = Path(__file__).resolve().parent / "unit"
if str(UNIT_DIR) not in sys.path:
    sys.path.insert(0, str(UNIT_DIR))

from live_battery_test_runner import print_device_list, run_live_battery_test
from ups_battery_test import send_battery_test_command, show_battery_test_status, show_full_history_json


import ctypes
import os

def ensure_admin() -> None:
    """
    ตรวจสอบว่ากระบวนการได้รับสิทธิ์ Administrator หรือไม่
    หากยังไม่ได้สิทธิ์ จะขอ UAC Elevation (RunAs) ผ่าน Windows ShellExecute ทันที
    """
    try:
        is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        is_admin = False

    if not is_admin:
        print("🔒 [UAC] คำสั่งนี้ต้องใช้สิทธิ์ Administrator ในการยิงสัญญาณสั่งงานฮาร์ดแวร์...")
        print("👉 กำลังขอสิทธิ์ UAC (โปรดกด 'Yes' ในหน้าต่างที่เด้งขึ้นมา)...")
        script = os.path.abspath(sys.argv[0])
        args = " ".join([f'"{a}"' for a in sys.argv[1:]])
        ret = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, f'"{script}" {args}', None, 1
        )
        if ret > 32:
            sys.exit(0)


def main() -> None:
    ensure_admin()
    parser = argparse.ArgumentParser(
        description="Universal PHOENIXTEC & HID UPS Battery Test Live Runner (All Brands)"
    )
    parser.add_argument(
        "--list", action="store_true", help="แสดงรายการอุปกรณ์ HID UPS ทั้งหมดที่เชื่อมต่อกับคอมพิวเตอร์"
    )
    parser.add_argument(
        "--quick", action="store_true", help="สั่ง Quick Battery Test (10 วินาที) พร้อม Hold Process อ่านค่าสดๆ"
    )
    parser.add_argument(
        "--deep", action="store_true", help="สั่ง Deep Battery Test (ทดสอบจนแบตต่ำ) พร้อม Hold Process"
    )
    parser.add_argument(
        "--cancel", action="store_true", help="ส่งคำสั่งยกเลิกการทดสอบ Battery Test"
    )
    parser.add_argument(
        "--device", type=int, help="ลำดับของอุปกรณ์ที่ต้องการทดสอบ (เช่น --device 1, --device 2)"
    )
    parser.add_argument(
        "--serial", type=str, help="Serial Number ของอุปกรณ์ที่ต้องการทดสอบ"
    )
    parser.add_argument(
        "--status", action="store_true", help="แสดงสถานะแบตเตอรี่และประวัติการทดสอบย้อนหลัง"
    )
    parser.add_argument(
        "--history", action="store_true", help="แสดงประวัติ Discharge History ในรูปแบบ Winpower G2 JSON Response"
    )

    args = parser.parse_args()

    if args.list:
        print_device_list()
    elif args.quick:
        run_live_battery_test("quick", max_timeout_s=60, device_index=args.device, target_serial=args.serial)
    elif args.deep:
        run_live_battery_test("deep", max_timeout_s=3600, device_index=args.device, target_serial=args.serial)
    elif args.cancel:
        send_battery_test_command("cancel")
    elif args.history:
        show_full_history_json()
    elif args.status:
        show_battery_test_status()
    else:
        # Default behavior: run live quick test runner
        print("💡 ไม่ระบุ flag: เริ่มรัน Quick Battery Test (10s) แบบ Hold Process (ใช้ --help เพื่อดูตัวเลือกอื่นๆ)\n")
        run_live_battery_test("quick", max_timeout_s=60, device_index=args.device, target_serial=args.serial)


if __name__ == "__main__":
    main()
