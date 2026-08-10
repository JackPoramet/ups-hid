#!/usr/bin/env python3
"""
tools/unit/test_sola_phoenixtec_2400baud.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
การยิงคำสั่งตามสเปก Phoenixtec SOLA Protocol (2400 Baud, 8N1, <cr>=0x0D):

1. ตั้งค่า Baud Rate บัส USB-to-Serial เป็น 2400 bps (0x00000960) ผ่าน SET_LINE_CODING (bRequest 0x20)
2. ส่งคำสั่ง Polling "Q1\r" (2400 Baud)
3. ส่งคำสั่ง Quick Battery Test "T\r" (2400 Baud)
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

def test_sola_phoenixtec():
    print("==============================================================================")
    print(" 🚀 Phoenixtec SOLA Protocol (2400 8N1) Hardware Battery Test Trigger")
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

        # STEP 1: SET_LINE_CODING (2400 Baud, 1 Stop, No Parity, 8 Data Bits)
        # 2400 in Hex (32-bit Little Endian) = 0x00000960 -> [0x60, 0x09, 0x00, 0x00, 0x00, 0x00, 0x08]
        print("\n⚙️  [STEP 1] ตั้งค่า Baud Rate เป็น 2400 bps (Phoenixtec SOLA Protocol Spec)...")
        line_coding = bytes([0x60, 0x09, 0x00, 0x00, 0x00, 0x00, 0x08])
        buf_baud = ctypes.create_string_buffer(line_coding)
        
        # SET_LINE_CODING (0x21, 0x20)
        ret_baud = libusb.usb_control_msg(handle, 0x21, 0x20, 0, 0, buf_baud, 7, 1000)
        print(f"    --> SET_LINE_CODING Result: {ret_baud}")

        # SET_CONTROL_LINE_STATE (0x21, 0x22, wValue=0x0003 - DTR + RTS)
        ret_dtr = libusb.usb_control_msg(handle, 0x21, 0x22, 0x0003, 0, None, 0, 1000)
        print(f"    --> SET_CONTROL_LINE_STATE (DTR/RTS): {ret_dtr}")

        # STEP 2: Polling "Q1\r"
        print("\n📡 [STEP 2] ส่งคำสั่ง Polling 'Q1\\r' (2400 Baud)...")
        payload_q1 = b"Q1\r\x00\x00\x00\x00\x00\x00"
        buf_q1 = ctypes.create_string_buffer(payload_q1)
        
        # Output Report wValue = 0x0200 / 0x0301
        libusb.usb_control_msg(handle, 0x21, 0x09, 0x0200, 0, buf_q1, 8, 1000)
        libusb.usb_control_msg(handle, 0x21, 0x09, 0x0301, 0, buf_q1, 8, 1000)

        buf_reply = ctypes.create_string_buffer(64)
        r_q1 = libusb.usb_interrupt_read(handle, 0x81, buf_reply, 32, 1000)
        if r_q1 > 0:
            print(f"    --> ตอบกลับจาก Q1: '{buf_reply.value.decode('ascii', errors='ignore')}'")

        # STEP 3: Quick Battery Test "T\r"
        print("\n⚡ [STEP 3] สั่งคำสั่ง Quick Battery Test 'T\\r' (2400 Baud)...")
        payload_t = b"T\r\x00\x00\x00\x00\x00\x00"
        buf_t = ctypes.create_string_buffer(payload_t)

        r_t1 = libusb.usb_control_msg(handle, 0x21, 0x09, 0x0200, 0, buf_t, 8, 1000)
        r_t2 = libusb.usb_control_msg(handle, 0x21, 0x09, 0x0301, 0, buf_t, 8, 1000)
        print(f"    --> Control Transfer [0x0200]: {r_t1} bytes sent")
        print(f"    --> Control Transfer [0x0301]: {r_t2} bytes sent")

        r_read_t = libusb.usb_interrupt_read(handle, 0x81, buf_reply, 32, 1000)
        if r_read_t > 0:
            print(f"    --> ตอบกลับหลังจากสั่ง T: '{buf_reply.value.decode('ascii', errors='ignore')}'")

        print("\n==============================================================================")
        print(" 🎉 คำสั่งถูกส่งด้วยความเร็ว 2400 Baud 8N1 ตรงตาม Phoenixtec SOLA Protocol Spec!")
        print(" 🔊 โปรดสังเกตเสียง RELAY CLICK สลับโหมด และเสียง BEEP จาก UPS!")
        print("==============================================================================")

    finally:
        try:
            libusb.usb_release_interface(handle, 0)
            libusb.usb_close(handle)
        except Exception:
            pass

if __name__ == "__main__":
    test_sola_phoenixtec()
