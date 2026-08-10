#!/usr/bin/env python3
"""
tools/monitor_ups.py
~~~~~~~~~~~~~~~~~~~~
Real-time UPS Telemetry Monitor Script.
Applies reverse engineering findings (UPSmart / WinPower G2 protocols)
to continuously monitor connected UPS devices (MEC0003 & Phoenixtec Innova Unity)
and display clean real-time status.

Usage:
    python tools/monitor_ups.py
    python tools/monitor_ups.py --vid 0x0001 --pid 0x0000
    python tools/monitor_ups.py --vid 0x06DA --pid 0xFFFF
    python tools/monitor_ups.py --interval 1.0 --count 60
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
import time
from pathlib import Path

# Add root directory to sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(ROOT_DIR / "windows"))

# Force UTF-8 encoding on Windows console
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

try:
    from windows.core_hid_ups import (
        decode_feature_reports,
        infer_tentative_live_values,
        list_ups_devices,
        open_ups_device,
        read_all_feature_reports,
    )
    HID_AVAILABLE = True
except ImportError:
    try:
        from core_hid_ups import (
            decode_feature_reports,
            infer_tentative_live_values,
            list_ups_devices,
            open_ups_device,
            read_all_feature_reports,
        )
        HID_AVAILABLE = True
    except ImportError as exc:
        print(f"Error importing core_hid_ups: {exc}")
        HID_AVAILABLE = False


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Real-time UPS Telemetry Monitor (MEC0003 & Phoenixtec Innova)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--vid",
        type=lambda x: int(x, 0),
        default=None,
        help="Vendor ID in hex (e.g. 0x0001 for MEC0003, 0x06DA for Innova Unity)",
    )
    p.add_argument(
        "--pid",
        type=lambda x: int(x, 0),
        default=None,
        help="Product ID in hex (e.g. 0x0000 or 0xFFFF)",
    )
    p.add_argument(
        "--interval",
        type=float,
        default=1.0,
        help="Polling interval in seconds (default: 1.0s)",
    )
    p.add_argument(
        "--count",
        type=int,
        default=0,
        help="Number of polling cycles (default: 0 = continuous until Ctrl+C)",
    )
    p.add_argument(
        "--json",
        action="store_true",
        help="Print raw decoded dict as JSON per iteration",
    )
    return p


def render_dashboard(dev_info: dict, state: dict, cycle: int) -> None:
    """Clear terminal screen and render clean real-time status dashboard."""
    mfr = str(dev_info.get("manufacturer_string") or "Unknown")
    prod = str(dev_info.get("product_string") or "Unknown")
    vid_hex = dev_info.get("vendor_id_hex") or f"0x{dev_info.get('vendor_id', 0):04X}"
    pid_hex = dev_info.get("product_id_hex") or f"0x{dev_info.get('product_id', 0):04X}"
    path_str = dev_info.get("path_str") or str(dev_info.get("path") or "N/A")

    ac_on = bool(state.get("ac_present", False))
    status_str = str(state.get("ups.status") or "UNKNOWN")
    mode_str = str(state.get("ups_mode") or "Unknown")
    charge = state.get("battery.charge", state.get("battery_capacity_percent"))
    runtime_s = state.get("battery.runtime", state.get("runtime_remaining_sec"))
    runtime_hr = state.get("battery.runtime.hr")
    v_in = state.get("input.voltage")
    f_in = state.get("input.frequency")
    v_out = state.get("output.voltage", state.get("output_voltage_v"))
    f_out = state.get("output.frequency", state.get("output_frequency_hz"))
    load = state.get("percent_load", state.get("ups.load"))
    v_batt = state.get("battery_voltage_v")
    temp_c = state.get("temperature_c", state.get("ups.temperature"))

    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Clear terminal screen (ANSI escape code)
    print("\033[H\033[J", end="")

    print("=" * 80)
    print(f" ⚡ UPS REAL-TIME TELEMETRY MONITOR  [{now_str}]  (Cycle #{cycle})")
    print("=" * 80)
    print(f" อุปกรณ์ : {mfr} {prod}  (VID={vid_hex} PID={pid_hex})")
    print(f" Device Path: {path_str}")
    print("-" * 80)

    # Status Banner
    if ac_on:
        ac_badge = "🟢 AC LINE NORMAL (เสียบปลั๊ก)"
    else:
        ac_badge = "🔴 AC POWER LOSS / ON BATTERY (ไฟดับ!)"

    print(f" สถานะ AC Wall Power : {ac_badge}")
    print(f" สถานะระบบ (NUT)    : {status_str}")
    print(f" โหมดการทำงาน        : {mode_str}")
    print("-" * 80)

    # Telemetry Table
    print(f" {'รายการวัด':<28} {'ค่าปัจจุบัน':<20} {'หน่วย':<10}")
    print(" " + "-" * 60)

    print(f" {'ระดับแบตเตอรี่ (Charge)':<28} {charge if charge is not None else 'N/A':<20} {'%'}")
    if runtime_s is not None:
        print(f" {'ระยะเวลาใช้งาน (Runtime)':<28} {runtime_s:<20} {'วินาที'}")
    if runtime_hr is not None:
        print(f" {'ระยะเวลาใช้งาน (Runtime)':<28} {runtime_hr:<20} {'ชั่วโมง'}")
    if v_batt is not None:
        print(f" {'แรงดันแบตเตอรี่ (Battery V)':<28} {v_batt:<20} {'V'}")
    if temp_c is not None:
        print(f" {'อุณหภูมิ (Temperature)':<28} {temp_c:<20} {'°C'}")
    if v_in is not None:
        print(f" {'แรงดันไฟฟ้าขาเข้า (Input V)':<28} {v_in:<20} {'V'}")
    if f_in is not None:
        print(f" {'ความถี่ขาเข้า (Input Freq)':<28} {f_in:<20} {'Hz'}")
    if v_out is not None:
        print(f" {'แรงดันไฟฟ้าขาออก (Output V)':<28} {v_out:<20} {'V'}")
    if f_out is not None:
        print(f" {'ความถี่ขาออก (Output Freq)':<28} {f_out:<20} {'Hz'}")
    if load is not None:
        print(f" {'ภาระโหลด (Percent Load)':<28} {load:<20} {'%'}")

    # Report Stats
    rep_count = state.get("scan.report_count", 0)
    rep_ids = ", ".join(state.get("scan.report_ids", []))
    print("-" * 80)
    print(f" HID Reports Captured: {rep_count} report(s) [{rep_ids}]")
    print("=" * 80)
    print(" [กด Ctrl+C เพื่อหยุดทำงาน]")


def main() -> int:
    args = build_arg_parser().parse_args()

    if not HID_AVAILABLE:
        print("Error: core_hid_ups module not available.")
        return 1

    devices = list_ups_devices(target_vid=args.vid, pid=args.pid)
    if not devices:
        print("\n❌ ไม่พบอุปกรณ์ UPS ที่เชื่อมต่ออยู่")
        print("   กรุณาเสียบสาย USB ของ UPS (MEC0003 หรือ Phoenixtec Innova)")
        return 1

    # Select target device (or default to first detected UPS)
    target_dev = devices[0]
    vid = target_dev.get("vendor_id") or 0x0001
    pid = target_dev.get("product_id") or 0x0000

    print(f"\nกำลังเปิดอุปกรณ์ UPS: {target_dev.get('manufacturer_string')} {target_dev.get('product_string')} (VID=0x{vid:04X} PID=0x{pid:04X})...")
    h, info = open_ups_device(vid=vid, pid=pid, target_path=target_dev.get("path_str"))
    if not h:
        print("❌ ไม่สามารถเปิด HID handle ได้")
        return 1

    # Determine report IDs to scan based on device VID
    if vid == 0x0001:
        report_ids = [0x01, 0x02, 0x03, 0x04, 0x05]
    else:
        report_ids = [0x01, 0x02, 0x03, 0x05, 0x06, 0x07, 0x08, 0x0C, 0x0D, 0x10, 0x14, 0x17, 0x24, 0x25, 0x26, 0x27, 0x29, 0x31, 0x42, 0x4A, 0x74]

    cycle = 0
    try:
        while True:
            cycle += 1
            raw, meta = read_all_feature_reports(
                h,
                report_ids=report_ids,
                sizes=(64,),
                retries=1,
                include_zero=True,
            )
            state = decode_feature_reports(raw, info)
            state.update(infer_tentative_live_values(raw, state))

            if args.json:
                print(json.dumps(state, indent=2, ensure_ascii=False))
            else:
                render_dashboard(info, state, cycle)

            if args.count > 0 and cycle >= args.count:
                break

            time.sleep(max(0.2, args.interval))

    except KeyboardInterrupt:
        print("\n\n👋 หยุดการทำงาน real-time monitor เรียบร้อย")
    finally:
        try:
            h.close()
        except Exception:
            pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
