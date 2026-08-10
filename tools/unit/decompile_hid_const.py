#!/usr/bin/env python3
"""
tools/unit/decompile_hid_const.py
Decompiles santak.hid.HidConstInt to see exact integer values for BATTERY_TESTSWITCHABLE and ACTION_QUICKTEST
"""
import subprocess
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

JAVA_EXE = r"C:\Program Files\WinpowerG2\jre\bin\javap.exe"
JAR_PATH = r"C:\Program Files\WinpowerG2\lib\usbcomm-1.0.0.jar"

cmd = [JAVA_EXE, "-cp", JAR_PATH, "santak.hid.HidConstInt"]
res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")

print(res.stdout)
