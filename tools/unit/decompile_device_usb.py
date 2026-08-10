#!/usr/bin/env python3
"""
tools/unit/decompile_device_usb.py
Decompiles DeviceUsb and LibUsb to see exact C/Java methods for Q1 string transfers
"""
import subprocess
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

JAVA_EXE = r"C:\Program Files\WinpowerG2\jre\bin\javap.exe"
JAR_PATH = r"C:\Program Files\WinpowerG2\lib\usbcomm-1.0.0.jar"

for cls in ["santak.lib.DeviceUsb", "santak.lib.LibUsb"]:
    print(f"==============================================================================")
    print(f" 📄 Class: {cls}")
    print("==============================================================================")
    cmd = [JAVA_EXE, "-cp", JAR_PATH, "-p", "-c", cls]
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    print(res.stdout[:8000])

