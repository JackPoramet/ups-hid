#!/usr/bin/env python3
"""
tools/unit/test_2000d_batttest_with_telemetry.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
PPC 2000D Battery Self-Test ส่งคำสั่ง + อ่านค่า Telemetry แบบ Real-Time

ใช้วิธีเดียวกับ test_2000d_hid_feature_24.py (ที่ทำงานได้สำเร็จ)
+ เพิ่มการอ่าน Feature Reports กลับมาเพื่อแสดง Telemetry ระหว่างทดสอบ

HID Descriptor ของ PPC 2000D (จาก 2000D_descriptor.txt):
  Input reports: 0x01, 0x06, 0x2D
  Feature reports: 0x01, 0x06, 0x07, 0x09, 0x0A, 0x0B, 0x10, 0x13, 0x24, 0x2D, 0x31, 0x36, 0x42, 0x4A, 0x72, 0x74, 0xE2

  Feature Report 0x01: ACPresent, BelowRemainingCapacityLimit, Charging, Discharging, Good, InternalFailure, Overload (7 bytes)
  Feature Report 0x06: RemainingCapacity (1 byte 0-100%), RunTimeToEmpty (2 bytes secs)
  Feature Report 0x07: PercentLoad (1 byte), Voltage (2 bytes output V)
  Feature Report 0x24: Test (1 byte, Data,Var,Abs,Vol — 0x01=Quick, 0x02=Deep, 0x03=Cancel)
  Feature Report 0x2D: Boost (1 byte), Buck (1 byte)
  Feature Report 0x31: Voltage (2 bytes input V) — ต้องอ่านผ่าน libusb0 control transfer
  Feature Report 0x42: Frequency (2 bytes), Voltage (2 bytes output V)
"""

import ctypes
import os
import struct
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

VID = 0x06DA
PID = 0xFFFF


def is_admin() -> bool:
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def read_feature_report(h, report_id: int) -> bytes | None:
    """อ่าน Feature Report ผ่าน hidapi (8 bytes ตาม descriptor ของ 2000D)"""
    try:
        data = h.get_feature_report(report_id, 8)
        if data and len(data) >= 2:
            return bytes(data)
    except Exception:
        pass
    return None


def decode_report_01(data: bytes) -> dict:
    """Feature Report 0x01: Status Flags (7 x 8-bit fields)"""
    if not data or len(data) < 8:
        return {}
    # data[0] = report_id (0x01)
    return {
        "ac_present": data[1] != 0,
        "below_remaining_capacity_limit": data[2] != 0,
        "charging": data[3] != 0,
        "discharging": data[4] != 0,
        "good": data[5] != 0,
        "internal_failure": data[6] != 0,
        "overload": data[7] != 0,
    }


def decode_report_06(data: bytes) -> dict:
    """Feature Report 0x06: RemainingCapacity (1 byte 0-100%) + RunTimeToEmpty (2 bytes secs)"""
    if not data or len(data) < 4:
        return {}
    remaining_capacity = data[1]
    runtime_to_empty = struct.unpack_from("<H", data, 2)[0]
    return {
        "battery_charge_pct": remaining_capacity,
        "runtime_to_empty_sec": runtime_to_empty,
    }


def decode_report_07(data: bytes) -> dict:
    """Feature Report 0x07: PercentLoad (1 byte) + Voltage (2 bytes output V)"""
    if not data or len(data) < 4:
        return {}
    percent_load = data[1]
    voltage_raw = struct.unpack_from("<H", data, 2)[0]
    # Unit exponent: 10^6*cm^2*g/s^3*A = centivolts (÷100) or decivolts (÷10)
    output_voltage = voltage_raw / 10.0 if voltage_raw > 2500 else voltage_raw / 1.0
    if output_voltage > 1000:
        output_voltage = voltage_raw / 100.0
    return {
        "percent_load": percent_load,
        "output_voltage": output_voltage,
        "output_voltage_raw": voltage_raw,
    }


def decode_report_24(data: bytes) -> dict:
    """Feature Report 0x24: Test status (1 byte)"""
    if not data or len(data) < 2:
        return {}
    test_val = data[1]
    test_status = "idle"
    if test_val == 1:
        test_status = "quick_test"
    elif test_val == 2:
        test_status = "deep_test"
    elif test_val == 3:
        test_status = "abort_test"
    return {
        "test_status": test_status,
        "test_raw": test_val,
    }


def decode_report_2d(data: bytes) -> dict:
    """Feature Report 0x2D: Boost (1 byte), Buck (1 byte)"""
    if not data or len(data) < 3:
        return {}
    return {
        "boost": data[1] != 0,
        "buck": data[2] != 0,
    }


def decode_report_42(data: bytes) -> dict:
    """Feature Report 0x42: Frequency (2 bytes 10^-1 Hz) + Voltage (2 bytes output V)"""
    if not data or len(data) < 5:
        return {}
    freq_raw = struct.unpack_from("<H", data, 1)[0]
    volt_raw = struct.unpack_from("<H", data, 3)[0]
    frequency = freq_raw / 10.0
    voltage = volt_raw / 10.0 if volt_raw > 2500 else volt_raw / 1.0
    if voltage > 1000:
        voltage = volt_raw / 100.0
    return {
        "output_frequency_hz": frequency,
        "output_voltage_42": voltage,
        "freq_raw": freq_raw,
        "volt_raw_42": volt_raw,
    }


def read_input_voltage_libusb() -> float | None:
    """
    [MANDATORY PHOENIXTEC RULE] อ่านค่า Input Voltage ($V_{in}$) ผ่าน libusb0.dll
    Direct USB Control Transfer bmRequestType=0xA1, bRequest=0x01, wValue=0x0331
    """
    dll_path = Path(r"C:\Program Files\WinpowerG2\libUSB_driver\amd64\libusb0.dll")
    if not dll_path.exists():
        dll_path = Path(r"C:\Windows\System32\libusb0.dll")
    if not dll_path.exists():
        return None

    try:
        libusb = ctypes.CDLL(str(dll_path))
        libusb.usb_init()
        libusb.usb_find_busses()
        libusb.usb_find_devices()

        # Minimal struct definitions for bus/device traversal
        class usb_dev_desc(ctypes.Structure):
            _fields_ = [
                ("bLength", ctypes.c_uint8), ("bDescriptorType", ctypes.c_uint8),
                ("bcdUSB", ctypes.c_uint16), ("bDeviceClass", ctypes.c_uint8),
                ("bDeviceSubClass", ctypes.c_uint8), ("bDeviceProtocol", ctypes.c_uint8),
                ("bMaxPacketSize0", ctypes.c_uint8), ("idVendor", ctypes.c_uint16),
                ("idProduct", ctypes.c_uint16), ("bcdDevice", ctypes.c_uint16),
                ("iManufacturer", ctypes.c_uint8), ("iProduct", ctypes.c_uint8),
                ("iSerialNumber", ctypes.c_uint8), ("bNumConfigurations", ctypes.c_uint8),
            ]

        class usb_device(ctypes.Structure): pass
        class usb_bus(ctypes.Structure): pass
        usb_device._fields_ = [
            ("next", ctypes.POINTER(usb_device)), ("prev", ctypes.POINTER(usb_device)),
            ("filename", ctypes.c_char * 512), ("bus", ctypes.POINTER(usb_bus)),
            ("descriptor", usb_dev_desc), ("config", ctypes.c_void_p),
            ("dev", ctypes.c_void_p), ("devnum", ctypes.c_uint8),
            ("num_children", ctypes.c_uint8), ("children", ctypes.c_void_p),
        ]
        usb_bus._fields_ = [
            ("next", ctypes.POINTER(usb_bus)), ("prev", ctypes.POINTER(usb_bus)),
            ("dirname", ctypes.c_char * 512), ("devices", ctypes.POINTER(usb_device)),
            ("location", ctypes.c_uint32), ("root_dev", ctypes.POINTER(usb_device)),
        ]

        libusb.usb_get_busses.restype = ctypes.POINTER(usb_bus)
        libusb.usb_open.restype = ctypes.c_void_p
        libusb.usb_open.argtypes = [ctypes.POINTER(usb_device)]
        libusb.usb_close.restype = ctypes.c_int
        libusb.usb_close.argtypes = [ctypes.c_void_p]
        libusb.usb_control_msg.restype = ctypes.c_int
        libusb.usb_control_msg.argtypes = [
            ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
            ctypes.c_int, ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_int
        ]

        bus_ptr = libusb.usb_get_busses()
        found_dev = None
        while bus_ptr:
            bus = bus_ptr.contents
            dev_ptr = bus.devices
            while dev_ptr:
                dev = dev_ptr.contents
                if dev.descriptor.idVendor == VID and dev.descriptor.idProduct == PID:
                    found_dev = dev_ptr
                    break
                dev_ptr = dev.next
            if found_dev:
                break
            bus_ptr = bus.next

        if not found_dev:
            return None

        handle = libusb.usb_open(found_dev)
        if not handle:
            return None

        try:
            buf = ctypes.create_string_buffer(8)
            # GET_REPORT Feature Report 0x31: bmRequestType=0xA1, bRequest=0x01, wValue=0x0331
            ret = libusb.usb_control_msg(handle, 0xA1, 0x01, 0x0331, 0, buf, 8, 1000)
            if ret >= 2:
                raw_val = struct.unpack_from("<H", buf.raw, 0)[0]
                # Unit exponent 10^7 = decivolts => ÷10
                v_in = raw_val / 10.0
                if v_in > 500:
                    v_in = raw_val / 100.0
                if 50 < v_in < 300:
                    return v_in
        finally:
            libusb.usb_close(handle)
    except Exception:
        pass
    return None


def poll_telemetry(h) -> dict:
    """อ่านค่า Telemetry ทั้งหมดจาก PPC 2000D ผ่าน HID Feature Reports"""
    result = {}

    r01 = read_feature_report(h, 0x01)
    if r01:
        result.update(decode_report_01(r01))

    r06 = read_feature_report(h, 0x06)
    if r06:
        result.update(decode_report_06(r06))

    r07 = read_feature_report(h, 0x07)
    if r07:
        result.update(decode_report_07(r07))

    r24 = read_feature_report(h, 0x24)
    if r24:
        result.update(decode_report_24(r24))

    r2d = read_feature_report(h, 0x2D)
    if r2d:
        result.update(decode_report_2d(r2d))

    r42 = read_feature_report(h, 0x42)
    if r42:
        result.update(decode_report_42(r42))

    # Input Voltage ต้องอ่านผ่าน libusb0 (MANDATORY PHOENIXTEC RULE)
    v_in = read_input_voltage_libusb()
    if v_in is not None:
        result["input_voltage"] = v_in

    return result


def run_battery_test_with_telemetry(test_type: str = "quick", duration_s: int = 25):
    """ส่งคำสั่ง Battery Test + Hold Process อ่านค่า Telemetry แบบ Real-Time"""

    print("==============================================================================")
    print(" ⚡ PPC 2000D Battery Self-Test + Real-Time Telemetry Monitor")
    print("==============================================================================")

    if not is_admin():
        print("🔒 [UAC] ขอยกระดับสิทธิ์ Administrator...")
        script = os.path.abspath(sys.argv[0])
        args_str = " ".join([f'"{a}"' for a in sys.argv[1:]])
        ret = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, f'"{script}" {args_str}', None, 1
        )
        if ret > 32:
            sys.exit(0)
        else:
            print("❌ ไม่ได้รับสิทธิ์ Admin")
            return

    import hid

    devices = hid.enumerate(VID, PID)
    if not devices:
        print("❌ ไม่พบอุปกรณ์ PPC 2000D (VID 0x06DA PID 0xFFFF)")
        return

    dev_info = devices[0]
    print(f"✅ พบอุปกรณ์: {dev_info.get('product_string', 'Offline UPS')}")
    print(f"   Path: {dev_info['path']}")

    h = hid.device()
    h.open_path(dev_info['path'])
    print("✅ เปิดพอร์ต HID สำเร็จ!\n")

    try:
        # --- Step 1: อ่าน Baseline Telemetry ---
        print("📡 [STEP 1] อ่านค่า Baseline Telemetry ก่อนสั่งทดสอบ...")
        baseline = poll_telemetry(h)

        ac_txt = "✅ ปกติ (AC Present)" if baseline.get("ac_present") else "⚠️ ไฟดับ (Battery)"
        print(f"   • สถานะไฟ AC    : {ac_txt}")
        print(f"   • แบตเตอรี่      : {baseline.get('battery_charge_pct', 'N/A')}%")
        print(f"   • Runtime ที่เหลือ : {baseline.get('runtime_to_empty_sec', 'N/A')} วินาที")
        print(f"   • Load           : {baseline.get('percent_load', 'N/A')}%")
        print(f"   • Output Voltage : {baseline.get('output_voltage', 'N/A')} V")
        v_in = baseline.get("input_voltage")
        if v_in:
            print(f"   • Input Voltage  : {v_in} V (อ่านผ่าน libusb0 Report 0x31)")
        print(f"   • Boost/Buck     : Boost={'Yes' if baseline.get('boost') else 'No'}, Buck={'Yes' if baseline.get('buck') else 'No'}")

        # --- Step 2: ส่งคำสั่ง Battery Test ---
        test_code = {"quick": 0x01, "deep": 0x02, "cancel": 0x03}.get(test_type, 0x01)
        test_name = {"quick": "Quick Test (10s)", "deep": "Deep Test", "cancel": "Cancel Test"}.get(test_type, "Quick Test")

        print(f"\n⚡ [STEP 2] ส่งคำสั่ง {test_name} ผ่าน Feature Report 0x24...")
        payload = bytes([0x24, test_code, 0, 0, 0, 0, 0, 0])
        res = h.send_feature_report(payload)
        print(f"   --> send_feature_report Return Code: {res} bytes written")

        if res <= 0:
            print("   ❌ ส่งคำสั่งล้มเหลว")
            return

        print(f"   🎉 ส่งคำสั่ง {test_name} สำเร็จ!")
        print(f"\n📊 [STEP 3] Hold Process — อ่านค่า Real-Time Telemetry ทุก 1 วินาที ({duration_s} วินาที)...\n")

        # --- Step 3: Hold loop อ่านค่า Telemetry ---
        header = f" {'Sec':>4} | {'AC':>3} | {'Disch':>5} | {'Batt%':>5} | {'Runtime':>8} | {'Load%':>5} | {'OutV':>6} | {'InV':>6} | {'Boost':>5} | {'Test':>10}"
        print("=" * len(header))
        print(header)
        print("=" * len(header))

        start_time = time.time()
        test_was_active = False

        for tick in range(duration_s):
            time.sleep(1.0)
            elapsed = int(time.time() - start_time)

            data = poll_telemetry(h)

            ac = "Y" if data.get("ac_present") else "N"
            disch = "Y" if data.get("discharging") else "N"
            batt_pct = data.get("battery_charge_pct", "?")
            runtime = data.get("runtime_to_empty_sec", "?")
            load = data.get("percent_load", "?")
            out_v = data.get("output_voltage", "?")
            in_v = data.get("input_voltage", "?")
            boost_txt = "Boost" if data.get("boost") else ("Buck" if data.get("buck") else "-")
            test_st = data.get("test_status", "?")

            # ตรวจว่ามีการ Discharge จริง (เช่น AC หายไป)
            if data.get("discharging"):
                test_was_active = True

            if isinstance(out_v, float):
                out_v = f"{out_v:.1f}"
            if isinstance(in_v, float):
                in_v = f"{in_v:.1f}"

            print(
                f" {elapsed:4d} | {ac:>3} | {disch:>5} | {str(batt_pct):>5} | {str(runtime):>8} | {str(load):>5} | {str(out_v):>6} | {str(in_v):>6} | {boost_txt:>5} | {test_st:>10}"
            )

            # ตรวจจับจบการทดสอบ
            if test_was_active and not data.get("discharging") and elapsed >= 5:
                print(f"\n🎉 การทดสอบเสร็จสิ้น! กลับสู่สภาวะ AC ปกติ ณ วินาทีที่ {elapsed}")
                break

        # --- Step 4: อ่านค่าสรุปหลัง Test ---
        print(f"\n📡 [STEP 4] อ่านค่าสรุปหลังการทดสอบ...")
        final = poll_telemetry(h)
        print("=" * 60)
        print(" 📊 สรุปผลการทดสอบ Battery Test")
        print("=" * 60)
        print(f"  • AC Present     : {'Yes' if final.get('ac_present') else 'No'}")
        print(f"  • Charging       : {'Yes' if final.get('charging') else 'No'}")
        print(f"  • Battery Charge : {final.get('battery_charge_pct', 'N/A')}%")
        print(f"  • Runtime Left   : {final.get('runtime_to_empty_sec', 'N/A')} วินาที")
        print(f"  • Load           : {final.get('percent_load', 'N/A')}%")
        print(f"  • Output Voltage : {final.get('output_voltage', 'N/A')} V")
        v_in_final = final.get("input_voltage")
        if v_in_final:
            print(f"  • Input Voltage  : {v_in_final} V")
        print(f"  • Good           : {'Yes' if final.get('good') else 'No'}")
        print(f"  • Internal Fail  : {'Yes' if final.get('internal_failure') else 'No'}")
        print(f"  • Overload       : {'Yes' if final.get('overload') else 'No'}")
        print("=" * 60)

    finally:
        h.close()
        print("\n🔒 ปิดพอร์ต HID เรียบร้อย")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="PPC 2000D Battery Test + Telemetry Monitor")
    parser.add_argument("--quick", action="store_true", help="Quick Battery Test (10s)")
    parser.add_argument("--deep", action="store_true", help="Deep Battery Test (until low battery)")
    parser.add_argument("--cancel", action="store_true", help="Cancel Battery Test")
    parser.add_argument("--duration", type=int, default=25, help="Monitor duration in seconds (default: 25)")
    parser.add_argument("--read-only", action="store_true", help="Read telemetry only, don't send test command")

    args = parser.parse_args()

    if args.read_only:
        # Read-only mode
        print("==============================================================================")
        print(" 📡 PPC 2000D Telemetry Read-Only Mode")
        print("==============================================================================")
        import hid
        devices = hid.enumerate(VID, PID)
        if devices:
            h = hid.device()
            h.open_path(devices[0]['path'])
            try:
                data = poll_telemetry(h)
                for k, v in sorted(data.items()):
                    print(f"  {k}: {v}")
            finally:
                h.close()
        else:
            print("❌ ไม่พบอุปกรณ์ PPC 2000D")
    elif args.cancel:
        run_battery_test_with_telemetry("cancel", duration_s=5)
    elif args.deep:
        run_battery_test_with_telemetry("deep", duration_s=args.duration or 600)
    else:
        run_battery_test_with_telemetry("quick", duration_s=args.duration)
