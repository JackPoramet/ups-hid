#!/usr/bin/env python3
"""
tools/unit/disassemble_libusb_win.py
Disassembles libUSB_Win.dll
"""
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DLL_PATH = Path(r"C:\Program Files\WinpowerG2\libUSB_Win.dll")

def analyze():
    print(f"==============================================================================")
    print(f" 🔍 Extracting strings from {DLL_PATH}")
    print(f"==============================================================================")

    data = DLL_PATH.read_bytes()
    
    ascii_strings = []
    curr = bytearray()
    for b in data:
        if 32 <= b <= 126:
            curr.append(b)
        else:
            if len(curr) >= 3:
                ascii_strings.append(curr.decode('ascii', errors='ignore'))
            curr = bytearray()
            
    print("\n--- Key String Constants in libUSB_Win.dll ---")
    for s in ascii_strings:
        if any(k in s for k in ["usb", "USB", "Order", "Report", "Feature", "libusb", "open", "control", "write", "read", "T", "Q1", "santak"]):
            print("  ", s)

if __name__ == "__main__":
    analyze()
