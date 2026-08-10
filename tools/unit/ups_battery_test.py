#!/usr/bin/env python3
"""
tools/unit/ups_battery_test.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
สคริปต์สำหรับตรวจสอบสถานะ Battery Test, สั่งรัน/ยกเลิก Battery Test และดูประวัติ Discharge History
(อ้างอิงโปรโตคอลและโครงสร้างข้อมูลจาก Winpower G2)

Usage:
    # 1. ดูสถานะปัจจุบันและประวัติล่าสุด
    python tools/unit/ups_battery_test.py

    # 2. สั่ง Quick Battery Test (ทดสอบ 10 วินาที)
    python tools/unit/ups_battery_test.py --quick

    # 3. สั่ง Deep Battery Test (ทดสอบจนแบตเตอรี่ต่ำ)
    python tools/unit/ups_battery_test.py --deep

    # 4. สั่งยกเลิกการทดสอบ (Cancel Test)
    python tools/unit/ups_battery_test.py --cancel

    # 5. แสดงประวัติ Discharge History ทั้งหมด (รูปแบบ Winpower G2 API)
    python tools/unit/ups_battery_test.py --history
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Add project root and windows path to sys.path
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

from core_hid_ups import (
    decode_feature_reports,
    infer_tentative_live_values,
    list_ups_devices,
    open_ups_device,
    read_all_feature_reports,
)
try:
    from win32_hid_wrapper import parse_q1_string
except Exception:
    parse_q1_string = None
from tray_service.database import DatabaseManager


def get_ups_connection():
    """เปิดการเชื่อมต่อ UPS Device ผ่าน HID"""
    devices = list_ups_devices(target_vid=0x06DA)
    if not devices:
        print("❌ ไม่พบอุปกรณ์ PHOENIXTEC / HID UPS ที่เชื่อมต่ออยู่")
        return None, None

    target = devices[0]
    h, info = open_ups_device(
        vid=target.get("vendor_id", 0x06DA),
        pid=target.get("product_id", 0xFFFF),
        target_path=target.get("path_str"),
        target_serial=target.get("serial_number"),
    )
    return h, target


def show_battery_test_status() -> None:
    """แสดงสถานะการทำงานปัจจุบันของ UPS และประวัติการทดสอบแบตเตอรี่ล่าสุด"""
    print("=" * 76)
    print(" 🔋 UPS Battery Test Monitor & Live Telemetry")
    print("=" * 76)

    h, target = get_ups_connection()
    if not h:
        return

    try:
        report_ids = target.get("report_ids") or [0x01, 0x02, 0x03, 0x08, 0x24, 0x30, 0x31]
        raw_reports, _ = read_all_feature_reports(h, report_ids=report_ids, sizes=(64,), retries=2)
        data = decode_feature_reports(raw_reports, device_info=target)
        data.update(infer_tentative_live_values(raw_reports, data))

        ac_present = data.get("ac_present", True)
        status_str = data.get("ups.status", "OL" if ac_present else "OB")
        ups_mode = data.get("ups_mode", "Line Mode (Online)")
        test_status = data.get("battery_test_status", "idle")
        v_bat = data.get("battery_voltage_v", data.get("battery.voltage", "N/A"))
        c_bat = data.get("battery.charge", "N/A")
        load_pct = data.get("percent_load", data.get("ups.load", "N/A"))

        print(f"  • Operating Mode     : {ups_mode} [{status_str}]")
        print(f"  • Battery Test Status: {test_status.upper()}")
        print(f"  • Battery Voltage    : {v_bat} V")
        print(f"  • Battery Charge     : {c_bat} %")
        print(f"  • UPS Load Level     : {load_pct} %")

        print("\n" + "=" * 76)
        print(" 📜 Recent Discharge / Battery Test History (SQLite DB)")
        print("=" * 76)

        db = DatabaseManager()
        history = db.get_discharge_history(limit=5)
        records = history.get("data", [])

        if not records:
            print("  (ไม่พบประวัติการ Discharge / Battery Test ในระบบ)")
        else:
            for idx, r in enumerate(records, start=1):
                reason_str = "Power Outage (ไฟดับ)" if r.get("dischargeReason") == 1 else "Battery Test (ทดสอบแบต)"
                result_str = "Passed (ปกติ)" if r.get("testResult") == 1 else "Failed/Error (ข้อผิดพลาด)"
                print(f"  [{idx}] ID={r.get('id')} | Reason: {reason_str}")
                print(f"      Start Time  : {r.get('startTime')}")
                print(f"      End Time    : {r.get('endTime')}")
                print(f"      Duration    : {r.get('duration')} seconds")
                print(f"      Result      : {result_str}")
                print(f"      Voltage     : {r.get('startVolt')}V ➔ {r.get('endVolt')}V")
                print(f"      Charge      : {r.get('startLevel')}% ➔ {r.get('endLevel')}%")
                print(f"      Load        : {r.get('startLoad')}% ➔ {r.get('endLoad')}%")
                print("  " + "-" * 72)

    except Exception as exc:
        print(f"❌ เกิดข้อผิดพลาดในการอ่านข้อมูล: {exc}")
    finally:
        try:
            h.close()
        except Exception:
            pass


def send_battery_test_command(cmd_type: str) -> bool:
    """
    ส่งคำสั่ง Battery Test ไปยัง UPS
    cmd_type: 'quick' (10s), 'deep' (test till low), 'cancel' (abort)
    """
    h, target = get_ups_connection()
    if not h:
        return False

    cmd_map = {
        "quick": (0x01, "Quick Battery Test (10 วินาที)"),
        "deep": (0x02, "Deep Battery Test (ทดสอบจนแบตเตอรี่ต่ำ)"),
        "cancel": (0x00, "Cancel Battery Test (ยกเลิกการทดสอบ)"),
    }

    if cmd_type not in cmd_map:
        print(f"❌ คำสั่งไม่ถูกต้อง: {cmd_type}")
        return False

    code, desc = cmd_map[cmd_type]
    print(f"\n🚀 กำลังส่งคำสั่ง: {desc} (Report ID 0x24 payload: [0x{code:02X}])...")

    try:
        # Report ID 0x24 (Battery Self Test Control)
        report_payload = [0x24, code]
        h.send_feature_report(report_payload)
        print("✅ ส่งคำสั่งสำเร็จ!")
        time.sleep(1)

        # หลังส่งคำสั่ง: poll อ่านค่าจาก UPS เพื่อแสดงสถานะการทดสอบแบบเรียลไทม์
        report_ids = target.get("report_ids") or [0x01, 0x02, 0x03, 0x08, 0x24, 0x30, 0x31]

        # กำหนด timeout ตามประเภทคำสั่ง
        if cmd_type == "quick":
            timeout_s = 30
        elif cmd_type == "deep":
            timeout_s = 3600
        else:
            timeout_s = 30

        start_ts = time.time()
        prev_status = None
        print("🔎 กำลังรอผลจาก UPS และแสดงสถานะแบบเรียลไทม์ (กด Ctrl+C เพื่อยกเลิก)...")
        try:
            while True:
                elapsed = int(time.time() - start_ts)
                if elapsed > timeout_s:
                    print(f"⏱️  หมดเวลารอ ({timeout_s}s) — ยุติการรอผล")
                    break

                try:
                    raw_reports, meta = read_all_feature_reports(h, report_ids=report_ids, sizes=(64,), retries=1, include_zero=True)
                    data = decode_feature_reports(raw_reports, device_info=target)
                    data.update(infer_tentative_live_values(raw_reports, data))
                except Exception as exc_read:
                    print(f"⚠️  อ่านข้อมูลจาก UPS ล้มเหลว: {exc_read}")
                    time.sleep(1)
                    continue

                test_status = data.get("battery_test_status", "idle")
                v_bat = data.get("battery_voltage_v", data.get("battery.voltage", "N/A"))
                c_bat = data.get("battery.charge", "N/A")
                load_pct = data.get("percent_load", data.get("ups.load", "N/A"))

                print(f"  [{elapsed:3}s] Status={test_status} | Voltage={v_bat}V | Charge={c_bat}% | Load={load_pct}%")

                # ถ้ายังไม่ได้สถานะการทดสอบจริงๆ ให้แสดง raw/meta ของ Report 0x24 เพื่อดีบัก
                if (test_status is None or test_status.startswith("unknown") or test_status == "idle"):
                    rid = 0x24
                    if rid in raw_reports:
                        raw_hex = " ".join(f"{b:02X}" for b in raw_reports[rid])
                        print(f"    [DBG] Raw 0x24: {raw_hex}")
                    if 'meta' in locals() and isinstance(meta, dict) and rid in meta:
                        print(f"    [DBG] Meta 0x24: {meta[rid]}")
                    # Fallback for Megatec Q1-style devices: read input reports and parse Q1 string
                    if parse_q1_string and ("meg" in (str(target.get("product_string") or "")).lower() or "ppc" in (str(target.get("product_string") or "")).lower() or 0x01 not in report_ids):
                        try:
                            print("    [FALLBACK] พยายามอ่าน Input Reports เพื่อค้นหา Q1 string (Megatec)")
                            for _i in range(6):
                                data_in = h.read(64, 500)
                                if not data_in:
                                    continue
                                arr = list(data_in)
                                # extract printable ASCII
                                s = ''.join(chr(b) for b in arr if 32 <= b < 127)
                                if not s:
                                    continue
                                parsed = parse_q1_string(s)
                                if parsed:
                                    print(f"    [Q1] raw='{s.strip()}' parsed.test_in_progress={parsed.get('test_in_progress')}")
                                    if parsed.get('test_in_progress'):
                                        prev_status = 'running'
                                    else:
                                        print("✅ Q1 reports indicate test finished")
                                        break
                        except Exception as exc_q1:
                            print(f"    [FALLBACK] อ่าน Q1 string ล้มเหลว: {exc_q1}")

                # ตรวจจับว่าการทดสอบสิ้นสุดลง (สถานะเปลี่ยนจาก running -> idle/finished/completed)
                if prev_status is None:
                    prev_status = test_status
                else:
                    if prev_status != test_status and test_status in ("idle", "finished", "completed", "done", "none", "passed"):
                        print("✅ UPS รายงานว่า Self-test สิ้นสุดแล้ว")
                        break
                    prev_status = test_status

                # สำหรับ Quick test ให้หยุดเมื่อผ่านเวลาทดสอบโดยประมาณ (10s)
                if cmd_type == "quick" and elapsed >= 12:
                    print("⚡ Quick test: เวลาทดสอบครบเวลาโดยประมาณ — หยุดรอผลเพิ่มเติม")
                    break

                time.sleep(1)
        except KeyboardInterrupt:
            print("✋ ยกเลิกการรอผลโดยผู้ใช้ (KeyboardInterrupt)")

        # บันทึก event ลง SQLite DB
        db = DatabaseManager()
        db.log_event(
            event_type=f"BATTERY_TEST_{cmd_type.upper()}",
            message=f"Triggered {desc} via CLI tool",
        )
        return True

    except Exception as exc:
        print(f"❌ ไม่สามารถส่งคำสั่งได้: {exc}")
        return False
    finally:
        try:
            h.close()
        except Exception:
            pass


def show_full_history_json() -> None:
    """แสดงประวัติ Discharge History ทั้งหมดในรูปแบบ Winpower G2 JSON API Response"""
    db = DatabaseManager()
    res = db.get_discharge_history(limit=100)
    print(json.dumps(res, indent=4, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="PHOENIXTEC UPS Battery Test Tool (Winpower G2 Compatible)"
    )
    parser.add_argument(
        "--quick", action="store_true", help="สั่ง Quick Battery Test (10 วินาที)"
    )
    parser.add_argument(
        "--deep", action="store_true", help="สั่ง Deep Battery Test (ทดสอบจนแบตต่ำ)"
    )
    parser.add_argument(
        "--cancel", action="store_true", help="ยกเลิกการทดสอบ Battery Test"
    )
    parser.add_argument(
        "--history", action="store_true", help="แสดงประวัติ Discharge History (JSON)"
    )

    args = parser.parse_args()

    if args.quick:
        send_battery_test_command("quick")
    elif args.deep:
        send_battery_test_command("deep")
    elif args.cancel:
        send_battery_test_command("cancel")
    elif args.history:
        show_full_history_json()
    else:
        show_battery_test_status()


if __name__ == "__main__":
    main()
