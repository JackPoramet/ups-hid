#!/usr/bin/env python3
import subprocess
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

JAVA_EXE = r"C:\Program Files\WinpowerG2\jre\bin\javap.exe"
JAR_PATH = r"C:\Program Files\WinpowerG2\lib\usbcomm-1.0.0.jar"

cmd = [JAVA_EXE, "-cp", JAR_PATH, "-v", "-p", "santak.hid.HidConstInt"]
res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")

lines = res.stdout.splitlines()
for i, line in enumerate(lines):
    if "BATTERY_TESTSWITCHABLE" in line or "ACTION_" in line:
        for j in range(max(0, i-2), min(len(lines), i+5)):
            print(lines[j])
        print("-" * 50)
