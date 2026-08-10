#!/usr/bin/env python3
"""
tools/unit/test_2000d_debug_all_channels.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
ดีบักช่องทาง Feature Report ของ PPC 2000D ระหว่าง Battery Test

HID Usage 0084:0058 (Power Device > Test) ค่าตามมาตรฐาน USB HID Power Device:
  1 = No Test Initiated
  2 = Test In Progress
  3 = No Test Available  
  4 = Test Passed (Deep discharge - battery good)
  5 = Test Failed (Deep discharge - battery needs replacement)
  6 = Test Passed (Quick Test - battery good)
"""

import ctypes
import os
import struct
import sys
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

TEST_NAMES = {
    0: "Idle (0)",
    1: "No Test Initiated (1)",
    2: "⚡ Test In Progress (2)",
    3: "No Test Available (3)",
    4: "✅ Deep Test PASSED (4)",
    5: "❌ Deep Test FAILED (5)",
    6: "✅ Quick Test PASSED (6)",
}


def is_admin() -> bool:
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def to_hex(data) -> str:
    if data is None:
        return "None"
    return " ".join(f"{b:02X}" for b in data)


def safe_read_feature(h, rid, size=8):
    try:
        data = h.get_feature_report(rid, size)
        return bytes(data) if data else None
    except Exception:
        return None


def main():
    print("=" * 90)
    print(" 🔍 PPC 2000D Battery Test Monitor (Feature Report Only — No h.read)")
    print("=" * 90)

    if not is_admin():
        script = os.path.abspath(sys.argv[0])
        ret = ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, f'"{script}"', None, 1)
        if ret > 32:
            sys.exit(0)
        print("❌ ต้องรันในสิทธิ์ Admin")
        return

    import hid

    devices = hid.enumerate(0x06DA, 0xFFFF)
    if not devices:
        print("❌ ไม่พบ PPC 2000D")
        return

    h = hid.device()
    h.open_path(devices[0]['path'])
    print(f"✅ เปิดพอร์ต HID สำเร็จ\n")

    FEATURE_RIDS = [0x01, 0x06, 0x07, 0x24, 0x2D, 0x42]

    try:
        # ============================================================
        # PHASE 1: Baseline
        # ============================================================
        print("=" * 90)
        print(" 📡 PHASE 1: Baseline (ก่อนสั่ง Test)")
        print("=" * 90)

        baseline = {}
        for rid in FEATURE_RIDS:
            data = safe_read_feature(h, rid)
            baseline[rid] = data
            extra = ""
            if rid == 0x01 and data and len(data) >= 8:
                extra = f"  AC={data[1]} Chrg={data[3]} Disch={data[4]} Good={data[5]}"
            elif rid == 0x06 and data and len(data) >= 4:
                extra = f"  Batt={data[1]}% Runtime={struct.unpack_from('<H', data, 2)[0]}s"
            elif rid == 0x07 and data and len(data) >= 4:
                extra = f"  Load={data[1]}% OutV_raw={struct.unpack_from('<H', data, 2)[0]}"
            elif rid == 0x24 and data and len(data) >= 2:
                tv = data[1]
                extra = f"  Test={tv} → {TEST_NAMES.get(tv, f'Unknown({tv})')}"
            elif rid == 0x42 and data and len(data) >= 5:
                freq = struct.unpack_from("<H", data, 1)[0]
                volt = struct.unpack_from("<H", data, 3)[0]
                extra = f"  Freq={freq/10.0}Hz OutV_raw={volt}"
            print(f"   0x{rid:02X}: {to_hex(data)}{extra}")

        # ============================================================
        # PHASE 2: ส่ง Quick Test
        # ============================================================
        print("\n" + "=" * 90)
        print(" ⚡ PHASE 2: ส่งคำสั่ง Quick Test")
        print("=" * 90)

        payload = b"\x24\x01\x00\x00\x00\x00\x00\x00"
        res = h.send_feature_report(payload)
        print(f"   send_feature_report → {res} bytes")
        if res > 0:
            print("   ✅ ส่งสำเร็จ — ฟังเสียง Relay Click / Beep")

        # อ่าน 0x24 ทันทีหลังส่ง
        time.sleep(0.3)
        r24_after = safe_read_feature(h, 0x24)
        if r24_after and len(r24_after) >= 2:
            tv = r24_after[1]
            print(f"   0x24 ทันทีหลังส่ง: {to_hex(r24_after)} → {TEST_NAMES.get(tv, f'Unknown({tv})')}")

        # ============================================================
        # PHASE 3: Monitor 30 วินาที
        # ============================================================
        print("\n" + "=" * 90)
        print(" 📊 PHASE 3: Monitor ทุก 1 วินาที (ดู Raw Hex + ค่าที่เปลี่ยน)")
        print("=" * 90)

        header = f" {'Sec':>4} | {'Report 0x01 (Raw)':^23} | {'Report 0x06 (Raw)':^17} | {'Report 0x07 (Raw)':^17} | {'0x24':>4} | {'Test Status':^25}"
        print(header)
        print("-" * len(header))

        MAX_SEC = 30
        start = time.time()
        prev_24_val = baseline.get(0x24, b"\x24\x00")[1] if baseline.get(0x24) else 0

        for tick in range(MAX_SEC):
            time.sleep(1.0)
            elapsed = int(time.time() - start)

            r01 = safe_read_feature(h, 0x01)
            r06 = safe_read_feature(h, 0x06)
            r07 = safe_read_feature(h, 0x07)
            r24 = safe_read_feature(h, 0x24)

            r01_hex = to_hex(r01) if r01 else "Error"
            r06_hex = to_hex(r06) if r06 else "Error"
            r07_hex = to_hex(r07) if r07 else "Error"

            test_val = r24[1] if r24 and len(r24) >= 2 else "?"
            test_name = TEST_NAMES.get(test_val, f"Unknown({test_val})") if isinstance(test_val, int) else "?"

            # ตรวจจับการเปลี่ยนแปลงของ 0x24
            changed_marker = ""
            if isinstance(test_val, int) and test_val != prev_24_val:
                changed_marker = f" ← CHANGED from {prev_24_val}!"
                prev_24_val = test_val

            print(
                f" {elapsed:4d} | {r01_hex:^23} | {r06_hex:^17} | {r07_hex:^17} | {str(test_val):>4} | {test_name}{changed_marker}"
            )

        # ============================================================
        # PHASE 4: สรุป
        # ============================================================
        print("\n" + "=" * 90)
        print(" 📊 PHASE 4: เปรียบเทียบ Baseline vs Final")
        print("=" * 90)

        for rid in FEATURE_RIDS:
            data = safe_read_feature(h, rid)
            prev = baseline.get(rid)
            changed = "SAME"
            if prev and data and prev != data:
                diffs = []
                for i in range(min(len(prev), len(data))):
                    if prev[i] != data[i]:
                        diffs.append(f"[{i}]:{prev[i]:02X}→{data[i]:02X}")
                changed = "CHANGED ⚠️ " + ", ".join(diffs)
            print(f"   0x{rid:02X}: Before={to_hex(prev)}  After={to_hex(data)}  {changed}")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        h.close()
        print("\n🔒 ปิดพอร์ต HID")


if __name__ == "__main__":
    main()
