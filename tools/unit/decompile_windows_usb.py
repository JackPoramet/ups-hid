#!/usr/bin/env python3
"""
tools/unit/decompile_windows_usb.py
Decompiles monitor1.WindowsUSB using javap
"""
import subprocess
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

JAVA_EXE = r"C:\Program Files\WinpowerG2\jre\bin\javap.exe"
JAR_PATH = r"C:\Program Files\WinpowerG2\lib\usbcomm-1.0.0.jar"

cmd = [JAVA_EXE, "-cp", JAR_PATH, "-p", "-c", "monitor1.WindowsUSB"]
res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")

print(res.stdout)
