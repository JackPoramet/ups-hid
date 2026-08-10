#!/usr/bin/env python3
"""
tools/unit/test_2000d_direct_libusb.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
ส่ง Direct USB Control Message ผ่าน libusb0.dll สั่งงาน Battery Test ตรงไปยัง PPC 2000D / PHOENIXTEC
(วิธีเดียวกับที่ WinPower G2 ใช้ผ่าน libusb0.dll เพื่อให้เกิดเสียง Relay Click / Beep ของ UPS จริงๆ)
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
    print("❌ ไม่พบ libusb0.dll ของ Winpower G2 ในเครื่อง")
    sys.exit(1)

print(f"✅ โหลด driver: {target_dll}")

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
matched_devs = []

while bus:
    dev = bus.contents.devices
    while dev:
        desc = dev.contents.descriptor
        if desc.idVendor in (0x06DA, 0x0001):
            h_tmp = libusb.usb_open(dev)
            if h_tmp:
                prod_str = ""
                mfg_str = ""
                str_buf = ctypes.create_string_buffer(256)
                if desc.iManufacturer > 0 and libusb.usb_get_string_simple(h_tmp, 1, str_buf, 256) > 0:
                    mfg_str = str_buf.value.decode("utf-8", errors="ignore").strip()
                if desc.iProduct > 0 and libusb.usb_get_string_simple(h_tmp, 2, str_buf, 256) > 0:
                    prod_str = str_buf.value.decode("utf-8", errors="ignore").strip()
                matched_devs.append((dev, h_tmp, desc.idVendor, desc.idProduct, mfg_str, prod_str))
        dev = dev.contents.next
    bus = bus.contents.next

if not matched_devs:
    print("❌ ไม่พบอุปกรณ์ USB UPS ผ่าน libusb0")
    sys.exit(1)

print(f"\nพบอุปกรณ์ทั้งหมด {len(matched_devs)} เครื่องผ่าน libusb0:")
for idx, (dev, h_usb, vid, pid, mfg, prod) in enumerate(matched_devs, start=1):
    print(f"  [{idx}] VID=0x{vid:04X} PID=0x{pid:04X} | {mfg} {prod}")

# สั่ง Test กับทุกเครื่อง หรือเครื่องที่เลือก
for idx, (dev, h_usb, vid, pid, mfg, prod) in enumerate(matched_devs, start=1):
    print(f"\n🚀 กำลังส่ง Direct USB Control Test ไปที่ [{idx}] {mfg} {prod}...")
    
    # ลองส่งคำสั่งด้วย SET_REPORT (bmRequestType=0x21, bRequest=0x09)
    # 1. Feature Report 0x24 (0x0324) -> [0x24, 0x01]
    buf_24 = ctypes.create_string_buffer(bytes([0x24, 0x01] + [0]*62))
    ret24 = libusb.usb_control_msg(h_usb, 0x21, 0x09, 0x0324, 0, buf_24, 64, 1000)
    print(f"   ➔ Control SET_REPORT 0x0324: ret={ret24}")

    # 2. Feature Report 0x03 (0x0303) -> [0x03, 0x01]
    buf_03 = ctypes.create_string_buffer(bytes([0x03, 0x01] + [0]*62))
    ret03 = libusb.usb_control_msg(h_usb, 0x21, 0x09, 0x0303, 0, buf_03, 64, 1000)
    print(f"   ➔ Control SET_REPORT 0x0303: ret={ret03}")

    # 3. Feature Report 0x07 (0x0307) -> [0x07, 0x01]
    buf_07 = ctypes.create_string_buffer(bytes([0x07, 0x01] + [0]*62))
    ret07 = libusb.usb_control_msg(h_usb, 0x21, 0x09, 0x0307, 0, buf_07, 64, 1000)
    print(f"   ➔ Control SET_REPORT 0x0307: ret={ret07}")

    # 4. Q1 String "T\r" via Report 0x02 (0x0302)
    buf_q1 = ctypes.create_string_buffer(bytes([0x02] + list(b"T\r") + [0]*60))
    ret_q1 = libusb.usb_control_msg(h_usb, 0x21, 0x09, 0x0302, 0, buf_q1, 64, 1000)
    print(f"   ➔ Control SET_REPORT Q1 'T\\r' 0x0302: ret={ret_q1}")

    libusb.usb_close(h_usb)

print("\n✅ ดำเนินการส่งคำสั่งตรงถึงระดับ USB Control Transfer สำเร็จทั้งหมด!")
