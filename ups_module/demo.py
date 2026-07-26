#!/usr/bin/env python3
"""
ups_module/demo.py
~~~~~~~~~~~~~~~~~~
สคริปต์ตัวอย่างสำหรับทดสอบ ups_module (Cross-Platform)

การรัน::
    python3 demo.py
    python3 demo.py --check
    python3 demo.py --mode oneshot
    python3 demo.py --mode poll
    python3 demo.py --mode monitor
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import time

# -- ups_module imports --
try:
    from ups_module import UPSClient, NotifyType, UPSData
except (ImportError, ValueError):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    try:
        from ups_module import UPSClient, NotifyType, UPSData
    except ImportError:
        from client import UPSClient
        from models import NotifyType, UPSData


def _check_system() -> bool:
    """ตรวจสอบความพร้อมของระบบแบบย่อ"""
    print("\n--- ตรวจสอบระบบ (System Check) ---")
    system = platform.system()
    print(f"  OS        : {system} {platform.machine()}")

    ok = True
    try:
        import hid
        devices = hid.enumerate(0x06DA, 0xFFFF)
        if devices:
            d = devices[0]
            mfr = d.get('manufacturer_string') or '?'
            prod = d.get('product_string') or '?'
            print(f"  hidapi    : OK ({mfr} / {prod})")
        else:
            print("  hidapi    : OK (ไม่พบ UPS - เช็คสาย USB)")
            ok = False
    except ImportError:
        print("  hidapi    : NG (ลอง: pip install hidapi)")
        ok = False

    if system == "Linux":
        from pathlib import Path
        has_rule = Path("/etc/udev/rules.d/99-ups-hid.rules").exists()
        print(f"  udev rule : {'OK' if has_rule else 'NG (ลอง: ./install.sh)'}")

    return ok


def demo_oneshot(output_json: bool = False) -> None:
    """อ่านค่าครั้งเดียวแบบ upsc"""
    print("\n--- One-shot Read (upsc) ---")
    try:
        with UPSClient() as client:
            if output_json:
                data = client.get_data()
                print(json.dumps(data.to_nut_dict(), ensure_ascii=False, indent=2))
            else:
                info = client.get_device_info()
                print(f"  UPS: {info.get('manufacturer')} {info.get('model')} (SN: {info.get('serial')})")
                print("-" * 40)
                vars_dict = client.get_vars()
                for k in sorted(vars_dict.keys()):
                    print(f"  {k:<24}: {vars_dict[k]}")
    except RuntimeError as e:
        print(f"  Error: {e}")


def demo_single_var(varname: str) -> None:
    """อ่านค่าตัวแปรเดียว"""
    print(f"\n--- Single Variable ({varname}) ---")
    try:
        with UPSClient() as client:
            val = client.get_var(varname)
            print(f"  {varname}: {val}")
    except RuntimeError as e:
        print(f"  Error: {e}")


def demo_poll(interval: float = 2.0, count: int = 0) -> None:
    """Poll ค่าอย่างต่อเนื่อง"""
    print(f"\n--- Continuous Poll ({interval}s) | กด Ctrl+C เพื่อหยุด ---")
    client = UPSClient()
    try:
        client.connect()
        iteration = 0
        while True:
            iteration += 1
            if 0 < count <= iteration:
                break
            data = client.get_data()
            ts = time.strftime("%H:%M:%S")
            print(
                f"  [{ts}] "
                f"Status: {data.ups_status or '?':<6} | "
                f"Batt: {data.battery_charge}% | "
                f"In: {data.input_voltage}V | "
                f"Out: {data.output_voltage}V | "
                f"Load: {data.ups_load}%"
            )
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\n  [หยุดการ poll]")
    except RuntimeError as e:
        print(f"  Error: {e}")
    finally:
        client.disconnect()


def demo_monitor(interval: float = 1.0) -> None:
    """Monitor events"""
    print(f"\n--- Event Monitor ({interval}s) | กด Ctrl+C เพื่อหยุด ---")
    client = UPSClient()
    try:
        client.connect()

        @client.on(NotifyType.ONLINE)
        def on_online(event):
            print(f"\n  [EVENT] {event.timestamp} ONLINE  : {event.message}")

        @client.on(NotifyType.ONBATT)
        def on_battery(event):
            print(f"\n  [EVENT] {event.timestamp} ONBATT  : {event.message}")

        @client.on(NotifyType.LOWBATT)
        def on_lowbatt(event):
            print(f"\n  [EVENT] {event.timestamp} LOWBATT : {event.message}")

        client.start_monitor(interval=interval)
        print("  กำลังติดตามสถานะ...")
        while True:
            data = client.get_data()
            ts = time.strftime("%H:%M:%S")
            print(f"  [{ts}] Status: {data.ups_status or '?'} | Batt: {data.battery_charge}%", end="\r")
            time.sleep(interval)

    except KeyboardInterrupt:
        print("\n  [หยุดการ monitor]")
    except RuntimeError as e:
        print(f"  Error: {e}")
    finally:
        client.stop_monitor()
        client.disconnect()


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    parser = argparse.ArgumentParser(description="ups_module demo")
    parser.add_argument("--check", action="store_true", help="เช็คระบบเท่านั้น")
    parser.add_argument("--mode", choices=["oneshot", "var", "poll", "monitor", "all"], default="oneshot")
    parser.add_argument("--var", default="battery.charge", help="ตัวแปรสำหรับโหมด var")
    parser.add_argument("--interval", type=float, default=2.0, help=" polling interval (sec)")
    parser.add_argument("--json", action="store_true", help="output JSON format")
    parser.add_argument("--count", type=int, default=0, help="รอบ poll (0 = ไม่จำกัด)")
    args = parser.parse_args()

    try:
        if args.check:
            return 0 if _check_system() else 1

        if args.mode == "oneshot":
            demo_oneshot(output_json=args.json)
        elif args.mode == "var":
            demo_single_var(args.var)
        elif args.mode == "poll":
            demo_poll(interval=args.interval, count=args.count)
        elif args.mode == "monitor":
            demo_monitor(interval=args.interval)
        elif args.mode == "all":
            demo_oneshot(output_json=args.json)
            demo_single_var(args.var)
            demo_poll(interval=args.interval, count=args.count or 3)
    except KeyboardInterrupt:
        print("\n[Exit]")

    return 0


if __name__ == "__main__":
    sys.exit(main())
