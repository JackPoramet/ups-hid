#!/usr/bin/env python3
"""
tools/unit/disassemble_jusb_dll.py
Disassembles and extracts PE exports, control transfer parameters, and USB specs from jusb.dll and libUSB_Win.dll
"""
import struct
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DLL_PATH = Path(r"C:\Program Files\WinpowerG2\jusb.dll")

def analyze():
    print(f"==============================================================================")
    print(f" 🔍 Deep Extracting Low-Level USB Spec from {DLL_PATH}")
    print(f"==============================================================================")

    data = DLL_PATH.read_bytes()
    
    # Search for control transfer constants or strings
    # ASCII strings
    ascii_strings = []
    curr = bytearray()
    for b in data:
        if 32 <= b <= 126:
            curr.append(b)
        else:
            if len(curr) >= 3:
                ascii_strings.append(curr.decode('ascii', errors='ignore'))
            curr = bytearray()
            
    print("\n--- Key String Constants in jusb.dll ---")
    for s in ascii_strings:
        if any(k in s for k in ["usb", "USB", "Order", "Report", "Feature", "libusb", "open", "control", "write", "read", "T\r", "Q1"]):
            print("  ", s)

if __name__ == "__main__":
    analyze()
