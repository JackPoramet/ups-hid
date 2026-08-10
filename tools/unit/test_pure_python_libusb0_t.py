#!/usr/bin/env python3
"""
tools/unit/test_pure_python_libusb0_t.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
สคริปต์ Python ล้วน (Pure Python via ctypes + libusb0.dll 64-bit)
ไม่ผ่าน Java / ไม่ผ่าน Winpower Service / ไม่ผ่าน REST API

ส่งคำสั่ง USB Control Transfer ตรงไปที่ PPC 2000D (VID 0x06DA PID 0xFFFF):
  bmRequestType = 0x21 (SET_REPORT: Host to Device | Class | Interface)
  bRequest      = 0x09 (HID_SET_REPORT)
  wValue        = 0x0324 (Feature Report ID 0x24) หรือ 0x0303 (Report ID 0x03)
  wIndex        = 0x0000
  bytes         = "T\r\0\0\0\0\0\0" (8 บิต)
"""

import ctypes
from ctypes import wintypes
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

class usb_device(ctypes.Structure):
    pass

class usb_bus(ctypes.Structure):
    pass

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

def run_pure_python_usb_trigger():
    print("==============================================================================")
    print(" 🚀 Pure Python Direct USB Hardware Battery Test Trigger for PPC 2000D")
    print("==============================================================================")

    if not LIBUSB0_DLL.exists():
        print(f"❌ ไม่พบ {LIBUSB0_DLL}")
        return False

    print(f"📦 โหลด Native DLL: {LIBUSB0_DLL}")
    libusb = ctypes.CDLL(str(LIBUSB0_DLL))

    # กำหนด 64-bit function signatures เพื่อป้องกัน OverflowError
    libusb.usb_init()
    libusb.usb_find_busses()
    libusb.usb_find_devices()

    libusb.usb_get_busses.restype = ctypes.POINTER(usb_bus)
    
    libusb.usb_open.restype = ctypes.c_void_p
    libusb.usb_open.argtypes = [ctypes.POINTER(usb_device)]

    libusb.usb_close.restype = ctypes.c_int
    libusb.usb_close.argtypes = [ctypes.c_void_p]

    libusb.usb_set_configuration.restype = ctypes.c_int
    libusb.usb_set_configuration.argtypes = [ctypes.c_void_p, ctypes.c_int]

    libusb.usb_claim_interface.restype = ctypes.c_int
    libusb.usb_claim_interface.argtypes = [ctypes.c_void_p, ctypes.c_int]

    libusb.usb_release_interface.restype = ctypes.c_int
    libusb.usb_release_interface.argtypes = [ctypes.c_void_p, ctypes.c_int]

    libusb.usb_control_msg.restype = ctypes.c_int
    libusb.usb_control_msg.argtypes = [
        ctypes.c_void_p, # dev handle
        ctypes.c_int,    # requesttype
        ctypes.c_int,    # request
        ctypes.c_int,    # value
        ctypes.c_int,    # index
        ctypes.c_char_p, # bytes
        ctypes.c_int,    # size
        ctypes.c_int     # timeout
    ]

    bus_ptr = libusb.usb_get_busses()
    found_dev = None

    while bus_ptr:
        bus = bus_ptr.contents
        dev_ptr = bus.devices
        while dev_ptr:
            dev = dev_ptr.contents
            vid = dev.descriptor.idVendor
            pid = dev.descriptor.idProduct
            filename = dev.filename.decode('ascii', errors='ignore')
            print(f"  --> Found USB Device: VID=0x{vid:04X}, PID=0x{pid:04X} ({filename})")

            if vid == 0x06DA and pid == 0xFFFF:
                print(f"  🎯 พบ PPC 2000D Hardware Target! (VID=0x06DA, PID=0xFFFF)")
                found_dev = dev_ptr
                break
            dev_ptr = dev.next
        if found_dev:
            break
        bus_ptr = bus.next

    if not found_dev:
        print("⚠️ ไม่พบอุปกรณ์ PPC 2000D (VID 0x06DA, PID 0xFFFF) บน libusb bus")
        return False

    handle = libusb.usb_open(found_dev)
    if not handle:
        print("❌ ไม่สามารถเปิด USB Handle ได้ (อาจต้องปิด Winpower Service หรือรันในสิทธิ์ Admin)")
        return False

    print(f"✅ เปิด USB Handle สำเร็จ! (Handle Pointer: {hex(handle)})")

    try:
        # Set configuration #1 & Claim Interface #0
        c_res = libusb.usb_set_configuration(handle, 1)
        print(f"  --> usb_set_configuration(1) res: {c_res}")

        i_res = libusb.usb_claim_interface(handle, 0)
        print(f"  --> usb_claim_interface(0) res: {i_res}")

        # Payload คำสั่ง Q1 "T\r" ป้อนความยาว 8 บิต
        payload = b"T\r\x00\x00\x00\x00\x00\x00"

        # ------------------------------------------------------------------
        # 1. ทดสอบยิง SET_REPORT (0x21, 0x09) บน Feature Report 0x24 (wValue = 0x0324)
        # ------------------------------------------------------------------
        print("\n⚡ [1/3] ยิง USB Control Message (SET_REPORT 0x21, 0x09, wValue=0x0324, payload='T\\r')...")
        r1 = libusb.usb_control_msg(handle, 0x21, 0x09, 0x0324, 0, payload, 8, 1000)
        print(f"    --> ผลลัพธ์ (ret code): {r1}")

        # ------------------------------------------------------------------
        # 2. ทดสอบยิง SET_REPORT บน Feature Report 0x03 (wValue = 0x0303)
        # ------------------------------------------------------------------
        print("⚡ [2/3] ยิง USB Control Message (SET_REPORT 0x21, 0x09, wValue=0x0303, payload='T\\r')...")
        r2 = libusb.usb_control_msg(handle, 0x21, 0x09, 0x0303, 0, payload, 8, 1000)
        print(f"    --> ผลลัพธ์ (ret code): {r2}")

        # ------------------------------------------------------------------
        # 3. ทดสอบยิง SET_REPORT บน Feature Report 0x01 (wValue = 0x0301)
        # ------------------------------------------------------------------
        print("⚡ [3/3] ยิง USB Control Message (SET_REPORT 0x21, 0x09, wValue=0x0301, payload='T\\r')...")
        r3 = libusb.usb_control_msg(handle, 0x21, 0x09, 0x0301, 0, payload, 8, 1000)
        print(f"    --> ผลลัพธ์ (ret code): {r3}")

        print("\n🔊 โปรดสังเกตเสียง Relay Click และเสียง Beep จากเครื่อง UPS!")

    finally:
        libusb.usb_release_interface(handle, 0)
        libusb.usb_close(handle)
        print("🔒 ปิด USB Handle เรียบร้อย")

    return True

if __name__ == "__main__":
    run_pure_python_usb_trigger()
