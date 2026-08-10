#!/usr/bin/env python3
"""
tools/unit/test_2000d_exact_lengths.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
ทดสอบส่ง Q1 Command ("T\r", "TL\r", "CT\r") ผ่าน libusb0 Direct USB Control Transfer
ด้วยความยาว Buffer ขนาดจริง (2 Bytes, 3 Bytes, 8 Bytes) โดยไม่เติม Zero 64 Bytes
เพื่อทดสอบว่าไมโครคอนโทรลเลอร์ของ PPC 2000D สวิตช์ Relay และส่งเสียง Beep จริงหรือไม่
"""

from __future__ import annotations

import ctypes
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

dll_path = r"C:\Program Files\WinpowerG2\libUSB_driver\amd64\libusb0.dll"
if not Path(dll_path).exists():
    print(f"❌ ไม่พบ {dll_path}")
    sys.exit(1)

libusb = ctypes.CDLL(dll_path)
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
target_h = None
target_name = ""

while bus:
    dev = bus.contents.devices
    while dev:
        desc = dev.contents.descriptor
        if desc.idVendor in (0x06DA, 0x0001):
            h_tmp = libusb.usb_open(dev)
            if h_tmp:
                str_buf = ctypes.create_string_buffer(256)
                ser_str = ""
                prod_str = ""
                if desc.iSerialNumber > 0 and libusb.usb_get_string_simple(h_tmp, 4, str_buf, 256) > 0:
                    ser_str = str_buf.value.decode("utf-8", errors="ignore").strip()
                if desc.iProduct > 0 and libusb.usb_get_string_simple(h_tmp, 2, str_buf, 256) > 0:
                    prod_str = str_buf.value.decode("utf-8", errors="ignore").strip()
                if "000000000" in ser_str or desc.bcdDevice == 3 or "mec" in prod_str.lower():
                    target_h = h_tmp
                    target_name = f"PPC 2000D (SN: {ser_str}, release: {desc.bcdDevice})"
                    break
                libusb.usb_close(h_tmp)
        dev = dev.contents.next
    if target_h:
        break
    bus = bus.contents.next

if not target_h:
    print("❌ ไม่พบอุปกรณ์ PPC 2000D ผ่าน libusb0")
    sys.exit(1)

print(f"✅ เชื่อมต่อ {target_name} ผ่าน libusb0 สำเร็จ!")

exact_tests = [
    ("Q1 'T\\r' 2-bytes (wValue=0x0200 Output)", 0x0200, b"T\r"),
    ("Q1 'T\\r' 2-bytes (wValue=0x0300 Feature)", 0x0300, b"T\r"),
    ("Q1 'T\\r' 2-bytes (wValue=0x0302 Feature)", 0x0302, b"T\r"),
    ("Q1 'T\\r' 2-bytes (wValue=0x0303 Feature)", 0x0303, b"T\r"),
    ("Q1 'T' 1-byte (wValue=0x0200 Output)", 0x0200, b"T"),
    ("Q1 'T' 1-byte (wValue=0x0300 Feature)", 0x0300, b"T"),
    ("Q1 'T' 1-byte (wValue=0x0302 Feature)", 0x0302, b"T"),
    ("Q1 'T\\r' 8-bytes padded [0x00, T, \\r, 0..]", 0x0200, bytes([0x00] + list(b"T\r") + [0]*5)),
    ("Q1 'T\\r' 8-bytes padded [0x02, T, \\r, 0..]", 0x0302, bytes([0x02] + list(b"T\r") + [0]*5)),
    ("Q1 'T\\r' 8-bytes padded [0x03, T, \\r, 0..]", 0x0303, bytes([0x03] + list(b"T\r") + [0]*5)),
    ("Q1 'T' 8-bytes padded [0x00, T, 0..]", 0x0200, bytes([0x00] + list(b"T") + [0]*6)),
    ("Byte Code 2-bytes [0x03, 0x01]", 0x0303, bytes([0x03, 0x01])),
    ("Byte Code 2-bytes [0x24, 0x01]", 0x0324, bytes([0x24, 0x01])),
]

print("\n🚀 เริ่มทดสอบส่ง Exact Buffer Lengths (เว้นระยะ 2.5 วินาทีโปรดฟังเสียง Relay / Beep)...\n")

for label, wval, p_bytes in exact_tests:
    buf = ctypes.create_string_buffer(p_bytes)
    # bmRequestType = 0x21 (Host to Device | Class | Interface), bRequest = 0x09 (SET_REPORT)
    ret = libusb.usb_control_msg(target_h, 0x21, 0x09, wval, 0, buf, len(p_bytes), 1000)
    print(f"  • {label:<50} ➔ ret={ret}")
    time.sleep(2.5)

libusb.usb_close(target_h)
print("\n✅ ทดสอบเสร็จสิ้นทั้งหมด")
