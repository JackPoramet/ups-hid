#!/usr/bin/env python3
"""
tools/unit/test_2000d_hid_feature_24.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
ทดสอบส่ง Feature Report 0x24 (Usage: 0084:0058 Power Device > Test)
ตาม HID Descriptor จริงของ PPC 2000D ผ่านทั้ง hidapi และ libusb0.dll Control Transfer (wValue = 0x0324)

Feature Report 0x24 Schema:
  - Byte 0: 0x24 (Report ID)
  - Byte 1: 0x01 (Quick Test), 0x02 (Deep Test), 0x03 (Cancel Test)
  - Byte 2..7: 0x00 (Padding 6 Bytes)
"""

import ctypes
import os
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

LIBUSB0_DLL = Path(r"C:\Program Files\WinpowerG2\libUSB_driver\amd64\libusb0.dll")
if not LIBUSB0_DLL.exists():
    LIBUSB0_DLL = Path(r"C:\Windows\System32\libusb0.dll")

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
    ("num_children", ctypes.c_uint8),
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

def is_admin() -> bool:
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False

def test_feature_24():
    print("==============================================================================")
    print(" 🎯 PPC 2000D HID Feature Report 0x24 (Power Device > Test) Trigger")
    print("==============================================================================")

    if not is_admin():
        print("🔒 [UAC] ขอยกระดับสิทธิ์ Administrator...")
        script = os.path.abspath(sys.argv[0])
        ret = ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, f'"{script}"', None, 1)
        if ret > 32:
            sys.exit(0)
        else:
            print("❌ ไม่ได้รับสิทธิ์ Admin")
            return

    # ------------------------------------------------------------------
    # ส่งคำสั่ง + Monitor Loop ตรวจจับการจบ Test
    # ------------------------------------------------------------------
    import hid
    import struct

    devices = hid.enumerate(0x06DA, 0xFFFF)
    if not devices:
        print("❌ ไม่พบอุปกรณ์ PPC 2000D (VID 0x06DA PID 0xFFFF)")
        return

    dev_path = devices[0]['path']
    print(f"✅ พบพอร์ต HID: {dev_path}")
    h = hid.device()
    h.open_path(dev_path)
    print("✅ เปิดพอร์ต HID สำเร็จ!")

    try:
        # --- อ่าน Baseline ก่อนสั่ง Test ---
        print("\n📡 อ่านค่า Baseline ก่อนสั่ง Test...")
        r01 = h.get_feature_report(0x01, 8)
        r06 = h.get_feature_report(0x06, 8)
        r07 = h.get_feature_report(0x07, 8)
        r24 = h.get_feature_report(0x24, 8)

        if r01 and len(r01) >= 8:
            print(f"   Report 0x01: ACPresent={r01[1]} Charging={r01[3]} Discharging={r01[4]} Good={r01[5]}")
        if r06 and len(r06) >= 4:
            batt_pct = r06[1]
            runtime = struct.unpack_from("<H", bytes(r06), 2)[0]
            print(f"   Report 0x06: Battery={batt_pct}% Runtime={runtime}s")
        if r07 and len(r07) >= 4:
            load = r07[1]
            out_v_raw = struct.unpack_from("<H", bytes(r07), 2)[0]
            print(f"   Report 0x07: Load={load}% OutputV_raw={out_v_raw}")
        if r24 and len(r24) >= 2:
            print(f"   Report 0x24: Test={r24[1]}")

        # บันทึก initial_val ของ 0x24 ก่อนส่งคำสั่ง (สำคัญมาก!)
        initial_val = r24[1] if r24 and len(r24) >= 2 else 6
        print(f"   >> initial_val = {initial_val} (จะรอดูว่า 0x24 เปลี่ยนจากค่านี้)")

        # --- ส่งคำสั่ง Quick Test ---
        print("\n⚡ ส่งคำสั่ง Quick Battery Test (Feature Report 0x24, value=0x01)...")
        payload = b"\x24\x01\x00\x00\x00\x00\x00\x00"
        res_hid = h.send_feature_report(payload)
        print(f"   --> send_feature_report Return Code: {res_hid} bytes written")

        if res_hid <= 0:
            print("   ❌ ส่งคำสั่งไม่สำเร็จ")
            return

        print("   🎉 ส่งคำสั่ง Quick Test สำเร็จ!")

        # --- Monitor Loop ---
        # Pattern จากข้อมูลจริง PPC 2000D:
        #   เริ่ม: 0x24 = 6 (ผลจาก Quick Test ครั้งก่อน)
        #   ระหว่าง Test: 0x24 เปลี่ยนเป็น 5 (ทดสอบอยู่)
        #   เสร็จ: 0x24 เปลี่ยนจาก 5 กลับเป็น 6 (หรือค่าอื่น)
        # ดังนั้น: ตรวจดู "mid_val" ที่ 0x24 เปลี่ยนเป็นหลังส่งคำสั่ง
        #          แล้วรอจนกว่า 0x24 เปลี่ยนออกจาก mid_val = Test เสร็จ
        print(f"\n{'='*90}")
        print(f" {'Sec':>4} | {'Batt%':>5} | {'Runtime':>7} | {'Load%':>5} | {'0x24':>4} | สถานะ")
        print(f"{'='*90}")

        start = time.time()
        mid_val = None   # ค่า 0x24 ระหว่าง Test (เช่น 5)
        MAX_WAIT = 35
        TEST_NAMES = {1: "No Test Initiated", 2: "Test In Progress", 3: "No Test Available", 4: "✅ Deep Test PASSED", 5: "❌ Deep Test FAILED", 6: "✅ Quick Test PASSED"}

        for tick in range(MAX_WAIT):
            time.sleep(1.0)
            elapsed = int(time.time() - start)

            r06 = h.get_feature_report(0x06, 8)
            r07 = h.get_feature_report(0x07, 8)
            r24 = h.get_feature_report(0x24, 8)

            batt = r06[1] if r06 and len(r06) >= 2 else "?"
            rt   = struct.unpack_from("<H", bytes(r06), 2)[0] if r06 and len(r06) >= 4 else "?"
            load = r07[1] if r07 and len(r07) >= 2 else "?"
            tv   = r24[1] if r24 and len(r24) >= 2 else None

            if tv is None:
                status = "⚠️ อ่านค่าไม่ได้"
            elif mid_val is None:
                # รอ 0x24 เปลี่ยนจาก initial_val ก่อน (= Test เริ่ม)
                if tv != initial_val:
                    mid_val = tv
                    status = f"🔋 Test เริ่มแล้ว! (0x24: {initial_val}→{tv})"
                else:
                    status = f"⏳ รอ Test เริ่ม... (0x24={tv})"
            elif tv == mid_val:
                # ยังอยู่ระหว่าง Test
                status = f"🔋 กำลังทดสอบ... (0x24={tv})"
            else:
                # 0x24 เปลี่ยนออกจาก mid_val = Test เสร็จ!
                status = f"✅ Test เสร็จ! (0x24: {mid_val}→{tv})"
                print(
                    f" {elapsed:4d} | {str(batt):>5} | {str(rt):>7} | {str(load):>5} | {str(tv):>4} | {status}"
                )
                print(f"\n{'='*90}")
                print(f" 🎉 การทดสอบแบตเตอรี่เสร็จสมบูรณ์! ณ วินาทีที่ {elapsed}")
                print(f" ผลลัพธ์ 0x24 = {tv}: {TEST_NAMES.get(tv, f'Unknown({tv})')}")
                print(f"{'='*90}")
                break

            print(
                f" {elapsed:4d} | {str(batt):>5} | {str(rt):>7} | {str(load):>5} | {str(tv):>4} | {status}"
            )

        else:
            print(f"\n⏰ ครบเวลา {MAX_WAIT} วินาที")
            if mid_val is None:
                print("   ⚠️ 0x24 ไม่เคยเปลี่ยนค่าเลย — อาจส่งคำสั่งไม่สำเร็จจริง หรือ Test เร็วมากก่อน Monitor เริ่ม")


        # --- อ่านค่าสรุปสุดท้าย ---
        print("\n📊 ค่าสรุปหลังการทดสอบ:")
        r01 = h.get_feature_report(0x01, 8)
        r06 = h.get_feature_report(0x06, 8)
        r07 = h.get_feature_report(0x07, 8)
        r24 = h.get_feature_report(0x24, 8)

        if r01 and len(r01) >= 8:
            print(f"   ACPresent={r01[1]}  Charging={r01[3]}  Discharging={r01[4]}  Good={r01[5]}  Overload={r01[7]}")
        if r06 and len(r06) >= 4:
            print(f"   Battery={r06[1]}%  Runtime={struct.unpack_from('<H', bytes(r06), 2)[0]}s")
        if r07 and len(r07) >= 4:
            print(f"   Load={r07[1]}%  OutputV_raw={struct.unpack_from('<H', bytes(r07), 2)[0]}")
        if r24 and len(r24) >= 2:
            t = r24[1]
            print(f"   Test={t} ({'idle' if t==0 else 'quick' if t==1 else 'deep' if t==2 else 'cancel' if t==3 else '?'})")

    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        h.close()
        print("\n🔒 ปิดพอร์ต HID เรียบร้อย")

if __name__ == "__main__":
    test_feature_24()

