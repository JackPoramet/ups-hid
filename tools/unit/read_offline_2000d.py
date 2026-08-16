#!/usr/bin/env python3
"""
tools/read_offline_2000d.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
PPC Offline UPS (2000D) USB HID Live Reader.
Uses core_hid_ups engine to read dynamic feature reports and telemetry.

Usage:
    python tools/read_offline_2000d.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

# Add project root and windows package to sys.path
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


def read_offline_2000d() -> None:
    print("=" * 76)
    print(" 🔌 PPC Offline UPS (2000D) — USB HID Live Reader")
    print(" Profile: ppc_offline_2000d")
    print("=" * 76)

    # Find connected Offline UPS (2000D)
    devices = list_ups_devices(target_vid=0x06DA)
    target = None
    for dev in devices:
        p_str = (dev.get("product_string") or "").lower()
        m_str = (dev.get("manufacturer_string") or "").lower()
        if "offline" in p_str or "2000" in p_str or "ppc" in m_str or dev.get("profile_id") == "ppc_offline_2000d":
            target = dev
            break

    if not target:
        print("\n❌ ไม่พบอุปกรณ์ PPC Offline UPS 2000D (VID=0x06DA, PID=0xFFFF)")
        print("   กรุณาตรวจสอบว่าได้เสียบสาย USB และไม่ได้เปิดโปรแกรมอื่นค้างไว้")
        return

    print(f"\n✅ พบอุปกรณ์: {target.get('manufacturer_string')} {target.get('product_string')}")
    print(f"   Serial Number: {target.get('serial_number') or 'N/A'}")
    print(f"   Device Path  : {target.get('path_str')}\n")

    h, info = open_ups_device(vid=0x06DA, pid=0xFFFF, target_path=target.get("path_str"), target_serial=target.get("serial_number"))
    if not h:
        print("❌ ไม่สามารถเปิดการเชื่อมต่อกับอุปกรณ์ได้")
        return

    try:
        report_ids = target.get("report_ids") or [0x01, 0x06, 0x07, 0x09, 0x0A, 0x0B, 0x10, 0x13, 0x24, 0x2D, 0x31, 0x36, 0x42, 0x4A, 0x72, 0x74, 0xE2]
        raw_reports, _ = read_all_feature_reports(h, report_ids=report_ids, sizes=(64,), retries=2)

        data = decode_feature_reports(raw_reports, device_info=info)
        # Tentative values (fallback) removed to show pure raw data

        ac_present = data.get("ac_present", True)
        status_str = data.get("ups.status", "OL" if ac_present else "OB")
        ups_mode = data.get("ups_mode", "Line Mode (Online)")
        boost = data.get("boost", False)
        buck = data.get("buck", False)

        avr_status = "Boost Active (เร่งแรงดัน)" if boost else ("Buck Active (ลดแรงดัน)" if buck else "Normal (ตรง)")

        print("=" * 76)
        print(" 📊 Real-Time Telemetry (Offline UPS 2000D)")
        print("=" * 76)
        print(f"  • Operating Mode     : {ups_mode} [{status_str}]")
        print(f"  • AVR Status         : {avr_status}")
        print(f"  • Input Voltage      : {data.get('input.voltage', 'N/A')} V")
        print(f"  • Input Frequency    : {data.get('input.frequency', 'N/A')} Hz")
        print(f"  • Output Voltage     : {data.get('output.voltage', 'N/A')} V")
        print(f"  • Output Frequency   : {data.get('output_frequency_hz', data.get('output.frequency', 'N/A'))} Hz")
        print(f"  • Load Level         : {data.get('percent_load', data.get('ups.load', 'N/A'))} %")
        print(f"  • Battery Charge     : {data.get('battery.charge', 'N/A')} %")
        print(f"  • Battery Voltage    : {data.get('battery_voltage_v', data.get('battery.voltage', 'N/A'))} V")

        rt_sec = data.get("battery.runtime")
        if rt_sec is not None:
            m = int(rt_sec // 60)
            s = int(rt_sec % 60)
            print(f"  • Estimated Runtime  : {m} min {s} sec ({data.get('battery.runtime.hr', 'N/A')} hr)")

        print(f"  • Discharging        : {'Yes (จ่ายไฟแบต)' if data.get('discharging') else 'No'}")
        print(f"  • Overload Status    : {'Overload!' if data.get('overload') else 'Normal'}")
        print("=" * 76)

    finally:
        h.close()


if __name__ == "__main__":
    read_offline_2000d()
