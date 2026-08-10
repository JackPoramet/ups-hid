#!/usr/bin/env python3
"""
tools/unit/test_call_libusb_win_dll.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
เรียกใช้งาน DLL ที่ Winpower G2 ใช้โดยตรง: libUSB_Win.dll (Java_santak_lib_LibUsb_*)
เพื่อค้นหาอุปกรณ์ เปิด USB Handle และส่ง setReport คำสั่ง Battery Test ("T\r")
"""

from __future__ import annotations

import ctypes
import sys
import time
from pathlib import Path

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

dll_path = r"C:\Program Files\WinpowerG2\libUSB_Win.dll"
if not Path(dll_path).exists():
    print(f"❌ ไม่พบ {dll_path}")
    sys.exit(1)

print(f"✅ โหลด Native DLL: {dll_path}")
dll = ctypes.CDLL(dll_path)

# กำหนด Signatures สำหรับ JNI C Functions (ส่ง JNIEnv*=NULL, jclass=NULL)
findUsb = dll.Java_santak_lib_LibUsb_findUsb
findUsb.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
findUsb.restype = ctypes.c_int

openUsb = dll.Java_santak_lib_LibUsb_openUsb
openUsb.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int]
openUsb.restype = ctypes.c_uint64

getVendorId = dll.Java_santak_lib_LibUsb_getVendorId
getVendorId.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint64]
getVendorId.restype = ctypes.c_int

getProductId = dll.Java_santak_lib_LibUsb_getProductId
getProductId.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint64]
getProductId.restype = ctypes.c_int

close = dll.Java_santak_lib_LibUsb_close
close.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint64]
close.restype = ctypes.c_int

# เรียก findUsb
count = findUsb(None, None)
print(f"🔍 พบอุปกรณ์ USB ทั้งหมดผ่าน libUSB_Win.dll: {count} เครื่อง")

target_h = None
target_idx = -1

for idx in range(count):
    h = openUsb(None, None, idx)
    if h:
        vid = getVendorId(None, None, h)
        pid = getProductId(None, None, h)
        print(f"  [{idx}] Handle=0x{h:X} | VID=0x{vid:04X} PID=0x{pid:04X}")
        if vid == 0x06DA and pid == 0xFFFF:
            target_h = h
            target_idx = idx

if not target_h:
    print("❌ ไม่พบอุปกรณ์ PPC 2000D ผ่าน libUSB_Win.dll")
    sys.exit(1)

print(f"\n🚀 เลือกอุปกรณ์ PPC 2000D ลำดับที่ [{target_idx}] (Handle=0x{target_h:X})")
print("⚡ เตรียมส่ง setReport คำสั่ง Battery Test 'T\\r'...")

# ลองสแกนหาวิธีส่ง setReport
# setReport(env, cls, handle, reportType, reportId, buffer_ptr, length)
setReport = dll.Java_santak_lib_LibUsb_setReport

# ทดสอบรูปแบบ argtypes ต่างๆ
cmd_bytes = b"T\r\x00\x00\x00\x00\x00\x00"
buf_ptr = ctypes.create_string_buffer(cmd_bytes)

print("\n🚀 เริ่มทดสอบยิงคำสั่ง setReport ผ่าน libUSB_Win.dll Native (ฟังเสียง Relay / Beep)...\n")

# reportType: 2 = Feature Report, 1 = Output Report
for r_type in [2, 1, 3]:
    for r_id in [0x00, 0x01, 0x02, 0x03, 0x24]:
        try:
            # setReport(NULL, NULL, handle, r_type, r_id, buf_ptr, 8)
            ret = setReport(None, None, ctypes.c_uint64(target_h), ctypes.c_int(r_type), ctypes.c_int(r_id), buf_ptr, ctypes.c_int(8))
            print(f"  • r_type={r_type}, r_id=0x{r_id:02X} ➔ ret={ret}")
        except Exception as e:
            print(f"  • r_type={r_type}, r_id=0x{r_id:02X} ➔ Exception: {e}")
        time.sleep(1.5)

close(None, None, ctypes.c_uint64(target_h))
print("\n✅ ปิด Handle และทดสอบเสร็จสิ้นทั้งหมด")
