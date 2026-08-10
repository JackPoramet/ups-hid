#!/usr/bin/env python3
"""
tools/unit/test_python_call_winpower_dll.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
เรียกใช้ JNI Entry Point ใน jusb.dll และ libUSB_Win.dll ตรงจาก Python ผ่าน ctypes
โดยไม่ต้องผ่าน Java / ไม่ต้องเปิดโปรแกรม Winpower G2
"""

import ctypes
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

JUSB_DLL = Path(r"C:\Program Files\WinpowerG2\jusb.dll")
LIBUSB_WIN_DLL = Path(r"C:\Program Files\WinpowerG2\libUSB_Win.dll")

def test_ctypes_jusb():
    print("==============================================================================")
    print(" 🚀 Python Direct Call to Winpower Native C-DLL (jusb.dll / libUSB_Win.dll)")
    print("==============================================================================")

    if not JUSB_DLL.exists() or not LIBUSB_WIN_DLL.exists():
        print("❌ ไม่พบ Winpower DLLs ใน C:\\Program Files\\WinpowerG2")
        return

    # โหลด DLLs
    ctypes.CDLL(str(LIBUSB_WIN_DLL))
    jusb = ctypes.CDLL(str(JUSB_DLL))

    print("✅ โหลด jusb.dll และ libUSB_Win.dll สำเร็จ!")

    # JNI Function Signatures
    # JNIEXPORT jint JNICALL Java_monitor1_WindowsUSB_findUSBDevices(JNIEnv *env, jobject obj, ...)
    # เนื่องจากเราเรียก C Function โดยตรงโดยไม่ผ่าน JVM, env/obj สามารถส่ง NULL (0) ไปได้
    try:
        find_usb = jusb.Java_monitor1_WindowsUSB_findUSBDevices
        find_usb.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int]
        find_usb.restype = ctypes.c_int

        order_ups = jusb.Java_monitor1_WindowsUSB_OrderUPS
        order_ups.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_uint64]
        order_ups.restype = ctypes.c_void_p

        get_handle = jusb.Java_monitor1_WindowsUSB_getHandleByIndex
        get_handle.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int]
        get_handle.restype = ctypes.c_uint64

        get_vid = jusb.Java_monitor1_WindowsUSB_getVendorIdByIndex
        get_vid.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int]
        get_vid.restype = ctypes.c_int

        get_pid = jusb.Java_monitor1_WindowsUSB_getProductIdByIndex
        get_pid.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int]
        get_pid.restype = ctypes.c_int

        print("\n🔍 กำลังเรียกค้นหาอุปกรณ์ USB ผ่าน jusb.dll (findUSBDevices)...")
        count = find_usb(None, None, None, 0, 0, 0)
        print(f"  --> จำนวนอุปกรณ์ USB ที่พบ: {count}")

        for i in range(count):
            vid = get_vid(None, None, i)
            pid = get_pid(None, None, i)
            h = get_handle(None, None, i)
            print(f"  [{i}] VID=0x{vid:04X}, PID=0x{pid:04X}, Native Handle=0x{h:X}")

            if vid == 0x06DA and pid == 0xFFFF and h != 0:
                print(f"\n🎯 พบ PPC 2000D Target! สั่งงาน OrderUPS('T', protocolId=4, timeout=1000, handle=0x{h:X})...")
                
                # สร้าง JNI String "T"
                # คำสั่ง Q1 "T" สำหรับ Quick Battery Test
                res_ptr = order_ups(None, None, None, 4, 1000, h)
                print(f"  --> OrderUPS Result Pointer: {res_ptr}")
                print("\n🔊 สังเกตเสียง RELAY CLICK และเสียง BEEP จากเครื่อง UPS!")

    except Exception as e:
        print(f"❌ เกิดข้อผิดพลาดขณะเรียก DLL: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_ctypes_jusb()
