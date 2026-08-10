#!/usr/bin/env python3
"""
tools/unit/test_hid_force_open.py
Inspects exports in libusb0.dll and libUSB_Win.dll for hid_force_openEx and tests calling it
"""
import ctypes
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

LIBUSB0_PATH = Path(r"C:\Program Files\WinpowerG2\libUSB_driver\amd64\libusb0.dll")
LIBUSB_WIN_PATH = Path(r"C:\Program Files\WinpowerG2\libUSB_Win.dll")

def check_exports():
    print("==============================================================================")
    print(" 🔍 Checking Native DLL Exports for hid_force_openEx")
    print("==============================================================================")

    for path in [LIBUSB0_PATH, LIBUSB_WIN_PATH]:
        if not path.exists():
            continue
        print(f"\n📦 Loading {path.name}...")
        try:
            dll = ctypes.CDLL(str(path))
            for func in ["hid_force_openEx", "hid_force_open", "usb_detach_kernel_driver_np", "usb_claim_interface", "usb_control_msg"]:
                has_fn = hasattr(dll, func)
                print(f"  --> {func}: {'FOUND ✅' if has_fn else 'NOT FOUND ❌'}")
        except Exception as e:
            print(f"  Error loading {path}: {e}")

if __name__ == "__main__":
    check_exports()
