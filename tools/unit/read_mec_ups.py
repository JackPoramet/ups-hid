#!/usr/bin/env python3
"""
tools/read_mec_ups.py
~~~~~~~~~~~~~~~~~~~~~
MEC MEC0003 (VID=0x0001, PID=0x0000) USB HID UPS Live Reader.
Reverse-engineered from UPSmart (IDBK Mega(USB) HID Engine).

Mechanism: Reads HID Indexed String Descriptors (Index 3 for live Q1 telemetry, Index 13 for rating info).

Usage:
    python tools/read_mec_ups.py
    python tools/read_mec_ups.py --monitor
"""

import argparse
import ctypes
from ctypes import wintypes
import sys
import time

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Win32 Constants
GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
OPEN_EXISTING = 3
INVALID_HANDLE_VALUE = -1

hid = ctypes.windll.hid
kernel32 = ctypes.windll.kernel32

CreateFileA = kernel32.CreateFileA
CreateFileA.argtypes = [wintypes.LPCSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
CreateFileA.restype = wintypes.HANDLE

CloseHandle = kernel32.CloseHandle
CloseHandle.argtypes = [wintypes.HANDLE]
CloseHandle.restype = wintypes.BOOL

HidD_GetIndexedString = hid.HidD_GetIndexedString
HidD_GetIndexedString.argtypes = [wintypes.HANDLE, wintypes.ULONG, wintypes.LPVOID, wintypes.ULONG]
HidD_GetIndexedString.restype = wintypes.BOOL


def get_device_path(vid=0x0001, pid=0x0000) -> str:
    import pywinusb.hid as pyhid
    devices = pyhid.HidDeviceFilter(vendor_id=vid, product_id=pid).get_devices()
    if devices:
        return devices[0].device_path
    return ""


def get_indexed_string(h_dev, index: int) -> str:
    buf = ctypes.create_unicode_buffer(256)
    res = HidD_GetIndexedString(h_dev, index, buf, 512)
    if res:
        return buf.value.strip()
    return ""


def parse_q1_string(raw_str: str) -> dict:
    res = {
        "raw_string": raw_str,
        "input_voltage": "0.0",
        "fault_voltage": "0.0",
        "output_voltage": "0.0",
        "load_percent": "0",
        "frequency": "0.0",
        "battery_voltage": "0.0",
        "temperature": "N/A",
        "utility_normal": False,
        "battery_low": False,
        "bypass_active": False,
        "ups_failed": False,
        "ups_type_standby": False,
        "test_in_progress": False,
        "shutdown_active": False,
        "beeper_on": False,
    }

    if not raw_str:
        return res

    clean_str = raw_str.lstrip("#(").strip()
    parts = clean_str.split()

    if len(parts) >= 8:
        res["input_voltage"] = parts[0]
        res["fault_voltage"] = parts[1]
        res["output_voltage"] = parts[2]
        res["load_percent"] = str(int(parts[3]))
        res["frequency"] = parts[4]
        res["battery_voltage"] = parts[5]
        res["temperature"] = parts[6]

        status_bits = parts[7]
        if len(status_bits) >= 8:
            res["utility_normal"] = (status_bits[0] == '0')
            res["battery_low"] = (status_bits[1] == '1')
            res["bypass_active"] = (status_bits[2] == '1')
            res["ups_failed"] = (status_bits[3] == '1')
            res["ups_type_standby"] = (status_bits[4] == '1')
            res["test_in_progress"] = (status_bits[5] == '1')
            res["shutdown_active"] = (status_bits[6] == '1')
            res["beeper_on"] = (status_bits[7] == '1')

    return res


def read_ups_data():
    dev_path = get_device_path()
    if not dev_path:
        print("❌ Device MEC0003 (VID=0x0001, PID=0x0000) not found!")
        print("   Please check USB connection or close UPSmart.")
        return

    h_dev = CreateFileA(
        dev_path.encode('ascii'),
        GENERIC_READ | GENERIC_WRITE,
        FILE_SHARE_READ | FILE_SHARE_WRITE,
        None,
        OPEN_EXISTING,
        0,
        None
    )

    if h_dev == INVALID_HANDLE_VALUE or h_dev == 0 or h_dev == -1:
        print(f"❌ Cannot open device handle. Error code: {kernel32.GetLastError()}")
        return

    manufacturer = get_indexed_string(h_dev, 1) or "MEC"
    product = get_indexed_string(h_dev, 2) or "MEC0003"
    raw_status = get_indexed_string(h_dev, 3)
    rating_str = get_indexed_string(h_dev, 13)

    data = parse_q1_string(raw_status)

    print("=" * 75)
    print(f" 🔌 {manufacturer} {product} USB HID UPS Live Monitor")
    print(" Reverse-Engineered from UPSmart (IDBK Mega(USB) HID Engine)")
    print("=" * 75)

    print(f"\n📌 Device Info : {manufacturer} {product}")
    if rating_str:
        print(f"   Rating Specs: {rating_str}")
    print(f"   Raw String  : {raw_status}\n")

    print("=" * 76)
    print(" 📊 Real-Time Telemetry (MEC MEC0003)")
    print("=" * 76)
    op_mode = "Line Mode (ไฟปกติ) [Line Interactive] [OL]" if data["utility_normal"] else "Battery Mode (ไฟดับ) [Line Interactive] [OB]"
    print(f"  • Operating Mode     : {op_mode}")
    print(f"  • Input Voltage      : {data['input_voltage']} V")
    if data['fault_voltage'] != "000.0":
        print(f"  • Fault Voltage      : {data['fault_voltage']} V")
    print(f"  • Input Frequency    : {data['frequency']} Hz")
    print(f"  • Output Voltage     : {data['output_voltage']} V")
    
    # Do not fallback to input frequency if output is off
    out_freq = "0.0" if data['output_voltage'] == "000.0" else data['frequency']
    print(f"  • Output Frequency   : {out_freq} Hz")
    print(f"  • Load Level         : {data['load_percent']} %")
    print(f"  • Battery Charge     : {'Low' if data['battery_low'] else 'Normal'}")
    print(f"  • Battery Voltage    : {data['battery_voltage']} V")
    if data['temperature'] != "--.-":
        print(f"  • Temperature        : {data['temperature']} °C")
    print(f"  • Bypass / AVR       : {'Active' if data['bypass_active'] else 'Inactive'}")
    print(f"  • UPS Failed         : {'Yes (Fault!)' if data['ups_failed'] else 'No'}")
    print("=" * 76)

    CloseHandle(h_dev)


def monitor_ups_data(interval=2.0):
    dev_path = get_device_path()
    if not dev_path:
        print("❌ Device MEC0003 not found!")
        return

    h_dev = CreateFileA(dev_path.encode('ascii'), GENERIC_READ | GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_WRITE, None, OPEN_EXISTING, 0, None)
    if h_dev == INVALID_HANDLE_VALUE or h_dev == 0 or h_dev == -1:
        print("❌ Cannot open handle!")
        return

    manufacturer = get_indexed_string(h_dev, 1) or "MEC"
    product = get_indexed_string(h_dev, 2) or "MEC0003"
    rating_str = get_indexed_string(h_dev, 13)

    print("=" * 75)
    print(f" 🔌 Live Monitoring: {manufacturer} {product} (Interval: {interval}s)")
    print(" Press Ctrl+C to stop.\n")

    try:
        while True:
            raw_status = get_indexed_string(h_dev, 3)
            data = parse_q1_string(raw_status)
            ts = time.strftime("%H:%M:%S")
            print(f"[{ts}] In: {data['input_voltage']}V | Out: {data['output_voltage']}V | Freq: {data['frequency']}Hz | Bat: {data['battery_voltage']}V | Load: {data['load_percent']}% | Mains: {'OK' if data['utility_normal'] else 'FAIL'}")
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nStopped live monitoring.")
    finally:
        CloseHandle(h_dev)


def main():
    parser = argparse.ArgumentParser(description="MEC MEC0003 Live UPS Reader")
    parser.add_argument("--monitor", action="store_true", help="Continuously monitor UPS telemetry")
    parser.add_argument("--interval", type=float, default=2.0, help="Monitoring refresh interval in seconds")
    args = parser.parse_args()

    if args.monitor:
        monitor_ups_data(args.interval)
    else:
        read_ups_data()


if __name__ == "__main__":
    main()

