#!/usr/bin/env python3
"""
tools/unit/test_2000d_payloads_libusb.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
ทดสอบส่ง Direct USB Control Transfer (libusb0.dll) หลากหลาย Payload ลายเซ็นต์ไปยัง PPC Offline UPS 2000D
เพื่อทดสอบว่า Payload รหัสใดกระตุ้นให้ Relay และเสียง Beep ของ 2000D ทำงานจริง
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
    ctypes.c_int,    # bmRequestType
    ctypes.c_int,    # bRequest
    ctypes.c_int,    # wValue
    ctypes.c_int,    # wIndex
    ctypes.c_char_p, # bytes
    ctypes.c_int,    # size
    ctypes.c_int,    # timeout
]
libusb.usb_control_msg.restype = ctypes.c_int

bus = libusb.usb_get_busses()
target_h = None
target_name = ""

while bus:
    dev = bus.contents.devices
    while dev:
        desc = dev.contents.descriptor
        if desc.idVendor == 0x06DA and desc.idProduct == 0xFFFF:
            h_tmp = libusb.usb_open(dev)
            if h_tmp:
                str_buf = ctypes.create_string_buffer(256)
                mfg_str = ""
                prod_str = ""
                if desc.iManufacturer > 0 and libusb.usb_get_string_simple(h_tmp, 1, str_buf, 256) > 0:
                    mfg_str = str_buf.value.decode("utf-8", errors="ignore").strip()
                if desc.iProduct > 0 and libusb.usb_get_string_simple(h_tmp, 2, str_buf, 256) > 0:
                    prod_str = str_buf.value.decode("utf-8", errors="ignore").strip()
                combined = f"{mfg_str} {prod_str}".lower()
                if "offline" in combined or "2000" in combined or "ppc" in combined:
                    target_h = h_tmp
                    target_name = f"{mfg_str} {prod_str}"
                    break
                libusb.usb_close(h_tmp)
        dev = dev.contents.next
    if target_h:
        break
    bus = bus.contents.next

if not target_h:
    print("❌ ไม่พบอุปกรณ์ PPC Offline UPS 2000D ผ่าน libusb0")
    sys.exit(1)

print(f"✅ เชื่อมต่อสำเร็จ: {target_name}")

test_payloads = [
    ("Report 0x24 [0x24, 0x01]", 0x0324, [0x24, 0x01]),
    ("Report 0x24 [0x24, 0x02]", 0x0324, [0x24, 0x02]),
    ("Report 0x24 [0x24, ord('T'), ord('\\r')]", 0x0324, [0x24, ord('T'), ord('\r')]),
    ("Report 0x10 [0x10, 0x01]", 0x0310, [0x10, 0x01]),
    ("Report 0x01 [0x01, 0x01]", 0x0301, [0x01, 0x01]),
    ("Report 0x06 [0x06, 0x01]", 0x0306, [0x06, 0x01]),
    ("Report 0x09 [0x09, 0x01]", 0x0309, [0x09, 0x01]),
    ("Report 0x0B [0x0B, 0x01]", 0x030B, [0x0B, 0x01]),
]

print("\n🚀 เริ่มทดสอบส่ง Direct USB Control Transfer (เว้นระยะ 2 วินาทีต่อชุด)...\n")
for name, wval, p_bytes in test_payloads:
    buf = ctypes.create_string_buffer(bytes(p_bytes + [0]*(64 - len(p_bytes))))
    ret = libusb.usb_control_msg(target_h, 0x21, 0x09, wval, 0, buf, 64, 1000)
    print(f"  • Sending {name:<40} ➔ ret={ret}")
    time.sleep(2.0)

libusb.usb_close(target_h)
print("\n✅ การทดสอบเสร็จสิ้นทั้งหมด")
