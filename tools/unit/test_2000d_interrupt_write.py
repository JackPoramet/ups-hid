#!/usr/bin/env python3
"""
tools/unit/test_2000d_interrupt_write.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
ทดสอบส่ง Interrupt Write (usb_interrupt_write) ไปยัง Endpoints (0x01, 0x02, 0x03) ของ PPC 2000D
เพื่อทดสอบการส่ง Q1 String Command ("T\r", "T", "TL\r") ตรงเข้า USB Hardware Endpoint ให้เกิดเสียง Relay Click & Beep
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

libusb.usb_set_configuration.argtypes = [ctypes.c_void_p, ctypes.c_int]
libusb.usb_set_configuration.restype = ctypes.c_int

libusb.usb_claim_interface.argtypes = [ctypes.c_void_p, ctypes.c_int]
libusb.usb_claim_interface.restype = ctypes.c_int

libusb.usb_release_interface.argtypes = [ctypes.c_void_p, ctypes.c_int]
libusb.usb_release_interface.restype = ctypes.c_int

libusb.usb_interrupt_write.argtypes = [
    ctypes.c_void_p, # dev handle
    ctypes.c_int,    # ep (endpoint)
    ctypes.c_char_p, # bytes
    ctypes.c_int,    # size
    ctypes.c_int,    # timeout
]
libusb.usb_interrupt_write.restype = ctypes.c_int

libusb.usb_bulk_write.argtypes = [
    ctypes.c_void_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_int
]
libusb.usb_bulk_write.restype = ctypes.c_int

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
                ser_str = ""
                if desc.iSerialNumber > 0 and libusb.usb_get_string_simple(h_tmp, 4, str_buf, 256) > 0:
                    ser_str = str_buf.value.decode("utf-8", errors="ignore").strip()
                if "000000000" in ser_str or desc.bcdDevice == 3:
                    target_h = h_tmp
                    target_name = f"PPC 2000D (release: {desc.bcdDevice})"
                    break
                libusb.usb_close(h_tmp)
        dev = dev.contents.next
    if target_h:
        break
    bus = bus.contents.next

if not target_h:
    print("❌ ไม่พบอุปกรณ์ PPC 2000D ผ่าน libusb0")
    sys.exit(1)

print(f"✅ เชื่อมต่อ {target_name} สำเร็จ!")

libusb.usb_set_configuration(target_h, 1)
libusb.usb_claim_interface(target_h, 0)

test_payloads = [
    ("Q1 Command 'T\\r'", b"T\r"),
    ("Q1 Command 'T'", b"T"),
    ("Report ID 0x00 + 'T\\r'", bytes([0x00] + list(b"T\r"))),
    ("Report ID 0x02 + 'T\\r'", bytes([0x02] + list(b"T\r"))),
    ("Byte Code [0x03, 0x01]", bytes([0x03, 0x01])),
    ("Byte Code [0x24, 0x01]", bytes([0x24, 0x01])),
]

endpoints = [0x01, 0x02, 0x81, 0x00]

print("\n🚀 เริ่มทดสอบส่ง Interrupt OUT Write (โปรดฟังเสียง Relay Click / Beep)...\n")

for ep in endpoints:
    print(f"--- Endpoint 0x{ep:02X} ---")
    for label, raw_bytes in test_payloads:
        # Padded to 8 bytes or 64 bytes
        buf8 = ctypes.create_string_buffer(bytes(raw_bytes + bytes(8 - len(raw_bytes))))
        ret_iw8 = libusb.usb_interrupt_write(target_h, ep, buf8, len(buf8), 1000)
        ret_bw8 = libusb.usb_bulk_write(target_h, ep, buf8, len(buf8), 1000)
        print(f"  • EP=0x{ep:02X} {label:<30} ➔ IntWrite={ret_iw8}, BulkWrite={ret_bw8}")
        time.sleep(1.5)

libusb.usb_release_interface(target_h, 0)
libusb.usb_close(target_h)
print("\n✅ การทดสอบเสร็จสิ้นทั้งหมด")
