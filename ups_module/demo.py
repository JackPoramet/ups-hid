#!/usr/bin/env python3
"""
ups_module/demo.py
~~~~~~~~~~~~~~~~~~
สคริปต์ตัวอย่างสำหรับทดสอบ ups_module (Cross-Platform: Linux/Windows/ARM)

รูปแบบการใช้งาน 4 แบบ ตามมาตรฐาน NUT (Network UPS Tools):

  1. One-shot read     -- เทียบ `upsc ups@local`
  2. Single variable   -- เทียบ `upsc ups@local battery.charge`
  3. Continuous poll    -- เทียบ `upsmon` polling loop
  4. Event monitoring  -- เทียบ `upsmon NOTIFYCMD`

การรัน::

    python -m ups_module.demo                   # รัน demo ทั้งหมด
    python -m ups_module.demo --check            # เช็คระบบก่อนรัน
    python -m ups_module.demo --mode oneshot      # รันเฉพาะ one-shot
    python -m ups_module.demo --mode monitor      # รัน event monitor
    python -m ups_module.demo --json              # output เป็น JSON
"""

from __future__ import annotations

import argparse
import json
import logging
import platform
import signal
import sys
import time
from typing import Optional

# -- ups_module imports --
try:
    from ups_module import UPSClient, NotifyType, UPSData
except ImportError:
    from . import UPSClient, NotifyType, UPSData


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _separator(title: str = "", char: str = "-", width: int = 60) -> None:
    if title:
        print(f"\n{char * width}")
        print(f"  {title}")
        print(f"{char * width}")
    else:
        print(char * width)


def _check_system() -> bool:
    """ตรวจสอบระบบก่อนใช้งาน -- เทียบ `upsdrvctl -t`"""
    _separator("ตรวจสอบระบบ (System Check)", "=")

    ok = True

    # 1. ตรวจ OS
    system = platform.system()
    machine = platform.machine()
    print(f"  OS        : {system} {machine}")

    # 2. ตรวจ hidapi
    try:
        import hid
        devices = hid.enumerate(0x06DA, 0xFFFF)
        if devices:
            d = devices[0]
            print(f"  hidapi    : [OK] พบ UPS device")
            print(f"              {d.get('manufacturer_string', '?')} / {d.get('product_string', '?')}")
        else:
            print(f"  hidapi    : [OK] import ได้ แต่ไม่พบ UPS device")
            print(f"              - ตรวจสอบว่าต่อสาย USB แล้ว")
            if system == "Linux":
                print(f"              - ลอง: lsusb | grep 06da")
            ok = False
    except ImportError:
        print(f"  hidapi    : [NG] ไม่พบ -- ลอง: pip install hidapi")
        ok = False
    except Exception as e:
        print(f"  hidapi    : [NG] {e}")
        ok = False

    # 3. ตรวจ pyusb (optional)
    try:
        import usb.core
        print(f"  pyusb     : [OK]")
    except ImportError:
        print(f"  pyusb     : [--] ไม่ได้ติดตั้ง (optional, ใช้อ่าน input voltage)")

    # 4. ตรวจ udev rule (Linux only)
    if system == "Linux":
        from pathlib import Path
        udev_path = Path("/etc/udev/rules.d/99-ups-hid.rules")
        if udev_path.exists():
            print(f"  udev rule : [OK] {udev_path}")
        else:
            print(f"  udev rule : [--] ไม่พบ (อาจต้องรันด้วย sudo)")
            print(f"              sudo python -m ups_module.linux_setup")

    # 5. ตรวจ ups_module
    try:
        from ups_module import __version__
        print(f"  ups_module: [OK] v{__version__}")
    except Exception:
        print(f"  ups_module: [OK]")

    print()
    if ok:
        print("  --> ระบบพร้อมใช้งาน")
    else:
        print("  --> มีรายการที่ต้องแก้ไข")

    return ok


# ---------------------------------------------------------------------------
# Mode 1: One-shot Read  (เทียบ `upsc ups@local`)
# ---------------------------------------------------------------------------

def demo_oneshot(output_json: bool = False) -> None:
    """อ่านค่า UPS ครั้งเดียว แล้วจบ -- เหมือน `upsc ups@local`"""
    _separator("Mode 1: One-shot Read (upsc)", "=")

    try:
        with UPSClient() as client:
            if output_json:
                data = client.get_data()
                print(json.dumps(data.to_nut_dict(), ensure_ascii=False, indent=2))
            else:
                info = client.get_device_info()
                vars_dict = client.get_vars()

                print(f"  device.manufacturer : {info.get('manufacturer', '?')}")
                print(f"  device.model        : {info.get('model', '?')}")
                print(f"  device.serial       : {info.get('serial', '?')}")
                print()
                for key in sorted(vars_dict.keys()):
                    val = vars_dict[key]
                    print(f"  {key}: {val}")

    except RuntimeError as e:
        print(f"  [Error] {e}")
        _print_troubleshoot()


# ---------------------------------------------------------------------------
# Mode 2: Single Variable  (เทียบ `upsc ups@local battery.charge`)
# ---------------------------------------------------------------------------

def demo_single_var(varname: str) -> None:
    """อ่านค่า UPS ตัวแปรเดียว -- เหมือน `upsc ups@local <varname>`"""
    _separator(f"Mode 2: Single Variable ({varname})", "=")

    try:
        with UPSClient() as client:
            val = client.get_var(varname)
            if val is not None:
                print(f"  {varname}: {val}")
            else:
                print(f"  [!] ไม่พบตัวแปร '{varname}'")
                print(f"      ตัวแปรที่มี:")
                for k in sorted(client.get_vars().keys()):
                    print(f"        {k}")

    except RuntimeError as e:
        print(f"  [Error] {e}")
        _print_troubleshoot()


# ---------------------------------------------------------------------------
# Mode 3: Continuous Poll  (เทียบ `upsmon` polling loop)
# ---------------------------------------------------------------------------

def demo_poll(interval: float = 2.0, count: int = 0) -> None:
    """Poll UPS ต่อเนื่อง -- เหมือน `upsmon` ทำงานเบื้องหลัง"""
    _separator("Mode 3: Continuous Poll (upsmon-style)", "=")
    print(f"  Interval: {interval}s | กด Ctrl+C เพื่อหยุด")
    print()

    client = UPSClient()
    try:
        client.connect()
    except RuntimeError as e:
        print(f"  [Error] {e}")
        _print_troubleshoot()
        return

    iteration = 0
    try:
        while True:
            iteration += 1
            if 0 < count <= iteration:
                break

            data = client.get_data()
            ts = time.strftime("%H:%M:%S")

            status = data.ups_status or "?"
            charge = f"{data.battery_charge}%" if data.battery_charge is not None else "?"
            vin = f"{data.input_voltage}V" if data.input_voltage is not None else "?"
            vout = f"{data.output_voltage}V" if data.output_voltage is not None else "?"
            load = f"{data.ups_load}%" if data.ups_load is not None else "?"
            temp = f"{data.ups_temperature}C" if data.ups_temperature is not None else "?"

            print(
                f"  [{ts}] "
                f"status={status:<8} "
                f"charge={charge:<5} "
                f"vin={vin:<8} "
                f"vout={vout:<8} "
                f"load={load:<5} "
                f"temp={temp}"
            )

            time.sleep(interval)

    except KeyboardInterrupt:
        print("\n  หยุด polling")
    finally:
        client.disconnect()
        print("  ปิดการเชื่อมต่อ")


# ---------------------------------------------------------------------------
# Mode 4: Event Monitoring  (เทียบ `upsmon NOTIFYCMD`)
# ---------------------------------------------------------------------------

def demo_monitor(interval: float = 1.0) -> None:
    """Monitor UPS events -- เหมือน `upsmon` กับ NOTIFYCMD"""
    _separator("Mode 4: Event Monitoring (upsmon NOTIFYCMD-style)", "=")
    print(f"  Interval: {interval}s | กด Ctrl+C เพื่อหยุด")
    print(f"  กำลังรอ event... (ลองถอดสาย AC ออกจาก UPS เพื่อทดสอบ)")
    print()

    client = UPSClient()
    try:
        client.connect()
    except RuntimeError as e:
        print(f"  [Error] {e}")
        _print_troubleshoot()
        return

    @client.on(NotifyType.ONLINE)
    def on_online(event):
        print(f"  [NOTIFY] {event.timestamp} ONLINE  : {event.message}")

    @client.on(NotifyType.ONBATT)
    def on_battery(event):
        print(f"  [NOTIFY] {event.timestamp} ONBATT  : {event.message}")

    @client.on(NotifyType.LOWBATT)
    def on_lowbatt(event):
        print(f"  [NOTIFY] {event.timestamp} LOWBATT : {event.message}")

    @client.on(NotifyType.FSD)
    def on_fsd(event):
        print(f"  [NOTIFY] {event.timestamp} FSD     : {event.message}")

    @client.on(NotifyType.COMMOK)
    def on_commok(event):
        print(f"  [NOTIFY] {event.timestamp} COMMOK  : {event.message}")

    @client.on(NotifyType.COMMBAD)
    def on_commbad(event):
        print(f"  [NOTIFY] {event.timestamp} COMMBAD : {event.message}")

    @client.on(NotifyType.REPLBATT)
    def on_replbatt(event):
        print(f"  [NOTIFY] {event.timestamp} REPLBATT: {event.message}")

    @client.on(NotifyType.CHARGING)
    def on_charging(event):
        print(f"  [NOTIFY] {event.timestamp} CHARGING: {event.message}")

    client.start_monitor(interval=interval)

    try:
        while True:
            data = client.get_data()
            ts = time.strftime("%H:%M:%S")
            status = data.ups_status or "?"
            charge = f"{data.battery_charge}%" if data.battery_charge is not None else "?"
            print(f"  [{ts}] status={status}  charge={charge}", end="\r")
            time.sleep(interval * 2)

    except KeyboardInterrupt:
        print("\n  หยุด monitoring")
    finally:
        client.stop_monitor()
        client.disconnect()
        print("  ปิดการเชื่อมต่อ")


# ---------------------------------------------------------------------------
# Troubleshoot helper
# ---------------------------------------------------------------------------

def _print_troubleshoot() -> None:
    print()
    print("  วิธีแก้ไข:")
    print("    1. ตรวจสอบว่า UPS ต่อสาย USB แล้ว")
    if platform.system() == "Linux":
        print("    2. ติดตั้ง system deps: sudo apt install libhidapi-hidraw0 libusb-1.0-0")
        print("    3. ตั้งค่า udev rule: sudo python -m ups_module.linux_setup")
        print("    4. ถอดปลั๊ก USB แล้วเสียบใหม่")
        print("    5. ลอง: python -m ups_module.demo --check")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    parser = argparse.ArgumentParser(
        description="ตัวอย่างการใช้งาน ups_module",
        prog="python -m ups_module.demo",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "ตัวอย่าง:\n"
            "  python -m ups_module.demo                    # รัน demo ทั้งหมด\n"
            "  python -m ups_module.demo --check            # เช็คระบบก่อน\n"
            "  python -m ups_module.demo --mode oneshot     # อ่านครั้งเดียว (upsc)\n"
            "  python -m ups_module.demo --mode poll        # poll ต่อเนื่อง (upsmon)\n"
            "  python -m ups_module.demo --mode monitor     # event monitor (NOTIFYCMD)\n"
            "  python -m ups_module.demo --mode var --var battery.charge\n"
        ),
    )
    parser.add_argument(
        "--check", action="store_true",
        help="ตรวจสอบระบบเท่านั้น ไม่รัน demo",
    )
    parser.add_argument(
        "--mode", choices=["oneshot", "var", "poll", "monitor", "all"],
        default="all",
        help="เลือกโหมดการทดสอบ (default: all)",
    )
    parser.add_argument(
        "--var", default="battery.charge",
        help="ชื่อตัวแปร NUT สำหรับโหมด var (default: battery.charge)",
    )
    parser.add_argument(
        "--interval", type=float, default=2.0,
        help="ช่วงเวลา polling/monitoring เป็นวินาที (default: 2.0)",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="แสดงผลเป็น JSON format",
    )
    parser.add_argument(
        "--count", type=int, default=0,
        help="จำนวนรอบ poll (0 = ไม่จำกัด, default: 0)",
    )

    args = parser.parse_args()

    signal.signal(signal.SIGINT, lambda *_: None)

    if args.check:
        ok = _check_system()
        return 0 if ok else 1

    if args.mode == "oneshot":
        demo_oneshot(output_json=args.json)
    elif args.mode == "var":
        demo_single_var(args.var)
    elif args.mode == "poll":
        demo_poll(interval=args.interval, count=args.count)
    elif args.mode == "monitor":
        demo_monitor(interval=args.interval)
    elif args.mode == "all":
        _check_system()

        print("\n\n")
        demo_oneshot(output_json=args.json)

        print("\n\n")
        demo_single_var(args.var)

        print("\n\n")
        print("  [TIP] กด Ctrl+C เพื่อข้ามไป mode ถัดไป")
        try:
            demo_poll(interval=args.interval, count=args.count or 5)
        except SystemExit:
            pass

        print("\n\n")
        print("  [TIP] กด Ctrl+C เพื่อหยุด")
        try:
            demo_monitor(interval=args.interval)
        except SystemExit:
            pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
