#!/usr/bin/env python3
"""
tools/unit/test_nut_phoenix_command.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
การทดสอบส่งคำสั่งตามโครงสร้างซอร์สโค้ดของ Network UPS Tools (NUT)
ไฟล์ drivers/blazer_usb.c -> phoenix_command():

1. Flush ข้อมูลค้างท่อผ่าน Interrupt Endpoint 0x81 (usb_interrupt_read)
2. ส่งคำสั่งผ่าน USB Control Transfer ด้วย wValue = 0x0200 (Output Report 0x00)
   payload = b"T\r\0\0\0\0\0\0" (8 บิต)
3. อ่านคำตอบกลับผ่าน Interrupt Endpoint 0x81 (usb_interrupt_read)
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

def test_nut_phoenix_command():
    print("==============================================================================")
    print(" 🚀 NUT Driver (blazer_usb.c -> phoenix_command) Hardware Test Runner")
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

    if not LIBUSB0_DLL.exists():
        print(f"❌ ไม่พบ {LIBUSB0_DLL}")
        return

    libusb = ctypes.CDLL(str(LIBUSB0_DLL))

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
    libusb.usb_clear_halt.restype = ctypes.c_int
    libusb.usb_clear_halt.argtypes = [ctypes.c_void_p, ctypes.c_int]

    libusb.usb_control_msg.restype = ctypes.c_int
    libusb.usb_control_msg.argtypes = [
        ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
        ctypes.c_int, ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_int
    ]

    libusb.usb_interrupt_read.restype = ctypes.c_int
    libusb.usb_interrupt_read.argtypes = [
        ctypes.c_void_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_int
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
            if vid == 0x06DA and pid == 0xFFFF:
                found_dev = dev_ptr
                break
            dev_ptr = dev.next
        if found_dev:
            break
        bus_ptr = bus.next

    if not found_dev:
        print("❌ ไม่พบอุปกรณ์ PPC 2000D (VID 0x06DA, PID 0xFFFF)")
        return

    handle = libusb.usb_open(found_dev)
    if not handle:
        print("❌ ไม่สามารถเปิด USB Handle ได้")
        return

    print(f"✅ เปิด USB Device Handle สำเร็จ! Pointer: {hex(handle)}")

    try:
        libusb.usb_set_configuration(handle, 1)
        libusb.usb_claim_interface(handle, 0)

        # STEP 1: Flush Interrupt IN Endpoint 0x81 (ตาม NUT phoenix_command)
        print("\n🧹 [NUT STEP 1] Flush ข้อมูลค้างท่อผ่าน Interrupt Endpoint 0x81...")
        buf_tmp = ctypes.create_string_buffer(8)
        for i in range(8):
            r_flush = libusb.usb_interrupt_read(handle, 0x81, buf_tmp, 8, 200)
            if r_flush < 0:
                libusb.usb_clear_halt(handle, 0x81)
                break
            print(f"    --> Flush read #{i+1}: {r_flush} bytes ({buf_tmp.raw})")

        # STEP 2: Send Command "T\r" via wValue = 0x0200 (Output Report 0x00)
        print("\n⚡ [NUT STEP 2] สั่งคำสั่ง 'T\\r' ด้วย wValue = 0x0200 (Output Report 0x00)...")
        payload = b"T\r\x00\x00\x00\x00\x00\x00"
        buf_out = ctypes.create_string_buffer(payload)
        
        # NUT Exact Formula: USB_TYPE_CLASS (0x20) + USB_RECIP_INTERFACE (0x01) = 0x21
        # bRequest = 0x09, wValue = 0x0200
        ret_cmd = libusb.usb_control_msg(handle, 0x21, 0x09, 0x0200, 0, buf_out, 8, 1000)
        print(f"    --> usb_control_msg (wValue=0x0200) Result: {ret_cmd} bytes sent")

        # STEP 3: Read Reply from Interrupt Endpoint 0x81
        print("\n📥 [NUT STEP 3] อ่านค่าคำตอบกลับจาก Interrupt Endpoint 0x81...")
        buf_reply = ctypes.create_string_buffer(32)
        for i in range(4):
            r_read = libusb.usb_interrupt_read(handle, 0x81, buf_reply, 8, 1000)
            if r_read > 0:
                reply_txt = buf_reply.value.decode("ascii", errors="ignore")
                print(f"    --> Reply #{i+1}: '{reply_txt}' (Hex: {buf_reply.raw[:r_read].hex()})")

        print("\n==============================================================================")
        print(" 🔊 โปรดสังเกตเสียง RELAY CLICK สลับโหมด และเสียง BEEP จาก UPS!")
        print("==============================================================================")

    finally:
        try:
            libusb.usb_release_interface(handle, 0)
            libusb.usb_close(handle)
        except Exception:
            pass

if __name__ == "__main__":
    test_nut_phoenix_command()
