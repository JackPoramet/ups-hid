#!/usr/bin/env python3
"""
tools/read_innova_unity.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~
PHOENIXTEC Innova Unity (Online 1K-3K) USB HID UPS Live Reader.
Uses core_hid_ups engine to read dynamic feature reports and telemetry.

Usage:
    python tools/read_innova_unity.py
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


def read_innova_unity() -> None:
    print("=" * 76)
    print(" 🔌 PHOENIXTEC Innova Unity — USB HID UPS Live Reader")
    print(" Profile: phoenixtec_innova_unity (Online 1K-3K)")
    print("=" * 76)

    # Find connected Innova Unity
    devices = list_ups_devices(target_vid=0x06DA)
    target = None
    for dev in devices:
        p_str = (dev.get("product_string") or "").lower()
        s_num = (dev.get("serial_number") or "").lower()
        if "unity" in p_str or "cp10" in s_num or dev.get("profile_id") == "phoenixtec_innova_unity":
            target = dev
            break

    if not target:
        print("\n❌ ไม่พบอุปกรณ์ PHOENIXTEC Innova Unity (VID=0x06DA, PID=0xFFFF)")
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
        report_ids = target.get("report_ids") or list(range(0x01, 0x80))
        raw_reports, _ = read_all_feature_reports(h, report_ids=report_ids, sizes=(64,), retries=2)

        data = decode_feature_reports(raw_reports, device_info=info)
        # Tentative values (fallback) removed to show pure raw data

        ac_present = data.get("ac_present", True)
        status_str = data.get("ups.status", "OL" if ac_present else "OB")
        ups_mode = data.get("ups_mode", "Line Mode (Online)")

        print("=" * 76)
        print(" 📊 Real-Time Telemetry (Innova Unity)")
        print("=" * 76)
        print(f"  • Operating Mode     : {ups_mode} [{status_str}]")
        print(f"  • Input Voltage      : {data.get('input.voltage', 'N/A')} V")
        print(f"  • Input Frequency    : {data.get('input.frequency', 'N/A')} Hz")
        print(f"  • Output Voltage     : {data.get('output.voltage', 'N/A')} V")
        print(f"  • Output Frequency   : {data.get('output_frequency_hz', data.get('output.frequency', 'N/A'))} Hz")
        print(f"  • Output Current     : {data.get('output_current_a', 'N/A')} A")
        print(f"  • Active Power       : {data.get('output_active_power_w', 'N/A')} W")
        print(f"  • Apparent Power     : {data.get('output_apparent_power_va', 'N/A')} VA")
        print(f"  • Load Level         : {data.get('percent_load', data.get('ups.load', 'N/A'))} %")
        print(f"  • Battery Charge     : {data.get('battery.charge', 'N/A')} %")
        print(f"  • Battery Voltage    : {data.get('battery_voltage_v', data.get('battery.voltage', 'N/A'))} V")

        rt_sec = data.get("battery.runtime")
        if rt_sec is not None:
            m = int(rt_sec // 60)
            s = int(rt_sec % 60)
            print(f"  • Estimated Runtime  : {m} min {s} sec ({data.get('battery.runtime.hr', 'N/A')} hr)")

        temp = data.get("temperature_c", data.get("ups.temperature"))
        if temp is not None:
            print(f"  • Temperature        : {temp} °C")

        print("=" * 76)

    finally:
        h.close()


if __name__ == "__main__":
    read_innova_unity()
