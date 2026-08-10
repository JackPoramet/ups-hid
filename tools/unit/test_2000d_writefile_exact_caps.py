#!/usr/bin/env python3
"""
tools/unit/test_2000d_writefile_exact_caps.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
แกะการทำงานของ jusb.dll: ดึง OutputReportByteLength ผ่าน HidP_GetCaps บน Windows
จัดขนาด Buffer ให้ตรง 100% กับข้อกำหนดของ HID Class Driver แล้วส่งคำสั่ง Q1 ("T\r") ผ่าน WriteFile Direct Handle
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import sys
import time
from pathlib import Path

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

from core_hid_ups import list_ups_devices
from win32_hid_wrapper import normalize_path

GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
OPEN_EXISTING = 3
INVALID_HANDLE_VALUE = -1

kernel32 = ctypes.windll.kernel32
hid_dll = ctypes.windll.hid

CreateFileA = kernel32.CreateFileA
CreateFileA.argtypes = [wintypes.LPCSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
CreateFileA.restype = wintypes.HANDLE

WriteFile = kernel32.WriteFile
WriteFile.argtypes = [wintypes.HANDLE, wintypes.LPCVOID, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), wintypes.LPVOID]
WriteFile.restype = wintypes.BOOL

CloseHandle = kernel32.CloseHandle
CloseHandle.argtypes = [wintypes.HANDLE]
CloseHandle.restype = wintypes.BOOL

class HIDP_CAPS(ctypes.Structure):
    _fields_ = [
        ("Usage", wintypes.USHORT),
        ("UsagePage", wintypes.USHORT),
        ("InputReportByteLength", wintypes.USHORT),
        ("OutputReportByteLength", wintypes.USHORT),
        ("FeatureReportByteLength", wintypes.USHORT),
        ("Reserved", wintypes.USHORT * 17),
        ("NumberNumberControlIDs", wintypes.USHORT),
        ("NumberInputValueCaps", wintypes.USHORT),
        ("NumberInputDataIndices", wintypes.USHORT),
        ("NumberOutputValueCaps", wintypes.USHORT),
        ("NumberOutputDataIndices", wintypes.USHORT),
        ("NumberFeatureValueCaps", wintypes.USHORT),
        ("NumberFeatureDataIndices", wintypes.USHORT),
    ]

HidD_GetPreparsedData = hid_dll.HidD_GetPreparsedData
HidD_GetPreparsedData.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.LPVOID)]
HidD_GetPreparsedData.restype = wintypes.BOOL

HidD_FreePreparsedData = hid_dll.HidD_FreePreparsedData
HidD_FreePreparsedData.argtypes = [wintypes.LPVOID]
HidD_FreePreparsedData.restype = wintypes.BOOL

HidP_GetCaps = hid_dll.HidP_GetCaps
HidP_GetCaps.argtypes = [wintypes.LPVOID, ctypes.POINTER(HIDP_CAPS)]
HidP_GetCaps.restype = wintypes.ULONG

devices = list_ups_devices(target_vid=None)
target = None

for d in devices:
    sn = str(d.get("serial_number") or "")
    path = str(d.get("path_str") or "")
    rel = d.get("release_number")
    if "000000000" in sn or "19f55223" in path or rel == 3:
        target = d
        break

if not target:
    print("❌ ไม่พบอุปกรณ์ PPC 2000D")
    sys.exit(1)

dev_path = normalize_path(target.get("path_str"))
print(f"✅ เลือกอุปกรณ์ PPC 2000D: {dev_path}")

path_bytes = dev_path.encode("ascii") if isinstance(dev_path, str) else dev_path

# เปิด handle แบบ Read/Write Shared
h_dev = CreateFileA(path_bytes, GENERIC_READ | GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_WRITE, None, OPEN_EXISTING, 0, None)
if h_dev == INVALID_HANDLE_VALUE or h_dev == 0:
    # ลองเปิดแบบ 0 Access Mode
    h_dev = CreateFileA(path_bytes, 0, FILE_SHARE_READ | FILE_SHARE_WRITE, None, OPEN_EXISTING, 0, None)

if h_dev == INVALID_HANDLE_VALUE or h_dev == 0:
    print("❌ ไม่สามารถเปิด CreateFileA handle ได้")
    sys.exit(1)

preparsed_data = wintypes.LPVOID()
caps = HIDP_CAPS()

if HidD_GetPreparsedData(h_dev, ctypes.byref(preparsed_data)):
    if HidP_GetCaps(preparsed_data, ctypes.byref(caps)) == 0x00110000: # HIDP_STATUS_SUCCESS
        print(f"✅ ดึง Caps สำเร็จ:")
        print(f"   • InputReportByteLength  : {caps.InputReportByteLength}")
        print(f"   • OutputReportByteLength : {caps.OutputReportByteLength}")
        print(f"   • FeatureReportByteLength: {caps.FeatureReportByteLength}")
    HidD_FreePreparsedData(preparsed_data)

out_len = caps.OutputReportByteLength or 9

print(f"\n🚀 เริ่มทดสอบส่ง Q1 Command 'T\\r' ผ่าน WriteFile ด้วย Buffer ขนาด {out_len} Bytes...")

# ทดสอบ Report ID ต่างๆ (0x00, 0x01, 0x02, 0x03, 0x24)
test_payloads = [
    ("Q1 'T\\r' (Report ID 0x00)", 0x00, b"T\r"),
    ("Q1 'T\\r' (Report ID 0x01)", 0x01, b"T\r"),
    ("Q1 'T\\r' (Report ID 0x02)", 0x02, b"T\r"),
    ("Q1 'T\\r' (Report ID 0x03)", 0x03, b"T\r"),
    ("Q1 'T\\r' (Report ID 0x24)", 0x24, b"T\r"),
    ("Q1 'T' (Report ID 0x00)", 0x00, b"T"),
    ("Q1 'T' (Report ID 0x02)", 0x02, b"T"),
]

written = wintypes.DWORD(0)

try:
    for label, rid, cmd_b in test_payloads:
        # สร้าง Buffer ตามความยาว out_len เป๊ะๆ
        buf_data = bytearray(out_len)
        buf_data[0] = rid
        for i, b in enumerate(cmd_b):
            if i + 1 < out_len:
                buf_data[i + 1] = b
        
        c_buf = ctypes.create_string_buffer(bytes(buf_data), out_len)
        res = WriteFile(h_dev, c_buf, out_len, ctypes.byref(written), None)
        err = kernel32.GetLastError() if not res else 0
        
        print(f"  • {label:<35} ➔ WriteFile={bool(res)} (written={written.value}, WinError={err})")
        time.sleep(2.0)

finally:
    CloseHandle(h_dev)

print("\n✅ ทดสอบเสร็จสิ้นทั้งหมด")
