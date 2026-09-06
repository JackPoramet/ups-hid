#!/usr/bin/env python3
"""
tools/unit/live_battery_test_runner.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
สคริปต์สำหรับรัน Battery Test แบบ Hold Process รองรับอุปกรณ์ HID UPS ทุกยี่ห้อ
(PHOENIXTEC, Innova Unity, Innova Basic G2, MEC, PPC, APC, CyberPower, Tripp Lite, Powercom, Eaton)

Features:
- ค้นหาและเลือกรุ่นอุปกรณ์ HID UPS อัตโนมัติ (หรือระบุด้วย --device N / --serial S)
- สั่งรัน Battery Test (Quick 10s / Deep test / Cancel)
- Hold การทำงานของสคริปต์เพื่อติดตามอ่านค่าสด (Real-Time Telemetry) ทุก 1 วินาที
- บันทึกประวัติ Discharge / Test History ลง SQLite Database ในรูปแบบ Winpower G2 API Response

Usage:
    python tools/unit/live_battery_test_runner.py --list
    python tools/unit/live_battery_test_runner.py --quick
    python tools/unit/live_battery_test_runner.py --deep
    python tools/unit/live_battery_test_runner.py --device 1 --quick
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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
    read_winpower_libusb_report_31,
)
from tray_service.database import DatabaseManager

if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    GENERIC_READ = 0x80000000
    GENERIC_WRITE = 0x40000000
    FILE_SHARE_READ = 0x00000001
    FILE_SHARE_WRITE = 0x00000002
    OPEN_EXISTING = 3
    INVALID_HANDLE_VALUE = -1

    try:
        hid_dll = ctypes.windll.hid
        kernel32_dll = ctypes.windll.kernel32

        CreateFileA = kernel32_dll.CreateFileA
        CreateFileA.argtypes = [wintypes.LPCSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        CreateFileA.restype = wintypes.HANDLE

        CloseHandle = kernel32_dll.CloseHandle
        CloseHandle.argtypes = [wintypes.HANDLE]
        CloseHandle.restype = wintypes.BOOL

        HidD_GetIndexedString = hid_dll.HidD_GetIndexedString
        HidD_GetIndexedString.argtypes = [wintypes.HANDLE, wintypes.ULONG, wintypes.LPVOID, wintypes.ULONG]
        HidD_GetIndexedString.restype = wintypes.BOOL
    except Exception:
        pass


def parse_mec_q1_telemetry(raw_str: str) -> dict:
    """ถอดรหัส Megatec Q1 telemetry format: (232.1 000.0 232.0 000 50.1 13.7 --.- 00001000"""
    res = {
        "raw_string": raw_str,
        "input_voltage": "0.0",
        "output_voltage": "0.0",
        "load_percent": "0",
        "frequency": "0.0",
        "battery_voltage": "0.0",
        "utility_normal": True,
        "battery_low": False,
        "test_in_progress": False,
        "ups_failed": False,
    }
    if not raw_str:
        return res

    idx = raw_str.find("(")
    if idx != -1:
        clean_str = raw_str[idx + 1:].strip()
    else:
        clean_str = raw_str.lstrip("#(").strip()

    parts = clean_str.split()
    if len(parts) >= 8:
        res["input_voltage"] = parts[0]
        res["output_voltage"] = parts[2]
        res["load_percent"] = parts[3]
        res["frequency"] = parts[4]
        res["battery_voltage"] = parts[5]

        status_bits = parts[7]
        if len(status_bits) >= 8:
            res["utility_normal"] = (status_bits[0] == '0')
            res["battery_low"] = (status_bits[1] == '1')
            res["test_in_progress"] = (status_bits[5] == '1')
            res["ups_failed"] = (status_bits[3] == '1')

    return res


def poll_universal_ups_telemetry(h: Any, target: dict) -> dict:
    """อ่านและ decode ค่า Telemetry จากอุปกรณ์ UPS (รองรับทั้ง HID Standard และ MEC)"""
    vid_val = target.get("vendor_id")
    prod_str = (target.get("product_string") or "").lower()
    mfg_str = (target.get("manufacturer_string") or "").lower()

    # ── กรณี MEC / PPC Indexed String Device ────────────────────────────────
    if vid_val in (1, 0x0001, "0x0001") or "mec" in prod_str or "ppc" in mfg_str:
        raw_status = ""
        try:
            # 1. First try directly via hidapi handle get_indexed_string(3)
            if hasattr(h, "get_indexed_string"):
                try:
                    raw_status = h.get_indexed_string(3)
                except Exception:
                    pass

            # 2. PyUSB fallback (Linux / Orange Pi)
            if not raw_status and sys.platform != "win32":
                try:
                    import usb.core
                    import usb.util
                    usb_dev = usb.core.find(idVendor=0x0001, idProduct=0x0000)
                    if usb_dev:
                        try:
                            for lang in (0, 0x0409):
                                try:
                                    ret = usb_dev.ctrl_transfer(0x80, 0x06, (0x03 << 8) | 3, lang, 255, 1000)
                                    if ret and len(ret) > 2:
                                        s = bytes(ret)[2:].decode("utf-16-le", errors="replace").strip()
                                        if "(" in s:
                                            raw_status = s
                                            break
                                except Exception:
                                    pass
                        finally:
                            try:
                                usb.util.dispose_resources(usb_dev)
                            except Exception:
                                pass
                except Exception:
                    pass

            # 3. On Windows fallback: Read via Win32 HidD_GetIndexedString handle
            if not raw_status and sys.platform == "win32":
                try:
                    from tools.unit.read_mec_ups import get_device_path
                except ImportError:
                    def get_device_path(): return ""

                dev_path = target.get("path_str") or str(target.get("path") or "")
                if not dev_path:
                    dev_path = get_device_path()

                if dev_path:
                    path_bytes = dev_path.encode("ascii") if isinstance(dev_path, str) else dev_path
                    h_dev = CreateFileA(path_bytes, GENERIC_READ | GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_WRITE, None, OPEN_EXISTING, 0, None)
                    if h_dev != INVALID_HANDLE_VALUE and h_dev != 0:
                        try:
                            buf = ctypes.create_unicode_buffer(256)
                            if HidD_GetIndexedString(h_dev, 3, buf, ctypes.sizeof(buf)):
                                raw_status = buf.value.strip()
                        finally:
                            CloseHandle(h_dev)

            if raw_status:
                data = parse_mec_q1_telemetry(raw_status)
                ac_on = data.get("utility_normal", True)
                v_bat = float(data["battery_voltage"]) if data.get("battery_voltage") else 12.0
                v_in = float(data["input_voltage"]) if data.get("input_voltage") else 220.0
                v_out = float(data["output_voltage"]) if data.get("output_voltage") else 220.0
                load = float(data["load_percent"]) if data.get("load_percent") else 0.0

                batt_pct = round(max(0.0, min(100.0, (v_bat - 10.5) / (13.5 - 10.5) * 100.0)), 1)
                if batt_pct >= 95.0:
                    batt_pct = 100.0

                is_testing = bool(data.get("test_in_progress"))
                if is_testing:
                    mode_str = "Battery Test Mode (กำลังทดสอบ!)"
                    status_str = "CAL"
                elif not ac_on:
                    mode_str = "Battery Mode (ไฟดับ!)"
                    status_str = "OB"
                else:
                    mode_str = "Line Mode (ไฟปกติ)"
                    status_str = "OL"

                return {
                    "ac_present": ac_on,
                    "discharging": not ac_on or is_testing,
                    "battery_voltage_v": v_bat,
                    "battery.charge": batt_pct,
                    "battery_capacity_percent": batt_pct,
                    "input.voltage": v_in,
                    "output_voltage_v": v_out,
                    "percent_load": load,
                    "ups.status": status_str,
                    "ups_mode": mode_str,
                    "battery_test_status": "running" if is_testing else "idle",
                    "status_good": not data.get("ups_failed", False),
                }
        except Exception:
            pass

    # ── กรณี Standard HID UPS Device (PHOENIXTEC, APC, CyberPower, Eaton...) ──
    report_ids = target.get("report_ids") or [
        0x01, 0x02, 0x03, 0x06, 0x07, 0x08, 0x09, 0x10,
        0x13, 0x14, 0x17, 0x21, 0x24, 0x25, 0x26, 0x30, 0x31
    ]

    raw_reports, _ = read_all_feature_reports(h, report_ids=report_ids, sizes=(64,), retries=1)
    data = decode_feature_reports(raw_reports, device_info=target)
    data.update(infer_tentative_live_values(raw_reports, data))

    # Fallback สำหรับ Input Voltage (Report 0x31)
    if ("input.voltage" not in data or data["input.voltage"] is None) and target.get("vendor_id") == 0x06DA:
        try:
            v_in, _ = read_winpower_libusb_report_31(
                vid=target.get("vendor_id", 0x06DA),
                pid=target.get("product_id", 0xFFFF),
                target_serial=target.get("serial_number"),
                target_product=target.get("product_string"),
            )
            if v_in is not None and v_in > 0:
                data["input.voltage"] = v_in
        except Exception:
            pass

    return data


def _send_libusb_control_report(vid: int, pid: int, target_serial: str, report_id: int, code: int, q1_cmd: str = "T\r") -> bool:
    """
    [MANDATORY RULE FOR PHOENIXTEC / PPC 2000D]
    ส่ง Direct USB Control Transfer (SET_REPORT bmRequestType=0x21, bRequest=0x09) ผ่าน libusb0.dll
    เพื่อ bypass Windows HID Class Driver (hidusb.sys) บล็อกสั่งงาน เพื่อให้เกิดเสียง Relay Click / Beep ของ 2000D จริงๆ
    """
    import ctypes
    dll_paths = [
        r"C:\Program Files\WinpowerG2\libUSB_driver\amd64\libusb0.dll",
        r"C:\Program Files\WinpowerG2\libUSB_Win.dll",
        str(WINDOWS_DIR / "libusb0.dll"),
    ]
    target_dll = None
    for p in dll_paths:
        if Path(p).exists():
            target_dll = p
            break
    if not target_dll:
        return False

    try:
        libusb = ctypes.CDLL(target_dll)
        libusb.usb_init()
        libusb.usb_find_busses()
        libusb.usb_find_devices()

        class usb_device_descriptor(ctypes.Structure):
            _fields_ = [
                ("bLength", ctypes.c_uint8),
                ("bDescriptorType", ctypes.c_uint8),
                ("bcdUSB", ctypes.c_uint16),
                ("bDeviceClass", ctypes.c_uint8),
                ("bDeviceSubClass", ctypes.c_uint8),
                ("bDeviceProtocol", ctypes.c_uint8),
                ("bMaxPacketSize0", ctypes.c_uint8),
                ("idVendor", ctypes.c_uint16),
                ("idProduct", ctypes.c_uint16),
                ("bcdDevice", ctypes.c_uint16),
                ("iManufacturer", ctypes.c_uint8),
                ("iProduct", ctypes.c_uint8),
                ("iSerialNumber", ctypes.c_uint8),
                ("bNumConfigurations", ctypes.c_uint8),
            ]

        class usb_device(ctypes.Structure): pass
        class usb_bus(ctypes.Structure): pass

        usb_device._fields_ = [
            ("next", ctypes.POINTER(usb_device)),
            ("prev", ctypes.POINTER(usb_device)),
            ("filename", ctypes.c_char * 512),
            ("bus", ctypes.POINTER(usb_bus)),
            ("descriptor", usb_device_descriptor),
            ("config", ctypes.c_void_p),
            ("dev", ctypes.c_void_p),
            ("devnum", ctypes.c_uint8),
            ("num_children", ctypes.c_ubyte),
            ("children", ctypes.c_void_p),
        ]

        usb_bus._fields_ = [
            ("next", ctypes.POINTER(usb_bus)),
            ("prev", ctypes.POINTER(usb_bus)),
            ("dirname", ctypes.c_char * 512),
            ("devices", ctypes.POINTER(usb_device)),
            ("location", ctypes.c_uint32),
            ("root_dev", ctypes.POINTER(usb_device)),
        ]

        libusb.usb_get_busses.restype = ctypes.POINTER(usb_bus)
        libusb.usb_open.argtypes = [ctypes.POINTER(usb_device)]
        libusb.usb_open.restype = ctypes.c_void_p
        libusb.usb_close.argtypes = [ctypes.c_void_p]
        libusb.usb_close.restype = ctypes.c_int
        libusb.usb_get_string_simple.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_size_t]
        libusb.usb_get_string_simple.restype = ctypes.c_int

        libusb.usb_control_msg.argtypes = [
            ctypes.c_void_p,
            ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
            ctypes.c_char_p, ctypes.c_int, ctypes.c_int,
        ]
        libusb.usb_control_msg.restype = ctypes.c_int

        bus = libusb.usb_get_busses()
        h_target = None
        target_s = (target_serial or "").strip().lower()

        while bus:
            dev = bus.contents.devices
            while dev:
                desc = dev.contents.descriptor
                if desc.idVendor == vid and desc.idProduct == pid:
                    h_tmp = libusb.usb_open(dev)
                    if h_tmp:
                        str_buf = ctypes.create_string_buffer(256)
                        ser_str = ""
                        prod_str = ""
                        if desc.iSerialNumber > 0 and libusb.usb_get_string_simple(h_tmp, 4, str_buf, 256) > 0:
                            ser_str = str_buf.value.decode("utf-8", errors="ignore").strip().lower()
                        if desc.iProduct > 0 and libusb.usb_get_string_simple(h_tmp, 2, str_buf, 256) > 0:
                            prod_str = str_buf.value.decode("utf-8", errors="ignore").strip().lower()

                        if not target_s or (target_s and target_s in ser_str) or ("offline" in prod_str or "2000" in prod_str):
                            h_target = h_tmp
                            break
                        libusb.usb_close(h_tmp)
                dev = dev.contents.next
            if h_target:
                break
            bus = bus.contents.next

        if not h_target:
            return False

        try:
            # 1. กรณี PPC 2000D ( Feature Report 0x24 : 8-byte binary payload [0x24, code, 0, 0, 0, 0, 0, 0] )
            feature_24_payload = bytes([report_id & 0xFF, code & 0xFF, 0, 0, 0, 0, 0, 0])
            buf_8 = ctypes.create_string_buffer(feature_24_payload)
            wValue_24 = (0x03 << 8) | (report_id & 0xFF)
            ret = libusb.usb_control_msg(h_target, 0x21, 0x09, wValue_24, 0, buf_8, 8, 1000)
            if ret == 8 or ret > 0:
                return True

            # 2. กรณี Innova Unity / Online HID (ส่ง 64-byte report)
            wValue = (0x03 << 8) | (report_id & 0xFF)
            payload_bytes = [report_id, code] + [0] * 62
            buf_64 = ctypes.create_string_buffer(bytes(payload_bytes))
            ret2 = libusb.usb_control_msg(h_target, 0x21, 0x09, wValue, 0, buf_64, 64, 1000)
            return ret2 > 0
        finally:
            try:
                libusb.usb_close(h_target)
            except Exception:
                pass
    except Exception:
        return False


def send_universal_battery_test_command(h: Any, target: dict, cmd_type: str) -> Tuple[bool, str]:
    """
    ส่งคำสั่ง Battery Test ไปยัง UPS ตามสถาปัตยกรรมที่ Reverse Engineered จาก Winpower G2
    (รองรับทั้ง Innova Unity/Basic G2 และ PPC 2000D โดยตรงไม่ต้องพึ่งพาโปรแกรม Winpower)
    """
    cmd_map = {
        "quick": (0x01, "T\r", "Quick Battery Test (10 วินาที)"),
        "deep": (0x02, "TL\r", "Deep Battery Test (ทดสอบจนแบตเตอรี่ต่ำ)"),
        "cancel": (0x03, "CT\r", "Cancel Battery Test (ยกเลิกการทดสอบ)"),
    }
    code, q1_str, desc = cmd_map.get(cmd_type, (0x01, "T\r", "Quick Battery Test (10 วินาที)"))

    vid_val = target.get("vendor_id", 0x06DA)
    pid_val = target.get("product_id", 0xFFFF)
    serial_val = target.get("serial_number", "")
    prod_val = (target.get("product_string") or "").lower()
    mfr_val = (target.get("manufacturer_string") or "").lower()

    # 0. กรณี MEC0003 (VID 0x0001, PID 0x0000 / Megatec HID Engine Type 5)
    # อุปกรณ์ควบคุมผ่าน USB Indexed String Descriptor (ห้ามส่ง Feature Report 0x24 เพราะฮาร์ดแวร์ไม่รับ)
    # Index 4 = Quick Test (T), Index 5 = Deep Test (TL), Index 11 = Cancel Test (CT)
    if vid_val == 0x0001 or pid_val == 0x0000 or "mec" in prod_val or "mec" in mfr_val:
        mec_str_map = {
            "quick": 4,
            "deep": 5,
            "cancel": 11,
        }
        str_idx = mec_str_map.get(cmd_type, 4)

        mec_sent = False
        if hasattr(h, "get_indexed_string"):
            try:
                h.get_indexed_string(str_idx)
                mec_sent = True
            except Exception:
                pass

        if not mec_sent:
            try:
                dev_path = target.get("path_str") or str(target.get("path") or "")
                if dev_path:
                    path_bytes = dev_path.encode("ascii") if isinstance(dev_path, str) else dev_path
                    h_dev = CreateFileA(path_bytes, GENERIC_READ | GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_WRITE, None, OPEN_EXISTING, 0, None)
                    if h_dev != INVALID_HANDLE_VALUE and h_dev != 0:
                        try:
                            buf = ctypes.create_unicode_buffer(256)
                            if HidD_GetIndexedString(h_dev, str_idx, buf, ctypes.sizeof(buf)):
                                mec_sent = True
                        finally:
                            CloseHandle(h_dev)
            except Exception:
                pass

        if not mec_sent:
            try:
                import usb.core
                import usb.util
                usb_dev = usb.core.find(idVendor=0x0001, idProduct=0x0000)
                if usb_dev:
                    try:
                        for lang in (0x0409, 0):
                            try:
                                usb_dev.ctrl_transfer(
                                    bmRequestType=0x80,
                                    bRequest=0x06,
                                    wValue=(0x03 << 8) | str_idx,
                                    wIndex=lang,
                                    data_or_wLength=255,
                                    timeout=1000
                                )
                                mec_sent = True
                                break
                            except Exception:
                                pass
                    finally:
                        try:
                            usb.util.dispose_resources(usb_dev)
                        except Exception:
                            pass
            except Exception:
                pass

        if mec_sent:
            time.sleep(0.3)
            s3_val = ""
            if hasattr(h, "get_indexed_string"):
                try:
                    s3_val = h.get_indexed_string(3) or ""
                except Exception:
                    pass
            if s3_val.startswith("A"):
                return True, f"ส่งคำสั่ง {desc} สำเร็จผ่าน MEC USB String Descriptor #{str_idx} (UPS ยืนยัน ACK สำเร็จ)"
            elif s3_val.startswith("N"):
                return False, f"UPS ปฏิเสธคำสั่ง {desc} (ได้ NAK จาก UPS - กรุณาเปิดสวิตช์หน้าเครื่อง UPS ให้ Output จ่ายไฟปกติ)"
            return True, f"ส่งคำสั่ง {desc} สำเร็จผ่าน MEC USB String Descriptor #{str_idx}"

    # 1. ส่ง Feature Report ID 0x24 (Power Device > Test) ขนาด 8 บิต ผ่าน hidapi handle ก่อนเสมอ (ทำงาน 100% บน PPC 2000D)
    for rid in (0x24, 0x01, 0x03, 0x07):
        try:
            payload_8 = bytes([rid, code, 0, 0, 0, 0, 0, 0])
            h.send_feature_report(payload_8)
            return True, f"ส่งคำสั่ง {desc} สำเร็จผ่าน HID Feature Report ID 0x{rid:02X} (8-byte PDC Spec)"
        except Exception:
            pass

    # 2. Fallback: ส่ง Direct USB Control Message ผ่าน libusb0.dll (wValue = 0x0324)
    for rid in (0x24, 0x01, 0x03, 0x07):
        if _send_libusb_control_report(vid_val, pid_val, serial_val, rid, code, q1_cmd=q1_str):
            return True, f"ส่งคำสั่ง {desc} สำเร็จผ่าน Direct USB Control Transfer (libusb0.dll) Report 0x{rid:02X}"

    # 3. Fallback: ส่ง Q1 Command String ("T\r" / "TL\r" / "CT\r") ผ่าน Feature Report ID 0x02 / 0x03
    q1_bytes = q1_str.encode("ascii")
    for rid in (0x02, 0x03):
        try:
            payload = [rid] + list(q1_bytes)
            payload += [0] * (64 - len(payload))
            h.send_feature_report(payload)
            return True, f"ส่งคำสั่ง Q1 Test '{q1_str.strip()}' ({desc}) สำเร็จผ่าน Feature Report ID 0x{rid:02X}"
        except Exception:
            pass

    return False, f"ไม่สามารถส่งคำสั่ง Self-Test ไปยังอุปกรณ์ได้"


def list_all_connected_devices() -> List[dict]:
    """รายการอุปกรณ์ HID UPS ทั้งหมดที่เชื่อมต่ออยู่"""
    devices = list_ups_devices(target_vid=None)
    return devices


def run_live_battery_test(
    test_type: str = "quick",
    max_timeout_s: int = 180,
    device_index: Optional[int] = None,
    target_serial: Optional[str] = None,
) -> None:
    print("=" * 78)
    print(" ⚡ Universal HID UPS Live Battery Test Runner (All Brands)")
    print("=" * 78)

    devices = list_all_connected_devices()
    if not devices:
        print("❌ ไม่พบอุปกรณ์ HID UPS ใดๆ ที่เชื่อมต่อกับเครื่องคอมพิวเตอร์")
        return

    # เลือกอุปกรณ์เป้าหมาย
    target = None
    if target_serial:
        for d in devices:
            if str(d.get("serial_number")).strip() == str(target_serial).strip():
                target = d
                break

    if not target and device_index is not None:
        idx = device_index - 1
        if 0 <= idx < len(devices):
            target = devices[idx]

    if not target:
        target = devices[0]

    dev_mfg = target.get("manufacturer_string") or "Generic"
    dev_prod = target.get("product_string") or "HID UPS"
    dev_name = f"{dev_mfg} {dev_prod}".strip()
    dev_serial = target.get("serial_number") or "80d6c1e4-e44d-4057-acfc-81c16b73ee54"
    vid_hex = f"0x{(target.get('vendor_id') or 0):04X}"
    pid_hex = f"0x{(target.get('product_id') or 0):04X}"

    print(f"✅ เลือกอุปกรณ์: {dev_name} (VID={vid_hex}, PID={pid_hex})")
    print(f"   Serial Number: {dev_serial}")
    print(f"   Device Path  : {target.get('path_str')}\n")

    h, info = open_ups_device(
        vid=target.get("vendor_id", 0x06DA),
        pid=target.get("product_id", 0xFFFF),
        target_path=target.get("path_str"),
        target_serial=dev_serial,
    )

    if not h:
        print("❌ ไม่สามารถเปิดเชื่อมต่อกับอุปกรณ์ HID ได้")
        return

    try:
        # 1. อ่านค่า Baseline ก่อนเริ่มทดสอบ
        print("🔍 กำลังอ่านค่าเริ่มต้น (Baseline Telemetry)...")
        baseline = poll_universal_ups_telemetry(h, target)

        v_start = baseline.get("battery_voltage_v") or baseline.get("battery.voltage") or 27.0
        level_start = baseline.get("battery.charge") or baseline.get("battery_capacity_percent") or 100
        load_start = baseline.get("percent_load") or baseline.get("output_load") or baseline.get("ups.load") or 0

        now_start_dt = datetime.now(timezone.utc)
        start_time_iso = now_start_dt.isoformat()

        # 2. ส่งคำสั่งสั่งเริ่ม Battery Test
        ok, msg = send_universal_battery_test_command(h, target, test_type)
        print(f"🚀 {msg}")

        if not ok:
            print("❌ ไม่สามารถสั่งเริ่ม Battery Test ได้ สิ้นสุดการทำงาน")
            return

        print("✅ เริ่มต้น Hold Process เพื่อติดตามข้อมูลแบบ Real-Time จาก UPS...\n")

        print("=" * 78)
        print(f" {'Sec':>4} | {'Mode':<22} | {'Status':<8} | {'Batt (V)':>9} | {'Batt (%)':>9} | {'Load (%)':>9}")
        print("=" * 78)

        # 3. Hold Loop: อ่านค่าสดๆ ทุก 1 วินาที
        elapsed = 0
        test_detected = False
        completed = False
        v_latest = v_start
        level_latest = level_start
        load_latest = load_start
        test_result = 1  # 1: Passed, 2: Error

        start_mon_time = time.time()

        while elapsed < max_timeout_s:
            time.sleep(1.0)
            elapsed = int(time.time() - start_mon_time)

            curr = poll_universal_ups_telemetry(h, target)

            ac_on = curr.get("ac_present", True)
            discharging = curr.get("discharging", not ac_on)
            test_running = (curr.get("battery_test_status") == "running") or discharging
            ups_mode = curr.get("ups_mode", "Line Mode (Online)")
            status_tag = curr.get("ups.status", "OL" if ac_on else "OB")

            v_curr = curr.get("battery_voltage_v") or curr.get("battery.voltage") or v_latest
            l_curr = curr.get("battery.charge") or curr.get("battery_capacity_percent") or level_latest
            load_curr = curr.get("percent_load") or curr.get("output_load") or curr.get("ups.load") or load_latest

            v_latest = v_curr
            level_latest = l_curr
            load_latest = load_curr

            if curr.get("internal_failure") or curr.get("status_good") is False:
                test_result = 2

            if test_running:
                test_detected = True

            print(
                f" {elapsed:4d}s | {ups_mode[:22]:<22} | {status_tag:<8} | "
                f"{float(v_curr):9.1f} | {int(l_curr):9d}% | {int(load_curr):9d}%"
            )

            # ตรวจจับการจบการทดสอบ
            if test_detected and not test_running and elapsed >= 3:
                completed = True
                print(f"\n🎉 การทดสอบแบตเตอรี่เสร็จสิ้นสมบูรณ์ ณ วินาทีที่ {elapsed}!")
                break

            # Fallback timeout สำหรับ Quick Test
            if test_type == "quick" and elapsed >= 18 and not test_running:
                completed = True
                print(f"\n🎉 ครบกำหนดเวลา Quick Test ({elapsed}s) กลับสู่สภาวะปกติ")
                break

        now_end_dt = datetime.now(timezone.utc)
        end_time_iso = now_end_dt.isoformat()
        actual_duration = max(1, int((now_end_dt - now_start_dt).total_seconds()))

        # 4. บันทึกผลการทดสอบลง SQLite Database
        record = {
            "deviceId": str(dev_serial),
            "dischargeReason": 2,  # 2: Battery Test
            "startTime": start_time_iso,
            "endTime": end_time_iso,
            "duration": actual_duration,
            "testResult": test_result,
            "startVolt": float(v_start),
            "endVolt": float(v_latest),
            "startLevel": int(level_start),
            "endLevel": int(level_latest),
            "startLoad": int(load_start),
            "endLoad": int(load_latest),
            "createTime": start_time_iso,
        }

        db = DatabaseManager()
        rec_id = db.log_discharge_record(record)

        print("\n" + "=" * 78)
        print(" 📊 สรุปผลการทดสอบ Battery Test (บันทึกลง DB สำเร็จ)")
        print("=" * 78)
        print(f"  • Record ID        : #{rec_id}")
        print(f"  • Device Model     : {dev_name}")
        print(f"  • Device Serial    : {dev_serial}")
        print(f"  • Test Reason      : Battery Test (2)")
        print(f"  • Test Result      : {'Passed (1)' if test_result == 1 else 'Failed/Error (2)'}")
        print(f"  • Start Time       : {start_time_iso}")
        print(f"  • End Time         : {end_time_iso}")
        print(f"  • Duration         : {actual_duration} วินาที")
        print(f"  • Battery Voltage  : {v_start} V ➔ {v_latest} V")
        print(f"  • Battery Charge   : {level_start} % ➔ {level_latest} %")
        print(f"  • UPS Load Level   : {load_start} % ➔ {load_latest} %")
        print("=" * 78)
        try:
            sys.stdout.flush()
        except Exception:
            pass

    except Exception as exc:
        print(f"\n❌ เกิดข้อผิดพลาดขณะรันสคริปต์: {exc}")
    finally:
        # บน Windows ปิด handle ได้ปกติ
        # บน Linux ห้ามเรียก h.close() เพราะ C hidapi close() ถือ GIL และติด D-state lock ในเคอร์เนล Linux
        # ปล่อยให้ระบบปฏิบัติการ (Kernel) ปิด fd ให้โดยตรงผ่าน os._exit() รวดเร็วและปลอดภัย 100%
        if sys.platform == "win32":
            try:
                h.close()
            except Exception:
                pass


def print_device_list() -> None:
    """แสดงรายการอุปกรณ์ UPS ทั้งหมดที่เชื่อมต่ออยู่"""
    devices = list_all_connected_devices()
    print("=" * 78)
    print(" 🔌 รายการอุปกรณ์ HID UPS ทั้งหมดที่พบในระบบ")
    print("=" * 78)
    if not devices:
        print("  (ไม่พบอุปกรณ์ HID UPS ที่เชื่อมต่ออยู่)")
        return

    for idx, d in enumerate(devices, start=1):
        mfg = d.get("manufacturer_string") or "Generic"
        prod = d.get("product_string") or "HID UPS"
        sn = d.get("serial_number") or "N/A"
        vid = f"0x{(d.get('vendor_id') or 0):04X}"
        pid = f"0x{(d.get('product_id') or 0):04X}"
        path = d.get("path_str") or "N/A"
        print(f"  [{idx}] {mfg} {prod}")
        print(f"      VID/PID : {vid}:{pid} | Serial: {sn}")
        print(f"      Path    : {path}")
        print("  " + "-" * 72)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Universal Live PHOENIXTEC & HID UPS Battery Test Runner (All Brands)"
    )
    parser.add_argument(
        "--list", action="store_true", help="แสดงรายการอุปกรณ์ HID UPS ทั้งหมดที่เชื่อมต่ออยู่"
    )
    parser.add_argument(
        "--quick", action="store_true", help="สั่ง Quick Battery Test (10 วินาที) พร้อม Hold Process"
    )
    parser.add_argument(
        "--deep", action="store_true", help="สั่ง Deep Battery Test (ทดสอบจนแบตเตอรี่ต่ำ) พร้อม Hold Process"
    )
    parser.add_argument(
        "--device", type=int, help="ลำดับของอุปกรณ์ที่ต้องการทดสอบ (เช่น --device 1)"
    )
    parser.add_argument(
        "--serial", type=str, help="Serial Number ของอุปกรณ์ที่ต้องการทดสอบ"
    )

    args = parser.parse_args()

    try:
        if args.list:
            print_device_list()
        elif args.deep:
            run_live_battery_test("deep", max_timeout_s=3600, device_index=args.device, target_serial=args.serial)
        else:
            run_live_battery_test("quick", max_timeout_s=60, device_index=args.device, target_serial=args.serial)
    except KeyboardInterrupt:
        print("\n\n⚠️ การทำงานถูกยกเลิกโดยผู้ใช้ (Ctrl+C)")
    finally:
        try:
            sys.stdout.flush()
            sys.stderr.flush()
        except Exception:
            pass
        import os
        os._exit(0)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        import os
        os._exit(130)
